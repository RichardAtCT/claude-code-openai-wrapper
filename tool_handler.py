"""
Tool execution handler for Claude Code tools in OpenAI format.
Bridges between OpenAI function calling and Claude Code tool usage.
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from tools import tool_registry
from models import Message, ToolCall, FunctionCall

logger = logging.getLogger(__name__)


class ToolHandler:
    """Handles tool execution and response formatting."""
    
    def __init__(self):
        self.tool_registry = tool_registry
        
    def should_enable_tools(self, request: Dict[str, Any]) -> bool:
        """
        Determine if tools should be enabled based on request parameters.
        
        Tools are enabled if:
        1. enable_tools is explicitly True
        2. tools parameter is provided with tool definitions
        3. functions parameter is provided (legacy format)
        """
        # Explicit enable_tools flag
        if request.get("enable_tools", False):
            return True
            
        # OpenAI format tools
        if request.get("tools"):
            return True
            
        # Legacy function calling
        if request.get("functions"):
            return True
            
        return False
    
    def get_tool_config(self, request: Dict[str, Any]) -> Tuple[Optional[List[str]], Optional[List[str]]]:
        """
        Get allowed and disallowed tools based on request.
        Returns (allowed_tools, disallowed_tools)
        """
        # If specific tools are provided, use only those
        if request.get("tools"):
            # Extract tool names from OpenAI format
            allowed = []
            for tool in request["tools"]:
                if tool.get("type") == "function":
                    func_name = tool.get("function", {}).get("name")
                    # Map OpenAI function names to Claude tool names
                    claude_tool = self._map_function_to_tool(func_name)
                    if claude_tool:
                        allowed.append(claude_tool)
            return allowed, None
            
        # If enable_tools is True, enable all tools
        if request.get("enable_tools"):
            return None, None  # All tools enabled
            
        # No tools
        return [], None
    
    def _map_function_to_tool(self, function_name: str) -> Optional[str]:
        """Map OpenAI function name to Claude tool name."""
        # Direct mappings from OpenAI names to Claude Code tool names
        mappings = {
            "read_file": "Read",
            "write_file": "Write",
            "edit_file": "Edit",
            "run_command": "Bash",
            "search_files": "Glob",
            "search_in_files": "Grep",
            "list_directory": "LS",
            "web_search": "WebSearch",
            "fetch_url": "WebFetch",
            "read_todo": "TodoRead",
            "write_todo": "TodoWrite",
        }
        return mappings.get(function_name)
    
    def parse_claude_tool_use(self, claude_response: str) -> List[ToolCall]:
        """
        Parse Claude's response for tool usage patterns.
        
        Claude may use tools in various formats:
        1. XML-like tags: <use_tool>read_file</use_tool><path>/etc/hosts</path>
        2. Function notation: read_file("/etc/hosts")
        3. Natural language with clear intent
        """
        tool_calls = []
        
        # Pattern 1: Look for explicit tool usage patterns
        # This would need to be adapted based on actual Claude output
        tool_patterns = [
            # XML-like pattern
            r'<use_tool>(\w+)</use_tool>(.*?)</(\w+)>',
            # Function call pattern
            r'(\w+)\((.*?)\)',
            # Command pattern
            r'```(?:bash|sh|shell)\n(.*?)\n```',
        ]
        
        # For now, return empty list
        # In production, this would parse actual Claude responses
        return tool_calls
    
    def format_tool_response(self, tool_call_id: str, result: Any, error: Optional[str] = None) -> Message:
        """Format a tool execution result as a tool message."""
        if error:
            content = f"Error executing tool: {error}"
        else:
            content = json.dumps(result) if not isinstance(result, str) else result
            
        return Message(
            role="tool",
            tool_call_id=tool_call_id,
            content=content
        )
    
    def inject_tool_context(self, messages: List[Message], tools: List[Dict[str, Any]]) -> List[Message]:
        """
        Inject tool availability context into the conversation.
        This helps Claude understand what tools are available.
        """
        if not tools:
            return messages
            
        # Build tool context
        tool_descriptions = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                name = func.get("name")
                desc = func.get("description")
                params = func.get("parameters", {})
                tool_descriptions.append(f"- {name}: {desc}")
                
        if tool_descriptions:
            # Inject as system message or modify existing system message
            tool_context = "\n\nAvailable tools:\n" + "\n".join(tool_descriptions)
            
            # Check if there's already a system message
            has_system = any(msg.role == "system" for msg in messages)
            
            if has_system:
                # Append to first system message
                for msg in messages:
                    if msg.role == "system":
                        msg.content = (msg.content or "") + tool_context
                        break
            else:
                # Insert new system message at beginning
                system_msg = Message(
                    role="system",
                    content=f"You have access to the following tools:{tool_context}\n\nWhen you need to use a tool, clearly indicate which tool and with what parameters."
                )
                messages.insert(0, system_msg)
                
        return messages
    
    def extract_tool_calls_from_message(self, message: Dict[str, Any]) -> Optional[List[ToolCall]]:
        """
        Extract tool calls from Claude's response message.
        This bridges between Claude's natural tool usage and OpenAI's structured format.
        """
        content = message.get("content", "")
        
        # Look for patterns that indicate tool usage
        tool_calls = []
        
        # Pattern: Command execution blocks
        bash_pattern = r'```(?:bash|sh|shell)\n(.*?)\n```'
        bash_matches = re.findall(bash_pattern, content, re.DOTALL)
        
        for i, command in enumerate(bash_matches):
            tool_call = ToolCall(
                id=f"call_{i}",
                type="function",
                function=FunctionCall(
                    name="run_command",
                    arguments=json.dumps({"command": command.strip()})
                )
            )
            tool_calls.append(tool_call)
            
        # Pattern: File operations
        # Looking for phrases like "Let me read the file X"
        read_pattern = r'(?:read|check|look at|examine|view)\s+(?:the\s+)?file\s+["\']?([^"\'\s]+)["\']?'
        read_matches = re.findall(read_pattern, content, re.IGNORECASE)
        
        for i, filepath in enumerate(read_matches, len(tool_calls)):
            tool_call = ToolCall(
                id=f"call_{i}",
                type="function", 
                function=FunctionCall(
                    name="read_file",
                    arguments=json.dumps({"path": filepath})
                )
            )
            tool_calls.append(tool_call)
            
        return tool_calls if tool_calls else None


# Global tool handler instance
tool_handler = ToolHandler()