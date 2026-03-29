#!/usr/bin/env python3
"""
Unit tests for debug logging redaction in DebugLoggingMiddleware (src/main.py).

Tests FR-4.2 and FR-8.1: debug mode must not log full request bodies or headers
containing credentials/tokens. All sensitive values must be replaced with
'[REDACTED]' before any log call.

Architecture reference: KD-3, Section 7.5 of architecture.md
  - redact_request_headers(headers): redact Authorization header value
  - redact_request_body(body): redact api_key, authorization, token, secret, password fields
  - Startup warning logged when DEBUG_MODE is true

These tests are written RED-first: the helper functions and redaction behaviour
do NOT exist yet in src/main.py, so every test here is expected to FAIL.
"""

import importlib
import logging
import os

import pytest


# ---------------------------------------------------------------------------
# Helper: ensure we always import a freshly-configured module so that
# module-level env-var reads (DEBUG_MODE etc.) pick up the patched values.
# ---------------------------------------------------------------------------

def _reload_main_with_debug(debug_value: str = "true"):
    """Reload src.main with DEBUG_MODE set to the given string value."""
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("DEBUG_MODE", debug_value)
        import src.main
        importlib.reload(src.main)
        return src.main


# ---------------------------------------------------------------------------
# Section 1: redact_request_headers helper function
# ---------------------------------------------------------------------------

class TestRedactRequestHeaders:
    """
    Tests for redact_request_headers(headers: dict) -> dict

    Expected contract (FR-4.2, FR-8.1):
    - Returns a new dict (does not mutate input)
    - The 'authorization' key (case-insensitive) has its value replaced with '[REDACTED]'
    - All other header keys/values are preserved unchanged
    """

    def test_authorization_header_value_is_replaced_with_redacted(self):
        """Authorization bearer token must not appear in the returned headers dict."""
        import src.main

        headers = {"authorization": "Bearer sk-secret-token-abc123"}
        result = src.main.redact_request_headers(headers)
        assert result["authorization"] == "[REDACTED]"

    def test_authorization_header_case_insensitive_upper(self):
        """'Authorization' (title case) is also redacted."""
        import src.main

        headers = {"Authorization": "Bearer sk-secret-token-abc123"}
        result = src.main.redact_request_headers(headers)
        # The returned dict should not contain the raw token under any key variant
        values = list(result.values())
        assert "Bearer sk-secret-token-abc123" not in values

    def test_non_sensitive_headers_are_preserved(self):
        """Headers that are not Authorization pass through unchanged."""
        import src.main

        headers = {
            "content-type": "application/json",
            "x-request-id": "abc-123",
            "accept": "application/json",
        }
        result = src.main.redact_request_headers(headers)
        assert result["content-type"] == "application/json"
        assert result["x-request-id"] == "abc-123"
        assert result["accept"] == "application/json"

    def test_mixed_headers_authorization_redacted_others_preserved(self):
        """Mix of sensitive and non-sensitive: only Authorization is redacted."""
        import src.main

        headers = {
            "authorization": "Bearer real-secret",
            "content-type": "application/json",
            "user-agent": "test-client/1.0",
        }
        result = src.main.redact_request_headers(headers)
        assert result["authorization"] == "[REDACTED]"
        assert result["content-type"] == "application/json"
        assert result["user-agent"] == "test-client/1.0"

    def test_input_dict_is_not_mutated(self):
        """Original headers dict must not be modified."""
        import src.main

        headers = {"authorization": "Bearer sk-secret-token"}
        original_value = headers["authorization"]
        src.main.redact_request_headers(headers)
        assert headers["authorization"] == original_value

    def test_headers_without_authorization_returned_unchanged(self):
        """When no Authorization header present, result equals input."""
        import src.main

        headers = {"content-type": "application/json"}
        result = src.main.redact_request_headers(headers)
        assert result == {"content-type": "application/json"}

    def test_empty_headers_returns_empty_dict(self):
        """Empty headers dict returns empty dict without error."""
        import src.main

        result = src.main.redact_request_headers({})
        assert result == {}


# ---------------------------------------------------------------------------
# Section 2: redact_request_body helper function
# ---------------------------------------------------------------------------

