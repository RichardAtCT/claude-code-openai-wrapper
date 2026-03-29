#!/usr/bin/env python3
"""
Unit tests for CORS middleware configuration in src/main.py.

FR-1.1: When CORS_ORIGINS is ["*"] (the default), allow_credentials must NOT
be True.  When CORS_ORIGINS contains specific origins, allow_credentials=True
is permitted so that credentialed requests work from those trusted origins.

The CORS middleware is configured at module load time in src/main.py:

    cors_origins = json.loads(os.getenv("CORS_ORIGINS", '["*"]'))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,   # <-- BUG: always True
        ...
    )

Tests use importlib.reload to force src.main to re-read CORS_ORIGINS from
the environment, exactly as test_auth_unit.py and test_rate_limiter_unit.py
do for their environment-variable-driven configurations.

The src.main lifespan startup (SDK verification) is bypassed by using
TestClient without a context-manager entry — TestClient only runs lifespan
startup/shutdown when used as a context manager.

Architecture reference: FR-1.1, KD-1, Section 7.1.
"""

import importlib
import os

import pytest
from starlette.testclient import TestClient
from unittest.mock import patch, AsyncMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_test_client_for_cors_origins(cors_origins_json: str) -> TestClient:
    """Reload src.main with CORS_ORIGINS set to the given JSON string and
    return a TestClient wrapping the freshly constructed app.

    The Claude CLI verify_cli call is patched out so the reload completes
    without network I/O.  TestClient is NOT used as a context manager so the
    lifespan startup (SDK connection) is not triggered.
    """
    with patch.dict(os.environ, {"CORS_ORIGINS": cors_origins_json}):
        with patch(
            "src.claude_cli.ClaudeCodeCLI.verify_cli",
            new_callable=AsyncMock,
            return_value=True,
        ):
            import src.main

            importlib.reload(src.main)
            app = src.main.app

    # TestClient without __enter__ skips lifespan
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Tests: default CORS config (wildcard origins)
# ---------------------------------------------------------------------------


class TestCorsWildcardOrigins:
    """Verify that the default CORS configuration (CORS_ORIGINS=["*"]) does
    NOT set allow_credentials=True.

    Combining allow_origins=["*"] with allow_credentials=True is a security
    misconfiguration: browsers refuse such a combination, and Starlette works
    around it by echoing the requesting origin back — effectively granting
    all origins credential access.

    Both tests in this class MUST FAIL against the current implementation
    (which hardcodes allow_credentials=True) and MUST PASS after FR-1.1 is
    implemented (which sets allow_credentials=False for wildcard origins).
    """

    @pytest.fixture
    def client(self):
        """TestClient configured with the default wildcard CORS_ORIGINS."""
        return _get_test_client_for_cors_origins('["*"]')

    def test_wildcard_cors_preflight_does_not_return_allow_credentials_true(self, client):
        """Preflight from any origin must NOT get Access-Control-Allow-Credentials: true
        when CORS_ORIGINS is ["*"].

        This directly verifies FR-1.1: the combination of wildcard origins and
        allow_credentials=True must not exist in the default configuration.

        Current code returns 'true' → test FAILS (RED).
        Fixed code omits the header → test PASSES (GREEN).
        """
        response = client.options(
            "/health",
            headers={
                "Origin": "http://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )

        allow_credentials_header = response.headers.get("access-control-allow-credentials")

        assert allow_credentials_header != "true", (
            "Security misconfiguration: Access-Control-Allow-Credentials must not be "
            "'true' when allow_origins is ['*'].  Browsers reject this combination and "
            "Starlette silently echoes the requesting origin, exposing credentials to "
            "every origin unconditionally.  Set allow_credentials=False when using "
            "wildcard origins."
        )

    def test_wildcard_cors_preflight_returns_wildcard_origin_header(self, client):
        """Preflight response must include Access-Control-Allow-Origin: * (the literal
        wildcard string) when CORS_ORIGINS is ["*"] and allow_credentials is False.

        When allow_credentials=True is combined with wildcard origins, Starlette echoes
        the requesting origin back instead of the '*' wildcard.  This is the observable
        symptom of the misconfiguration: any origin appears allowed with credentials.
        After the fix (allow_credentials=False), Starlette correctly returns '*'.

        Current code echoes 'http://evil.com' → test FAILS (RED).
        Fixed code returns '*' → test PASSES (GREEN).
        """
        response = client.options(
            "/health",
            headers={
                "Origin": "http://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )

        allow_origin_header = response.headers.get("access-control-allow-origin")

        assert allow_origin_header == "*", (
            f"Expected Access-Control-Allow-Origin: * for default (wildcard) CORS config, "
            f"but received: {allow_origin_header!r}.  The echoed origin indicates that "
            f"allow_credentials=True is still set, which causes Starlette to replace '*' "
            f"with the actual requesting origin — an unintended side-effect."
        )


# ---------------------------------------------------------------------------
# Tests: custom CORS config (specific origin list)
# ---------------------------------------------------------------------------


class TestCorsSpecificOrigins:
    """Verify that a custom CORS config with specific origins DOES set
    allow_credentials=True so that browsers accept credentialed requests.

    This is the positive counterpart to TestCorsWildcardOrigins: operators who
    have restricted CORS to specific trusted origins must retain the ability to
    make credentialed requests from those origins.

    The test in this class should PASS against both the current (broken) code
    and the fixed code, serving as a non-regression guard to ensure the fix
    does not inadvertently break specific-origin configurations.
    """

    @pytest.fixture
    def client(self):
        """TestClient configured with a specific trusted origin."""
        return _get_test_client_for_cors_origins('["http://localhost:3000"]')

    def test_specific_origins_preflight_from_allowed_origin_returns_allow_credentials_true(
        self, client
    ):
        """Preflight from an explicitly allowed origin MUST get both the correct
        Access-Control-Allow-Origin header and Access-Control-Allow-Credentials: true
        when CORS_ORIGINS contains that origin.

        FR-1.1 acceptance criterion: 'Existing CORS_ORIGINS env var override still works.'
        The fix must only remove credentials from the wildcard case, not from specific
        origin configurations.
        """
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        allow_origin_header = response.headers.get("access-control-allow-origin")
        allow_credentials_header = response.headers.get("access-control-allow-credentials")

        assert allow_origin_header == "http://localhost:3000", (
            f"Expected Access-Control-Allow-Origin: http://localhost:3000 for a "
            f"specific-origins CORS config, got: {allow_origin_header!r}"
        )
        assert allow_credentials_header == "true", (
            "Expected Access-Control-Allow-Credentials: true for a specific-origins CORS "
            "config.  Operators who restrict CORS to trusted origins must be able to use "
            "credentialed requests (cookies, Authorization headers)."
        )


# ---------------------------------------------------------------------------
# Module reset fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_main_module():
    """Reload src.main after each test to prevent state leaking between tests.

    CORS_ORIGINS is read at module load time, so each reload must have a clean
    environment.  The same pattern is used in test_auth_unit.py and
    test_rate_limiter_unit.py.
    """
    yield
    with patch(
        "src.claude_cli.ClaudeCodeCLI.verify_cli",
        new_callable=AsyncMock,
        return_value=True,
    ):
        import src.main

        importlib.reload(src.main)
