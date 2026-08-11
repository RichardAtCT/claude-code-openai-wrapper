#!/usr/bin/env python3
"""
Tests for tool execution functionality.

Tests the fixes for enable_tools=true parameter:
- permission_mode passthrough to ClaudeAgentOptions
- parse_claude_message correctly handling multi-turn ResultMessage
- DEFAULT_ALLOWED_TOOLS configuration
"""

import pytest
import tempfile
from unittest.mock import patch
from claude_agent_sdk import ClaudeAgentOptions


class TestPermissionMode:
    """Test permission_mode configuration for tool execution."""

    def test_permission_mode_option_exists(self):
        """Test that ClaudeAgentOptions supports permission_mode."""
        options = ClaudeAgentOptions(max_turns=1, permission_mode="bypassPermissions")
        assert options.permission_mode == "bypassPermissions"

    def test_permission_mode_default(self):
        """Test that permission_mode defaults to None/default."""
        options = ClaudeAgentOptions(max_turns=1)
        # permission_mode should be None or "default" when not set
        assert options.permission_mode in [None, "default", ""]

    def test_permission_mode_accept_edits(self):
        """Test acceptEdits permission mode."""
        options = ClaudeAgentOptions(max_turns=1, permission_mode="acceptEdits")
        assert options.permission_mode == "acceptEdits"


class TestDefaultAllowedTools:
    """Test DEFAULT_ALLOWED_TOOLS constant."""

    def test_default_allowed_tools_defined(self):
        """Test that DEFAULT_ALLOWED_TOOLS is defined."""
        from src.constants import DEFAULT_ALLOWED_TOOLS

        assert isinstance(DEFAULT_ALLOWED_TOOLS, list)
        assert len(DEFAULT_ALLOWED_TOOLS) > 0

    def test_default_allowed_tools_contains_safe_tools(self):
        """Test that DEFAULT_ALLOWED_TOOLS contains expected safe tools."""
        from src.constants import DEFAULT_ALLOWED_TOOLS

        # These tools should be in the default allowed set
        expected_tools = ["Read", "Glob", "Grep", "Bash", "Write", "Edit"]
        for tool in expected_tools:
            assert tool in DEFAULT_ALLOWED_TOOLS, f"Expected {tool} in DEFAULT_ALLOWED_TOOLS"

    def test_default_allowed_tools_excludes_dangerous(self):
        """Test that potentially dangerous tools are excluded by default."""
        from src.constants import DEFAULT_ALLOWED_TOOLS

        # These tools should NOT be in the default allowed set
        # (they're in DEFAULT_DISALLOWED_TOOLS)
        dangerous_tools = ["Task", "WebFetch", "WebSearch"]
        for tool in dangerous_tools:
            assert (
                tool not in DEFAULT_ALLOWED_TOOLS
            ), f"{tool} should not be in DEFAULT_ALLOWED_TOOLS"


class TestParseClaudeMessage:
    """Test parse_claude_message correctly handles multi-turn conversations."""

    def test_result_message_priority(self):
        """Test that ResultMessage.result is prioritized over AssistantMessage."""
        from src.claude_cli import ClaudeCodeCLI

        cli = ClaudeCodeCLI(cwd="/tmp")

        # Simulate multi-turn conversation messages
        messages = [
            # First assistant message (initial response)
            {
                "content": [type("TextBlock", (), {"text": "I'll list the files."})()],
            },
            # Tool use message (not text)
            {
                "content": [type("ToolUseBlock", (), {"name": "Bash", "input": {}})()],
            },
            # Final result message with full answer
            {
                "subtype": "success",
                "result": "The files are:\n1. file1.txt\n2. file2.txt\n3. file3.txt",
            },
        ]

        result = cli.parse_claude_message(messages)

        # Should return the ResultMessage.result, not the first AssistantMessage
        assert result == "The files are:\n1. file1.txt\n2. file2.txt\n3. file3.txt"

    def test_fallback_to_last_assistant_message(self):
        """Test fallback to last AssistantMessage when no ResultMessage."""
        from src.claude_cli import ClaudeCodeCLI

        cli = ClaudeCodeCLI(cwd="/tmp")

        # Simulate messages without ResultMessage
        messages = [
            {
                "content": [type("TextBlock", (), {"text": "First response"})()],
            },
            {
                "content": [type("TextBlock", (), {"text": "Second response"})()],
            },
        ]

        result = cli.parse_claude_message(messages)

        # Should return the LAST text, not the first
        assert result == "Second response"

    def test_handles_empty_messages(self):
        """Test handling of empty message list."""
        from src.claude_cli import ClaudeCodeCLI

        cli = ClaudeCodeCLI(cwd="/tmp")

        result = cli.parse_claude_message([])
        assert result is None

    def test_handles_dict_content_blocks(self):
        """Test handling of dict-based content blocks (old format)."""
        from src.claude_cli import ClaudeCodeCLI

        cli = ClaudeCodeCLI(cwd="/tmp")

        messages = [{"content": [{"type": "text", "text": "Hello world"}]}]

        result = cli.parse_claude_message(messages)
        assert result == "Hello world"


class TestClaudeCliPermissionMode:
    """Test that ClaudeCodeCLI passes permission_mode via the generic claude_options mechanism."""

    @pytest.fixture
    def cli_instance(self):
        """Create a CLI instance with mocked auth (no live SDK)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("src.auth.validate_claude_code_auth") as mock_validate:
                with patch("src.auth.auth_manager") as mock_auth:
                    mock_validate.return_value = (True, {"method": "anthropic"})
                    mock_auth.get_claude_code_env_vars.return_value = {}

                    from src.claude_cli import ClaudeCodeCLI

                    cli = ClaudeCodeCLI(cwd=temp_dir)
                    yield cli

    def test_run_completion_accepts_claude_options(self):
        """run_completion exposes a generic claude_options dict, not an explicit permission_mode param."""
        from src.claude_cli import ClaudeCodeCLI
        import inspect

        sig = inspect.signature(ClaudeCodeCLI.run_completion)

        assert "claude_options" in sig.parameters, (
            "run_completion should accept a generic claude_options dict"
        )

    @pytest.mark.asyncio
    async def test_permission_mode_flows_to_claude_agent_options(self, cli_instance):
        """permission_mode supplied via claude_options reaches ClaudeAgentOptions."""
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield {"type": "assistant"}

        with patch("src.claude_cli.query", mock_query):
            async for _ in cli_instance.run_completion(
                "Hello", claude_options={"permission_mode": "acceptEdits"}
            ):
                pass

        assert len(captured_options) == 1
        assert captured_options[0].permission_mode == "acceptEdits"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
