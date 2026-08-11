import os
import asyncio
import tempfile
import atexit
import shutil
from typing import AsyncGenerator, Dict, Any, Optional, List
from pathlib import Path
import logging

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    SystemMessage,
)

logger = logging.getLogger(__name__)


def _message_to_dict(message: Any) -> Dict[str, Any]:
    """Normalize an SDK message into the dict shape the downstream parser expects.

    Uses typed isinstance checks against the SDK 0.2.x message classes so a
    field rename does not silently break extraction. Dicts pass through
    unchanged (e.g. injected error results). Unknown message types fall back to
    copying public, non-callable attributes.
    """
    if isinstance(message, dict):
        return message

    if isinstance(message, ResultMessage):
        return {
            "type": "result",
            "subtype": message.subtype,
            "result": message.result,
            "total_cost_usd": message.total_cost_usd,
            "duration_ms": message.duration_ms,
            "num_turns": message.num_turns,
            "session_id": message.session_id,
            "usage": message.usage,
            "stop_reason": message.stop_reason,
            "is_error": message.is_error,
        }

    if isinstance(message, SystemMessage):
        return {
            "type": "system",
            "subtype": message.subtype,
            "data": message.data,
        }

    if isinstance(message, AssistantMessage):
        return {
            "type": "assistant",
            "content": list(message.content or []),
        }

    # Generic fallback for any other SDK message type (UserMessage, etc.).
    message_dict: Dict[str, Any] = {}
    for attr_name in dir(message):
        if attr_name.startswith("_"):
            continue
        try:
            value = getattr(message, attr_name)
        except Exception:
            continue
        if not callable(value):
            message_dict[attr_name] = value
    return message_dict or {"type": "unknown"}


