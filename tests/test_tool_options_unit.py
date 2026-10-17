#!/usr/bin/env python3
"""
Unit tests for apply_tool_options in src/main.py.

Covers how enable_tools combines with options extracted from X-Claude-* headers.
These are pure unit tests that don't require a running server.
"""

from unittest.mock import patch

from src.constants import CLAUDE_TOOLS, DEFAULT_ALLOWED_TOOLS
from src.main import apply_tool_options
from src.parameter_validator import ParameterValidator


def headers_to_options(headers):
    return ParameterValidator.extract_claude_headers(headers)


class TestToolsEnabled:
    def test_defaults_without_headers(self):
        options = {}
        with patch("src.main.DEFAULT_DISALLOWED_TOOLS", []):
            apply_tool_options(options, True)
        assert options["allowed_tools"] == DEFAULT_ALLOWED_TOOLS
        assert options["disallowed_tools"] == []
        assert options["permission_mode"] == "bypassPermissions"
        assert "max_turns" not in options

    def test_allowed_tools_header_wins(self):
        options = headers_to_options({"x-claude-allowed-tools": "Read,Grep,Glob"})
        apply_tool_options(options, True)
        assert options["allowed_tools"] == ["Read", "Grep", "Glob"]

    def test_disallowed_tools_header_wins(self):
        options = headers_to_options({"x-claude-disallowed-tools": "Bash"})
        with patch("src.main.DEFAULT_DISALLOWED_TOOLS", ["WebFetch"]):
            apply_tool_options(options, True)
        assert options["disallowed_tools"] == ["Bash"]

    def test_disallowed_tools_env_default_applies(self):
        options = {}
        with patch("src.main.DEFAULT_DISALLOWED_TOOLS", ["Task", "WebFetch"]):
            apply_tool_options(options, True)
        assert options["disallowed_tools"] == ["Task", "WebFetch"]

    def test_permission_mode_header_wins(self):
        options = headers_to_options({"x-claude-permission-mode": "acceptEdits"})
        apply_tool_options(options, True)
        assert options["permission_mode"] == "acceptEdits"

    def test_max_turns_header_kept(self):
        options = headers_to_options({"x-claude-max-turns": "50"})
        apply_tool_options(options, True)
        assert options["max_turns"] == 50

    def test_defaults_are_copies(self):
        options = {}
        apply_tool_options(options, True)
        options["allowed_tools"].append("Task")
        assert "Task" not in DEFAULT_ALLOWED_TOOLS


class TestToolsDisabled:
    def test_forces_qa_mode(self):
        options = {}
        apply_tool_options(options, False)
        assert options["disallowed_tools"] == CLAUDE_TOOLS
        assert options["max_turns"] == 1

    def test_headers_cannot_reenable_tools(self):
        options = headers_to_options(
            {
                "x-claude-max-turns": "50",
                "x-claude-disallowed-tools": "Bash",
            }
        )
        apply_tool_options(options, False)
        assert options["disallowed_tools"] == CLAUDE_TOOLS
        assert options["max_turns"] == 1

    def test_none_treated_as_disabled(self):
        options = {}
        apply_tool_options(options, None)
        assert options["max_turns"] == 1
