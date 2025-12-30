#!/usr/bin/env python3
"""
Unit tests for src/tool_manager.py

Tests the ToolMetadata, ToolConfiguration, and ToolManager classes.
These are pure unit tests that don't require a running server.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import threading
import time

from src.tool_manager import (
    ToolMetadata,
    ToolConfiguration,
    ToolManager,
    TOOL_METADATA,
    tool_manager,
)
from src.constants import CLAUDE_TOOLS, DEFAULT_ALLOWED_TOOLS, DEFAULT_DISALLOWED_TOOLS


class TestToolMetadata:
    """Test the ToolMetadata dataclass."""

    def test_creation_with_required_fields(self):
        """ToolMetadata can be created with just required fields."""
        metadata = ToolMetadata(
            name="TestTool",
            description="A test tool",
            category="test",
        )
        assert metadata.name == "TestTool"
        assert metadata.description == "A test tool"
        assert metadata.category == "test"
        assert metadata.parameters == {}
        assert metadata.examples == []
        assert metadata.is_safe is True
        assert metadata.requires_network is False

    def test_creation_with_all_fields(self):
        """ToolMetadata can be created with all fields."""
        metadata = ToolMetadata(
            name="FullTool",
            description="Full description",
            category="system",
            parameters={"param1": "value1", "param2": "value2"},
            examples=["Example 1", "Example 2"],
            is_safe=False,
            requires_network=True,
        )
        assert metadata.name == "FullTool"
        assert metadata.parameters == {"param1": "value1", "param2": "value2"}
        assert len(metadata.examples) == 2
        assert metadata.is_safe is False
        assert metadata.requires_network is True

    def test_tool_metadata_has_bash_tool(self):
        """TOOL_METADATA contains Bash tool."""
        assert "Bash" in TOOL_METADATA
        bash = TOOL_METADATA["Bash"]
        assert bash.name == "Bash"
        assert bash.category == "system"
        assert "command" in bash.parameters

    def test_tool_metadata_has_read_tool(self):
        """TOOL_METADATA contains Read tool."""
        assert "Read" in TOOL_METADATA
        read = TOOL_METADATA["Read"]
        assert read.name == "Read"
        assert read.category == "file"
        assert read.is_safe is True

    def test_tool_metadata_has_webfetch_tool(self):
        """TOOL_METADATA contains WebFetch tool with network requirement."""
        assert "WebFetch" in TOOL_METADATA
        webfetch = TOOL_METADATA["WebFetch"]
        assert webfetch.requires_network is True

    def test_tool_metadata_task_is_unsafe(self):
        """Task tool is marked as unsafe (can spawn sub-agents)."""
        assert "Task" in TOOL_METADATA
        task = TOOL_METADATA["Task"]
        assert task.is_safe is False
        assert task.category == "agent"


class TestToolConfiguration:
    """Test the ToolConfiguration dataclass."""

    def test_creation_with_defaults(self):
        """ToolConfiguration creates with default values."""
        config = ToolConfiguration()
        assert config.allowed_tools is None
        assert config.disallowed_tools is None
        assert isinstance(config.created_at, datetime)
        assert isinstance(config.updated_at, datetime)

    def test_creation_with_allowed_tools(self):
        """ToolConfiguration can be created with allowed tools."""
        config = ToolConfiguration(allowed_tools=["Bash", "Read", "Write"])
        assert config.allowed_tools == ["Bash", "Read", "Write"]
        assert config.disallowed_tools is None

    def test_creation_with_disallowed_tools(self):
        """ToolConfiguration can be created with disallowed tools."""
        config = ToolConfiguration(disallowed_tools=["Task", "WebSearch"])
        assert config.allowed_tools is None
        assert config.disallowed_tools == ["Task", "WebSearch"]

    def test_creation_with_both_lists(self):
        """ToolConfiguration can have both allowed and disallowed."""
        config = ToolConfiguration(
            allowed_tools=["Bash", "Read", "Write", "Task"],
            disallowed_tools=["Task"],
        )
        assert "Task" in config.allowed_tools
        assert "Task" in config.disallowed_tools

    def test_get_effective_tools_with_allowed_only(self):
        """get_effective_tools uses allowed_tools when set."""
        config = ToolConfiguration(allowed_tools=["Bash", "Read"])
        effective = config.get_effective_tools()
        assert effective == {"Bash", "Read"}

    def test_get_effective_tools_with_disallowed_only(self):
        """get_effective_tools removes disallowed from all tools."""
        config = ToolConfiguration(disallowed_tools=["Task"])
        effective = config.get_effective_tools()
        assert "Task" not in effective
        # Should have most other tools
        assert "Bash" in effective
        assert "Read" in effective

    def test_get_effective_tools_with_both(self):
        """get_effective_tools applies both allowed and disallowed."""
        config = ToolConfiguration(
            allowed_tools=["Bash", "Read", "Write", "Task"],
            disallowed_tools=["Task", "Write"],
        )
        effective = config.get_effective_tools()
        assert effective == {"Bash", "Read"}

    def test_get_effective_tools_defaults_to_all_claude_tools(self):
        """When nothing set, uses all CLAUDE_TOOLS."""
        config = ToolConfiguration()
        effective = config.get_effective_tools()
        assert effective == set(CLAUDE_TOOLS)

    def test_update_sets_allowed_tools(self):
        """update() can set allowed_tools."""
        config = ToolConfiguration()
        original_updated = config.updated_at

        time.sleep(0.001)  # Ensure time difference
        config.update(allowed_tools=["Bash"])

        assert config.allowed_tools == ["Bash"]
        assert config.updated_at > original_updated

    def test_update_sets_disallowed_tools(self):
        """update() can set disallowed_tools."""
        config = ToolConfiguration()
        config.update(disallowed_tools=["Task"])

        assert config.disallowed_tools == ["Task"]

    def test_update_with_none_preserves_existing(self):
        """update() with None doesn't clear existing values."""
        config = ToolConfiguration(allowed_tools=["Bash"])
        config.update(disallowed_tools=["Task"])

        assert config.allowed_tools == ["Bash"]
        assert config.disallowed_tools == ["Task"]


