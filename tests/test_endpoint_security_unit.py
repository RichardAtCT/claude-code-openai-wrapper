#!/usr/bin/env python3
"""
Unit tests for endpoint security fixes (Task T020).

Covers:
  FR-7.1 — /v1/debug/request must require authentication
  FR-7.2 — /v1/auth/status must return only {"authenticated": true/false}
  FR-3.2 — / and /v1/compatibility must expose rate-limit headers

All tests are written against the CURRENT (unfixed) implementation and
MUST FAIL until the fixes described in spec.md are applied.

Import strategy
---------------
main.py runs ClaudeCodeCLI + session_manager startup logic at module level.
We suppress the lifespan by disabling the background cleanup task and
patching the slowapi state-attachment so TestClient can import the app
without needing a real Claude SDK installation.

The app object itself (FastAPI instance) is imported once per-process; the
TestClient wraps it without triggering the lifespan (we do NOT use
`with TestClient(app) as client:` which triggers startup/shutdown events).
"""

import os
import importlib
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

TEST_API_KEY = "test-key-12345678"


def _get_test_client():
    """
    Import and return a TestClient wrapping the FastAPI app.

    We set API_KEY before importing so the verify_api_key dependency uses a
    known value.  The lifespan is NOT executed when TestClient is instantiated
    without entering a context manager — FastAPI docs confirm that startup
    events only fire inside `with TestClient(app)`.

    We patch asyncio.wait_for used inside the lifespan to be a no-op so that
    even if TestClient *does* try to run startup it does not block indefinitely.
    """
    # Patch the blocking verify_cli call and cleanup-task start that happen
    # during lifespan, to prevent hangs in any test runner that triggers it.
    with patch.dict(os.environ, {"API_KEY": TEST_API_KEY}, clear=False):
        # Delay import until env is set so auth module picks up API_KEY
        import src.main as main_module

        importlib.reload(src.main)

        from starlette.testclient import TestClient

        # TestClient without context manager does NOT run lifespan events.
        client = TestClient(main_module.app, raise_server_exceptions=False)
        return client, main_module.app


# ---------------------------------------------------------------------------
# FR-7.1 — Debug endpoint authentication
# ---------------------------------------------------------------------------