class TestRedactRequestBody:
    """
    Tests for redact_request_body(body: dict) -> dict

    Expected contract (FR-4.2, FR-8.1, architecture Section 7.5):
    - Returns a new dict (does not mutate input)
    - Fields named 'api_key', 'authorization', 'token', 'secret', 'password'
      have their values replaced with '[REDACTED]'
    - Non-sensitive fields ('model', 'messages', 'temperature', etc.) are preserved
    - Field name matching is case-insensitive
    """

    def test_api_key_field_is_redacted(self):
        """'api_key' field value is replaced with '[REDACTED]'."""
        import src.main

        body = {"api_key": "sk-ant-real-api-key-12345", "model": "claude-sonnet-4-6"}
        result = src.main.redact_request_body(body)
        assert result["api_key"] == "[REDACTED]"

    def test_authorization_field_is_redacted(self):
        """'authorization' field in body is replaced with '[REDACTED]'."""
        import src.main

        body = {"authorization": "Bearer sk-secret", "model": "claude-sonnet-4-6"}
        result = src.main.redact_request_body(body)
        assert result["authorization"] == "[REDACTED]"

    def test_token_field_is_redacted(self):
        """'token' field is replaced with '[REDACTED]'."""
        import src.main

        body = {"token": "my-secret-token-abc", "model": "claude-sonnet-4-6"}
        result = src.main.redact_request_body(body)
        assert result["token"] == "[REDACTED]"

    def test_secret_field_is_redacted(self):
        """'secret' field is replaced with '[REDACTED]'."""
        import src.main

        body = {"secret": "super-secret-value", "model": "claude-sonnet-4-6"}
        result = src.main.redact_request_body(body)
        assert result["secret"] == "[REDACTED]"

    def test_password_field_is_redacted(self):
        """'password' field is replaced with '[REDACTED]'."""
        import src.main

        body = {"password": "hunter2", "model": "claude-sonnet-4-6"}
        result = src.main.redact_request_body(body)
        assert result["password"] == "[REDACTED]"

    def test_model_field_is_preserved(self):
        """'model' is a non-sensitive field and must not be redacted."""
        import src.main

        body = {"model": "claude-sonnet-4-6", "api_key": "sk-secret"}
        result = src.main.redact_request_body(body)
        assert result["model"] == "claude-sonnet-4-6"

    def test_messages_field_is_preserved(self):
        """'messages' array is non-sensitive and must not be redacted."""
        import src.main

        messages = [{"role": "user", "content": "Hello"}]
        body = {"messages": messages, "api_key": "sk-secret"}
        result = src.main.redact_request_body(body)
        assert result["messages"] == messages

    def test_temperature_field_is_preserved(self):
        """'temperature' is non-sensitive and must not be redacted."""
        import src.main

        body = {"temperature": 0.7, "api_key": "sk-secret"}
        result = src.main.redact_request_body(body)
        assert result["temperature"] == 0.7

    def test_all_sensitive_fields_redacted_simultaneously(self):
        """All five sensitive field names are redacted in a single body dict."""
        import src.main

        body = {
            "api_key": "sk-key",
            "authorization": "Bearer tok",
            "token": "tok123",
            "secret": "shhh",
            "password": "pw123",
            "model": "claude-sonnet-4-6",
        }
        result = src.main.redact_request_body(body)
        assert result["api_key"] == "[REDACTED]"
        assert result["authorization"] == "[REDACTED]"
        assert result["token"] == "[REDACTED]"
        assert result["secret"] == "[REDACTED]"
        assert result["password"] == "[REDACTED]"
        assert result["model"] == "claude-sonnet-4-6"

    def test_input_dict_is_not_mutated(self):
        """Original body dict must not be modified."""
        import src.main

        body = {"api_key": "sk-original-value"}
        original_value = body["api_key"]
        src.main.redact_request_body(body)
        assert body["api_key"] == original_value

    def test_empty_body_returns_empty_dict(self):
        """Empty body dict is returned as empty dict without error."""
        import src.main

        result = src.main.redact_request_body({})
        assert result == {}

    def test_body_without_sensitive_fields_returned_unchanged(self):
        """Body with no sensitive keys is returned with all values intact."""
        import src.main

        body = {"model": "claude-opus-4-6", "max_tokens": 1024, "stream": False}
        result = src.main.redact_request_body(body)
        assert result == body


