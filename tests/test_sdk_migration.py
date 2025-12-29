#!/usr/bin/env python3
"""
Critical tests for Claude Agent SDK migration.

Tests system prompt formats, message conversion, and basic SDK integration.
"""

import asyncio
import pytest
from claude_agent_sdk import ClaudeAgentOptions


class TestSystemPromptFormats:
    """Test that system prompt formats work correctly with new SDK."""

    def test_text_system_prompt_format(self):
        """Test text-based system prompt format."""
        options = ClaudeAgentOptions(
            max_turns=1, system_prompt={"type": "text", "text": "You are a helpful assistant."}
        )
        assert options.system_prompt is not None
        assert isinstance(options.system_prompt, dict)
        assert options.system_prompt["type"] == "text"

    def test_preset_system_prompt_format(self):
        """Test preset-based system prompt format."""
        options = ClaudeAgentOptions(
            max_turns=1, system_prompt={"type": "preset", "preset": "claude_code"}
        )
        assert options.system_prompt is not None
        assert isinstance(options.system_prompt, dict)
        assert options.system_prompt["type"] == "preset"
        assert options.system_prompt["preset"] == "claude_code"


class TestClaudeAgentOptions:
    """Test ClaudeAgentOptions configuration."""

    def test_basic_options_creation(self):
        """Test creating basic options."""
        options = ClaudeAgentOptions(max_turns=5)
        assert options.max_turns == 5

    def test_options_with_model(self):
        """Test options with model specification."""
        options = ClaudeAgentOptions(max_turns=1, model="claude-sonnet-4-5-20250929")
        assert options.model == "claude-sonnet-4-5-20250929"

    def test_options_with_tools(self):
        """Test options with tool restrictions."""
        options = ClaudeAgentOptions(
            max_turns=1, allowed_tools=["Read", "Write"], disallowed_tools=["Bash"]
        )
        assert options.allowed_tools == ["Read", "Write"]
        assert options.disallowed_tools == ["Bash"]


class TestConstants:
    """Test that constants are properly defined."""

    def test_claude_models_defined(self):
        """Test that CLAUDE_MODELS constant exists and has expected models."""
        from src.constants import CLAUDE_MODELS, DEFAULT_MODEL, FAST_MODEL

        assert isinstance(CLAUDE_MODELS, list)
        assert len(CLAUDE_MODELS) > 0

        # Check latest models are included
        assert "claude-sonnet-4-5-20250929" in CLAUDE_MODELS
        assert "claude-haiku-4-5-20251001" in CLAUDE_MODELS

    def test_default_model_defined(self):
        """Test that DEFAULT_MODEL is set to recommended model."""
        from src.constants import DEFAULT_MODEL, CLAUDE_MODELS

        assert DEFAULT_MODEL in CLAUDE_MODELS
        assert DEFAULT_MODEL == "claude-sonnet-4-5-20250929"

    def test_fast_model_defined(self):
        """Test that FAST_MODEL is set to fastest model."""
        from src.constants import FAST_MODEL, CLAUDE_MODELS

        assert FAST_MODEL in CLAUDE_MODELS
        assert FAST_MODEL == "claude-haiku-4-5-20251001"

    def test_claude_tools_defined(self):
        """Test that CLAUDE_TOOLS constant exists."""
        from src.constants import CLAUDE_TOOLS

        assert isinstance(CLAUDE_TOOLS, list)
        assert len(CLAUDE_TOOLS) > 0

        # Check common tools are included
        assert "Read" in CLAUDE_TOOLS
        assert "Write" in CLAUDE_TOOLS
        assert "Bash" in CLAUDE_TOOLS


class TestMessageHandling:
    """Test message conversion and handling."""

    def test_message_adapter_import(self):
        """Test that MessageAdapter can be imported."""
        from src.message_adapter import MessageAdapter

        assert MessageAdapter is not None

    def test_filter_content_basic(self):
        """Test basic content filtering."""
        from src.message_adapter import MessageAdapter

        # Test with simple text
        result = MessageAdapter.filter_content("Hello world")
        assert result == "Hello world"

    def test_filter_content_with_images(self):
        """Test content filtering with image references in output."""
        from src.message_adapter import MessageAdapter

        # Test with image reference in Claude's output (string format)
        content = "Here is the result: [Image: example.jpg] as you can see."

        result = MessageAdapter.filter_content(content)
        assert isinstance(result, str)
        # Image reference should be converted to placeholder
        assert "[Image: Content not supported" in result


class TestAPIModels:
    """Test API models and validation."""

    def test_chat_completion_request_import(self):
        """Test that ChatCompletionRequest can be imported."""
        from src.models import ChatCompletionRequest

        assert ChatCompletionRequest is not None

    def test_chat_completion_request_creation(self):
        """Test creating a ChatCompletionRequest."""
        from src.models import ChatCompletionRequest

        request = ChatCompletionRequest(
            model="claude-sonnet-4-5-20250929", messages=[{"role": "user", "content": "Hello"}]
        )

        assert request.model == "claude-sonnet-4-5-20250929"
        assert len(request.messages) == 1


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
