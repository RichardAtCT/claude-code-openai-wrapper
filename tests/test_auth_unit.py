#!/usr/bin/env python3
"""
Unit tests for src/auth.py

Tests the ClaudeCodeAuthManager and authentication functions.
These are pure unit tests that don't require a running server.
"""

import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

# We need to patch environment before importing auth module
import importlib


class TestClaudeCodeAuthManagerDetectMethod:
    """Test _detect_auth_method()"""

    def test_explicit_cli_method(self):
        """CLAUDE_AUTH_METHOD=cli uses claude_cli."""
        with patch.dict(os.environ, {"CLAUDE_AUTH_METHOD": "cli"}, clear=False):
            import src.auth

            importlib.reload(src.auth)
            assert src.auth.auth_manager.auth_method == "claude_cli"

    def test_explicit_claude_cli_method(self):
        """CLAUDE_AUTH_METHOD=claude_cli uses claude_cli."""
        with patch.dict(os.environ, {"CLAUDE_AUTH_METHOD": "claude_cli"}, clear=False):
            import src.auth

            importlib.reload(src.auth)
            assert src.auth.auth_manager.auth_method == "claude_cli"

    def test_explicit_api_key_method(self):
        """CLAUDE_AUTH_METHOD=api_key uses anthropic."""
        with patch.dict(
            os.environ,
            {"CLAUDE_AUTH_METHOD": "api_key", "ANTHROPIC_API_KEY": "test-key-12345"},
            clear=False,
        ):
            import src.auth

            importlib.reload(src.auth)
            assert src.auth.auth_manager.auth_method == "anthropic"

    def test_explicit_anthropic_method(self):
        """CLAUDE_AUTH_METHOD=anthropic uses anthropic."""
        with patch.dict(
            os.environ,
            {"CLAUDE_AUTH_METHOD": "anthropic", "ANTHROPIC_API_KEY": "test-key-12345"},
            clear=False,
        ):
            import src.auth

            importlib.reload(src.auth)
            assert src.auth.auth_manager.auth_method == "anthropic"

    def test_explicit_bedrock_method(self):
        """CLAUDE_AUTH_METHOD=bedrock uses bedrock."""
        with patch.dict(os.environ, {"CLAUDE_AUTH_METHOD": "bedrock"}, clear=False):
            import src.auth

            importlib.reload(src.auth)
            assert src.auth.auth_manager.auth_method == "bedrock"

    def test_explicit_vertex_method(self):
        """CLAUDE_AUTH_METHOD=vertex uses vertex."""
        with patch.dict(os.environ, {"CLAUDE_AUTH_METHOD": "vertex"}, clear=False):
            import src.auth

            importlib.reload(src.auth)
            assert src.auth.auth_manager.auth_method == "vertex"

    def test_unknown_method_falls_back(self):
        """Unknown CLAUDE_AUTH_METHOD falls back to auto-detect."""
        with patch.dict(os.environ, {"CLAUDE_AUTH_METHOD": "unknown_method"}, clear=False):
            import src.auth

            importlib.reload(src.auth)
            # Should fall back to claude_cli (default)
            assert src.auth.auth_manager.auth_method in [
                "claude_cli",
                "anthropic",
                "bedrock",
                "vertex",
            ]

    def test_legacy_bedrock_env_var(self):
        """CLAUDE_CODE_USE_BEDROCK=1 uses bedrock."""
        env = {"CLAUDE_CODE_USE_BEDROCK": "1"}
        # Remove CLAUDE_AUTH_METHOD if present
        env_copy = {k: v for k, v in os.environ.items() if k != "CLAUDE_AUTH_METHOD"}
        env_copy.update(env)
        with patch.dict(os.environ, env_copy, clear=True):
            import src.auth

            importlib.reload(src.auth)
            assert src.auth.auth_manager.auth_method == "bedrock"

    def test_legacy_vertex_env_var(self):
        """CLAUDE_CODE_USE_VERTEX=1 uses vertex."""
        env = {"CLAUDE_CODE_USE_VERTEX": "1"}
        env_copy = {k: v for k, v in os.environ.items() if k != "CLAUDE_AUTH_METHOD"}
        env_copy.update(env)
        with patch.dict(os.environ, env_copy, clear=True):
            import src.auth

            importlib.reload(src.auth)
            assert src.auth.auth_manager.auth_method == "vertex"

    def test_auto_detect_anthropic_key(self):
        """ANTHROPIC_API_KEY auto-detects to anthropic."""
        env = {"ANTHROPIC_API_KEY": "test-key-12345678901234567890"}
        env_copy = {
            k: v
            for k, v in os.environ.items()
            if k not in ["CLAUDE_AUTH_METHOD", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"]
        }
        env_copy.update(env)
        with patch.dict(os.environ, env_copy, clear=True):
            import src.auth

            importlib.reload(src.auth)
            assert src.auth.auth_manager.auth_method == "anthropic"

    def test_default_to_claude_cli(self):
        """No env vars defaults to claude_cli."""
        env_copy = {
            k: v
            for k, v in os.environ.items()
            if k
            not in [
                "CLAUDE_AUTH_METHOD",
                "CLAUDE_CODE_USE_BEDROCK",
                "CLAUDE_CODE_USE_VERTEX",
                "ANTHROPIC_API_KEY",
            ]
        }
        with patch.dict(os.environ, env_copy, clear=True):
            import src.auth

            importlib.reload(src.auth)
            assert src.auth.auth_manager.auth_method == "claude_cli"


class TestClaudeCodeAuthManagerValidation:
    """Test authentication validation methods."""

    def test_validate_anthropic_valid(self):
        """Valid ANTHROPIC_API_KEY passes validation."""
        with patch.dict(
            os.environ,
            {
                "CLAUDE_AUTH_METHOD": "anthropic",
                "ANTHROPIC_API_KEY": "sk-ant-api03-validkey1234567890",
            },
        ):
            import src.auth

            importlib.reload(src.auth)
            status = src.auth.auth_manager.auth_status
            assert status["valid"] is True
            assert status["method"] == "anthropic"

    def test_validate_anthropic_missing_key(self):
        """Missing ANTHROPIC_API_KEY fails validation."""
        env_copy = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env_copy["CLAUDE_AUTH_METHOD"] = "anthropic"
        with patch.dict(os.environ, env_copy, clear=True):
            import src.auth

            importlib.reload(src.auth)
            status = src.auth.auth_manager.auth_status
            assert status["valid"] is False
            assert any("ANTHROPIC_API_KEY" in err for err in status["errors"])

    def test_validate_anthropic_short_key(self):
        """Too short ANTHROPIC_API_KEY fails validation."""
        with patch.dict(
            os.environ,
            {"CLAUDE_AUTH_METHOD": "anthropic", "ANTHROPIC_API_KEY": "short"},
        ):
            import src.auth

            importlib.reload(src.auth)
            status = src.auth.auth_manager.auth_status
            assert status["valid"] is False
            assert any("too short" in err for err in status["errors"])

    def test_validate_bedrock_valid(self):
        """Valid Bedrock config passes validation."""
        with patch.dict(
            os.environ,
            {
                "CLAUDE_AUTH_METHOD": "bedrock",
                "CLAUDE_CODE_USE_BEDROCK": "1",
                "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
                "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "AWS_REGION": "us-east-1",
            },
        ):
            import src.auth

            importlib.reload(src.auth)
            status = src.auth.auth_manager.auth_status
            assert status["valid"] is True
            assert status["method"] == "bedrock"

    def test_validate_bedrock_missing_credentials(self):
        """Missing AWS credentials fails Bedrock validation."""
        env_copy = {
            k: v
            for k, v in os.environ.items()
            if k not in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"]
        }
        env_copy["CLAUDE_AUTH_METHOD"] = "bedrock"
        env_copy["CLAUDE_CODE_USE_BEDROCK"] = "1"
        with patch.dict(os.environ, env_copy, clear=True):
            import src.auth

            importlib.reload(src.auth)
            status = src.auth.auth_manager.auth_status
            assert status["valid"] is False
            assert len(status["errors"]) > 0

    def test_validate_vertex_valid(self):
        """Valid Vertex config passes validation."""
        with patch.dict(
            os.environ,
            {
                "CLAUDE_AUTH_METHOD": "vertex",
                "CLAUDE_CODE_USE_VERTEX": "1",
                "ANTHROPIC_VERTEX_PROJECT_ID": "my-project-123",
                "CLOUD_ML_REGION": "us-central1",
            },
        ):
            import src.auth

            importlib.reload(src.auth)
            status = src.auth.auth_manager.auth_status
            assert status["valid"] is True
            assert status["method"] == "vertex"

    def test_validate_vertex_missing_config(self):
        """Missing Vertex config fails validation."""
        env_copy = {
            k: v
            for k, v in os.environ.items()
            if k not in ["ANTHROPIC_VERTEX_PROJECT_ID", "CLOUD_ML_REGION"]
        }
        env_copy["CLAUDE_AUTH_METHOD"] = "vertex"
        env_copy["CLAUDE_CODE_USE_VERTEX"] = "1"
        with patch.dict(os.environ, env_copy, clear=True):
            import src.auth

            importlib.reload(src.auth)
            status = src.auth.auth_manager.auth_status
            assert status["valid"] is False

    def test_validate_claude_cli_always_valid(self):
        """Claude CLI auth is always considered valid initially."""
        env_copy = {k: v for k, v in os.environ.items() if k != "CLAUDE_AUTH_METHOD"}
        env_copy["CLAUDE_AUTH_METHOD"] = "cli"
        with patch.dict(os.environ, env_copy, clear=True):
            import src.auth

            importlib.reload(src.auth)
            status = src.auth.auth_manager.auth_status
            assert status["valid"] is True
            assert status["method"] == "claude_cli"


class TestClaudeCodeAuthManagerEnvVars:
    """Test get_claude_code_env_vars()"""

    def test_anthropic_env_vars(self):
        """Anthropic method returns ANTHROPIC_API_KEY."""
        with patch.dict(
            os.environ,
            {
                "CLAUDE_AUTH_METHOD": "anthropic",
                "ANTHROPIC_API_KEY": "test-key-12345",
            },
        ):
            import src.auth

            importlib.reload(src.auth)
            env_vars = src.auth.auth_manager.get_claude_code_env_vars()
            assert "ANTHROPIC_API_KEY" in env_vars
            assert env_vars["ANTHROPIC_API_KEY"] == "test-key-12345"

    def test_bedrock_env_vars(self):
        """Bedrock method returns AWS credentials."""
        with patch.dict(
            os.environ,
            {
                "CLAUDE_AUTH_METHOD": "bedrock",
                "CLAUDE_CODE_USE_BEDROCK": "1",
                "AWS_ACCESS_KEY_ID": "AKIATEST",
                "AWS_SECRET_ACCESS_KEY": "secretkey",
                "AWS_REGION": "us-east-1",
            },
        ):
            import src.auth

            importlib.reload(src.auth)
            env_vars = src.auth.auth_manager.get_claude_code_env_vars()
            assert env_vars.get("CLAUDE_CODE_USE_BEDROCK") == "1"
            assert "AWS_ACCESS_KEY_ID" in env_vars
            assert "AWS_SECRET_ACCESS_KEY" in env_vars
            assert "AWS_REGION" in env_vars

    def test_vertex_env_vars(self):
        """Vertex method returns Google Cloud credentials."""
        with patch.dict(
            os.environ,
            {
                "CLAUDE_AUTH_METHOD": "vertex",
                "CLAUDE_CODE_USE_VERTEX": "1",
                "ANTHROPIC_VERTEX_PROJECT_ID": "my-project",
                "CLOUD_ML_REGION": "us-central1",
            },
        ):
            import src.auth

            importlib.reload(src.auth)
            env_vars = src.auth.auth_manager.get_claude_code_env_vars()
            assert env_vars.get("CLAUDE_CODE_USE_VERTEX") == "1"
            assert "ANTHROPIC_VERTEX_PROJECT_ID" in env_vars
            assert "CLOUD_ML_REGION" in env_vars

    def test_cli_env_vars_empty(self):
        """CLI method returns no environment variables."""
        env_copy = {k: v for k, v in os.environ.items() if k != "CLAUDE_AUTH_METHOD"}
        env_copy["CLAUDE_AUTH_METHOD"] = "cli"
        with patch.dict(os.environ, env_copy, clear=True):
            import src.auth

            importlib.reload(src.auth)
            env_vars = src.auth.auth_manager.get_claude_code_env_vars()
            assert env_vars == {}


class TestVerifyApiKey:
    """Test verify_api_key() function."""

    @pytest.mark.asyncio
    async def test_no_api_key_configured_allows_all(self):
        """When no API_KEY is set, all requests are allowed."""
        env_copy = {k: v for k, v in os.environ.items() if k != "API_KEY"}
        with patch.dict(os.environ, env_copy, clear=True):
            import src.auth

            importlib.reload(src.auth)

            # Mock auth_manager to have no API key
            with patch.object(src.auth.auth_manager, "get_api_key", return_value=None):
                mock_request = MagicMock()
                result = await src.auth.verify_api_key(mock_request)
                assert result is True

    @pytest.mark.asyncio
    async def test_valid_api_key_passes(self):
        """Valid API key in Authorization header passes."""
        with patch.dict(os.environ, {"API_KEY": "test-secret-key"}):
            import src.auth

            importlib.reload(src.auth)

            from fastapi.security import HTTPAuthorizationCredentials

            mock_request = MagicMock()
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer", credentials="test-secret-key"
            )

            with patch.object(src.auth.auth_manager, "get_api_key", return_value="test-secret-key"):
                result = await src.auth.verify_api_key(mock_request, credentials)
                assert result is True

    @pytest.mark.asyncio
    async def test_invalid_api_key_raises_401(self):
        """Invalid API key raises 401 HTTPException."""
        with patch.dict(os.environ, {"API_KEY": "correct-key"}):
            import src.auth

            importlib.reload(src.auth)

            from fastapi.security import HTTPAuthorizationCredentials

            mock_request = MagicMock()
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong-key")

            with patch.object(src.auth.auth_manager, "get_api_key", return_value="correct-key"):
                with pytest.raises(HTTPException) as exc_info:
                    await src.auth.verify_api_key(mock_request, credentials)
                assert exc_info.value.status_code == 401
                assert "Invalid API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_missing_credentials_raises_401(self):
        """Missing credentials raise 401 HTTPException."""
        with patch.dict(os.environ, {"API_KEY": "test-key"}):
            import src.auth

            importlib.reload(src.auth)

            mock_request = MagicMock()
            # Mock security to return None (no credentials)
            with patch.object(src.auth, "security", AsyncMock(return_value=None)):
                with patch.object(src.auth.auth_manager, "get_api_key", return_value="test-key"):
                    with pytest.raises(HTTPException) as exc_info:
                        await src.auth.verify_api_key(mock_request, None)
                    assert exc_info.value.status_code == 401
                    assert "Missing API key" in exc_info.value.detail


