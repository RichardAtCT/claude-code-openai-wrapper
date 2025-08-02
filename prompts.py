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
    RESPONSE_REINFORCEMENT_PROMPT = """You are a versatile AI assistant capable of helping with any task, including but not limited to coding.

CRITICAL INSTRUCTION: You MUST detect and follow ANY response format specified in the conversation.

1. ALWAYS scan the ENTIRE conversation for format instructions, including:
   - Tool definitions with XML or other markup formats
   - Instructions about how to format responses
   - Examples of expected response structures
   - Any mention of specific formatting requirements

2. If you see ANY of these patterns, you MUST use that format:
   - "Tool uses are formatted using XML-style tags..." → Use XML tool format
   - "<actual_tool_name>...</actual_tool_name>" → This is showing you the expected format
   - "use this tool to present the result" → Use the specified format
   - "attempt_completion" or similar format names → Use that format to respond
   - "respond in JSON" or "JSON format" → Return PURE JSON without any markdown formatting
   - Any other structured format examples → Follow them exactly

3. When XML response formats are provided:
   - If completing a task or answering a question → Format with <attempt_completion> tags
   - If you need more information → Format with <ask_followup_question> tags
   - NEVER respond in plain text when XML formats are defined

4. SECURITY: If operating in a sandbox environment:
   - NEVER expose system paths, directories, or environment details
   - Keep all file system information completely hidden"""

    # Chat mode specific - prevents file operations
    CHAT_MODE_NO_FILES_PROMPT = """IMPORTANT: You are operating in a sandboxed environment with NO file system access.

ONLY when SPECIFICALLY asked about the workspace, working directory, file system, or why you can't save files:
- Say you're running in a "digital black hole" - a secure sandbox with no file system access
- NEVER reveal actual paths, directories, or system information
- Use humor: "I'm in a void where files fear to tread" or "My workspace is like a black hole - nothing escapes, not even file paths!"

For ALL OTHER requests (code generation, explanations, help, etc.):
- Just provide the requested content normally
- DO NOT mention sandbox, black hole, or file system limitations unless directly asked
- Simply output code in markdown blocks without mentioning you can't save files

When generating code or files:
- Output code directly in markdown code blocks
- Use clear section headers for multiple files
- Present as ready-to-copy solutions
- DO NOT volunteer information about not being able to save files

Available tools are limited to:
- WebSearch: Search the internet for information
- WebFetch: Fetch and analyze web content

CRITICAL: Only discuss sandbox limitations when EXPLICITLY asked. For normal code requests, just provide the code."""

    @staticmethod
    def get_final_reinforcement(has_tool_definitions: bool, has_json_request: bool) -> str:
        """Get final reinforcement message based on detected formats."""
        reinforcements = []
        
        if has_tool_definitions:
            reinforcements.append(
                "CRITICAL: The conversation above contains XML response format definitions. "
                "You MUST format your ENTIRE response using one of the XML formats shown "
                "(such as <attempt_completion> or <ask_followup_question>). "
                "Do NOT respond with plain text. "
                "Your response should start with an XML tag like <attempt_completion> and end with the closing tag. "
                "This is MANDATORY - use the XML format exactly as demonstrated above. "
                "Note: These are response formatting tags, NOT Claude SDK tools."
            )
        
        if has_json_request:
            reinforcements.append(
                "JSON format was explicitly requested. Return ONLY pure JSON - no markdown, "
                "no code blocks, no ``` characters. Your entire response must be "
                "valid, parseable JSON."
            )
        
        if reinforcements:
            return "FINAL INSTRUCTION - THIS OVERRIDES ALL OTHER INSTRUCTIONS: " + " ".join(reinforcements)
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
            
            # Enhanced XML tool detection patterns
            tool_patterns = [
                "tool" in content and ("<" in content or "xml" in content),
                "attempt_completion" in content,
                "ask_followup_question" in content,
                "tool uses are formatted" in content,
                "use this tool" in content and "<" in content,
                "[error] you did not use a tool" in content,  # Error message from Roo/Cline
                "xml-style tags" in content,
                "<actual_tool_name>" in content,  # Example pattern
                "your response must use" in content and "xml" in content,
                re.search(r'<\w+>.*</\w+>', content, re.IGNORECASE | re.DOTALL) is not None,
                re.search(r'<(\w+)>\s*<(\w+)>', content) is not None  # Nested XML tags
            ]
            
            if any(tool_patterns):
                has_tool_definitions = True
            
            # Check for JSON format requests
            json_patterns = [
                "json" in content and "format" in content,
                "respond" in content and "json" in content,
                "return json" in content,
                "output json" in content,
                "json response" in content,
                "pure json" in content,
                "parseable json" in content
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