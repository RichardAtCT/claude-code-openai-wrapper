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
from xml_detector import DeterministicXMLDetector

logger = logging.getLogger(__name__)

# Pre-compiled regex patterns for performance
import re
XML_TAG_PATTERN = re.compile(r'<(\w+)>.*?</\1>', re.DOTALL | re.IGNORECASE)
TOOL_NAME_PATTERN = re.compile(r'<tool_name>(\w+)</tool_name>', re.IGNORECASE)
NESTED_XML_PATTERN = re.compile(r'<\w+>\s*<\w+>')


class ClaudeCodeCLI:
    def __init__(self, timeout: int = 600000, cwd: Optional[str] = None):
        self.timeout = timeout / 1000  # Convert ms to seconds
        
        # Check if chat mode is enabled
        self.chat_mode = ChatMode.is_enabled()
        self.format_detector = FormatDetector()
        self.prompts = ChatModePrompts()
        self.xml_detector = DeterministicXMLDetector()
        
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
        logger.debug(f"Preparing prompt with injections, chat_mode={self.chat_mode}")
        # Import MessageAdapter to use the format detection
        from message_adapter import MessageAdapter
        import re
        
        # Check if the prompt already has structured format
        has_structured_prompt = MessageAdapter.has_structured_format(prompt)
        logger.debug(f"Has structured prompt format: {has_structured_prompt}")
        
        if has_structured_prompt:
            # For structured prompts (XML, JSON, etc), preserve the exact format
            logger.debug("Detected structured prompt format - applying enhanced injection")
            
            pre_injections = []
            mid_injections = []
            post_injections = []
            
            # Use deterministic XML detector
            xml_required, detection_reason, xml_tool_names = self.xml_detector.detect(prompt, messages)
            
            # Log the detection result
            logger.info(f"🔍 XML Detection Result: {'YES' if xml_required else 'NO'}")
            logger.info(f"   Reason: {detection_reason}")
            if xml_tool_names:
                logger.info(f"   Tools: {', '.join(xml_tool_names)}")
            
            if xml_required and self.chat_mode:
                # Layer 1: Prime at the beginning
                pre_injections.append(
                    "ATTENTION: This conversation uses XML-formatted tools. "
                    "You MUST respond using the EXACT XML format demonstrated in the conversation."
                )
                
                # Layer 2: Reinforce with examples (if we found any)
                if xml_tool_names:
                    # Use the first tool name as primary example
                    primary_tool = xml_tool_names[0]
                    
                    # Build more specific guidance based on common formatting tags
                    if 'attempt_completion' in xml_tool_names:
                        example_text = (
                            f"\n\nREMINDER: Format your response using XML tags.\n"
                            f"For completing tasks, format as: <attempt_completion><result>your response</result></attempt_completion>\n"
                            f"For asking questions, format as: <ask_followup_question><question>your question</question><follow_up>...</follow_up></ask_followup_question>\n"
                            f"DO NOT use <environment_details>, <task>, or other structural tags - only the response formatting tags above."
                        )
                    else:
                        example_text = (
                            f"\n\nREMINDER: Your response MUST be formatted with XML tags.\n"
                            f"Use ONLY these formatting tags: {', '.join([f'<{tool}>' for tool in xml_tool_names])}\n"
                            f"Example: <{primary_tool}>your_response_here</{primary_tool}>\n"
                            f"DO NOT use <environment_details>, <task>, or other structural tags."
                        )
                    
                    mid_injections.append(example_text)
                    logger.debug(f"Added specific XML formatting guidance for: {xml_tool_names}")
                
                # Layer 3: Critical final enforcement
                tool_instruction = (
                    "\n\nCRITICAL - THIS IS MANDATORY:\n"
                    "1. Your ENTIRE response MUST be formatted using XML tags\n"
                    "2. Use ONLY these XML formatting tags: <attempt_completion>, <ask_followup_question>, etc.\n"
                    "3. DO NOT use <environment_details>, <task>, <response> or any non-formatting tags\n"
                    "4. Start your response with an opening XML tag and end with the closing tag\n"
                    "5. NO plain text outside the XML tags\n"
                    "6. For general responses, format as: <attempt_completion><result>...</result></attempt_completion>\n\n"
                    "CLARIFICATION: These XML tags are RESPONSE FORMATTING - NOT Claude tools.\n"
                    "You don't need any SDK tools to use these XML tags. Simply format your text response within them.\n\n"
                    "IMPORTANT: Provide COMPLETE responses - do not truncate or abbreviate."
                )
                post_injections.append(tool_instruction)
                logger.info("XML ENFORCEMENT ACTIVE: Multi-layer XML response formatting enforcement applied")
                logger.debug(f"Enforcement layers: pre={len(pre_injections)}, mid={len(mid_injections)}, post={len(post_injections)}")
            elif self.chat_mode and not xml_required:
                # Only add full chat mode prompt if there are no XML requirements
                pre_injections.append(self.prompts.CHAT_MODE_NO_FILES_PROMPT)
                # Add completeness instruction for non-tool responses
                post_injections.append(
                    "\n\nIMPORTANT: Provide COMPLETE and THOROUGH responses. "
                    "Do not truncate or abbreviate your answers. "
                    "If writing code, include the FULL implementation with all necessary details. "
                    "If explaining concepts, be comprehensive and address all aspects of the question."
                )
                logger.debug("Added full chat mode prompt with completeness instruction (no XML format required)")
            
            # Build the final prompt with all injection layers
            final_prompt = prompt
            
            # Apply pre-injections
            if pre_injections:
                final_prompt = "\n\n".join(pre_injections) + "\n\n" + final_prompt
            
            # Apply mid-injections (after the main content but before final instructions)
            if mid_injections:
                final_prompt = final_prompt + "\n\n" + "\n\n".join(mid_injections)
            
            # Apply post-injections - CRITICAL: These must be at the END
            if post_injections:
                final_prompt = final_prompt + "\n\n" + "\n\n".join(post_injections)
            
            # VERIFICATION: If we detected XML tools but no enforcement was added, add it now
            if xml_required and self.chat_mode:
                # Check if XML enforcement is present in the final prompt
                enforcement_present = any([
                    "CRITICAL - THIS IS MANDATORY" in final_prompt,
                    "Your ENTIRE response MUST be wrapped in proper TOOL XML tags" in final_prompt,
                    "XML ENFORCEMENT ACTIVE" in logger.handlers[0].baseFilename if logger.handlers else False
                ])
                
                if not enforcement_present:
                    logger.warning("XML enforcement missing despite detection - adding failsafe enforcement")
                    failsafe_enforcement = (
                        "\n\n[FAILSAFE XML ENFORCEMENT]\n"
                        "CRITICAL: You MUST format your response using XML tags.\n"
                        "Wrap your ENTIRE response in formatting tags like:\n"
                        "<attempt_completion><result>your response here</result></attempt_completion>\n"
                        "DO NOT respond with plain text or markdown!\n"
                        "Remember: These are response formatting tags, NOT SDK tools."
                    )
                    final_prompt = final_prompt + failsafe_enforcement
                    logger.info("FAILSAFE: Added XML enforcement as final prompt instruction")
                
            return final_prompt
        else:
            # For plain text prompts, use the full injection with role prefixes
            prompt_parts = []
            final_parts = []
            
            # Add response reinforcement only in chat mode
            if self.chat_mode:
                prompt_parts.append(f"System: {self.prompts.RESPONSE_REINFORCEMENT_PROMPT}")
                prompt_parts.append(f"System: {self.prompts.CHAT_MODE_NO_FILES_PROMPT}")
                # Add completeness instruction
                prompt_parts.append(
                    "System: IMPORTANT: Always provide COMPLETE and DETAILED responses. "
                    "Do not truncate, abbreviate, or cut off your answers. "
                    "Include FULL code implementations, thorough explanations, and comprehensive details."
                )
            
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
            logger.debug(f"Original prompt length: {len(prompt)}")
            enhanced_prompt = self._prepare_prompt_with_injections(prompt, messages)
            logger.debug(f"Enhanced prompt length: {len(enhanced_prompt)}")
            if enhanced_prompt != prompt:
                logger.info(f"Prompt was enhanced with injections (added {len(enhanced_prompt) - len(prompt)} chars)")
                # Log first and last 500 chars of enhanced prompt
                if len(enhanced_prompt) > 1000:
                    logger.debug(f"Enhanced prompt start: {enhanced_prompt[:500]}...")
                    logger.info(f"Enhanced prompt end: ...{enhanced_prompt[-500:]}")
                else:
                    logger.debug(f"Enhanced prompt: {enhanced_prompt}")
            
            # Log the complete SDK options
            logger.info("=== SDK OPTIONS ===")
            logger.info(f"allowed_tools: {allowed_tools}")
            logger.info(f"disallowed_tools: {disallowed_tools}")
            logger.info(f"max_turns: {max_turns}")
            logger.info(f"model: {model}")
            logger.info(f"stream: {stream}")
            logger.info(f"session_id: {session_id}")
            logger.info(f"continue_session: {continue_session}")
            logger.info("=== END SDK OPTIONS ===")
            
            # Verify XML enforcement is present if expected
            xml_check_required, _, _ = self.xml_detector.detect(prompt, messages)
            if xml_check_required:
                if "CRITICAL - THIS IS MANDATORY" in enhanced_prompt or "FAILSAFE XML ENFORCEMENT" in enhanced_prompt:
                    logger.info("✓ XML enforcement successfully added to prompt")
                else:
                    logger.error("✗ XML enforcement NOT found in enhanced prompt despite deterministic detection!")
            
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
                    logger.info(f"Executing query with enhanced prompt in chat mode")
                    logger.info(f"SDK options: sandbox_dir={options.cwd}, max_turns={options.max_turns}")
                    logger.info(f"Allowed tools: {options.allowed_tools}")
                    logger.info(f"Model: {options.model}")
                    logger.info(f"System prompt set: {bool(options.system_prompt)}")
                    
                    # Log critical SDK environment state
                    logger.info("=== SDK EXECUTION STARTING ===")
                    logger.info(f"Chat mode allowed tools: {allowed_tools}")
                    logger.info(f"Options allowed_tools: {options.allowed_tools}")
                    
                    
                    try:
                        total_content_length = 0
                        sdk_message_count = 0
                        
                        
                        async for message in query(prompt=enhanced_prompt, options=options):
                            sdk_message_count += 1
                            processed_msg = self._process_message(message)
                            msg_type = processed_msg.get('type')
                            msg_subtype = processed_msg.get('subtype')
                            logger.debug(f"SDK message #{sdk_message_count} type: {msg_type}, subtype: {msg_subtype}")
                            
                            # Additional logging for assistant messages to track sequencing
                            if msg_type == "assistant":
                                logger.info(f"Assistant message #{sdk_message_count} detected in SDK stream")
                            # Log assistant responses with content length tracking
                            if processed_msg.get("type") == "assistant" or "content" in processed_msg:
                                content = processed_msg.get("content", [])
                                if isinstance(content, list):
                                    for block in content:
                                        if hasattr(block, 'text'):
                                            block_length = len(block.text)
                                            total_content_length += block_length
                                            logger.debug(f"Assistant text block length: {block_length}, total so far: {total_content_length}")
                                        elif isinstance(block, dict) and block.get("type") == "text":
                                            block_length = len(block.get("text", ""))
                                            total_content_length += block_length
                                            logger.debug(f"Assistant text block length: {block_length}, total so far: {total_content_length}")
                                elif isinstance(content, str):
                                    content_length = len(content)
                                    total_content_length += content_length
                                    logger.debug(f"Assistant content length: {content_length}, total so far: {total_content_length}")
                                logger.debug(f"Assistant message type: {processed_msg.get('type')}, has content: {'content' in processed_msg}")
                            # Log completion summary
                            if processed_msg.get("subtype") == "success":
                                logger.info(f"Response completed - Total content length: {total_content_length} characters")
                            yield processed_msg
                        
                        logger.info(f"SDK stream ended normally after {sdk_message_count} messages, total content: {total_content_length} chars")
                        logger.info("=== SDK EXECUTION COMPLETED ===")
                    except Exception as sdk_error:
                        # Handle SDK errors gracefully
                        if "cancel scope" in str(sdk_error).lower():
                            logger.warning(f"SDK cancel scope issue detected (will continue): {sdk_error}")
                            # Don't propagate cancel scope errors - they're internal to SDK
                        else:
                            logger.error(f"SDK error during streaming: {sdk_error}")
                            logger.error("SDK error traceback:", exc_info=True)
                            logger.error("=== SDK EXECUTION FAILED ===")
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
                    total_content_length = 0
                    sdk_message_count = 0
                    logger.info("Starting SDK query with enhanced prompt")
                    logger.debug(f"Options object: {options}")
                    
                    try:
                        async for message in query(prompt=enhanced_prompt, options=options):
                            sdk_message_count += 1
                            logger.debug(f"SDK message #{sdk_message_count} received from query")
                            
                            processed_msg = self._process_message(message)
                            
                            # Log message type and subtype
                            msg_type = processed_msg.get("type", "unknown")
                            msg_subtype = processed_msg.get("subtype", "unknown")
                            logger.debug(f"Processed message type: {msg_type}, subtype: {msg_subtype}")
                            
                            # Track content length in normal mode too
                            if processed_msg.get("type") == "assistant" or "content" in processed_msg:
                                content = processed_msg.get("content", [])
                                if isinstance(content, list):
                                    for block in content:
                                        if hasattr(block, 'text'):
                                            total_content_length += len(block.text)
                                        elif isinstance(block, dict) and block.get("type") == "text":
                                            total_content_length += len(block.get("text", ""))
                                elif isinstance(content, str):
                                    total_content_length += len(content)
                            # Log completion summary
                            if processed_msg.get("subtype") == "success":
                                logger.info(f"Response completed - Total content length: {total_content_length} characters")
                            yield processed_msg
                        
                        logger.info(f"SDK query generator completed after {sdk_message_count} messages")
                    except Exception as query_error:
                        logger.error(f"Exception during SDK query: {type(query_error).__name__}: {query_error}")
                        logger.error("Query error traceback:", exc_info=True)
                        raise
                    
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