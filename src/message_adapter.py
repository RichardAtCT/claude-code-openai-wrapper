from typing import List, Optional, Dict, Any
from src.models import Message
import re


class MessageAdapter:
    """Converts between OpenAI message format and Claude Code prompts."""

    @staticmethod
    def messages_to_prompt(messages: List[Message], model: Optional[str] = None) -> tuple[str, Optional[str]]:
        """
        Convert OpenAI messages to Claude Code prompt format.
        Returns (prompt, system_prompt)
        """
        system_prompt = None
        conversation_parts = []
        
        # Check if it's a Gemini model
        is_gemini = model and (
            model.startswith("gemini") 
            or model in ["pro", "flash", "flash-lite", "auto"]
        )

        for message in messages:
            if message.role == "system":
                # Use the last system message as the system prompt
                system_prompt = message.content
            elif message.role == "user":
                if is_gemini:
                    conversation_parts.append(message.content)
                else:
                    conversation_parts.append(f"Human: {message.content}")
            elif message.role == "assistant":
                if is_gemini:
                    conversation_parts.append(message.content)
                else:
                    conversation_parts.append(f"Assistant: {message.content}")

        # Join conversation parts
        prompt = "\n\n".join(conversation_parts)

        # If the last message wasn't from the user, add a prompt for assistant
        if messages and messages[-1].role != "user":
            if not is_gemini:
                prompt += "\n\nHuman: Please continue."

        return prompt, system_prompt

    @staticmethod
    def filter_content(content: str, prompt_echo: Optional[str] = None) -> str:
        """
        Filter content for unsupported features and tool usage.
        Remove thinking blocks, tool calls, and image references.
        """
        if content is None:
            return ""

        # Strip exact prompt echoes if provided (common with some CLI tools)

        if prompt_echo and content.startswith(prompt_echo):
            content = content[len(prompt_echo):].strip()
            # Also handle cases where Human: prefix is echoed
            if content.startswith("Assistant:"):
                content = content[len("Assistant:"):].strip()

        # Remove thinking blocks (common when tools are disabled but Claude tries to think)
        thinking_patterns = [r"<thinking>.*?</thinking>", r"<thought>.*?</thought>"]
        for pattern in thinking_patterns:
            content = re.sub(pattern, "", content, flags=re.DOTALL)

        # Extract content from attempt_completion blocks (these contain the actual user response)
        attempt_completion_pattern = r"<attempt_completion>(.*?)</attempt_completion>"
        attempt_matches = re.findall(attempt_completion_pattern, content, flags=re.DOTALL)
        if attempt_matches:
            # Use the content from the attempt_completion block
            extracted_content = attempt_matches[0].strip()

            # If there's a <result> tag inside, extract from that
            result_pattern = r"<result>(.*?)</result>"
            result_matches = re.findall(result_pattern, extracted_content, flags=re.DOTALL)
            if result_matches:
                extracted_content = result_matches[0].strip()

            if extracted_content:
                content = extracted_content
        else:
            # Instead of deleting all tool blocks, replace them with a short placeholder
            # This prevents the message from being empty and explains what Claude was doing.
            tool_tags = [
                "read_file", "write_file", "bash", "search_files", 
                "str_replace_editor", "args", "ask_followup_question", 
                "question", "follow_up", "suggest"
            ]
            
            for tag in tool_tags:
                pattern = f"<{tag}>(.*?)</{tag}>"
                # If we find a tool tag, replace it with a shorter placeholder but keep some of the content
                def replace_tool(match):
                    inner = match.group(1).strip()
                    # Only show first 50 chars of the tool command/arg to keep it clean
                    summary = (inner[:47] + "...") if len(inner) > 50 else inner
                    return f"\n[Tool: {tag} {summary}]\n"
                
                content = re.sub(pattern, replace_tool, content, flags=re.DOTALL)

        # Pattern to match image references or base64 data
        image_pattern = r"\[Image:.*?\]|data:image/.*?;base64,.*?(?=\s|$)"

        def replace_image(match):
            return "[Image: Content not supported by Claude Code]"

        content = re.sub(image_pattern, replace_image, content)

        # Clean up extra whitespace and newlines
        content = re.sub(r"\n\s*\n\s*\n", "\n\n", content)  # Multiple newlines to double
        content = content.strip()

        # If content is now empty or only whitespace, and we originally HAD content,
        # provide a more conversational fallback that indicates we understood but filtered.
        if not content or content.isspace():
            return "I've processed your request. How else can I help you with this project today?"

        return content

    @staticmethod
    def format_claude_response(
        content: str, model: str, finish_reason: str = "stop"
    ) -> Dict[str, Any]:
        """Format Claude response for OpenAI compatibility."""
        return {
            "role": "assistant",
            "content": content,
            "finish_reason": finish_reason,
            "model": model,
        }

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Rough estimation of token count.
        OpenAI's rule of thumb: ~4 characters per token for English text.
        """
        return len(text) // 4
