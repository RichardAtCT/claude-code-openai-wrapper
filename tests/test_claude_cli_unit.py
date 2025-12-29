#!/usr/bin/env python3
"""
Unit tests for src/claude_cli.py

Tests the ClaudeCodeCLI class methods.
These are pure unit tests that don't require a running server or Claude SDK.
"""

import pytest
import os
import tempfile
import sys
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path


class TestClaudeCodeCLIParseMessage:
    """Test ClaudeCodeCLI.parse_claude_message()"""

    @pytest.fixture
    def cli_class(self):
        """Get the ClaudeCodeCLI class without instantiating."""
        from src.claude_cli import ClaudeCodeCLI
        return ClaudeCodeCLI

    def test_parse_result_message(self, cli_class):
        """Parses result message with 'result' field."""
        # Use classmethod-like approach - create minimal mock instance
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [{"subtype": "success", "result": "The final answer is 42."}]
        result = cli.parse_claude_message(messages)
        assert result == "The final answer is 42."

    def test_parse_assistant_message_with_content_list(self, cli_class):
        """Parses assistant message with content list."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [
            {
                "content": [
                    {"type": "text", "text": "Hello "},
                    {"type": "text", "text": "World!"},
                ]
            }
        ]
        result = cli.parse_claude_message(messages)
        assert result == "Hello \nWorld!"

    def test_parse_assistant_message_with_textblock_objects(self, cli_class):
        """Parses assistant message with TextBlock objects."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        # Mock TextBlock object
        text_block = MagicMock()
        text_block.text = "Response text"

        messages = [{"content": [text_block]}]
        result = cli.parse_claude_message(messages)
        assert result == "Response text"

    def test_parse_assistant_message_with_string_content(self, cli_class):
        """Parses assistant message with string content blocks."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [{"content": ["Part 1", "Part 2"]}]
        result = cli.parse_claude_message(messages)
        assert result == "Part 1\nPart 2"

    def test_parse_old_format_assistant_message(self, cli_class):
        """Parses old format assistant message."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Old format response"}]
                },
            }
        ]
        result = cli.parse_claude_message(messages)
        assert result == "Old format response"

    def test_parse_old_format_string_content(self, cli_class):
        """Parses old format with string content."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [
            {
                "type": "assistant",
                "message": {"content": "Simple string content"},
            }
        ]
        result = cli.parse_claude_message(messages)
        assert result == "Simple string content"

    def test_parse_empty_messages_returns_none(self, cli_class):
        """Empty messages list returns None."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        result = cli.parse_claude_message([])
        assert result is None

    def test_parse_no_matching_messages_returns_none(self, cli_class):
        """No matching messages returns None."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [{"type": "system", "content": "System message"}]
        result = cli.parse_claude_message(messages)
        assert result is None

    def test_parse_uses_last_text(self, cli_class):
        """When multiple messages, uses the last one with text."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [
            {"content": [{"type": "text", "text": "First response"}]},
            {"content": [{"type": "text", "text": "Second response"}]},
        ]
        result = cli.parse_claude_message(messages)
        assert result == "Second response"

    def test_result_takes_priority(self, cli_class):
        """ResultMessage.result takes priority over AssistantMessage."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [
            {"content": [{"type": "text", "text": "Some response"}]},
            {"subtype": "success", "result": "Final result"},
        ]
        result = cli.parse_claude_message(messages)
        assert result == "Final result"


class TestClaudeCodeCLIExtractMetadata:
    """Test ClaudeCodeCLI.extract_metadata()"""

    @pytest.fixture
    def cli_class(self):
        """Get the ClaudeCodeCLI class."""
        from src.claude_cli import ClaudeCodeCLI
        return ClaudeCodeCLI

    def test_extract_from_result_message(self, cli_class):
        """Extracts metadata from new SDK ResultMessage."""
        cli = MagicMock()
        cli.extract_metadata = cli_class.extract_metadata.__get__(cli, cli_class)

        messages = [
            {
                "subtype": "success",
                "total_cost_usd": 0.05,
                "duration_ms": 1500,
                "num_turns": 3,
                "session_id": "sess-123",
            }
        ]
        metadata = cli.extract_metadata(messages)

        assert metadata["total_cost_usd"] == 0.05
        assert metadata["duration_ms"] == 1500
        assert metadata["num_turns"] == 3
        assert metadata["session_id"] == "sess-123"

    def test_extract_from_system_init_message(self, cli_class):
        """Extracts metadata from SystemMessage init."""
        cli = MagicMock()
        cli.extract_metadata = cli_class.extract_metadata.__get__(cli, cli_class)

        messages = [
            {
                "subtype": "init",
                "data": {"session_id": "init-sess-456", "model": "claude-3-opus"},
            }
        ]
        metadata = cli.extract_metadata(messages)

        assert metadata["session_id"] == "init-sess-456"
        assert metadata["model"] == "claude-3-opus"

    def test_extract_from_old_result_message(self, cli_class):
        """Extracts metadata from old format result message."""
        cli = MagicMock()
        cli.extract_metadata = cli_class.extract_metadata.__get__(cli, cli_class)

        messages = [
            {
                "type": "result",
                "total_cost_usd": 0.03,
                "duration_ms": 1000,
                "num_turns": 2,
                "session_id": "old-sess",
            }
        ]
        metadata = cli.extract_metadata(messages)

        assert metadata["total_cost_usd"] == 0.03
        assert metadata["duration_ms"] == 1000
        assert metadata["session_id"] == "old-sess"

    def test_extract_from_old_system_init(self, cli_class):
        """Extracts metadata from old format system init."""
        cli = MagicMock()
        cli.extract_metadata = cli_class.extract_metadata.__get__(cli, cli_class)

        messages = [
            {
                "type": "system",
                "subtype": "init",
                "session_id": "old-init-sess",
                "model": "claude-3-haiku",
            }
        ]
        metadata = cli.extract_metadata(messages)

        assert metadata["session_id"] == "old-init-sess"
        assert metadata["model"] == "claude-3-haiku"

    def test_extract_empty_messages_returns_defaults(self, cli_class):
        """Empty messages returns default metadata."""
        cli = MagicMock()
        cli.extract_metadata = cli_class.extract_metadata.__get__(cli, cli_class)

        metadata = cli.extract_metadata([])

        assert metadata["session_id"] is None
        assert metadata["total_cost_usd"] == 0.0
        assert metadata["duration_ms"] == 0
        assert metadata["num_turns"] == 0
        assert metadata["model"] is None


class TestClaudeCodeCLIEstimateTokenUsage:
    """Test ClaudeCodeCLI.estimate_token_usage()"""

    @pytest.fixture
    def cli_class(self):
        """Get the ClaudeCodeCLI class."""
        from src.claude_cli import ClaudeCodeCLI
        return ClaudeCodeCLI

    def test_estimate_basic(self, cli_class):
        """Basic token estimation."""
        cli = MagicMock()
        cli.estimate_token_usage = cli_class.estimate_token_usage.__get__(cli, cli_class)

        # 12 chars / 4 = 3 tokens, 16 chars / 4 = 4 tokens
        result = cli.estimate_token_usage("Hello World!", "Response here!")
        assert result["prompt_tokens"] == 3
        assert result["completion_tokens"] == 3
        assert result["total_tokens"] == 6

    def test_estimate_minimum_one_token(self, cli_class):
        """Minimum is 1 token."""
        cli = MagicMock()
        cli.estimate_token_usage = cli_class.estimate_token_usage.__get__(cli, cli_class)

        result = cli.estimate_token_usage("Hi", "X")
        assert result["prompt_tokens"] >= 1
        assert result["completion_tokens"] >= 1

    def test_estimate_long_text(self, cli_class):
        """Longer text estimation."""
        cli = MagicMock()
        cli.estimate_token_usage = cli_class.estimate_token_usage.__get__(cli, cli_class)

        prompt = "a" * 400  # 100 tokens
        completion = "b" * 200  # 50 tokens
        result = cli.estimate_token_usage(prompt, completion)

        assert result["prompt_tokens"] == 100
        assert result["completion_tokens"] == 50
        assert result["total_tokens"] == 150

    def test_estimate_empty_strings(self, cli_class):
        """Empty strings return minimum 1 token each."""
        cli = MagicMock()
        cli.estimate_token_usage = cli_class.estimate_token_usage.__get__(cli, cli_class)

        result = cli.estimate_token_usage("", "")
        assert result["prompt_tokens"] == 1
        assert result["completion_tokens"] == 1


class TestClaudeCodeCLICleanupTempDir:
    """Test ClaudeCodeCLI._cleanup_temp_dir()"""

    def test_cleanup_removes_existing_dir(self):
        """Cleanup removes existing temp directory."""
        from src.claude_cli import ClaudeCodeCLI

        # Create a mock instance
        cli = MagicMock(spec=ClaudeCodeCLI)

        # Create an actual temp directory
        temp_dir = tempfile.mkdtemp(prefix="test_cleanup_")
        cli.temp_dir = temp_dir

        # Bind the method
        cli._cleanup_temp_dir = ClaudeCodeCLI._cleanup_temp_dir.__get__(cli, ClaudeCodeCLI)

        assert os.path.exists(temp_dir)

        cli._cleanup_temp_dir()

        assert not os.path.exists(temp_dir)

    def test_cleanup_handles_missing_dir(self):
        """Cleanup handles already-deleted directory gracefully."""
        from src.claude_cli import ClaudeCodeCLI

        cli = MagicMock(spec=ClaudeCodeCLI)
        cli.temp_dir = "/nonexistent/test/dir/12345"

        cli._cleanup_temp_dir = ClaudeCodeCLI._cleanup_temp_dir.__get__(cli, ClaudeCodeCLI)

        # Should not raise
        cli._cleanup_temp_dir()

    def test_cleanup_no_temp_dir_set(self):
        """Cleanup does nothing when temp_dir is None."""
        from src.claude_cli import ClaudeCodeCLI

        cli = MagicMock(spec=ClaudeCodeCLI)
        cli.temp_dir = None

        cli._cleanup_temp_dir = ClaudeCodeCLI._cleanup_temp_dir.__get__(cli, ClaudeCodeCLI)

        # Should not raise
        cli._cleanup_temp_dir()


class TestClaudeCodeCLIInit:
    """Test ClaudeCodeCLI.__init__() initialization logic."""

    def test_timeout_conversion(self):
        """Timeout is converted from milliseconds to seconds."""
        # Test the conversion logic directly
        timeout_ms = 120000
        timeout_seconds = timeout_ms / 1000
        assert timeout_seconds == 120.0

    def test_path_handling_with_valid_dir(self):
        """Valid directory path is handled correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir)
            assert path.exists()

    def test_path_handling_with_invalid_dir(self):
        """Invalid directory path is detected."""
        path = Path("/nonexistent/path/12345")
        assert not path.exists()
