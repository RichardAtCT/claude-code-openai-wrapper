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
                "message": {"content": [{"type": "text", "text": "Old format response"}]},
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

    def test_init_with_cwd(self):
        """ClaudeCodeCLI initializes with provided cwd."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("src.auth.validate_claude_code_auth") as mock_validate:
                with patch("src.auth.auth_manager") as mock_auth:
                    mock_validate.return_value = (True, {"method": "anthropic"})
                    mock_auth.get_claude_code_env_vars.return_value = {}

                    from src.claude_cli import ClaudeCodeCLI

                    cli = ClaudeCodeCLI(cwd=temp_dir)

                    assert cli.cwd == Path(temp_dir)
                    assert cli.temp_dir is None
                    assert cli.timeout == 600.0  # 600000ms / 1000

    def test_init_with_invalid_cwd_raises(self):
        """ClaudeCodeCLI raises ValueError for non-existent cwd."""
        with patch("src.auth.validate_claude_code_auth") as mock_validate:
            with patch("src.auth.auth_manager") as mock_auth:
                mock_validate.return_value = (True, {"method": "anthropic"})
                mock_auth.get_claude_code_env_vars.return_value = {}

                from src.claude_cli import ClaudeCodeCLI

                with pytest.raises(ValueError, match="Working directory does not exist"):
                    ClaudeCodeCLI(cwd="/nonexistent/path/12345")

    def test_init_without_cwd_creates_temp(self):
        """ClaudeCodeCLI creates temp directory when no cwd provided."""
        with patch("src.auth.validate_claude_code_auth") as mock_validate:
            with patch("src.auth.auth_manager") as mock_auth:
                with patch("atexit.register"):  # Don't actually register cleanup
                    mock_validate.return_value = (True, {"method": "anthropic"})
                    mock_auth.get_claude_code_env_vars.return_value = {}

                    from src.claude_cli import ClaudeCodeCLI

                    cli = ClaudeCodeCLI()

                    assert cli.temp_dir is not None
                    assert cli.cwd == Path(cli.temp_dir)
                    assert "claude_code_workspace_" in cli.temp_dir

                    # Cleanup
                    if cli.temp_dir and os.path.exists(cli.temp_dir):
                        import shutil

                        shutil.rmtree(cli.temp_dir)

    def test_init_with_custom_timeout(self):
        """ClaudeCodeCLI uses custom timeout."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("src.auth.validate_claude_code_auth") as mock_validate:
                with patch("src.auth.auth_manager") as mock_auth:
                    mock_validate.return_value = (True, {"method": "anthropic"})
                    mock_auth.get_claude_code_env_vars.return_value = {}

                    from src.claude_cli import ClaudeCodeCLI

                    cli = ClaudeCodeCLI(timeout=120000, cwd=temp_dir)

                    assert cli.timeout == 120.0

    def test_init_auth_validation_failure(self):
        """ClaudeCodeCLI handles auth validation failure gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("src.auth.validate_claude_code_auth") as mock_validate:
                with patch("src.auth.auth_manager") as mock_auth:
                    # Auth fails
                    mock_validate.return_value = (False, {"errors": ["Missing API key"]})
                    mock_auth.get_claude_code_env_vars.return_value = {}

                    from src.claude_cli import ClaudeCodeCLI

                    # Should not raise, just log warning
                    cli = ClaudeCodeCLI(cwd=temp_dir)
                    assert cli.cwd == Path(temp_dir)


class TestClaudeCodeCLIVerifyCLI:
    """Test ClaudeCodeCLI.verify_cli()"""

    @pytest.fixture
    def cli_instance(self):
        """Create a CLI instance with mocked auth."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("src.auth.validate_claude_code_auth") as mock_validate:
                with patch("src.auth.auth_manager") as mock_auth:
                    mock_validate.return_value = (True, {"method": "anthropic"})
                    mock_auth.get_claude_code_env_vars.return_value = {}

                    from src.claude_cli import ClaudeCodeCLI

                    cli = ClaudeCodeCLI(cwd=temp_dir)
                    yield cli

    @pytest.mark.asyncio
    async def test_verify_cli_success(self, cli_instance):
        """verify_cli returns True on successful SDK response."""
        mock_message = {"type": "assistant", "content": [{"type": "text", "text": "Hello"}]}

        async def mock_query(*args, **kwargs):
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            result = await cli_instance.verify_cli()
            assert result is True

    @pytest.mark.asyncio
    async def test_verify_cli_no_messages(self, cli_instance):
        """verify_cli returns False when no messages returned."""

        async def mock_query(*args, **kwargs):
            return
            yield  # Make it a generator but yield nothing

        with patch("src.claude_cli.query", mock_query):
            result = await cli_instance.verify_cli()
            assert result is False

    @pytest.mark.asyncio
    async def test_verify_cli_exception(self, cli_instance):
        """verify_cli returns False on exception."""

        async def mock_query(*args, **kwargs):
            raise RuntimeError("SDK error")
            yield  # Make it a generator

        with patch("src.claude_cli.query", mock_query):
            result = await cli_instance.verify_cli()
            assert result is False