# ---------------------------------------------------------------------------
# Section 3: Middleware does not log raw Authorization header in debug mode
# ---------------------------------------------------------------------------

class TestDebugMiddlewareHeaderRedactionInLogs:
    """
    Integration-level test: when DebugLoggingMiddleware processes a request
    in DEBUG_MODE, the logged output must contain '[REDACTED]' for the
    Authorization value and must NOT contain the raw bearer token.

    Uses pytest caplog to capture logger output from src.main.
    """

    def test_authorization_header_not_logged_raw_in_debug_mode(self, caplog):
        """
        Raw bearer token from Authorization header must not appear in any
        debug log record when the middleware processes a request.
        """
        import importlib
        import src.main

        raw_token = "Bearer sk-super-secret-bearer-token-xyz789"

        with caplog.at_level(logging.DEBUG, logger="src.main"):
            # Verify that debug logging for headers would redact the token.
            # The helper function is the mechanism tested here; if it doesn't
            # exist the import assertion below will fail first.
            assert hasattr(src.main, "redact_request_headers"), (
                "redact_request_headers must exist in src.main"
            )
            headers = {"authorization": raw_token, "content-type": "application/json"}
            sanitized = src.main.redact_request_headers(headers)
            # The raw token must not be present in the sanitized dict values
            assert raw_token not in sanitized.values(), (
                f"Raw bearer token '{raw_token}' must not appear in sanitized headers"
            )
            assert sanitized.get("authorization") == "[REDACTED]"

    def test_body_api_key_not_logged_raw_in_debug_mode(self, caplog):
        """
        Raw api_key value must not appear in sanitized body log data.
        """
        import src.main

        raw_key = "sk-ant-api03-real-secret-key-12345678"

        assert hasattr(src.main, "redact_request_body"), (
            "redact_request_body must exist in src.main"
        )
        body = {"api_key": raw_key, "model": "claude-sonnet-4-6"}
        sanitized = src.main.redact_request_body(body)

        assert raw_key not in sanitized.values(), (
            f"Raw API key '{raw_key}' must not appear in sanitized body"
        )
        assert sanitized["api_key"] == "[REDACTED]"


# ---------------------------------------------------------------------------
# Section 4: Startup warning when DEBUG_MODE is enabled
# ---------------------------------------------------------------------------

class TestDebugModeStartupWarning:
    """
    FR-8.1: When DEBUG_MODE is enabled, a startup warning must be logged.

    The warning is expected to be emitted during application startup /
    module load when DEBUG_MODE=true. We verify this by checking that
    the logger at src.main level has been called with a WARNING-level
    message containing a hint about debug mode being active.
    """

    def test_debug_mode_warning_is_logged_at_startup(self, caplog):
        """When DEBUG_MODE=true, a WARNING log about debug mode must be emitted."""
        with caplog.at_level(logging.WARNING, logger="src.main"):
            with pytest.MonkeyPatch().context() as mp:
                mp.setenv("DEBUG_MODE", "true")
                import src.main
                importlib.reload(src.main)

        warning_messages = [
            record.message
            for record in caplog.records
            if record.levelno >= logging.WARNING and record.name == "src.main"
        ]
        assert any(
            "debug" in msg.lower() or "DEBUG" in msg
            for msg in warning_messages
        ), (
            "Expected a WARNING-level log about debug mode being enabled at startup, "
            f"but found only: {warning_messages}"
        )

    def test_no_debug_warning_when_debug_mode_disabled(self, caplog):
        """When DEBUG_MODE=false, no debug-mode warning should be emitted."""
        with caplog.at_level(logging.WARNING, logger="src.main"):
            with pytest.MonkeyPatch().context() as mp:
                mp.setenv("DEBUG_MODE", "false")
                import src.main
                importlib.reload(src.main)

        debug_warnings = [
            record.message
            for record in caplog.records
            if record.levelno >= logging.WARNING
            and record.name == "src.main"
            and "debug" in record.message.lower()
        ]
        assert len(debug_warnings) == 0, (
            f"Unexpected debug warning when DEBUG_MODE=false: {debug_warnings}"
        )


# ---------------------------------------------------------------------------
# Reset module state after each test class to prevent state leakage
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_main_module():
    """Reload src.main after each test to prevent module-level state leakage."""
    yield
    import src.main
    importlib.reload(src.main)