class ClaudeCodeCLI:
    def __init__(self, timeout: int = 600000, cwd: Optional[str] = None):
        self.timeout = timeout / 1000  # Convert ms to seconds
        self.temp_dir = None

        # If cwd is provided (from CLAUDE_CWD env var), use it
        # Otherwise create an isolated temp directory
        if cwd:
            self.cwd = Path(cwd)
            # Check if the directory exists
            if not self.cwd.exists():
                logger.error(f"ERROR: Specified working directory does not exist: {self.cwd}")
                logger.error(
                    "Please create the directory first or unset CLAUDE_CWD to use a temporary directory"
                )
                raise ValueError(f"Working directory does not exist: {self.cwd}")
            else:
                logger.info(f"Using CLAUDE_CWD: {self.cwd}")
        else:
            # Create isolated temp directory (cross-platform)
            self.temp_dir = tempfile.mkdtemp(prefix="claude_code_workspace_")
            self.cwd = Path(self.temp_dir)
            logger.info(f"Using temporary isolated workspace: {self.cwd}")

            # Register cleanup function to remove temp dir on exit
            atexit.register(self._cleanup_temp_dir)

        # Import auth manager
        from src.auth import auth_manager, validate_claude_code_auth

        # Validate authentication
        is_valid, auth_info = validate_claude_code_auth()
        if not is_valid:
            logger.warning(f"Claude Code authentication issues detected: {auth_info['errors']}")
        else:
            logger.info(f"Claude Code authentication method: {auth_info.get('method', 'unknown')}")

        # Store auth environment variables for SDK
        self.claude_env_vars = auth_manager.get_claude_code_env_vars()

    async def verify_cli(self, prompt: str = "Hello") -> bool:
        """Verify Claude Agent SDK is working and authenticated."""
        try:
            # Test SDK with a simple query
            logger.info(f"Testing Claude Agent SDK with prewarm query: '{prompt}'...")

            messages = []
            async for message in query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    max_turns=1,
                    cwd=self.cwd,
                    system_prompt={"type": "preset", "preset": "claude_code"},
                ),
            ):
                messages.append(message)
                # Break early on first response to speed up verification
                if isinstance(message, AssistantMessage):
                    break

            if messages:
                logger.info("✅ Claude Agent SDK verified successfully")
                return True
            else:
                logger.warning("⚠️ Claude Agent SDK test returned no messages")
                return False

        except Exception as e:
            logger.error(f"Claude Agent SDK verification failed: {e}")
            logger.warning("Please ensure Claude Code is installed and authenticated:")
            logger.warning("  1. Install: npm install -g @anthropic-ai/claude-code")
            logger.warning("  2. Set ANTHROPIC_API_KEY environment variable")
            logger.warning("  3. Test: claude --print 'Hello'")
            return False

    async def run_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        stream: bool = True,
        session_id: Optional[str] = None,
        continue_session: bool = False,
        claude_options: Optional[Dict] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run Claude Agent using the Python SDK and yield response chunks."""
        async for chunk in self._run_completion_inner(
            prompt, system_prompt, stream, session_id, continue_session, claude_options
        ):
            yield chunk

    async def _run_completion_inner(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        stream: bool = True,
        session_id: Optional[str] = None,
        continue_session: bool = False,
        claude_options: Optional[Dict] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Inner implementation of run_completion."""

        try:
            # Build SDK options (default max_turns=10 for tool-enabled context)
            options = ClaudeAgentOptions(max_turns=10, cwd=self.cwd)

            # Set system prompt - CLAUDE AGENT SDK STRUCTURED FORMAT
            if system_prompt:
                options.system_prompt = {"type": "text", "text": system_prompt}
            else:
                # Use Claude Code preset to maintain expected behavior
                options.system_prompt = {"type": "preset", "preset": "claude_code"}

            # Handle session continuity
            if continue_session:
                options.continue_conversation = True
            elif session_id:
                options.resume = session_id

            # Apply claude_options via generic setattr — handles model, max_turns,
            # allowed_tools, disallowed_tools, permission_mode, max_thinking_tokens,
            # effort, output_format, user, max_budget_usd, thinking, etc.
            for key, value in (claude_options or {}).items():
                if value is not None and hasattr(options, key):
                    setattr(options, key, value)

            # Set authentication env vars directly on options (avoids os.environ mutation
            # and the serializing lock that came with it — requests are now fully concurrent)
            if self.claude_env_vars:
                options.env = {**dict(os.environ), **self.claude_env_vars}

            # Run the query and yield messages (with timeout to prevent indefinite hang)
            async with asyncio.timeout(self.timeout):
                async for message in query(prompt=prompt, options=options):
                    # Debug logging
                    logger.debug(f"Raw SDK message type: {type(message)}")
                    logger.debug(f"Raw SDK message: {message}")
                    yield _message_to_dict(message)

        except Exception as e:
            logger.error(f"Claude Agent SDK error: {e}")
            # Yield error message in the expected format
            yield {
                "type": "result",
                "subtype": "error_during_execution",
                "is_error": True,
                "error_message": str(e),
            }

    def parse_claude_message(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        """Extract the assistant message from Claude Agent SDK messages.

        Prioritizes ResultMessage.result for multi-turn conversations,
        falls back to last AssistantMessage content.
        """
        # First, check for ResultMessage with 'result' field (multi-turn completion)
        for message in messages:
            if message.get("subtype") == "success" and "result" in message:
                return message["result"]

        # Collect all text from AssistantMessages (take the last one with text)
        last_text = None
        for message in messages:
            # Look for AssistantMessage type (new SDK format)
            if "content" in message and isinstance(message["content"], list):
                text_parts = []
                for block in message["content"]:
                    # Handle TextBlock objects
                    if hasattr(block, "text"):
                        text_parts.append(block.text)
                    elif isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)

                if text_parts:
                    last_text = "\n".join(text_parts)

            # Fallback: look for old format
            elif message.get("type") == "assistant" and "message" in message:
                sdk_message = message["message"]
                if isinstance(sdk_message, dict) and "content" in sdk_message:
                    content = sdk_message["content"]
                    if isinstance(content, list) and len(content) > 0:
                        # Handle content blocks (Anthropic SDK format)
                        text_parts = []
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                        if text_parts:
                            last_text = "\n".join(text_parts)
                    elif isinstance(content, str):
                        last_text = content

        return last_text

    def extract_metadata(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract metadata like costs, tokens, session info, and stop reason from SDK messages."""
        metadata = {
            "session_id": None,
            "total_cost_usd": 0.0,
            "duration_ms": 0,
            "num_turns": 0,
            "model": None,
            "usage": None,
            "stop_reason": None,
        }

        for message in messages:
            # New SDK format - ResultMessage
            if message.get("subtype") == "success" and "total_cost_usd" in message:
                metadata.update(
                    {
                        "total_cost_usd": message.get("total_cost_usd", 0.0),
                        "duration_ms": message.get("duration_ms", 0),
                        "num_turns": message.get("num_turns", 0),
                        "session_id": message.get("session_id"),
                        "usage": message.get("usage"),
                        "stop_reason": message.get("stop_reason"),
                    }
                )
            # New SDK format - SystemMessage
            elif message.get("subtype") == "init" and "data" in message:
                data = message["data"]
                metadata.update({"session_id": data.get("session_id"), "model": data.get("model")})
            # Old format fallback
            elif message.get("type") == "result":
                metadata.update(
                    {
                        "total_cost_usd": message.get("total_cost_usd", 0.0),
                        "duration_ms": message.get("duration_ms", 0),
                        "num_turns": message.get("num_turns", 0),
                        "session_id": message.get("session_id"),
                        "usage": message.get("usage"),
                        "stop_reason": message.get("stop_reason"),
                    }
                )
            elif message.get("type") == "system" and message.get("subtype") == "init":
                metadata.update(
                    {"session_id": message.get("session_id"), "model": message.get("model")}
                )

        return metadata

    @staticmethod
    def map_stop_reason_openai(stop_reason: Optional[str]) -> str:
        """Map Claude SDK stop_reason to OpenAI finish_reason."""
        if stop_reason == "max_tokens":
            return "length"
        elif stop_reason == "stop_sequence":
            return "stop"
        # "end_turn", None, or any unknown value → "stop"
        return "stop"

    def estimate_token_usage(
        self, prompt: str, completion: str, model: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Estimate token usage based on character count.

        Uses rough approximation: ~4 characters per token for English text.
        This is approximate and may not match actual tokenization.
        """
        # Rough approximation: 1 token ≈ 4 characters
        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = max(1, len(completion) // 4)

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    def _cleanup_temp_dir(self):
        """Clean up temporary directory on exit."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temporary workspace: {self.temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp directory {self.temp_dir}: {e}")