class TestToolManager:
    """Test the ToolManager class."""

    @pytest.fixture
    def manager(self):
        """Create a fresh ToolManager for each test."""
        return ToolManager()

    def test_initialization(self, manager):
        """ToolManager initializes with global config and empty session configs."""
        assert manager.global_config is not None
        assert manager.session_configs == {}
        assert manager.global_config.allowed_tools == list(DEFAULT_ALLOWED_TOOLS)
        assert manager.global_config.disallowed_tools == list(DEFAULT_DISALLOWED_TOOLS)

    def test_get_tool_metadata_existing(self, manager):
        """get_tool_metadata returns metadata for existing tool."""
        metadata = manager.get_tool_metadata("Bash")
        assert metadata is not None
        assert metadata.name == "Bash"
        assert metadata.category == "system"

    def test_get_tool_metadata_nonexistent(self, manager):
        """get_tool_metadata returns None for nonexistent tool."""
        metadata = manager.get_tool_metadata("NonExistentTool")
        assert metadata is None

    def test_list_all_tools(self, manager):
        """list_all_tools returns all tool metadata."""
        tools = manager.list_all_tools()
        assert len(tools) == len(TOOL_METADATA)
        assert all(isinstance(t, ToolMetadata) for t in tools)

    def test_get_global_config(self, manager):
        """get_global_config returns the global configuration."""
        config = manager.get_global_config()
        assert config is manager.global_config

    def test_update_global_config(self, manager):
        """update_global_config updates the global configuration."""
        result = manager.update_global_config(
            allowed_tools=["Bash", "Read"],
            disallowed_tools=["Task"],
        )
        assert result.allowed_tools == ["Bash", "Read"]
        assert result.disallowed_tools == ["Task"]

    def test_get_session_config_nonexistent(self, manager):
        """get_session_config returns None for nonexistent session."""
        config = manager.get_session_config("nonexistent-session")
        assert config is None

    def test_set_session_config_creates_new(self, manager):
        """set_session_config creates new config for session."""
        result = manager.set_session_config(
            session_id="session-123",
            allowed_tools=["Bash"],
        )
        assert result.allowed_tools == ["Bash"]
        assert "session-123" in manager.session_configs

    def test_set_session_config_updates_existing(self, manager):
        """set_session_config updates existing session config."""
        manager.set_session_config("session-123", allowed_tools=["Bash"])
        manager.set_session_config("session-123", disallowed_tools=["Task"])

        config = manager.get_session_config("session-123")
        assert config.allowed_tools == ["Bash"]
        assert config.disallowed_tools == ["Task"]

    def test_delete_session_config_existing(self, manager):
        """delete_session_config removes existing session config."""
        manager.set_session_config("session-123", allowed_tools=["Bash"])
        assert "session-123" in manager.session_configs

        result = manager.delete_session_config("session-123")
        assert result is True
        assert "session-123" not in manager.session_configs

    def test_delete_session_config_nonexistent(self, manager):
        """delete_session_config returns False for nonexistent session."""
        result = manager.delete_session_config("nonexistent")
        assert result is False

    def test_get_effective_config_no_session(self, manager):
        """get_effective_config returns global config when no session."""
        config = manager.get_effective_config()
        assert config is manager.global_config

    def test_get_effective_config_with_session(self, manager):
        """get_effective_config returns session config when exists."""
        manager.set_session_config("session-123", allowed_tools=["Bash"])
        config = manager.get_effective_config("session-123")

        assert config is not manager.global_config
        assert config.allowed_tools == ["Bash"]

    def test_get_effective_config_missing_session_uses_global(self, manager):
        """get_effective_config uses global when session doesn't exist."""
        config = manager.get_effective_config("nonexistent")
        assert config is manager.global_config

    def test_get_effective_tools_global(self, manager):
        """get_effective_tools returns sorted list from global config."""
        manager.update_global_config(allowed_tools=["Write", "Bash", "Read"])
        tools = manager.get_effective_tools()

        assert tools == ["Bash", "Read", "Write"]  # Sorted

    def test_get_effective_tools_session(self, manager):
        """get_effective_tools returns tools from session config."""
        manager.set_session_config("session-123", allowed_tools=["Grep", "Glob"])
        tools = manager.get_effective_tools("session-123")

        assert tools == ["Glob", "Grep"]  # Sorted

    def test_validate_tools_all_valid(self, manager):
        """validate_tools returns True for valid tools."""
        result = manager.validate_tools(["Bash", "Read", "Write"])
        assert result == {"Bash": True, "Read": True, "Write": True}

    def test_validate_tools_some_invalid(self, manager):
        """validate_tools returns False for invalid tools."""
        result = manager.validate_tools(["Bash", "FakeTool", "Read"])
        assert result == {"Bash": True, "FakeTool": False, "Read": True}

    def test_validate_tools_empty_list(self, manager):
        """validate_tools handles empty list."""
        result = manager.validate_tools([])
        assert result == {}

    def test_get_stats(self, manager):
        """get_stats returns statistics about tools."""
        # Add some session configs
        manager.set_session_config("session-1", allowed_tools=["Bash"])
        manager.set_session_config("session-2", allowed_tools=["Read"])

        stats = manager.get_stats()

        assert stats["total_tools"] == len(CLAUDE_TOOLS)
        assert stats["session_configs"] == 2
        assert "tool_categories" in stats
        assert "file" in stats["tool_categories"]
        assert "system" in stats["tool_categories"]

    def test_global_allowed_count_in_stats(self, manager):
        """get_stats shows correct global allowed count."""
        manager.update_global_config(allowed_tools=["Bash", "Read", "Write"])
        stats = manager.get_stats()
        assert stats["global_allowed"] == 3

    def test_global_disallowed_count_in_stats(self, manager):
        """get_stats shows correct global disallowed count."""
        manager.update_global_config(disallowed_tools=["Task", "WebSearch"])
        stats = manager.get_stats()
        assert stats["global_disallowed"] == 2