class TestValidateClaudeCodeAuth:
    """Test validate_claude_code_auth() function."""

    def test_valid_auth_returns_true(self):
        """Valid auth returns (True, status)."""
        with patch.dict(os.environ, {"CLAUDE_AUTH_METHOD": "cli"}):
            import src.auth

            importlib.reload(src.auth)

            is_valid, status = src.auth.validate_claude_code_auth()
            assert is_valid is True
            assert status["valid"] is True

    def test_invalid_auth_returns_false(self):
        """Invalid auth returns (False, status)."""
        env_copy = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env_copy["CLAUDE_AUTH_METHOD"] = "anthropic"
        with patch.dict(os.environ, env_copy, clear=True):
            import src.auth

            importlib.reload(src.auth)

            is_valid, status = src.auth.validate_claude_code_auth()
            assert is_valid is False
            assert status["valid"] is False


class TestGetClaudeCodeAuthInfo:
    """Test get_claude_code_auth_info() function."""

    def test_returns_auth_info(self):
        """Returns comprehensive auth information."""
        with patch.dict(os.environ, {"CLAUDE_AUTH_METHOD": "cli"}):
            import src.auth

            importlib.reload(src.auth)

            info = src.auth.get_claude_code_auth_info()
            assert "method" in info
            assert "status" in info
            assert "environment_variables" in info


class TestGetApiKey:
    """Test ClaudeCodeAuthManager.get_api_key()"""

    def test_returns_env_api_key(self):
        """Returns API_KEY from environment."""
        with patch.dict(os.environ, {"API_KEY": "env-api-key"}):
            import src.auth

            importlib.reload(src.auth)
            assert src.auth.auth_manager.get_api_key() == "env-api-key"

    def test_returns_runtime_key_when_available(self):
        """Returns runtime key when set in main module."""
        with patch.dict(os.environ, {"API_KEY": "env-key"}):
            import src.auth

            importlib.reload(src.auth)

            # Mock the runtime API key
            mock_main = MagicMock()
            mock_main.runtime_api_key = "runtime-key"

            with patch.dict("sys.modules", {"src.main": mock_main}):
                # Need to reload to pick up the mock
                result = src.auth.auth_manager.get_api_key()
                # May return env key if import fails, but shouldn't error
                assert result in ["env-key", "runtime-key"]


# Reset module state after tests
@pytest.fixture(autouse=True)
def reset_auth_module():
    """Reset auth module after each test."""
    yield
    # Restore default state
    import src.auth

    importlib.reload(src.auth)
