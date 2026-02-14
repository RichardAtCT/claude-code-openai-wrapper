"""
OpenClaw Bridge - Converts OpenAI-format tool definitions to SDK MCP tools
and translates Claude tool_use blocks back to OpenAI tool_calls format.

This module enables agent frameworks like OpenClaw to use their native tools
through the Claude Agent SDK by:
1. Converting OpenAI function definitions to in-process MCP tools
2. Extracting ToolUseBlock content from Claude's response
3. Formatting tool calls as OpenAI-compatible SSE streaming events
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from claude_agent_sdk import create_sdk_mcp_server, tool, SdkMcpTool

logger = logging.getLogger(__name__)

# Sentinel prefix for placeholder tool results
TOOL_CALL_PLACEHOLDER = "[OPENCLAW_TOOL_CALL_FORWARDED]"


def openai_tools_to_mcp_server(
    tools: List[Dict[str, Any]],
    server_name: str = "openclaw_tools",
) -> Tuple[Any, List[str]]:
    """Convert OpenAI-format tool definitions to an SDK MCP server.

    Args:
        tools: List of OpenAI tool definitions with format:
            [{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]
        server_name: Name for the MCP server

    Returns:
        Tuple of (McpSdkServerConfig, list of tool names)
    """
    sdk_tools: List[SdkMcpTool] = []
    tool_names: List[str] = []

    for tool_def in tools:
        if tool_def.get("type") != "function":
            continue

        func_def = tool_def.get("function", {})
        name = func_def.get("name", "")
        description = func_def.get("description", "")
        parameters = func_def.get("parameters", {"type": "object", "properties": {}})

        if not name:
            continue

        tool_names.append(name)

        # Create MCP tool with a placeholder handler
        # In single-turn mode (max_turns=1), this handler is never called
        # because the SDK returns the assistant message without executing tools.
        # If it IS called (shouldn't happen), return a placeholder.
        sdk_tool = _create_placeholder_tool(name, description, parameters)
        sdk_tools.append(sdk_tool)

    if not sdk_tools:
        logger.warning("No valid tool definitions found in request")
        return None, []

    mcp_server = create_sdk_mcp_server(
        name=server_name,
        version="1.0.0",
        tools=sdk_tools,
    )

    logger.info(f"Created MCP server '{server_name}' with {len(sdk_tools)} tools: {tool_names}")
    return mcp_server, tool_names


def _create_placeholder_tool(
    name: str, description: str, parameters: Dict[str, Any]
) -> SdkMcpTool:
    """Create an MCP tool with a placeholder handler.

    The handler should never be called in single-turn mode, but if it is,
    it returns a sentinel value that signals this is an external tool call.
    """

    @tool(name, description, parameters)
    async def placeholder_handler(args: Any) -> Dict[str, Any]:
        logger.warning(
            f"Placeholder handler called for tool '{name}' - "
            "this shouldn't happen in single-turn mode. "
            f"Args: {args}"
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"{TOOL_CALL_PLACEHOLDER}: {name}({json.dumps(args)})",
                }
            ]
        }

    return placeholder_handler


def extract_tool_calls_from_chunks(
    chunks: List[Dict[str, Any]],
    external_tool_names: Optional[List[str]] = None,
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """Extract text content and tool calls from Claude SDK response chunks.

    Scans assistant messages for TextBlock and ToolUseBlock content,
    separating them into text content and tool_calls.

    Args:
        chunks: List of SDK message dicts
        external_tool_names: If provided, only extract tool calls for these tool names.
            Tool calls for other tools (Claude built-in) are ignored.

    Returns:
        Tuple of (text_content, tool_calls) where tool_calls is a list of
        OpenAI-format tool call dicts.
    """
    text_parts = []
    tool_calls = []
    tool_call_index = 0

    for chunk in chunks:
        content = None

        # Handle ResultMessage with 'result' field
        if chunk.get("subtype") == "success" and "result" in chunk:
            if chunk["result"]:
                text_parts.append(chunk["result"])
            continue

        # Handle AssistantMessage content
        if "content" in chunk and isinstance(chunk["content"], list):
            content = chunk["content"]
        elif chunk.get("type") == "assistant" and "message" in chunk:
            message = chunk["message"]
            if isinstance(message, dict) and "content" in message:
                content = message["content"]

        if content is None:
            continue

        if not isinstance(content, list):
            if isinstance(content, str) and content:
                text_parts.append(content)
            continue

        for block in content:
            # Handle TextBlock
            if hasattr(block, "text"):
                if block.text:
                    text_parts.append(block.text)
            elif isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    text_parts.append(text)

            # Handle ToolUseBlock
            elif hasattr(block, "name") and hasattr(block, "input") and hasattr(block, "id"):
                tool_name = block.name
                # Filter by external tool names if provided
                if external_tool_names and tool_name not in external_tool_names:
                    logger.debug(f"Skipping internal tool call: {tool_name}")
                    continue

                tool_call = {
                    "index": tool_call_index,
                    "id": getattr(block, "id", f"call_{uuid.uuid4().hex[:24]}"),
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(block.input) if isinstance(block.input, dict) else str(block.input),
                    },
                }
                tool_calls.append(tool_call)
                tool_call_index += 1
                logger.info(f"Extracted tool call: {tool_name} (id={tool_call['id']})")

            elif isinstance(block, dict) and block.get("type") == "tool_use":
                tool_name = block.get("name", "")
                if external_tool_names and tool_name not in external_tool_names:
                    logger.debug(f"Skipping internal tool call: {tool_name}")
                    continue

                tool_input = block.get("input", {})
                tool_call = {
                    "index": tool_call_index,
                    "id": block.get("id", f"call_{uuid.uuid4().hex[:24]}"),
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_input) if isinstance(tool_input, dict) else str(tool_input),
                    },
                }
                tool_calls.append(tool_call)
                tool_call_index += 1
                logger.info(f"Extracted tool call (dict): {tool_name}")

    text_content = "\n".join(text_parts) if text_parts else None
    return text_content, tool_calls


def format_tool_calls_for_sse(
    tool_calls: List[Dict[str, Any]],
    request_id: str,
    model: str,
) -> List[str]:
    """Format tool calls as OpenAI SSE streaming events.

    Returns a list of SSE-formatted data strings ready to yield.
    """
    events = []

    for tc in tool_calls:
        # Send tool call start (with id, type, name)
        start_chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {
                                "index": tc["index"],
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["function"]["name"],
                                    "arguments": "",
                                },
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ],
        }
        events.append(f"data: {json.dumps(start_chunk)}\n\n")

        # Send arguments in chunks (could split for large args, but send all at once for simplicity)
        args_chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {
                                "index": tc["index"],
                                "function": {
                                    "arguments": tc["function"]["arguments"],
                                },
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ],
        }
        events.append(f"data: {json.dumps(args_chunk)}\n\n")

    return events
