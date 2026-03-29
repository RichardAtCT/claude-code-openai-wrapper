#!/usr/bin/env python3
"""
Unit tests for new security configuration constants in src/constants.py.

Tests default values and environment variable override behavior for:
  - MAX_SESSIONS         (FR-6.1)
  - MAX_SESSION_MESSAGES (FR-6.2)
  - TRUSTED_PROXIES      (FR-3.1)
  - CLAUDE_CWD_ALLOWED_BASE (FR-5.1)

These are pure unit tests with no I/O or external dependencies.
"""

import importlib
import os
import tempfile
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_constants():
    """Reload src.constants so module-level os.getenv() calls re-evaluate."""
    import src.constants

    importlib.reload(src.constants)
    return src.constants


# ---------------------------------------------------------------------------
# MAX_SESSIONS
# ---------------------------------------------------------------------------


class TestMaxSessionsConstant:
    """Tests for MAX_SESSIONS constant (FR-6.1)."""

    def test_max_sessions_default_is_1000(self):
        """MAX_SESSIONS defaults to 1000 when env var is not set."""
        env = {k: v for k, v in os.environ.items() if k != "MAX_SESSIONS"}
        with patch.dict(os.environ, env, clear=True):
            constants = _reload_constants()
            assert constants.MAX_SESSIONS == 1000

    def test_max_sessions_default_is_integer(self):
        """MAX_SESSIONS default value is an int, not a string."""
        env = {k: v for k, v in os.environ.items() if k != "MAX_SESSIONS"}
        with patch.dict(os.environ, env, clear=True):
            constants = _reload_constants()
            assert isinstance(constants.MAX_SESSIONS, int)

    def test_max_sessions_can_be_overridden_via_env(self):
        """MAX_SESSIONS can be set to a custom value via environment variable."""
        with patch.dict(os.environ, {"MAX_SESSIONS": "500"}):
            constants = _reload_constants()
            assert constants.MAX_SESSIONS == 500

    def test_max_sessions_env_override_is_integer(self):
        """MAX_SESSIONS env var override is parsed to int, not kept as string."""
        with patch.dict(os.environ, {"MAX_SESSIONS": "250"}):
            constants = _reload_constants()
            assert isinstance(constants.MAX_SESSIONS, int)


# ---------------------------------------------------------------------------
# MAX_SESSION_MESSAGES
# ---------------------------------------------------------------------------


class TestMaxSessionMessagesConstant:
    """Tests for MAX_SESSION_MESSAGES constant (FR-6.2)."""

    def test_max_session_messages_default_is_100(self):
        """MAX_SESSION_MESSAGES defaults to 100 when env var is not set."""
        env = {k: v for k, v in os.environ.items() if k != "MAX_SESSION_MESSAGES"}
        with patch.dict(os.environ, env, clear=True):
            constants = _reload_constants()
            assert constants.MAX_SESSION_MESSAGES == 100

    def test_max_session_messages_default_is_integer(self):
        """MAX_SESSION_MESSAGES default value is an int, not a string."""
        env = {k: v for k, v in os.environ.items() if k != "MAX_SESSION_MESSAGES"}
        with patch.dict(os.environ, env, clear=True):
            constants = _reload_constants()
            assert isinstance(constants.MAX_SESSION_MESSAGES, int)

    def test_max_session_messages_can_be_overridden_via_env(self):
        """MAX_SESSION_MESSAGES can be set to a custom value via environment variable."""
        with patch.dict(os.environ, {"MAX_SESSION_MESSAGES": "50"}):
            constants = _reload_constants()
            assert constants.MAX_SESSION_MESSAGES == 50

    def test_max_session_messages_env_override_is_integer(self):
        """MAX_SESSION_MESSAGES env var override is parsed to int, not kept as string."""
        with patch.dict(os.environ, {"MAX_SESSION_MESSAGES": "25"}):
            constants = _reload_constants()
            assert isinstance(constants.MAX_SESSION_MESSAGES, int)


# ---------------------------------------------------------------------------
# TRUSTED_PROXIES
# ---------------------------------------------------------------------------


