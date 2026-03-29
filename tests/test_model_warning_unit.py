#!/usr/bin/env python3
"""
Unit and integration tests for the model warning header (FR-9.1).

Tests that:
- ParameterValidator.is_model_recognized() correctly identifies known vs unknown models
- The /v1/chat/completions endpoint adds X-Claude-Model-Warning: unrecognized
  when the requested model is not in the known Claude model list
- The header is NOT added when the model is recognized

These tests are in RED phase. The integration tests for the warning header will
FAIL against current code because main.py does not yet set the header.
"""

import os
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.parameter_validator import ParameterValidator


# ---------------------------------------------------------------------------
# Unit tests — ParameterValidator.is_model_recognized()
# These verify the helper logic that the endpoint should use.
# ---------------------------------------------------------------------------


class TestIsModelRecognized:
    """Test ParameterValidator.is_model_recognized() returns correct bool."""

    def test_is_model_recognized_known_sonnet_46_returns_true(self):
        """claude-sonnet-4-6 is in SUPPORTED_MODELS and must return True."""
        assert ParameterValidator.is_model_recognized("claude-sonnet-4-6") is True

    def test_is_model_recognized_known_opus_46_returns_true(self):
        """claude-opus-4-6 is in SUPPORTED_MODELS and must return True."""
        assert ParameterValidator.is_model_recognized("claude-opus-4-6") is True

    def test_is_model_recognized_known_sonnet_45_dated_returns_true(self):
        """claude-sonnet-4-5-20250929 is in SUPPORTED_MODELS and must return True."""
        assert ParameterValidator.is_model_recognized("claude-sonnet-4-5-20250929") is True

    def test_is_model_recognized_openai_model_returns_false(self):
        """gpt-4-turbo is not a Claude model and must return False."""
        assert ParameterValidator.is_model_recognized("gpt-4-turbo") is False

    def test_is_model_recognized_arbitrary_unknown_model_returns_false(self):
        """A made-up model name is not in SUPPORTED_MODELS and must return False."""
        assert ParameterValidator.is_model_recognized("nonexistent-model-xyz") is False

    def test_is_model_recognized_empty_string_returns_false(self):
        """Empty string is not in SUPPORTED_MODELS and must return False."""
        assert ParameterValidator.is_model_recognized("") is False

    def test_is_model_recognized_all_claude_models_return_true(self):
        """Every model in SUPPORTED_MODELS must be recognized."""
        for model in ParameterValidator.SUPPORTED_MODELS:
            assert (
                ParameterValidator.is_model_recognized(model) is True
            ), f"Expected {model!r} to be recognized but it was not"


# ---------------------------------------------------------------------------
# Integration tests — /v1/chat/completions endpoint header behavior
#
# These tests use FastAPI's TestClient (httpx-based) and mock out the Claude
# Agent SDK so no real API calls are made.
#
# RED: The tests that check for X-Claude-Model-Warning will FAIL until
# main.py is updated to set the header for unrecognized models.
# ---------------------------------------------------------------------------


def _make_async_generator(chunks):
    """Helper: create an async generator that yields the given chunks."""

    async def _gen(*args, **kwargs):
        for chunk in chunks:
            yield chunk

    return _gen


def _mock_run_completion_chunks():
    """Return a list of Claude SDK message dicts that represent a valid response."""
    return [
        {
            "type": "assistant",
            "subtype": "success",
            "result": "Hello from mocked Claude",
            "total_cost_usd": 0.0,
            "duration_ms": 100,
            "num_turns": 1,
            "session_id": "mock-session-id",
        }
    ]


