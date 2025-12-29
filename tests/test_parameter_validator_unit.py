#!/usr/bin/env python3
"""
Unit tests for src/parameter_validator.py

Tests the ParameterValidator and CompatibilityReporter classes.
These are pure unit tests that don't require a running server.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.parameter_validator import ParameterValidator, CompatibilityReporter
from src.models import Message, ChatCompletionRequest


class TestParameterValidatorValidateModel:
    """Test ParameterValidator.validate_model()"""

    def test_valid_model_returns_true(self):
        """Known supported model returns True."""
        result = ParameterValidator.validate_model("claude-sonnet-4-5-20250929")
        assert result is True

    def test_unknown_model_returns_true_with_warning(self):
        """Unknown model returns True (graceful degradation) with warning logged."""
        with patch("src.parameter_validator.logger") as mock_logger:
            result = ParameterValidator.validate_model("unknown-model-xyz")
            assert result is True
            mock_logger.warning.assert_called_once()
            assert "unknown-model-xyz" in str(mock_logger.warning.call_args)

    def test_all_known_models_valid(self):
        """All models in SUPPORTED_MODELS are valid."""
        for model in ParameterValidator.SUPPORTED_MODELS:
            assert ParameterValidator.validate_model(model) is True


class TestParameterValidatorValidatePermissionMode:
    """Test ParameterValidator.validate_permission_mode()"""

    def test_valid_permission_mode_default(self):
        """'default' permission mode is valid."""
        assert ParameterValidator.validate_permission_mode("default") is True

    def test_valid_permission_mode_accept_edits(self):
        """'acceptEdits' permission mode is valid."""
        assert ParameterValidator.validate_permission_mode("acceptEdits") is True

    def test_valid_permission_mode_bypass(self):
        """'bypassPermissions' permission mode is valid."""
        assert ParameterValidator.validate_permission_mode("bypassPermissions") is True

    def test_invalid_permission_mode_returns_false(self):
        """Invalid permission mode returns False with error logged."""
        with patch("src.parameter_validator.logger") as mock_logger:
            result = ParameterValidator.validate_permission_mode("invalidMode")
            assert result is False
            mock_logger.error.assert_called_once()
            assert "invalidMode" in str(mock_logger.error.call_args)


class TestParameterValidatorValidateTools:
    """Test ParameterValidator.validate_tools()"""

    def test_valid_tools_list(self):
        """List of valid tool names returns True."""
        tools = ["Read", "Write", "Bash"]
        assert ParameterValidator.validate_tools(tools) is True

    def test_empty_string_tool_returns_false(self):
        """Tool list with empty string returns False."""
        with patch("src.parameter_validator.logger") as mock_logger:
            result = ParameterValidator.validate_tools(["Read", "", "Bash"])
            assert result is False
            mock_logger.error.assert_called_once()

    def test_whitespace_only_tool_returns_false(self):
        """Tool list with whitespace-only string returns False."""
        with patch("src.parameter_validator.logger") as mock_logger:
            result = ParameterValidator.validate_tools(["Read", "   ", "Bash"])
            assert result is False
            mock_logger.error.assert_called_once()

    def test_non_string_tool_returns_false(self):
        """Tool list with non-string element returns False."""
        with patch("src.parameter_validator.logger") as mock_logger:
            result = ParameterValidator.validate_tools(["Read", 123, "Bash"])
            assert result is False
            mock_logger.error.assert_called_once()

    def test_empty_list_returns_true(self):
        """Empty tool list returns True (no invalid tools)."""
        assert ParameterValidator.validate_tools([]) is True


class TestParameterValidatorCreateEnhancedOptions:
    """Test ParameterValidator.create_enhanced_options()"""

    @pytest.fixture
    def basic_request(self):
        """Create a basic chat completion request for testing."""
        return ChatCompletionRequest(
            model="claude-sonnet-4-5-20250929",
            messages=[Message(role="user", content="Hello")],
        )

    def test_basic_options_from_request(self, basic_request):
        """Basic request options are extracted correctly."""
        options = ParameterValidator.create_enhanced_options(basic_request)
        assert "model" in options
        assert options["model"] == "claude-sonnet-4-5-20250929"

    def test_max_turns_added_when_provided(self, basic_request):
        """max_turns is added to options when provided."""
        options = ParameterValidator.create_enhanced_options(basic_request, max_turns=5)
        assert options.get("max_turns") == 5

    def test_max_turns_warning_for_out_of_range(self, basic_request):
        """Warning logged when max_turns is out of recommended range."""
        with patch("src.parameter_validator.logger") as mock_logger:
            # Test value below range
            ParameterValidator.create_enhanced_options(basic_request, max_turns=0)
            mock_logger.warning.assert_called()

            mock_logger.reset_mock()

            # Test value above range
            ParameterValidator.create_enhanced_options(basic_request, max_turns=150)
            mock_logger.warning.assert_called()

    def test_allowed_tools_added_when_valid(self, basic_request):
        """allowed_tools is added when valid tools provided."""
        tools = ["Read", "Write"]
        options = ParameterValidator.create_enhanced_options(basic_request, allowed_tools=tools)
        assert options.get("allowed_tools") == tools

    def test_disallowed_tools_added_when_valid(self, basic_request):
        """disallowed_tools is added when valid tools provided."""
        tools = ["Bash", "Edit"]
        options = ParameterValidator.create_enhanced_options(basic_request, disallowed_tools=tools)
        assert options.get("disallowed_tools") == tools

    def test_permission_mode_added_when_valid(self, basic_request):
        """permission_mode is added when valid mode provided."""
        options = ParameterValidator.create_enhanced_options(
            basic_request, permission_mode="acceptEdits"
        )
        assert options.get("permission_mode") == "acceptEdits"

    def test_permission_mode_not_added_when_invalid(self, basic_request):
        """permission_mode is not added when invalid mode provided."""
        options = ParameterValidator.create_enhanced_options(
            basic_request, permission_mode="invalidMode"
        )
        assert "permission_mode" not in options

    def test_max_thinking_tokens_added(self, basic_request):
        """max_thinking_tokens is added when provided."""
        options = ParameterValidator.create_enhanced_options(
            basic_request, max_thinking_tokens=5000
        )
        assert options.get("max_thinking_tokens") == 5000

    def test_max_thinking_tokens_warning_for_out_of_range(self, basic_request):
        """Warning logged when max_thinking_tokens is out of range."""
        with patch("src.parameter_validator.logger") as mock_logger:
            # Test negative value
            ParameterValidator.create_enhanced_options(basic_request, max_thinking_tokens=-100)
            mock_logger.warning.assert_called()

            mock_logger.reset_mock()

            # Test value above range
            ParameterValidator.create_enhanced_options(basic_request, max_thinking_tokens=60000)
            mock_logger.warning.assert_called()


class TestParameterValidatorExtractClaudeHeaders:
    """Test ParameterValidator.extract_claude_headers()"""

    def test_empty_headers_returns_empty_dict(self):
        """Empty headers dict returns empty options dict."""
        result = ParameterValidator.extract_claude_headers({})
        assert result == {}

    def test_extracts_max_turns(self):
        """X-Claude-Max-Turns header is extracted correctly."""
        headers = {"x-claude-max-turns": "10"}
        result = ParameterValidator.extract_claude_headers(headers)
        assert result.get("max_turns") == 10

    def test_invalid_max_turns_logs_warning(self):
        """Invalid X-Claude-Max-Turns logs warning and is ignored."""
        headers = {"x-claude-max-turns": "not-a-number"}
        with patch("src.parameter_validator.logger") as mock_logger:
            result = ParameterValidator.extract_claude_headers(headers)
            assert "max_turns" not in result
            mock_logger.warning.assert_called_once()

    def test_extracts_allowed_tools(self):
        """X-Claude-Allowed-Tools header is extracted correctly."""
        headers = {"x-claude-allowed-tools": "Read,Write,Bash"}
        result = ParameterValidator.extract_claude_headers(headers)
        assert result.get("allowed_tools") == ["Read", "Write", "Bash"]

    def test_allowed_tools_strips_whitespace(self):
        """Tool names have whitespace stripped."""
        headers = {"x-claude-allowed-tools": " Read , Write , Bash "}
        result = ParameterValidator.extract_claude_headers(headers)
        assert result.get("allowed_tools") == ["Read", "Write", "Bash"]

    def test_extracts_disallowed_tools(self):
        """X-Claude-Disallowed-Tools header is extracted correctly."""
        headers = {"x-claude-disallowed-tools": "Edit,Delete"}
        result = ParameterValidator.extract_claude_headers(headers)
        assert result.get("disallowed_tools") == ["Edit", "Delete"]

    def test_extracts_permission_mode(self):
        """X-Claude-Permission-Mode header is extracted correctly."""
        headers = {"x-claude-permission-mode": "bypassPermissions"}
        result = ParameterValidator.extract_claude_headers(headers)
        assert result.get("permission_mode") == "bypassPermissions"

    def test_extracts_max_thinking_tokens(self):
        """X-Claude-Max-Thinking-Tokens header is extracted correctly."""
        headers = {"x-claude-max-thinking-tokens": "5000"}
        result = ParameterValidator.extract_claude_headers(headers)
        assert result.get("max_thinking_tokens") == 5000

    def test_invalid_max_thinking_tokens_logs_warning(self):
        """Invalid X-Claude-Max-Thinking-Tokens logs warning."""
        headers = {"x-claude-max-thinking-tokens": "invalid"}
        with patch("src.parameter_validator.logger") as mock_logger:
            result = ParameterValidator.extract_claude_headers(headers)
            assert "max_thinking_tokens" not in result
            mock_logger.warning.assert_called_once()

    def test_extracts_multiple_headers(self):
        """Multiple Claude headers are all extracted."""
        headers = {
            "x-claude-max-turns": "5",
            "x-claude-allowed-tools": "Read,Write",
            "x-claude-permission-mode": "default",
            "x-claude-max-thinking-tokens": "3000",
        }
        result = ParameterValidator.extract_claude_headers(headers)
        assert result.get("max_turns") == 5
        assert result.get("allowed_tools") == ["Read", "Write"]
        assert result.get("permission_mode") == "default"
        assert result.get("max_thinking_tokens") == 3000


class TestCompatibilityReporter:
    """Test CompatibilityReporter.generate_compatibility_report()"""

    @pytest.fixture
    def minimal_request(self):
        """Request with minimal parameters."""
        return ChatCompletionRequest(
            model="claude-sonnet-4-5-20250929",
            messages=[Message(role="user", content="Hello")],
        )

    def test_supported_parameters_identified(self, minimal_request):
        """Model and messages are identified as supported."""
        report = CompatibilityReporter.generate_compatibility_report(minimal_request)
        assert "model" in report["supported_parameters"]
        assert "messages" in report["supported_parameters"]

    def test_stream_identified_as_supported(self):
        """Stream parameter is identified as supported."""
        request = ChatCompletionRequest(
            model="claude-sonnet-4-5-20250929",
            messages=[Message(role="user", content="Hello")],
            stream=True,
        )
        report = CompatibilityReporter.generate_compatibility_report(request)
        assert "stream" in report["supported_parameters"]

    def test_user_identified_as_supported(self):
        """User parameter is identified as supported (for logging)."""
        request = ChatCompletionRequest(
            model="claude-sonnet-4-5-20250929",
            messages=[Message(role="user", content="Hello")],
            user="test_user",
        )
        report = CompatibilityReporter.generate_compatibility_report(request)
        assert "user (for logging)" in report["supported_parameters"]

    def test_temperature_unsupported_when_not_default(self):
        """Non-default temperature is flagged as unsupported."""
        request = ChatCompletionRequest(
            model="claude-sonnet-4-5-20250929",
            messages=[Message(role="user", content="Hello")],
            temperature=0.8,
        )
        report = CompatibilityReporter.generate_compatibility_report(request)
        assert "temperature" in report["unsupported_parameters"]
        assert len(report["suggestions"]) > 0

    def test_top_p_unsupported_when_not_default(self):
        """Non-default top_p is flagged as unsupported."""
        request = ChatCompletionRequest(
            model="claude-sonnet-4-5-20250929",
            messages=[Message(role="user", content="Hello")],
            top_p=0.9,
        )
        report = CompatibilityReporter.generate_compatibility_report(request)
        assert "top_p" in report["unsupported_parameters"]

    def test_max_tokens_unsupported(self):
        """max_tokens is flagged as unsupported."""
        request = ChatCompletionRequest(
            model="claude-sonnet-4-5-20250929",
            messages=[Message(role="user", content="Hello")],
            max_tokens=500,
        )
        report = CompatibilityReporter.generate_compatibility_report(request)
        assert "max_tokens" in report["unsupported_parameters"]

    def test_stop_sequences_unsupported(self):
        """stop sequences are flagged as unsupported."""
        request = ChatCompletionRequest(
            model="claude-sonnet-4-5-20250929",
            messages=[Message(role="user", content="Hello")],
            stop=["END"],
        )
        report = CompatibilityReporter.generate_compatibility_report(request)
        assert "stop" in report["unsupported_parameters"]

    def test_penalties_unsupported(self):
        """presence_penalty and frequency_penalty are flagged as unsupported."""
        request = ChatCompletionRequest(
            model="claude-sonnet-4-5-20250929",
            messages=[Message(role="user", content="Hello")],
            presence_penalty=0.5,
            frequency_penalty=0.5,
        )
        report = CompatibilityReporter.generate_compatibility_report(request)
        assert "presence_penalty" in report["unsupported_parameters"]
        assert "frequency_penalty" in report["unsupported_parameters"]

    def test_logit_bias_unsupported(self):
        """logit_bias is flagged as unsupported."""
        request = ChatCompletionRequest(
            model="claude-sonnet-4-5-20250929",
            messages=[Message(role="user", content="Hello")],
            logit_bias={"hello": 2.0},
        )
        report = CompatibilityReporter.generate_compatibility_report(request)
        assert "logit_bias" in report["unsupported_parameters"]

    def test_report_has_all_sections(self, minimal_request):
        """Report contains all expected sections."""
        report = CompatibilityReporter.generate_compatibility_report(minimal_request)
        assert "supported_parameters" in report
        assert "unsupported_parameters" in report
        assert "warnings" in report
        assert "suggestions" in report

    def test_minimal_request_has_no_unsupported(self, minimal_request):
        """Minimal request with defaults has no unsupported parameters."""
        report = CompatibilityReporter.generate_compatibility_report(minimal_request)
        assert len(report["unsupported_parameters"]) == 0