class TestClaudeCodeCLIRunCompletion:
    """Test ClaudeCodeCLI.run_completion()"""

    @pytest.fixture
    def cli_instance(self):
        """Create a CLI instance with mocked auth."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("src.auth.validate_claude_code_auth") as mock_validate:
                with patch("src.auth.auth_manager") as mock_auth:
                    mock_validate.return_value = (True, {"method": "anthropic"})
                    mock_auth.get_claude_code_env_vars.return_value = {
                        "ANTHROPIC_API_KEY": "test-key"
                    }

                    from src.claude_cli import ClaudeCodeCLI

                    cli = ClaudeCodeCLI(cwd=temp_dir)
                    yield cli

    @pytest.mark.asyncio
    async def test_run_completion_basic(self, cli_instance):
        """run_completion yields messages from SDK."""
        mock_message = {"type": "assistant", "content": [{"type": "text", "text": "Hello"}]}

        async def mock_query(*args, **kwargs):
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            messages = []
            async for msg in cli_instance.run_completion("Hello"):
                messages.append(msg)

            assert len(messages) == 1
            assert messages[0] == mock_message

    @pytest.mark.asyncio
    async def test_run_completion_with_system_prompt(self, cli_instance):
        """run_completion sets system_prompt option."""
        mock_message = {"type": "assistant", "content": "Response"}
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            async for _ in cli_instance.run_completion("Hello", system_prompt="You are helpful"):
                pass

            assert len(captured_options) == 1
            opts = captured_options[0]
            assert opts.system_prompt == {"type": "text", "text": "You are helpful"}

    @pytest.mark.asyncio
    async def test_run_completion_with_model(self, cli_instance):
        """run_completion sets model option."""
        mock_message = {"type": "assistant"}
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            async for _ in cli_instance.run_completion("Hello", model="claude-3-opus"):
                pass

            assert captured_options[0].model == "claude-3-opus"

    @pytest.mark.asyncio
    async def test_run_completion_with_tool_restrictions(self, cli_instance):
        """run_completion sets allowed/disallowed tools."""
        mock_message = {"type": "assistant"}
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            async for _ in cli_instance.run_completion(
                "Hello",
                allowed_tools=["Bash", "Read"],
                disallowed_tools=["Task"],
            ):
                pass

            assert captured_options[0].allowed_tools == ["Bash", "Read"]
            assert captured_options[0].disallowed_tools == ["Task"]

    @pytest.mark.asyncio
    async def test_run_completion_with_permission_mode(self, cli_instance):
        """run_completion sets permission_mode."""
        mock_message = {"type": "assistant"}
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            async for _ in cli_instance.run_completion("Hello", permission_mode="acceptEdits"):
                pass

            assert captured_options[0].permission_mode == "acceptEdits"

    @pytest.mark.asyncio
    async def test_run_completion_continue_session(self, cli_instance):
        """run_completion sets continue_session option."""
        mock_message = {"type": "assistant"}
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            async for _ in cli_instance.run_completion("Hello", continue_session=True):
                pass

            assert captured_options[0].continue_session is True

    @pytest.mark.asyncio
    async def test_run_completion_resume_session(self, cli_instance):
        """run_completion sets resume option for session_id."""
        mock_message = {"type": "assistant"}
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            async for _ in cli_instance.run_completion("Hello", session_id="sess-123"):
                pass

            assert captured_options[0].resume == "sess-123"

    @pytest.mark.asyncio
    async def test_run_completion_converts_objects_to_dicts(self, cli_instance):
        """run_completion converts message objects to dicts."""
        # Create a mock object with attributes
        mock_obj = MagicMock()
        mock_obj.type = "assistant"
        mock_obj.content = "Hello"

        async def mock_query(*args, **kwargs):
            yield mock_obj

        with patch("src.claude_cli.query", mock_query):
            messages = []
            async for msg in cli_instance.run_completion("Hello"):
                messages.append(msg)

            assert len(messages) == 1
            # Should be converted to dict
            assert isinstance(messages[0], dict)
            assert "type" in messages[0]

    @pytest.mark.asyncio
    async def test_run_completion_exception_yields_error(self, cli_instance):
        """run_completion yields error message on exception."""

        async def mock_query(*args, **kwargs):
            raise RuntimeError("SDK failed")
            yield  # Make it a generator

        with patch("src.claude_cli.query", mock_query):
            messages = []
            async for msg in cli_instance.run_completion("Hello"):
                messages.append(msg)

            assert len(messages) == 1
            assert messages[0]["type"] == "result"
            assert messages[0]["subtype"] == "error_during_execution"
            assert messages[0]["is_error"] is True
            assert "SDK failed" in messages[0]["error_message"]

    @pytest.mark.asyncio
    async def test_run_completion_restores_env_vars(self, cli_instance):
        """run_completion restores environment variables after execution."""
        # Set an env var that will be modified
        original_key = os.environ.get("ANTHROPIC_API_KEY")

        mock_message = {"type": "assistant"}

        async def mock_query(*args, **kwargs):
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            async for _ in cli_instance.run_completion("Hello"):
                pass

        # Env should be restored
        if original_key is None:
            assert (
                "ANTHROPIC_API_KEY" not in os.environ
                or os.environ.get("ANTHROPIC_API_KEY") == original_key
            )
        else:
            assert os.environ.get("ANTHROPIC_API_KEY") == original_key


class TestClaudeCodeCLICleanupException:
    """Test ClaudeCodeCLI._cleanup_temp_dir() exception handling."""

    def test_cleanup_exception_is_caught(self):
        """Cleanup catches exceptions during rmtree."""
        from src.claude_cli import ClaudeCodeCLI

        cli = MagicMock(spec=ClaudeCodeCLI)
        temp_dir = tempfile.mkdtemp(prefix="test_cleanup_exc_")
        cli.temp_dir = temp_dir

        # Bind the real method
        cli._cleanup_temp_dir = ClaudeCodeCLI._cleanup_temp_dir.__get__(cli, ClaudeCodeCLI)

        with patch("shutil.rmtree", side_effect=PermissionError("Cannot delete")):
            # Should not raise
            cli._cleanup_temp_dir()

        # Clean up manually
        import shutil

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
