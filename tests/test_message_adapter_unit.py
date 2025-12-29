#!/usr/bin/env python3
"""
Unit tests for src/message_adapter.py

Tests the MessageAdapter class for message format conversion.
These are pure unit tests that don't require a running server.
"""

import pytest
from src.message_adapter import MessageAdapter
from src.models import Message


class TestMessagesToPrompt:
    """Test MessageAdapter.messages_to_prompt()"""

    def test_single_user_message(self):
        """Single user message converts correctly."""
        messages = [Message(role="user", content="Hello")]
        prompt, system = MessageAdapter.messages_to_prompt(messages)

        assert "Human: Hello" in prompt
        assert system is None

    def test_user_and_assistant_conversation(self):
        """User and assistant messages form conversation."""
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
            Message(role="user", content="How are you?"),
        ]
        prompt, system = MessageAdapter.messages_to_prompt(messages)

        assert "Human: Hello" in prompt
        assert "Assistant: Hi there!" in prompt
        assert "Human: How are you?" in prompt

    def test_system_message_extracted(self):
        """System message is extracted as system_prompt."""
        messages = [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Hello"),
        ]
        prompt, system = MessageAdapter.messages_to_prompt(messages)

        assert system == "You are a helpful assistant."
        assert "Human: Hello" in prompt

    def test_multiple_system_messages_uses_last(self):
        """Multiple system messages use the last one."""
        messages = [
            Message(role="system", content="First system message"),
            Message(role="user", content="Hello"),
            Message(role="system", content="Second system message"),
        ]
        prompt, system = MessageAdapter.messages_to_prompt(messages)

        assert system == "Second system message"

    def test_last_message_not_user_adds_continue(self):
        """If last message isn't from user, adds 'Please continue'."""
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
        ]
        prompt, system = MessageAdapter.messages_to_prompt(messages)

        assert "Please continue" in prompt

    def test_last_message_is_user_no_continue(self):
        """If last message is from user, no 'Please continue' added."""
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi!"),
            Message(role="user", content="What's up?"),
        ]
        prompt, system = MessageAdapter.messages_to_prompt(messages)

        assert "Please continue" not in prompt

    def test_empty_messages_list(self):
        """Empty messages list returns empty prompt."""
        messages = []
        prompt, system = MessageAdapter.messages_to_prompt(messages)

        assert prompt == ""
        assert system is None


