#!/usr/bin/env python3
"""
Unit tests for src/rate_limiter.py

Tests the rate limiting functions and configuration.
These are pure unit tests that don't require a running server.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import Request
from fastapi.responses import JSONResponse

# Need to patch environment before importing the module
import os


class TestGetRateLimitKey:
    """Test get_rate_limit_key()"""

    def test_returns_remote_address(self):
        """Should return the remote address from the request."""
        with patch("src.rate_limiter.get_remote_address") as mock_get_addr:
            mock_get_addr.return_value = "192.168.1.100"
            mock_request = MagicMock(spec=Request)

            from src.rate_limiter import get_rate_limit_key

            result = get_rate_limit_key(mock_request)
            assert result == "192.168.1.100"
            mock_get_addr.assert_called_once_with(mock_request)


class TestCreateRateLimiter:
    """Test create_rate_limiter()"""

    def test_rate_limiter_disabled_returns_none(self):
        """When RATE_LIMIT_ENABLED=false, returns None."""
        with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": "false"}):
            # Need to reimport to pick up new env var
            import importlib
            import src.rate_limiter

            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.create_rate_limiter()
            assert result is None

    def test_rate_limiter_enabled_returns_limiter(self):
        """When RATE_LIMIT_ENABLED=true, returns Limiter instance."""
        with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": "true"}):
            import importlib
            import src.rate_limiter

            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.create_rate_limiter()
            assert result is not None

    def test_rate_limiter_disabled_with_0(self):
        """When RATE_LIMIT_ENABLED=0, returns None."""
        with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": "0"}):
            import importlib
            import src.rate_limiter

            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.create_rate_limiter()
            assert result is None

    def test_rate_limiter_disabled_with_no(self):
        """When RATE_LIMIT_ENABLED=no, returns None."""
        with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": "no"}):
            import importlib
            import src.rate_limiter

            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.create_rate_limiter()
            assert result is None

    def test_rate_limiter_enabled_by_default(self):
        """When RATE_LIMIT_ENABLED not set, rate limiting is enabled."""
        # Remove the env var if set
        env_copy = os.environ.copy()
        if "RATE_LIMIT_ENABLED" in env_copy:
            del env_copy["RATE_LIMIT_ENABLED"]

        with patch.dict(os.environ, env_copy, clear=True):
            import importlib
            import src.rate_limiter

            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.create_rate_limiter()
            assert result is not None


class TestRateLimitExceededHandler:
    """Test rate_limit_exceeded_handler()"""

    @pytest.fixture
    def mock_rate_limit_exceeded(self):
        """Create a mock RateLimitExceeded exception."""
        from slowapi.errors import RateLimitExceeded

        # Create a mock Limit object that RateLimitExceeded expects
        mock_limit = MagicMock()
        mock_limit.error_message = None
        mock_exc = MagicMock(spec=RateLimitExceeded)
        mock_exc.limit = mock_limit
        return mock_exc

    def test_returns_json_response(self, mock_rate_limit_exceeded):
        """Returns a JSONResponse."""
        from src.rate_limiter import rate_limit_exceeded_handler

        mock_request = MagicMock(spec=Request)

        response = rate_limit_exceeded_handler(mock_request, mock_rate_limit_exceeded)
        assert isinstance(response, JSONResponse)

    def test_returns_429_status(self, mock_rate_limit_exceeded):
        """Returns 429 Too Many Requests status."""
        from src.rate_limiter import rate_limit_exceeded_handler

        mock_request = MagicMock(spec=Request)

        response = rate_limit_exceeded_handler(mock_request, mock_rate_limit_exceeded)
        assert response.status_code == 429

    def test_includes_retry_after_header(self, mock_rate_limit_exceeded):
        """Response includes Retry-After header."""
        from src.rate_limiter import rate_limit_exceeded_handler

        mock_request = MagicMock(spec=Request)

        response = rate_limit_exceeded_handler(mock_request, mock_rate_limit_exceeded)
        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"] == "60"


class TestGetRateLimitForEndpoint:
    """Test get_rate_limit_for_endpoint()"""

    def test_chat_endpoint_default(self):
        """Chat endpoint has default rate limit."""
        with patch.dict(os.environ, {}, clear=False):
            # Ensure no override
            if "RATE_LIMIT_CHAT_PER_MINUTE" in os.environ:
                del os.environ["RATE_LIMIT_CHAT_PER_MINUTE"]

            import importlib
            import src.rate_limiter

            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.get_rate_limit_for_endpoint("chat")
            assert result == "10/minute"

    def test_debug_endpoint_default(self):
        """Debug endpoint has default rate limit."""
        import importlib
        import src.rate_limiter

        # Clear any override
        env_copy = {k: v for k, v in os.environ.items() if k != "RATE_LIMIT_DEBUG_PER_MINUTE"}
        with patch.dict(os.environ, env_copy, clear=True):
            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.get_rate_limit_for_endpoint("debug")
            assert result == "2/minute"

    def test_health_endpoint_default(self):
        """Health endpoint has default rate limit."""
        import importlib
        import src.rate_limiter

        env_copy = {k: v for k, v in os.environ.items() if k != "RATE_LIMIT_HEALTH_PER_MINUTE"}
        with patch.dict(os.environ, env_copy, clear=True):
            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.get_rate_limit_for_endpoint("health")
            assert result == "30/minute"

    def test_session_endpoint_default(self):
        """Session endpoint has default rate limit."""
        import importlib
        import src.rate_limiter

        env_copy = {k: v for k, v in os.environ.items() if k != "RATE_LIMIT_SESSION_PER_MINUTE"}
        with patch.dict(os.environ, env_copy, clear=True):
            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.get_rate_limit_for_endpoint("session")
            assert result == "15/minute"

    def test_auth_endpoint_default(self):
        """Auth endpoint has default rate limit."""
        import importlib
        import src.rate_limiter

        env_copy = {k: v for k, v in os.environ.items() if k != "RATE_LIMIT_AUTH_PER_MINUTE"}
        with patch.dict(os.environ, env_copy, clear=True):
            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.get_rate_limit_for_endpoint("auth")
            assert result == "10/minute"

    def test_general_endpoint_default(self):
        """General/unknown endpoint has default rate limit."""
        import importlib
        import src.rate_limiter

        env_copy = {k: v for k, v in os.environ.items() if k != "RATE_LIMIT_PER_MINUTE"}
        with patch.dict(os.environ, env_copy, clear=True):
            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.get_rate_limit_for_endpoint("general")
            assert result == "30/minute"

    def test_custom_rate_limit_from_env(self):
        """Rate limit can be customized via environment variable."""
        import importlib
        import src.rate_limiter

        with patch.dict(os.environ, {"RATE_LIMIT_CHAT_PER_MINUTE": "50"}):
            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.get_rate_limit_for_endpoint("chat")
            assert result == "50/minute"

    def test_unknown_endpoint_uses_general_default(self):
        """Unknown endpoint uses general rate limit."""
        import importlib
        import src.rate_limiter

        env_copy = {k: v for k, v in os.environ.items() if k != "RATE_LIMIT_PER_MINUTE"}
        with patch.dict(os.environ, env_copy, clear=True):
            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.get_rate_limit_for_endpoint("unknown_endpoint")
            assert result == "30/minute"


class TestRateLimitEndpointDecorator:
    """Test rate_limit_endpoint decorator factory."""

    def test_decorator_returns_function(self):
        """Decorator returns a function."""
        from src.rate_limiter import rate_limit_endpoint

        decorator = rate_limit_endpoint("chat")
        assert callable(decorator)

    def test_decorator_wraps_function_with_request(self):
        """Decorated function with request parameter can still be called."""
        from src.rate_limiter import rate_limit_endpoint

        # slowapi requires a 'request' parameter on decorated functions
        @rate_limit_endpoint("chat")
        def my_endpoint(request):
            return "hello"

        # The function should still be callable (though it may be wrapped)
        assert callable(my_endpoint)

    def test_decorator_without_limiter(self):
        """When limiter is None, returns original function unchanged."""
        import importlib
        import src.rate_limiter

        # Disable rate limiting
        with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": "false"}):
            importlib.reload(src.rate_limiter)

            @src.rate_limiter.rate_limit_endpoint("chat")
            def my_endpoint():
                return "hello"

            # Function should work normally
            assert my_endpoint() == "hello"


# Reset module state after tests
@pytest.fixture(autouse=True)
def reset_rate_limiter_module():
    """Reset rate limiter module after each test to avoid test pollution."""
    yield
    # Clean up after test
    import importlib
    import src.rate_limiter

    # Reset to default state
    with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": "true"}, clear=False):
        importlib.reload(src.rate_limiter)
