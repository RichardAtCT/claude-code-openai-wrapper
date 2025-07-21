"""
Prompt engineering and format detection for chat mode.

This module handles prompt injection and format detection to ensure
compatibility with chat clients that expect specific response formats.
"""

from typing import List, Dict, Any, Tuple
import re


class ChatModePrompts:
    """Centralized prompt definitions for chat mode."""
    
    # Always active - ensures format compliance
    RESPONSE_REINFORCEMENT_PROMPT = """You are a versatile AI assistant capable of helping with any task.

CRITICAL INSTRUCTION: You MUST detect and follow ANY response format specified in the conversation.

1. ALWAYS scan the ENTIRE conversation for format instructions, including:
   - Tool definitions with XML or other markup formats
   - Instructions about how to format responses
   - Examples of expected response structures
   - Any mention of specific formatting requirements

2. If you see ANY of these patterns, you MUST use that format:
   - "Tool uses are formatted using XML-style tags..." → Use XML tool format
   - "<actual_tool_name>...</actual_tool_name>" → This is showing you the expected format
   - "attempt_completion" or similar tool names → Use that tool to respond
   - "respond in JSON" or "JSON format" → Return PURE JSON without any markdown formatting

3. When tool definitions are provided:
   - If completing a task → Use attempt_completion tool
   - If you need more information → Use ask_followup_question tool
   - NEVER respond in plain text if tools are defined"""

    # Chat mode specific - prevents file operations
    CHAT_MODE_NO_FILES_PROMPT = """IMPORTANT: You are operating in chat-only mode with LIMITED TOOLS.

You ONLY have access to:
- WebSearch: Search the internet for information
- WebFetch: Fetch and analyze web content
- Task: Perform deep searches and research

ALL OTHER TOOLS ARE DISABLED, including:
- File operations (Write, Edit, MultiEdit)
- File system access (Grep, Glob, LS)
- Command execution (Bash)
- Notebook operations
- Todo management
- Planning tools

When asked to write code or create files:
- Output ALL code directly in markdown code blocks
- Use clear section headers for multiple files
- NEVER attempt to create, write, or save files
- Present code as ready-to-copy solutions"""

    @staticmethod
    def get_final_reinforcement(has_tool_definitions: bool, has_json_request: bool) -> str:
        """Get final reinforcement message based on detected formats."""
        reinforcements = []
        
        if has_tool_definitions:
            reinforcements.append(
                "You have been provided with tool definitions in this conversation. "
                "Your response MUST use the XML tool format that was shown to you. "
                "Do NOT respond in plain text. Use the appropriate tool "
                "(like <attempt_completion>) to format your response."
            )
        
        if has_json_request:
            reinforcements.append(
                "JSON format was requested. Return ONLY pure JSON - no markdown, "
                "no code blocks, no ``` characters. Your entire response must be "
                "valid, parseable JSON."
            )
        
        if reinforcements:
            return "FINAL REMINDER: " + " ".join(reinforcements)
        return ""


class FormatDetector:
    """Detect special format requirements in messages."""
    
    @staticmethod
    def detect_special_formats(messages: List[Dict[str, Any]]) -> Tuple[bool, bool]:
        """
        Detect if messages contain tool definitions or JSON format requests.
        
        Returns:
            Tuple of (has_tool_definitions, has_json_request)
        """
        has_tool_definitions = False
        has_json_request = False
        
        for msg in messages:
            content = str(msg.get("content", "")).lower()
            
            # Check for XML tool definitions (common in chat clients)
            tool_patterns = [
                "tool" in content and ("<" in content or "xml" in content),
                "attempt_completion" in content,
                "ask_followup_question" in content,
                "tool uses are formatted" in content,
                "use this tool" in content and "<" in content,
                re.search(r'<\w+>.*</\w+>', content, re.IGNORECASE) is not None
            ]
            
            if any(tool_patterns):
                has_tool_definitions = True
            
            # Check for JSON format requests
            json_patterns = [
                "json" in content and "format" in content,
                "respond" in content and "json" in content,
                "return json" in content,
                "output json" in content,
                "json response" in content
            ]
            
            if any(json_patterns):
                has_json_request = True
        
        return has_tool_definitions, has_json_request
    
    @staticmethod
    def contains_tool_example(content: str) -> bool:
        """Check if content contains an XML tool example."""
        # Look for XML-like tags that might be tool examples
        xml_pattern = r'<(\w+)>[\s\S]*?</\1>'
        return bool(re.search(xml_pattern, content))


def inject_prompts(messages: List[Dict[str, Any]], chat_mode: bool = False) -> List[Dict[str, Any]]:
    """
    Inject system prompts into message list based on mode and format detection.
    
    Args:
        messages: Original message list
        chat_mode: Whether chat mode is enabled
        
    Returns:
        Enhanced message list with injected prompts
    """
    detector = FormatDetector()
    prompts = ChatModePrompts()
    
    # Detect special formats
    has_tool_defs, has_json_req = detector.detect_special_formats(messages)
    
    # Build enhanced message list
    enhanced_messages = []
    
    # Always add response reinforcement as first system message
    enhanced_messages.append({
        "role": "system",
        "content": prompts.RESPONSE_REINFORCEMENT_PROMPT
    })
    
    # Add chat mode prompt if enabled
    if chat_mode:
        enhanced_messages.append({
            "role": "system", 
            "content": prompts.CHAT_MODE_NO_FILES_PROMPT
        })
    
    # Add original messages
    enhanced_messages.extend(messages)
    
    # Add final reinforcement if needed
    final_reinforcement = prompts.get_final_reinforcement(has_tool_defs, has_json_req)
    if final_reinforcement:
        enhanced_messages.append({
            "role": "system",
            "content": final_reinforcement
        })
    
    return enhanced_messages