class TestToolManagerThreadSafety:
    """Test thread safety of ToolManager operations."""

    @pytest.fixture
    def manager(self):
        """Create a fresh ToolManager for each test."""
        return ToolManager()

    def test_concurrent_session_creation(self, manager):
        """Multiple threads can create session configs concurrently."""
        results = []
        errors = []

        def create_session(session_id):
            try:
                manager.set_session_config(session_id, allowed_tools=["Bash"])
                results.append(session_id)
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(20):
            t = threading.Thread(target=create_session, args=(f"session-{i}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 20
        assert len(manager.session_configs) == 20

    def test_concurrent_config_updates(self, manager):
        """Multiple threads can update global config concurrently."""
        errors = []

        def update_config(tool_name):
            try:
                manager.update_global_config(allowed_tools=[tool_name])
            except Exception as e:
                errors.append(str(e))

        threads = []
        tools = ["Bash", "Read", "Write", "Edit", "Glob"]
        for tool in tools:
            t = threading.Thread(target=update_config, args=(tool,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0
        # One of the tools should be set (last one to update wins)
        assert manager.global_config.allowed_tools is not None


class TestToolMetadataCategories:
    """Test tool categories in TOOL_METADATA."""

    def test_file_tools_category(self):
        """File tools are correctly categorized."""
        file_tools = ["Glob", "Grep", "Read", "Edit", "Write", "NotebookEdit"]
        for tool_name in file_tools:
            assert TOOL_METADATA[tool_name].category == "file"

    def test_system_tools_category(self):
        """System tools are correctly categorized."""
        system_tools = ["Bash", "BashOutput", "KillShell"]
        for tool_name in system_tools:
            assert TOOL_METADATA[tool_name].category == "system"

    def test_web_tools_category(self):
        """Web tools are correctly categorized."""
        web_tools = ["WebFetch", "WebSearch"]
        for tool_name in web_tools:
            assert TOOL_METADATA[tool_name].category == "web"
            assert TOOL_METADATA[tool_name].requires_network is True

    def test_productivity_tools_category(self):
        """Productivity tools are correctly categorized."""
        productivity_tools = ["TodoWrite", "Skill", "SlashCommand"]
        for tool_name in productivity_tools:
            assert TOOL_METADATA[tool_name].category == "productivity"

    def test_agent_tools_category(self):
        """Agent tools are correctly categorized."""
        assert TOOL_METADATA["Task"].category == "agent"


class TestGlobalToolManagerInstance:
    """Test the global tool_manager instance."""

    def test_global_instance_exists(self):
        """Global tool_manager instance is available."""
        assert tool_manager is not None
        assert isinstance(tool_manager, ToolManager)

    def test_global_instance_has_default_config(self):
        """Global instance has default configuration."""
        assert tool_manager.global_config is not None