class TestTrustedProxiesConstant:
    """Tests for TRUSTED_PROXIES constant (FR-3.1)."""

    def test_trusted_proxies_default_is_empty_list(self):
        """TRUSTED_PROXIES defaults to an empty list when env var is not set."""
        env = {k: v for k, v in os.environ.items() if k != "TRUSTED_PROXIES"}
        with patch.dict(os.environ, env, clear=True):
            constants = _reload_constants()
            assert constants.TRUSTED_PROXIES == []

    def test_trusted_proxies_default_is_list_type(self):
        """TRUSTED_PROXIES default value is a list, not a string or None."""
        env = {k: v for k, v in os.environ.items() if k != "TRUSTED_PROXIES"}
        with patch.dict(os.environ, env, clear=True):
            constants = _reload_constants()
            assert isinstance(constants.TRUSTED_PROXIES, list)

    def test_trusted_proxies_single_ip_override(self):
        """TRUSTED_PROXIES can be set to a single IP via environment variable."""
        with patch.dict(os.environ, {"TRUSTED_PROXIES": "10.0.0.1"}):
            constants = _reload_constants()
            assert constants.TRUSTED_PROXIES == ["10.0.0.1"]

    def test_trusted_proxies_multiple_ips_override(self):
        """TRUSTED_PROXIES parses comma-separated IPs into a list of two entries."""
        with patch.dict(os.environ, {"TRUSTED_PROXIES": "10.0.0.1,10.0.0.2"}):
            constants = _reload_constants()
            assert constants.TRUSTED_PROXIES == ["10.0.0.1", "10.0.0.2"]

    def test_trusted_proxies_env_override_is_list_type(self):
        """TRUSTED_PROXIES env var override is parsed to a list, not left as a string."""
        with patch.dict(os.environ, {"TRUSTED_PROXIES": "192.168.1.1,192.168.1.2"}):
            constants = _reload_constants()
            assert isinstance(constants.TRUSTED_PROXIES, list)

    def test_trusted_proxies_empty_env_var_gives_empty_list(self):
        """An explicitly empty TRUSTED_PROXIES env var results in an empty list."""
        with patch.dict(os.environ, {"TRUSTED_PROXIES": ""}):
            constants = _reload_constants()
            assert constants.TRUSTED_PROXIES == []


# ---------------------------------------------------------------------------
# CLAUDE_CWD_ALLOWED_BASE
# ---------------------------------------------------------------------------


class TestClaudeCwdAllowedBaseConstant:
    """Tests for CLAUDE_CWD_ALLOWED_BASE constant (FR-5.1)."""

    def test_claude_cwd_allowed_base_default_is_tempdir(self):
        """CLAUDE_CWD_ALLOWED_BASE defaults to the system temp directory."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CWD_ALLOWED_BASE"}
        with patch.dict(os.environ, env, clear=True):
            constants = _reload_constants()
            assert constants.CLAUDE_CWD_ALLOWED_BASE == tempfile.gettempdir()

    def test_claude_cwd_allowed_base_default_is_string(self):
        """CLAUDE_CWD_ALLOWED_BASE default value is a string."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CWD_ALLOWED_BASE"}
        with patch.dict(os.environ, env, clear=True):
            constants = _reload_constants()
            assert isinstance(constants.CLAUDE_CWD_ALLOWED_BASE, str)

    def test_claude_cwd_allowed_base_can_be_overridden_via_env(self):
        """CLAUDE_CWD_ALLOWED_BASE can be set to a custom path via environment variable."""
        with patch.dict(os.environ, {"CLAUDE_CWD_ALLOWED_BASE": "/custom/path"}):
            constants = _reload_constants()
            assert constants.CLAUDE_CWD_ALLOWED_BASE == "/custom/path"

    def test_claude_cwd_allowed_base_env_override_is_string(self):
        """CLAUDE_CWD_ALLOWED_BASE env var override remains a string."""
        with patch.dict(os.environ, {"CLAUDE_CWD_ALLOWED_BASE": "/srv/app/workspaces"}):
            constants = _reload_constants()
            assert isinstance(constants.CLAUDE_CWD_ALLOWED_BASE, str)


# ---------------------------------------------------------------------------
# Module-level cleanup fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_constants_module():
    """Reload constants module after each test to restore default state.

    This prevents env var patches from leaking between tests via the
    module-level os.getenv() calls evaluated at import time.
    """
    yield
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "MAX_SESSIONS",
            "MAX_SESSION_MESSAGES",
            "TRUSTED_PROXIES",
            "CLAUDE_CWD_ALLOWED_BASE",
        )
    }
    with patch.dict(os.environ, env, clear=True):
        _reload_constants()
