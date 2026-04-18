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
        """Should return the direct peer IP from the request when no trusted proxies are set."""
        import importlib
        import src.constants
        import src.rate_limiter

        mock_request = MagicMock(spec=Request)
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {}

        with patch.dict(os.environ, {"TRUSTED_PROXIES": ""}):
            importlib.reload(src.constants)
            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.get_rate_limit_key(mock_request)

        assert result == "192.168.1.100"


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


class TestGetRateLimitKeyTrustedProxy:
    """Test get_rate_limit_key() with trusted proxy support (FR-3.1).

    The function must only trust X-Forwarded-For when the direct peer IP is
    in TRUSTED_PROXIES.  When TRUSTED_PROXIES is empty or the peer is not
    trusted, the function must ignore X-Forwarded-For entirely to prevent
    IP spoofing attacks that would allow bypassing rate limits.

    Architecture reference: Section 5.3 and 7.2.

    Patching strategy: the new implementation will read TRUSTED_PROXIES from
    src.constants at module import time (from src.constants import
    TRUSTED_PROXIES).  We therefore reload src.rate_limiter after patching the
    TRUSTED_PROXIES environment variable so that each test gets a fresh module
    with the desired proxy list.  Using importlib.reload mirrors the pattern
    already established in this file for RATE_LIMIT_ENABLED.

    All five tests MUST FAIL against the current implementation because
    get_rate_limit_key() does not yet consult TRUSTED_PROXIES at all: it
    delegates unconditionally to get_remote_address() which ignores XFF and
    always returns request.client.host.  The failures prove the feature is
    missing and define the contract the implementer must satisfy.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_request(client_ip: str, x_forwarded_for: str = None):
        """Return a mock Request with the given peer IP and optional XFF header.

        Headers are stored as a plain dict.  The new implementation must call
        request.headers.get("x-forwarded-for") which MagicMock satisfies when
        headers is a dict-like object (MagicMock.__getitem__ is available, but
        .get() on a plain dict works too).
        """
        mock_request = MagicMock(spec=Request)
        mock_request.client = MagicMock()
        mock_request.client.host = client_ip

        # Use a real dict so .get() behaves correctly
        headers = {}
        if x_forwarded_for is not None:
            headers["x-forwarded-for"] = x_forwarded_for
        mock_request.headers = headers

        return mock_request

    @staticmethod
    def _load_get_rate_limit_key(trusted_proxies_value: str):
        """Reload src.rate_limiter with TRUSTED_PROXIES set to the given
        comma-separated string and return the freshly bound get_rate_limit_key.

        This forces the module to re-evaluate TRUSTED_PROXIES from constants
        (which reads os.environ) so each test exercises an isolated state.
        """
        import importlib
        import src.constants
        import src.rate_limiter

        with patch.dict(os.environ, {"TRUSTED_PROXIES": trusted_proxies_value}):
            importlib.reload(src.constants)
            importlib.reload(src.rate_limiter)
            # Return a reference captured while the patches are still active
            return src.rate_limiter.get_rate_limit_key

    # ------------------------------------------------------------------
    # TC-1: No TRUSTED_PROXIES configured, no X-Forwarded-For header
    #        → must return the direct peer IP
    # ------------------------------------------------------------------

    def test_get_rate_limit_key_no_trusted_proxies_no_xff_returns_client_ip(self):
        """When TRUSTED_PROXIES is empty and no XFF header is present,
        get_rate_limit_key must return the direct peer IP."""
        import importlib
        import src.constants
        import src.rate_limiter

        mock_request = self._make_request("203.0.113.10")

        with patch.dict(os.environ, {"TRUSTED_PROXIES": ""}):
            importlib.reload(src.constants)
            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.get_rate_limit_key(mock_request)

        assert result == "203.0.113.10"

    # ------------------------------------------------------------------
    # TC-2: No TRUSTED_PROXIES configured, X-Forwarded-For is present
    #        → must return the direct peer IP (header MUST be ignored)
    #
    # This is the primary security requirement: a client that forges
    # X-Forwarded-For must NOT be able to impersonate a different IP.
    # ------------------------------------------------------------------

    def test_get_rate_limit_key_no_trusted_proxies_xff_present_ignores_xff(self):
        """When TRUSTED_PROXIES is empty, X-Forwarded-For must be ignored
        regardless of its value.  Trusting it without proxy validation
        lets any client bypass rate limits by setting a forged header."""
        import importlib
        import src.constants
        import src.rate_limiter

        mock_request = self._make_request(
            "203.0.113.10",
            x_forwarded_for="1.2.3.4",
        )

        with patch.dict(os.environ, {"TRUSTED_PROXIES": ""}):
            importlib.reload(src.constants)
            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.get_rate_limit_key(mock_request)

        # Must be the real direct-connection peer, NOT the attacker-supplied IP
        assert result == "203.0.113.10", (
            "get_rate_limit_key must not trust X-Forwarded-For when " "TRUSTED_PROXIES is empty"
        )
        assert result != "1.2.3.4"

    # ------------------------------------------------------------------
    # TC-3: Peer IP is NOT in TRUSTED_PROXIES, XFF is present (spoofed)
    #        → must return the direct peer IP (header MUST be ignored)
    # ------------------------------------------------------------------

    def test_get_rate_limit_key_untrusted_peer_xff_spoofed_returns_client_ip(self):
        """When the peer IP is not in TRUSTED_PROXIES, X-Forwarded-For is
        attacker-controlled data and must be ignored entirely."""
        import importlib
        import src.constants
        import src.rate_limiter

        mock_request = self._make_request(
            "198.51.100.99",  # not a trusted proxy
            x_forwarded_for="1.2.3.4, 10.0.0.1",
        )

        # 10.0.0.1 is a trusted proxy, but 198.51.100.99 (the peer) is not
        with patch.dict(os.environ, {"TRUSTED_PROXIES": "10.0.0.1"}):
            importlib.reload(src.constants)
            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.get_rate_limit_key(mock_request)

        # Must return the real untrusted peer, not any value from XFF
        assert result == "198.51.100.99"
        assert result not in ("1.2.3.4", "10.0.0.1")

    # ------------------------------------------------------------------
    # TC-4: Peer IP IS in TRUSTED_PROXIES, XFF chain contains both
    #        trusted and non-trusted IPs
    #        → must return the rightmost non-trusted IP
    #
    # This is the core "happy path" for reverse-proxy deployments.
    # ------------------------------------------------------------------

    def test_get_rate_limit_key_trusted_peer_valid_xff_returns_rightmost_non_trusted_ip(self):
        """When the peer is a trusted proxy and the X-Forwarded-For chain
        contains non-trusted IPs, the rightmost non-trusted IP is the actual
        client and must be used for rate limiting.

        XFF chain:  "1.2.3.4, 10.0.0.2"
        Direct peer: 10.0.0.1 (trusted)
        Trusted proxies: 10.0.0.1, 10.0.0.2

        Walking from right: 10.0.0.2 is trusted (skip); 1.2.3.4 is not trusted
        → return 1.2.3.4
        """
        import importlib
        import src.constants
        import src.rate_limiter

        mock_request = self._make_request(
            "10.0.0.1",  # trusted proxy (direct peer)
            x_forwarded_for="1.2.3.4, 10.0.0.2",
        )

        with patch.dict(os.environ, {"TRUSTED_PROXIES": "10.0.0.1,10.0.0.2"}):
            importlib.reload(src.constants)
            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.get_rate_limit_key(mock_request)

        assert result == "1.2.3.4"

    # ------------------------------------------------------------------
    # TC-5: Peer IP IS in TRUSTED_PROXIES but no XFF header is present
    #        → must fall back to the peer IP (no error, no None)
    # ------------------------------------------------------------------

    def test_get_rate_limit_key_trusted_peer_missing_xff_falls_back_to_peer_ip(self):
        """When the peer is a trusted proxy but no X-Forwarded-For header
        exists, there is no upstream IP to extract.  The function must fall
        back to the peer IP rather than raising an exception or returning
        None."""
        import importlib
        import src.constants
        import src.rate_limiter

        mock_request = self._make_request("10.0.0.1")  # no XFF header

        with patch.dict(os.environ, {"TRUSTED_PROXIES": "10.0.0.1"}):
            importlib.reload(src.constants)
            importlib.reload(src.rate_limiter)
            result = src.rate_limiter.get_rate_limit_key(mock_request)

        assert result == "10.0.0.1"


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
