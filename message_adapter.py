from typing import List, Optional, Dict, Any
from models import Message
import re


class MessageAdapter:
    """Converts between OpenAI message format and Claude Code prompts."""
    
    @staticmethod
    def messages_to_prompt(messages: List[Message]) -> tuple[str, Optional[str]]:
        """
        Convert OpenAI messages to Claude Code prompt format.
        Returns (prompt, system_prompt)
        """
        system_prompt = None
        conversation_parts = []
        
        for message in messages:
            if message.role == "system":
                # Use the last system message as the system prompt
                system_prompt = message.content
            elif message.role == "user":
                conversation_parts.append(f"Human: {message.content}")
            elif message.role == "assistant":
                conversation_parts.append(f"Assistant: {message.content}")
        
        # Join conversation parts
        prompt = "\n\n".join(conversation_parts)
        
        # If the last message wasn't from the user, add a prompt for assistant
        if messages and messages[-1].role != "user":
            prompt += "\n\nHuman: Please continue."
            
        return prompt, system_prompt
    
    @staticmethod
    def filter_content(content: str) -> str:
        """
        Filter content for unsupported features and tool usage.
        Remove thinking blocks, tool calls, and image references.
        """
        if not content:
            return content
            
        # Remove thinking blocks (common when tools are disabled but Claude tries to think)
        thinking_pattern = r'<thinking>.*?</thinking>'
        content = re.sub(thinking_pattern, '', content, flags=re.DOTALL)
        
        # Extract content from attempt_completion blocks (these contain the actual user response)
        attempt_completion_pattern = r'<attempt_completion>(.*?)</attempt_completion>'
        attempt_matches = re.findall(attempt_completion_pattern, content, flags=re.DOTALL)
        if attempt_matches:
            # Use the content from the attempt_completion block
            extracted_content = attempt_matches[0].strip()
            
            # If there's a <result> tag inside, extract from that
            result_pattern = r'<result>(.*?)</result>'
            result_matches = re.findall(result_pattern, extracted_content, flags=re.DOTALL)
            if result_matches:
                extracted_content = result_matches[0].strip()
            
            if extracted_content:
                content = extracted_content
        else:
            # Remove other tool usage blocks (when tools are disabled but Claude tries to use them)
            tool_patterns = [
                r'<read_file>.*?</read_file>',
                r'<write_file>.*?</write_file>',
                r'<bash>.*?</bash>',
                r'<search_files>.*?</search_files>',
                r'<str_replace_editor>.*?</str_replace_editor>',
                r'<args>.*?</args>',
                r'<ask_followup_question>.*?</ask_followup_question>',
                r'<attempt_completion>.*?</attempt_completion>',
                r'<question>.*?</question>',
                r'<follow_up>.*?</follow_up>',
                r'<suggest>.*?</suggest>',
            ]
            
            for pattern in tool_patterns:
                content = re.sub(pattern, '', content, flags=re.DOTALL)
        
        # Pattern to match image references or base64 data
        image_pattern = r'\[Image:.*?\]|data:image/.*?;base64,.*?(?=\s|$)'
        
        def replace_image(match):
            return "[Image: Content not supported by Claude Code]"
        
        content = re.sub(image_pattern, replace_image, content)
        
        # Clean up extra whitespace and newlines
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)  # Multiple newlines to double
        content = content.strip()
        
        # If content is now empty or only whitespace, provide a fallback
        if not content or content.isspace():
            return "I understand you're testing the system. How can I help you today?"
            
        return content
    
    @staticmethod
    def format_claude_response(content: str, model: str, finish_reason: str = "stop") -> Dict[str, Any]:
        """Format Claude response for OpenAI compatibility."""
        return {
            "role": "assistant",
            "content": content,
            "finish_reason": finish_reason,
            "model": model
        }
    
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Rough estimation of token count.
        OpenAI's rule of thumb: ~4 characters per token for English text.
        """
        return len(text) // 4