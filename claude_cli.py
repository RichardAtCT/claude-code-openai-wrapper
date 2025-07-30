import asyncio
import json
import os
from typing import AsyncGenerator, Dict, Any, Optional, List
from pathlib import Path
import logging

from claude_code_sdk import query, ClaudeCodeOptions, Message

logger = logging.getLogger(__name__)


class ClaudeCodeCLI:
    def __init__(self, timeout: int = 600000, cwd: Optional[str] = None):
        self.timeout = timeout / 1000  # Convert ms to seconds
        self.cwd = Path(cwd) if cwd else Path.cwd()
        
        # Import auth manager
        from auth import auth_manager, validate_claude_code_auth
        
        # Validate authentication
        is_valid, auth_info = validate_claude_code_auth()
        if not is_valid:
            logger.warning(f"Claude Code authentication issues detected: {auth_info['errors']}")
        else:
            logger.info(f"Claude Code authentication method: {auth_info.get('method', 'unknown')}")
        
        # Store auth environment variables for SDK
        self.claude_env_vars = auth_manager.get_claude_code_env_vars()
        
    async def verify_cli(self) -> bool:
        """Verify Claude Code SDK is working and authenticated."""
        try:
            # Test SDK with a simple query
            logger.info("Testing Claude Code SDK...")
            
            messages = []
            async for message in query(
                prompt="Hello",
                options=ClaudeCodeOptions(
                    max_turns=1,
                    cwd=self.cwd,
                    model="claude-3-5-haiku-20241022"  # Use Haiku for faster/cheaper verification
                )
            ):
                messages.append(message)
                # Break early on first response to speed up verification
                # Handle both dict and object types
                msg_type = getattr(message, 'type', None) if hasattr(message, 'type') else message.get("type") if isinstance(message, dict) else None
                if msg_type == "assistant":
                    break
            
            if messages:
                logger.info("✅ Claude Code SDK verified successfully")
                return True
            else:
                logger.warning("⚠️ Claude Code SDK test returned no messages")
                return False
                
        except Exception as e:
            logger.error(f"Claude Code SDK verification failed: {e}")
            logger.warning("Please ensure Claude Code is installed and authenticated:")
            logger.warning("  1. Install: npm install -g @anthropic-ai/claude-code")
            logger.warning("  2. Set ANTHROPIC_API_KEY environment variable")
            logger.warning("  3. Test: claude --print 'Hello'")
            return False
    
    async def run_completion(
        self, 
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        stream: bool = True,
        max_turns: int = 10,
        allowed_tools: Optional[List[str]] = None,
        disallowed_tools: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        continue_session: bool = False
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run Claude Code using the Python SDK and yield response chunks."""
        
        try:
            # Set authentication environment variables (if any)
            original_env = {}
            if self.claude_env_vars:  # Only set env vars if we have any
                for key, value in self.claude_env_vars.items():
                    original_env[key] = os.environ.get(key)
                    os.environ[key] = value
            
            try:
                # Build SDK options
                options = ClaudeCodeOptions(
                    max_turns=max_turns,
                    cwd=self.cwd
                )
                
                # Set model if specified
                if model:
                    options.model = model
                    
                # Set system prompt if specified
                if system_prompt:
                    options.system_prompt = system_prompt
                    
                # Set tool restrictions
                if allowed_tools:
                    options.allowed_tools = allowed_tools
                if disallowed_tools:
                    options.disallowed_tools = disallowed_tools
                    
                # Handle session continuity
                if continue_session:
                    options.continue_session = True
                elif session_id:
                    options.resume = session_id
                
                # Run the query and yield messages
                async for message in query(prompt=prompt, options=options):
                    # Debug logging
                    logger.debug(f"Raw SDK message type: {type(message)}")
                    logger.debug(f"Raw SDK message: {message}")
                    
                    # Convert message object to dict if needed
                    if hasattr(message, '__dict__') and not isinstance(message, dict):
                        # Convert object to dict for consistent handling
                        message_dict = {}
                        
                        # Get all attributes from the object
                        for attr_name in dir(message):
                            if not attr_name.startswith('_'):  # Skip private attributes
                                try:
                                    attr_value = getattr(message, attr_name)
                                    if not callable(attr_value):  # Skip methods
                                        message_dict[attr_name] = attr_value
                                except:
                                    pass
                        
                        logger.debug(f"Converted message dict: {message_dict}")
                        yield message_dict
                    else:
                        yield message
                    
            finally:
                # Restore original environment (if we changed anything)
                if original_env:
                    for key, original_value in original_env.items():
                        if original_value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = original_value
                
        except Exception as e:
            logger.error(f"Claude Code SDK error: {e}")
            # Yield error message in the expected format
            yield {
                "type": "result",
                "subtype": "error_during_execution",
                "is_error": True,
                "error_message": str(e)
            }
    
    def parse_claude_message(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        """Extract the assistant message from Claude Code SDK messages."""
        for message in messages:
            # Look for AssistantMessage type (new SDK format)
            if "content" in message and isinstance(message["content"], list):
                text_parts = []
                for block in message["content"]:
                    # Handle TextBlock objects
                    if hasattr(block, 'text'):
                        text_parts.append(block.text)
                    elif isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                
                if text_parts:
                    return "\n".join(text_parts)
            
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
                        return "\n".join(text_parts) if text_parts else None
                    elif isinstance(content, str):
                        return content
        
        return None
        
    def extract_metadata(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract metadata like costs, tokens, and session info from SDK messages."""
        metadata = {
            "session_id": None,
            "total_cost_usd": 0.0,
            "duration_ms": 0,
            "num_turns": 0,
            "model": None
        }
        
        for message in messages:
            # New SDK format - ResultMessage
            if message.get("subtype") == "success" and "total_cost_usd" in message:
                metadata.update({
                    "total_cost_usd": message.get("total_cost_usd", 0.0),
                    "duration_ms": message.get("duration_ms", 0),
                    "num_turns": message.get("num_turns", 0),
                    "session_id": message.get("session_id")
                })
            # New SDK format - SystemMessage  
            elif message.get("subtype") == "init" and "data" in message:
                data = message["data"]
                metadata.update({
                    "session_id": data.get("session_id"),
                    "model": data.get("model")
                })
            # Old format fallback
            elif message.get("type") == "result":
                metadata.update({
                    "total_cost_usd": message.get("total_cost_usd", 0.0),
                    "duration_ms": message.get("duration_ms", 0),
                    "num_turns": message.get("num_turns", 0),
                    "session_id": message.get("session_id")
                })
            elif message.get("type") == "system" and message.get("subtype") == "init":
                metadata.update({
                    "session_id": message.get("session_id"),
                    "model": message.get("model")
                })
                
        return metadata