@pytest.fixture(scope="module")
def test_client():
    """
    Create a TestClient for the FastAPI app with all external calls mocked.

    Patches applied at module import time:
    - ClaudeCodeCLI.__init__ — prevents real subprocess/auth setup
    - validate_claude_code_auth — returns (True, {}) so auth passes
    - claude_cli.run_completion — returns a mocked async generator
    - session_manager.start_cleanup_task — prevents background task noise
    """
    with (
        patch("src.claude_cli.ClaudeCodeCLI.__init__", return_value=None),
        patch("src.auth.validate_claude_code_auth", return_value=(True, {"method": "mock"})),
    ):
        # Import app AFTER patching ClaudeCodeCLI so the module-level
        # `claude_cli = ClaudeCodeCLI(...)` call in main.py succeeds.
        from src.main import app

        # Patch the module-level claude_cli instance used by the endpoint.
        mock_cli = MagicMock()
        mock_cli.run_completion = _make_async_generator(_mock_run_completion_chunks())
        mock_cli.parse_claude_message = MagicMock(return_value="Hello from mocked Claude")
        mock_cli.extract_metadata = MagicMock(return_value={})
        mock_cli.estimate_token_usage = MagicMock(
            return_value={"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}
        )

        import src.main as main_module
        import src.session_manager as sm_module

        original_cli = main_module.claude_cli
        original_start = sm_module.session_manager.start_cleanup_task

        main_module.claude_cli = mock_cli
        sm_module.session_manager.start_cleanup_task = MagicMock()

        from fastapi.testclient import TestClient

        with TestClient(app, raise_server_exceptions=True) as client:
            yield client

        # Restore originals (best-effort; module is cached anyway)
        main_module.claude_cli = original_cli
        sm_module.session_manager.start_cleanup_task = original_start


def _chat_request_body(model: str) -> dict:
    """Return a minimal /v1/chat/completions request body for the given model."""
    return {
        "model": model,
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": False,
    }


def _auth_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


class TestModelWarningHeaderEndpoint:
    """
    Integration tests for the X-Claude-Model-Warning response header.

    FR-9.1: When a chat completion request uses an unrecognized model the
    response MUST include the header  X-Claude-Model-Warning: unrecognized.
    When a known model is used the header MUST NOT be present.
    """

    def test_unknown_model_response_has_warning_header(self, test_client):
        """
        RED: Request with an unrecognized model returns X-Claude-Model-Warning: unrecognized.

        This test FAILS against current code because main.py does not set the header.
        It will pass once main.py is updated (GREEN phase).
        """
        api_key = "test-key-for-warning-header"

        with (
            patch.dict(os.environ, {"API_KEY": api_key}),
            patch("src.main.validate_claude_code_auth", return_value=(True, {"method": "mock"})),
            patch("src.main.claude_cli") as mock_cli_patch,
        ):
            mock_cli_patch.run_completion = _make_async_generator(_mock_run_completion_chunks())
            mock_cli_patch.parse_claude_message = MagicMock(return_value="Hello from mocked Claude")

            response = test_client.post(
                "/v1/chat/completions",
                json=_chat_request_body("gpt-4-turbo"),
                headers=_auth_headers(api_key),
            )

        assert response.status_code == 200
        assert (
            "x-claude-model-warning" in response.headers
        ), "Expected X-Claude-Model-Warning header in response for unrecognized model 'gpt-4-turbo'"
        assert (
            response.headers["x-claude-model-warning"] == "unrecognized"
        ), "Expected X-Claude-Model-Warning header value to be 'unrecognized'"

    def test_known_model_response_has_no_warning_header(self, test_client):
        """
        When a known Claude model is used, no X-Claude-Model-Warning header is present.

        This test documents the expected ABSENCE of the header for recognized models.
        It may pass or fail depending on implementation details; we include it to
        ensure the implementation does not spam the header on every response.
        """
        api_key = "test-key-for-warning-header"

        with (
            patch.dict(os.environ, {"API_KEY": api_key}),
            patch("src.main.validate_claude_code_auth", return_value=(True, {"method": "mock"})),
            patch("src.main.claude_cli") as mock_cli_patch,
        ):
            mock_cli_patch.run_completion = _make_async_generator(_mock_run_completion_chunks())
            mock_cli_patch.parse_claude_message = MagicMock(return_value="Hello from mocked Claude")

            response = test_client.post(
                "/v1/chat/completions",
                json=_chat_request_body("claude-sonnet-4-6"),
                headers=_auth_headers(api_key),
            )

        assert response.status_code == 200
        assert (
            "x-claude-model-warning" not in response.headers
        ), "Expected no X-Claude-Model-Warning header for recognized model 'claude-sonnet-4-6'"

    def test_nonexistent_model_string_triggers_warning_header(self, test_client):
        """
        RED: A completely made-up model name also triggers the warning header.

        This test FAILS against current code.
        """
        api_key = "test-key-for-warning-header"

        with (
            patch.dict(os.environ, {"API_KEY": api_key}),
            patch("src.main.validate_claude_code_auth", return_value=(True, {"method": "mock"})),
            patch("src.main.claude_cli") as mock_cli_patch,
        ):
            mock_cli_patch.run_completion = _make_async_generator(_mock_run_completion_chunks())
            mock_cli_patch.parse_claude_message = MagicMock(return_value="Hello from mocked Claude")

            response = test_client.post(
                "/v1/chat/completions",
                json=_chat_request_body("nonexistent-model-99999"),
                headers=_auth_headers(api_key),
            )

        assert response.status_code == 200
        assert (
            "x-claude-model-warning" in response.headers
        ), "Expected X-Claude-Model-Warning header for completely unknown model"
        assert response.headers["x-claude-model-warning"] == "unrecognized"