class TestFilterContent:
    """Test MessageAdapter.filter_content()"""

    def test_empty_content_returns_empty(self):
        """Empty content returns empty."""
        assert MessageAdapter.filter_content("") == ""
        assert MessageAdapter.filter_content(None) is None

    def test_plain_text_unchanged(self):
        """Plain text content is unchanged."""
        content = "Hello, how can I help you today?"
        result = MessageAdapter.filter_content(content)
        assert result == content

    def test_removes_thinking_blocks(self):
        """Thinking blocks are removed."""
        content = "<thinking>Let me think about this...</thinking>Here is my answer."
        result = MessageAdapter.filter_content(content)

        assert "<thinking>" not in result
        assert "Let me think" not in result
        assert "Here is my answer" in result

    def test_removes_multiline_thinking_blocks(self):
        """Multiline thinking blocks are removed."""
        content = """<thinking>
        Line 1 of thinking
        Line 2 of thinking
        </thinking>
        The actual response."""
        result = MessageAdapter.filter_content(content)

        assert "<thinking>" not in result
        assert "The actual response" in result

    def test_extracts_attempt_completion_content(self):
        """Content from attempt_completion blocks is extracted."""
        content = """Some preamble
        <attempt_completion>
        This is the actual response to return.
        </attempt_completion>
        Some other stuff"""
        result = MessageAdapter.filter_content(content)

        assert "This is the actual response to return" in result

    def test_extracts_result_from_attempt_completion(self):
        """Content from result tags inside attempt_completion is extracted."""
        content = """<attempt_completion>
        <result>The extracted result.</result>
        </attempt_completion>"""
        result = MessageAdapter.filter_content(content)

        assert result == "The extracted result."

    def test_removes_read_file_blocks(self):
        """read_file blocks are removed."""
        content = "Response <read_file>path/to/file.txt</read_file> more text"
        result = MessageAdapter.filter_content(content)

        assert "<read_file>" not in result
        assert "path/to/file" not in result

    def test_removes_write_file_blocks(self):
        """write_file blocks are removed."""
        content = "Response <write_file>content</write_file> more text"
        result = MessageAdapter.filter_content(content)

        assert "<write_file>" not in result

    def test_removes_bash_blocks(self):
        """bash blocks are removed."""
        content = "Here's the output: <bash>ls -la</bash> done"
        result = MessageAdapter.filter_content(content)

        assert "<bash>" not in result
        assert "ls -la" not in result

    def test_removes_search_files_blocks(self):
        """search_files blocks are removed."""
        content = "<search_files>pattern</search_files>Result"
        result = MessageAdapter.filter_content(content)

        assert "<search_files>" not in result

    def test_removes_str_replace_editor_blocks(self):
        """str_replace_editor blocks are removed."""
        content = "<str_replace_editor>edit</str_replace_editor>Done"
        result = MessageAdapter.filter_content(content)

        assert "<str_replace_editor>" not in result

    def test_removes_args_blocks(self):
        """args blocks are removed."""
        content = "Command <args>--flag value</args> executed"
        result = MessageAdapter.filter_content(content)

        assert "<args>" not in result

    def test_removes_ask_followup_question_blocks(self):
        """ask_followup_question blocks are removed."""
        content = "<ask_followup_question>What do you mean?</ask_followup_question>Ok"
        result = MessageAdapter.filter_content(content)

        assert "<ask_followup_question>" not in result

    def test_removes_question_blocks(self):
        """question blocks are removed."""
        content = "<question>Do you want to proceed?</question>Answer"
        result = MessageAdapter.filter_content(content)

        assert "<question>" not in result

    def test_removes_follow_up_blocks(self):
        """follow_up blocks are removed."""
        content = "<follow_up>Please clarify</follow_up>Response"
        result = MessageAdapter.filter_content(content)

        assert "<follow_up>" not in result

    def test_removes_suggest_blocks(self):
        """suggest blocks are removed."""
        content = "<suggest>try this</suggest>Suggestion"
        result = MessageAdapter.filter_content(content)

        assert "<suggest>" not in result

    def test_replaces_image_references(self):
        """Image references are replaced with placeholder."""
        content = "Here's the image: [Image: screenshot.png] as you can see"
        result = MessageAdapter.filter_content(content)

        assert "[Image: Content not supported by Claude Code]" in result
        assert "screenshot.png" not in result

    def test_replaces_base64_image_data(self):
        """Base64 image data is replaced."""
        content = "Image: data:image/png;base64,iVBORw0KGgoAAAANSUhE end"
        result = MessageAdapter.filter_content(content)

        assert "base64" not in result
        assert "iVBORw0" not in result

    def test_collapses_multiple_newlines(self):
        """Multiple consecutive newlines are collapsed."""
        content = "Line 1\n\n\n\n\nLine 2"
        result = MessageAdapter.filter_content(content)

        # Should have at most double newlines
        assert "\n\n\n" not in result

    def test_empty_after_filtering_returns_fallback(self):
        """If content is empty after filtering, returns fallback message."""
        content = "<thinking>Only thinking content</thinking>"
        result = MessageAdapter.filter_content(content)

        assert "How can I help you today?" in result

    def test_whitespace_only_after_filtering_returns_fallback(self):
        """If content is only whitespace after filtering, returns fallback."""
        content = "<thinking>content</thinking>   \n   \n   "
        result = MessageAdapter.filter_content(content)

        assert "How can I help you today?" in result


class TestFormatClaudeResponse:
    """Test MessageAdapter.format_claude_response()"""

    def test_basic_formatting(self):
        """Basic response formatting."""
        result = MessageAdapter.format_claude_response(
            content="Hello!", model="claude-3-opus"
        )

        assert result["role"] == "assistant"
        assert result["content"] == "Hello!"
        assert result["model"] == "claude-3-opus"
        assert result["finish_reason"] == "stop"

    def test_custom_finish_reason(self):
        """Can specify custom finish_reason."""
        result = MessageAdapter.format_claude_response(
            content="Hello!", model="claude-3", finish_reason="length"
        )

        assert result["finish_reason"] == "length"

    def test_preserves_content_exactly(self):
        """Content is preserved exactly as provided."""
        content = "Multi\nline\ncontent with special chars: <>&\""
        result = MessageAdapter.format_claude_response(content=content, model="claude")

        assert result["content"] == content


class TestEstimateTokens:
    """Test MessageAdapter.estimate_tokens()"""

    def test_short_text(self):
        """Short text token estimation."""
        # 12 chars / 4 = 3 tokens
        result = MessageAdapter.estimate_tokens("Hello World!")
        assert result == 3

    def test_empty_text(self):
        """Empty text returns 0 tokens."""
        result = MessageAdapter.estimate_tokens("")
        assert result == 0

    def test_long_text(self):
        """Longer text estimation."""
        # 100 chars / 4 = 25 tokens
        text = "a" * 100
        result = MessageAdapter.estimate_tokens(text)
        assert result == 25

    def test_realistic_text(self):
        """Realistic text estimation."""
        text = "This is a realistic sentence that might appear in a conversation."
        result = MessageAdapter.estimate_tokens(text)
        # 67 chars / 4 = 16 tokens
        assert result == 16