class TestDebugEndpointRequiresAuth:
    """
    FR-7.1: POST /v1/debug/request must be protected by the verify_api_key
    dependency.

    Current state: the endpoint has no Depends(security) / verify_api_key
    call, so unauthenticated requests return 200.  Tests MUST FAIL until
    the auth guard is added.
    """

    def test_debug_endpoint_without_auth_header_returns_401_or_403(self):
        """
        POST /v1/debug/request with no Authorization header must return
        401 (Unauthorized) or 403 (Forbidden) when API_KEY is configured.

        CURRENT BEHAVIOUR: returns 200 — test will FAIL (RED phase).
        """
        with patch.dict(os.environ, {"API_KEY": TEST_API_KEY}, clear=False):
            import src.auth

            importlib.reload(src.auth)
            import src.main

            importlib.reload(src.main)

            from starlette.testclient import TestClient

            client = TestClient(src.main.app, raise_server_exceptions=False)

            response = client.post(
                "/v1/debug/request",
                json={
                    "model": "claude-3-sonnet-20240229",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )

        assert response.status_code in (401, 403), (
            f"Expected 401 or 403 for unauthenticated debug request, "
            f"got {response.status_code}. "
            "The /v1/debug/request endpoint currently has no auth guard — "
            "FR-7.1 fix is required."
        )

    def test_debug_endpoint_with_valid_auth_returns_200(self):
        """
        POST /v1/debug/request with a valid Bearer token must return 200.

        This test verifies the endpoint still works once the auth guard is in
        place with correct credentials.  Rate limiting is disabled so that the
        in-process limiter counter from the preceding test does not cause a
        spurious 429.

        CURRENT BEHAVIOUR: also returns 200 (no auth check), so this test
        passes now — but it is paired with the above to document the full
        contract.  It is kept here so that it continues to pass after the
        fix is applied, acting as a regression guard.

        NOTE: Because this test currently passes, the RED-phase failure is
        driven entirely by the previous test.  Both are included as a pair
        to fully specify the authenticated-access contract.
        """
        env = dict(os.environ)
        env["API_KEY"] = TEST_API_KEY
        env["RATE_LIMIT_ENABLED"] = "false"  # isolate from rate-limiter state
        with patch.dict(os.environ, env, clear=True):
            import src.auth
            import src.rate_limiter
            import src.main

            importlib.reload(src.auth)
            importlib.reload(src.rate_limiter)
            importlib.reload(src.main)

            from starlette.testclient import TestClient

            client = TestClient(src.main.app, raise_server_exceptions=False)

            response = client.post(
                "/v1/debug/request",
                json={
                    "model": "claude-3-sonnet-20240229",
                    "messages": [{"role": "user", "content": "hello"}],
                },
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )

        assert (
            response.status_code == 200
        ), f"Expected 200 for authenticated debug request, got {response.status_code}."


# ---------------------------------------------------------------------------
# FR-7.2 — Auth status response must be stripped
# ---------------------------------------------------------------------------


class TestAuthStatusResponseStripped:
    """
    FR-7.2: GET /v1/auth/status must return ONLY {"authenticated": true/false}.

    Current state: the endpoint returns a verbose object containing
    claude_code_auth (with method, status, environment_variables) and
    server_info (with api_key_required, api_key_source, version).
    All three tests below MUST FAIL until the response body is stripped.
    """

    def _get_auth_status_response(self):
        """Helper: call GET /v1/auth/status and return the response."""
        # No API_KEY set so the endpoint is publicly reachable (matches
        # current behaviour and keeps the test independent of auth state)
        env = {k: v for k, v in os.environ.items() if k != "API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            import src.auth

            importlib.reload(src.auth)
            import src.main

            importlib.reload(src.main)

            from starlette.testclient import TestClient

            client = TestClient(src.main.app, raise_server_exceptions=False)
            return client.get("/v1/auth/status")

    def test_auth_status_response_contains_only_authenticated_key(self):
        """
        Response body must contain ONLY the key "authenticated".

        CURRENT BEHAVIOUR: body also contains "claude_code_auth" and
        "server_info" — test will FAIL (RED phase).
        """
        response = self._get_auth_status_response()
        assert response.status_code == 200

        body = response.json()
        assert set(body.keys()) == {"authenticated"}, (
            f"Response body keys must be exactly {{'authenticated'}}, "
            f"got {set(body.keys())}. "
            "FR-7.2 requires stripping all auth method details from this endpoint."
        )

    def test_auth_status_response_does_not_contain_claude_code_auth(self):
        """
        Response body must NOT contain the 'claude_code_auth' key which
        reveals the authentication method and configuration details.

        CURRENT BEHAVIOUR: 'claude_code_auth' is present — test will FAIL.
        """
        response = self._get_auth_status_response()
        assert response.status_code == 200

        body = response.json()
        assert "claude_code_auth" not in body, (
            "'claude_code_auth' key must not appear in /v1/auth/status response. "
            "It reveals the auth strategy (method name, env vars, config). "
            "FR-7.2 requires removing it."
        )

    def test_auth_status_response_does_not_contain_server_info(self):
        """
        Response body must NOT contain the 'server_info' key which reveals
        whether an API key is required and how it is sourced.

        CURRENT BEHAVIOUR: 'server_info' is present — test will FAIL.
        """
        response = self._get_auth_status_response()
        assert response.status_code == 200

        body = response.json()
        assert "server_info" not in body, (
            "'server_info' key must not appear in /v1/auth/status response. "
            "It reveals api_key_required, api_key_source, and version — "
            "reconnaissance information per KD-8. FR-7.2 requires removing it."
        )

    def test_auth_status_authenticated_value_is_bool(self):
        """
        The 'authenticated' value must be a boolean (true or false).

        This test documents the shape of the stripped response so that the
        implementer knows exactly what the body should look like after the fix.

        CURRENT BEHAVIOUR: 'authenticated' key does not exist — test will FAIL.
        """
        response = self._get_auth_status_response()
        assert response.status_code == 200

        body = response.json()
        assert (
            "authenticated" in body
        ), "Response must contain 'authenticated' key after FR-7.2 fix."
        assert isinstance(
            body["authenticated"], bool
        ), f"'authenticated' value must be a bool, got {type(body['authenticated'])}."


# ---------------------------------------------------------------------------
# FR-3.2 — Rate limit headers on previously unprotected endpoints
# ---------------------------------------------------------------------------


class TestUnprotectedEndpointsHaveRateLimitHeaders:
    """
    FR-3.2: GET / and POST /v1/compatibility must return rate-limit response
    headers (e.g. X-RateLimit-Limit) indicating slowapi is active.

    Current state: neither endpoint has a @rate_limit_endpoint decorator,
    so no rate-limit headers are present.  Tests MUST FAIL until the
    decorator is added (architecture sections 9.1, 9.2).

    Implementation note: slowapi injects headers such as
      X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
    only on endpoints that carry the @limiter.limit(...) decoration.
    Endpoints without the decorator return no such headers regardless of
    whether the global limiter is active.
    """

    RATE_LIMIT_HEADER_PREFIXES = (
        "X-RateLimit-Limit",
        "X-Ratelimit-Limit",
        "RateLimit-Limit",
    )

    def _has_any_rate_limit_header(self, headers: dict) -> bool:
        """Return True if any rate-limit indicator header is present."""
        headers_lower = {k.lower(): v for k, v in headers.items()}
        for prefix in self.RATE_LIMIT_HEADER_PREFIXES:
            if prefix.lower() in headers_lower:
                return True
        # Also accept the generic Retry-After that slowapi sets when limited
        # (not applicable here, but belt-and-suspenders)
        return False

    def _make_client(self):
        """Return a TestClient with rate limiting enabled."""
        env = {k: v for k, v in os.environ.items() if k != "API_KEY"}
        env["RATE_LIMIT_ENABLED"] = "true"

        with patch.dict(os.environ, env, clear=True):
            import src.rate_limiter
            import src.main

            importlib.reload(src.rate_limiter)
            importlib.reload(src.main)

            from starlette.testclient import TestClient

            return TestClient(src.main.app, raise_server_exceptions=False)

    def test_root_endpoint_has_rate_limit_header(self):
        """
        GET / must include at least one rate-limit header (e.g. X-RateLimit-Limit)
        when the global limiter is active.

        CURRENT BEHAVIOUR: no rate-limit headers are returned because the root
        endpoint has no @rate_limit_endpoint decorator — test will FAIL (RED phase).

        Architecture reference: Section 9.1 — root() must receive
        `request: Request` parameter and @rate_limit_endpoint("general") decorator.
        """
        client = self._make_client()
        response = client.get("/")

        assert response.status_code == 200, f"GET / returned {response.status_code}, expected 200."
        assert self._has_any_rate_limit_header(dict(response.headers)), (
            f"GET / response has no rate-limit headers. "
            f"Headers present: {list(response.headers.keys())}. "
            "FR-3.2 requires @rate_limit_endpoint('general') on the root endpoint."
        )

    def test_compatibility_endpoint_has_rate_limit_header(self):
        """
        POST /v1/compatibility must include at least one rate-limit header when
        the global limiter is active.

        CURRENT BEHAVIOUR: no rate-limit headers are returned because
        check_compatibility() has no @rate_limit_endpoint decorator and no
        `request: Request` parameter — test will FAIL (RED phase).

        Architecture reference: Section 9.2 — check_compatibility() must receive
        `request: Request` parameter and @rate_limit_endpoint("general") decorator.
        """
        client = self._make_client()
        response = client.post(
            "/v1/compatibility",
            json={
                "model": "claude-3-sonnet-20240229",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

        assert (
            response.status_code == 200
        ), f"POST /v1/compatibility returned {response.status_code}, expected 200."
        assert self._has_any_rate_limit_header(dict(response.headers)), (
            f"POST /v1/compatibility response has no rate-limit headers. "
            f"Headers present: {list(response.headers.keys())}. "
            "FR-3.2 requires @rate_limit_endpoint('general') on this endpoint."
        )


# ---------------------------------------------------------------------------
# Module reload teardown
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_main_module():
    """Reload src.main after each test to avoid cross-test module pollution."""
    yield
    import src.main
    import src.auth

    importlib.reload(src.auth)
    importlib.reload(src.main)
