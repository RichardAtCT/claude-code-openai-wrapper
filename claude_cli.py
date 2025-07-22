import asyncio
import json
import os
from typing import AsyncGenerator, Dict, Any, Optional, List
from pathlib import Path
import logging

from claude_code_sdk import query, ClaudeCodeOptions, Message

# Import chat mode utilities
from chat_mode import ChatMode
from prompts import ChatModePrompts, FormatDetector, inject_prompts

logger = logging.getLogger(__name__)


class ClaudeCodeCLI:
    def __init__(self, timeout: int = 600000, cwd: Optional[str] = None):
        self.timeout = timeout / 1000  # Convert ms to seconds
        
        # Check if chat mode is enabled
        self.chat_mode = ChatMode.is_enabled()
        self.format_detector = FormatDetector()
        self.prompts = ChatModePrompts()
        
        if self.chat_mode:
            # In chat mode, we'll create sandbox directories per request
            self.cwd = None
            logger.info("Chat mode enabled - sessions disabled, sandbox execution active")
        else:
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
                    cwd=self.cwd
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
    
    def _prepare_prompt_with_injections(self, prompt: str, messages: Optional[List[Dict]] = None) -> str:
        """Prepare prompt with system injections based on mode and format detection."""
        # Import MessageAdapter to use the format detection
        from message_adapter import MessageAdapter
        import re
        
        # Check if the prompt already has structured format
        has_structured_prompt = MessageAdapter.has_structured_format(prompt)
        
        if has_structured_prompt:
            # For structured prompts (XML, JSON, etc), preserve the exact format
            logger.debug("Detected structured prompt format - minimal injection")
            
            pre_injections = []
            post_injections = []
            
            # Check if the prompt contains tool definitions
            # Look for common patterns that indicate tool usage expectations
            prompt_lower = prompt.lower()
            has_tool_indicators = any([
                "tool use" in prompt_lower,
                "tool uses are formatted" in prompt_lower,
                "<actual_tool_name>" in prompt_lower,
                "xml-style tags" in prompt_lower,
                "attempt_completion" in prompt_lower,
                "ask_followup_question" in prompt_lower,
                re.search(r'<\w+>\s*<\w+>', prompt) is not None  # XML-like nested tags
            ])
            
            if has_tool_indicators and self.chat_mode:
                # Only add strong XML enforcement in chat mode
                # This ensures compatibility with Roo/Cline while not affecting normal usage
                tool_instruction = (
                    "\n\nCRITICAL FINAL INSTRUCTION: You MUST use the XML tool format shown above in your response. "
                    "The conversation above contains tool definitions like <attempt_completion>, <ask_followup_question>, etc. "
                    "You MUST format your ENTIRE response using one of these XML tools. "
                    "Do NOT respond with plain text. Use the appropriate XML tool tag to wrap your response."
                )
                post_injections.append(tool_instruction)
                logger.debug("Added XML tool usage instruction for chat mode")
            elif self.chat_mode and not has_tool_indicators:
                # Only add full chat mode prompt if there are no tool indicators
                pre_injections.append(self.prompts.CHAT_MODE_NO_FILES_PROMPT)
                logger.debug("Added full chat mode prompt (no tool indicators detected)")
            
            # Build the final prompt with pre and post injections
            final_prompt = prompt
            if pre_injections:
                final_prompt = "\n\n".join(pre_injections) + "\n\n" + final_prompt
            if post_injections:
                final_prompt = final_prompt + "\n\n".join(post_injections)
                
            return final_prompt
        else:
            # For plain text prompts, use the full injection with role prefixes
            prompt_parts = []
            final_parts = []
            
            # Add response reinforcement only in chat mode
            if self.chat_mode:
                prompt_parts.append(f"System: {self.prompts.RESPONSE_REINFORCEMENT_PROMPT}")
                prompt_parts.append(f"System: {self.prompts.CHAT_MODE_NO_FILES_PROMPT}")
            
            # Add user prompt
            if self.chat_mode:
                prompt_parts.append(f"User: {prompt}")
            else:
                # In normal mode, return prompt as-is
                return prompt
            
            # Detect formats and add final reinforcement if we have messages (chat mode only)
            if messages and self.chat_mode:
                has_tool_defs, has_json_req = self.format_detector.detect_special_formats(messages)
                
                final_reinforcement = self.prompts.get_final_reinforcement(has_tool_defs, has_json_req)
                if final_reinforcement:
                    # Add this as a final part after everything else
                    final_parts.append(f"System: {final_reinforcement}")
            
            # Combine all parts with final reinforcement at the very end
            full_prompt = "\n\n".join(prompt_parts)
            if final_parts:
                full_prompt += "\n\n" + "\n\n".join(final_parts)
                
            return full_prompt
    
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
        continue_session: bool = False,
        messages: Optional[List[Dict]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run Claude Code using the Python SDK and yield response chunks."""
        
        # In chat mode, override certain behaviors
        if self.chat_mode:
            # Log if session parameters were provided
            if session_id or continue_session:
                logger.warning("Session parameters ignored in chat mode - each request is stateless")
            
            # Create sandbox directory for this request
            sandbox_dir = ChatMode.create_sandbox()
            cwd = Path(sandbox_dir)
            
            # Force allowed tools to chat mode tools
            allowed_tools = ChatMode.get_allowed_tools()
            
            # Prepare prompt with injections
            enhanced_prompt = self._prepare_prompt_with_injections(prompt, messages)
        else:
            # Normal mode
            cwd = self.cwd
            enhanced_prompt = prompt
        
        try:
            # Set authentication environment variables (if any)
            original_env = {}
            if self.claude_env_vars:  # Only set env vars if we have any
                for key, value in self.claude_env_vars.items():
                    original_env[key] = os.environ.get(key)
                    os.environ[key] = value
            
            try:
                # Execute in chat mode without environment sanitization
                # The SDK needs auth env vars, but execution is still sandboxed via cwd
                if self.chat_mode:
                    # Build SDK options with sandbox
                    options = ClaudeCodeOptions(
                        max_turns=max_turns,
                        cwd=cwd  # This provides the file system isolation
                    )
                    
                    # Set model if specified
                    if model:
                        options.model = model
                        
                    # Set system prompt if specified
                    if system_prompt:
                        options.system_prompt = system_prompt
                        
                    # Set tool restrictions
                    options.allowed_tools = allowed_tools
                    
                    # Force disable session features in chat mode
                    options.continue_session = False
                    options.resume = None
                    
                    # Run the query and yield messages
                    logger.debug(f"Executing query with enhanced prompt in chat mode")
                    try:
                        async for message in query(prompt=enhanced_prompt, options=options):
                            processed_msg = self._process_message(message)
                            # Log assistant responses
                            if processed_msg.get("type") == "assistant" or "content" in processed_msg:
                                logger.debug(f"Assistant message type: {processed_msg.get('type')}, has content: {'content' in processed_msg}")
                            yield processed_msg
                    except Exception as sdk_error:
                        # Handle SDK errors gracefully
                        if "cancel scope" in str(sdk_error).lower():
                            logger.warning(f"SDK cancel scope issue detected (will continue): {sdk_error}")
                            # Don't propagate cancel scope errors - they're internal to SDK
                        else:
                            logger.error(f"SDK error during streaming: {sdk_error}")
                            raise
                else:
                    # Normal mode - existing logic
                    options = ClaudeCodeOptions(
                        max_turns=max_turns,
                        cwd=cwd
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
                    async for message in query(prompt=enhanced_prompt, options=options):
                        yield self._process_message(message)
                    
            finally:
                # Restore original environment (if we changed anything)
                if original_env:
                    for key, original_value in original_env.items():
                        if original_value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = original_value
                
                # Note: Sandbox cleanup moved to main.py to avoid premature cleanup
                
        except Exception as e:
            # Don't log cancel scope errors as errors
            if "cancel scope" in str(e).lower():
                logger.warning(f"SDK cancel scope issue at completion: {e}")
            else:
                logger.error(f"Claude Code SDK error: {e}")
                # Yield error message in the expected format
                yield {
                    "type": "result",
                    "subtype": "error_during_execution",
                    "is_error": True,
                    "error_message": str(e)
                }
    
    def _process_message(self, message: Any) -> Dict[str, Any]:
        """Process message from SDK to consistent dict format."""
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
            return message_dict
        else:
            return message
    
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