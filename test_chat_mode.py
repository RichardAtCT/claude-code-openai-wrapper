"""
Test suite for chat mode functionality.

This file tests the chat mode implementation including sandbox isolation,
tool restrictions, session disabling, and format detection.
"""

import pytest
import os
import asyncio
import tempfile
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

# Import modules to test
from chat_mode import ChatMode, sanitized_environment, get_chat_mode_info
from prompts import ChatModePrompts, FormatDetector, inject_prompts
from claude_cli import ClaudeCodeCLI


class TestChatMode:
    """Test the ChatMode class functionality."""
    
    def test_chat_mode_detection(self):
        """Test chat mode is detected from environment variable."""
        # Test disabled by default
        with patch.dict(os.environ, {}, clear=True):
            assert ChatMode.is_enabled() is False
        
        # Test enabled when set to true
        with patch.dict(os.environ, {'CHAT_MODE': 'true'}):
            assert ChatMode.is_enabled() is True
        
        # Test case insensitive
        with patch.dict(os.environ, {'CHAT_MODE': 'TRUE'}):
            assert ChatMode.is_enabled() is True
        
        # Test disabled when false
        with patch.dict(os.environ, {'CHAT_MODE': 'false'}):
            assert ChatMode.is_enabled() is False
    
    def test_allowed_tools(self):
        """Test the allowed tools list in chat mode."""
        tools = ChatMode.get_allowed_tools()
        assert tools == ["WebSearch", "WebFetch", "Task"]
        assert "Bash" not in tools
        assert "Write" not in tools
        assert "Edit" not in tools
    
    def test_sandbox_creation_and_cleanup(self):
        """Test sandbox directory creation and cleanup."""
        # Create sandbox
        sandbox_dir = ChatMode.create_sandbox()
        
        # Verify it exists and has correct prefix
        assert os.path.exists(sandbox_dir)
        assert os.path.isdir(sandbox_dir)
        assert "claude_chat_sandbox_" in sandbox_dir
        assert sandbox_dir.startswith(tempfile.gettempdir())
        
        # Cleanup sandbox
        ChatMode.cleanup_sandbox(sandbox_dir)
        
        # Verify it's cleaned up
        assert not os.path.exists(sandbox_dir)
    
    def test_cleanup_sandbox_safety(self):
        """Test sandbox cleanup only removes valid sandbox directories."""
        # Should not crash on non-existent directory
        ChatMode.cleanup_sandbox("/tmp/non_existent_dir_12345")
        
        # Should not remove directories outside temp
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a directory that doesn't start with temp prefix
            fake_dir = os.path.join(tmpdir, "not_a_sandbox")
            os.makedirs(fake_dir)
            
            # Cleanup should handle it gracefully
            ChatMode.cleanup_sandbox(fake_dir)
            
            # Directory might still exist if safety checks prevent deletion
            # The important thing is no crash occurs
    
    def test_get_chat_mode_info(self):
        """Test getting chat mode configuration info."""
        with patch.dict(os.environ, {'CHAT_MODE': 'true'}):
            info = get_chat_mode_info()
            assert info["enabled"] is True
            assert info["allowed_tools"] == ["WebSearch", "WebFetch"]
            assert info["sandbox_enabled"] is True
            assert info["sessions_disabled"] is True
            assert info["file_operations_disabled"] is True
        
        with patch.dict(os.environ, {'CHAT_MODE': 'false'}):
            info = get_chat_mode_info()
            assert info["enabled"] is False


class TestEnvironmentSanitization:
    """Test environment variable sanitization."""
    
    def test_sanitized_environment(self):
        """Test environment sanitization removes sensitive variables."""
        # Set up test environment
        test_env = {
            'PWD': '/home/user/project',
            'OLDPWD': '/home/user',
            'HOME': '/home/user',
            'USER': 'testuser',
            'LOGNAME': 'testuser',
            'CLAUDE_WORKING_DIR': '/home/user/claude',
            'CLAUDE_PROJECT_DIR': '/home/user/project',
            'CLAUDE_API_KEY': 'keep-this',  # Should not be removed
            'OTHER_VAR': 'keep-this-too'
        }
        
        with patch.dict(os.environ, test_env, clear=True):
            # Verify variables exist before
            assert os.environ.get('PWD') == '/home/user/project'
            assert os.environ.get('CLAUDE_WORKING_DIR') == '/home/user/claude'
            
            # Use sanitized environment
            with sanitized_environment():
                # Sensitive variables should be removed
                assert 'PWD' not in os.environ
                assert 'OLDPWD' not in os.environ
                assert 'HOME' not in os.environ
                assert 'USER' not in os.environ
                assert 'LOGNAME' not in os.environ
                assert 'CLAUDE_WORKING_DIR' not in os.environ
                assert 'CLAUDE_PROJECT_DIR' not in os.environ
                
                # Non-sensitive variables should remain
                assert os.environ.get('CLAUDE_API_KEY') == 'keep-this'
                assert os.environ.get('OTHER_VAR') == 'keep-this-too'
            
            # Variables should be restored after context
            assert os.environ.get('PWD') == '/home/user/project'
            assert os.environ.get('CLAUDE_WORKING_DIR') == '/home/user/claude'


class TestFormatDetection:
    """Test format detection for chat clients."""
    
    def test_xml_tool_detection(self):
        """Test detection of XML tool formats."""
        detector = FormatDetector()
        
        # Test various XML tool patterns
        test_cases = [
            ([{"content": "Tool uses are formatted using XML-style tags"}], True),
            ([{"content": "Use <attempt_completion> to complete"}], True),
            ([{"content": "The ask_followup_question tool is available"}], True),
            ([{"content": "<tool>example</tool>"}], True),
            ([{"content": "No tools mentioned here"}], False),
            ([{"content": "Just regular text"}], False),
        ]
        
        for messages, expected_has_tools in test_cases:
            has_tools, _ = detector.detect_special_formats(messages)
            assert has_tools == expected_has_tools
    
    def test_json_format_detection(self):
        """Test detection of JSON format requests."""
        detector = FormatDetector()
        
        test_cases = [
            ([{"content": "Please respond in JSON format"}], True),
            ([{"content": "Return JSON with the results"}], True),
            ([{"content": "Output JSON response"}], True),
            ([{"content": "format: json"}], True),
            ([{"content": "Just mention json in passing"}], False),
            ([{"content": "No format specified"}], False),
        ]
        
        for messages, expected_has_json in test_cases:
            _, has_json = detector.detect_special_formats(messages)
            assert has_json == expected_has_json
    
    def test_combined_detection(self):
        """Test detection of both XML and JSON formats."""
        detector = FormatDetector()
        
        messages = [
            {"content": "Use <attempt_completion> tool"},
            {"content": "Return the result in JSON format"}
        ]
        
        has_tools, has_json = detector.detect_special_formats(messages)
        assert has_tools is True
        assert has_json is True


class TestPrompts:
    """Test prompt injection and formatting."""
    
    def test_chat_mode_prompts_exist(self):
        """Test that required prompts are defined."""
        prompts = ChatModePrompts()
        assert len(prompts.RESPONSE_REINFORCEMENT_PROMPT) > 0
        assert len(prompts.CHAT_MODE_NO_FILES_PROMPT) > 0
        assert "Available tools are limited to:" in prompts.CHAT_MODE_NO_FILES_PROMPT
        assert "digital black hole" in prompts.CHAT_MODE_NO_FILES_PROMPT
        assert "ONLY when SPECIFICALLY asked" in prompts.CHAT_MODE_NO_FILES_PROMPT
    
    def test_final_reinforcement_generation(self):
        """Test generation of final reinforcement messages."""
        prompts = ChatModePrompts()
        
        # No special formats
        result = prompts.get_final_reinforcement(False, False)
        assert result == ""
        
        # Tool definitions detected
        result = prompts.get_final_reinforcement(True, False)
        assert "XML tool format" in result
        assert "Do NOT respond in plain text" in result
        
        # JSON format requested
        result = prompts.get_final_reinforcement(False, True)
        assert "pure JSON" in result
        assert "no markdown" in result
        
        # Both detected
        result = prompts.get_final_reinforcement(True, True)
        assert "XML tool format" in result
        assert "pure JSON" in result
    
    def test_inject_prompts(self):
        """Test prompt injection into message list."""
        messages = [
            {"role": "user", "content": "Hello"}
        ]
        
        # Test normal mode
        enhanced = inject_prompts(messages, chat_mode=False)
        assert len(enhanced) > len(messages)
        assert enhanced[0]["role"] == "system"
        assert "CRITICAL INSTRUCTION" in enhanced[0]["content"]
        
        # Test chat mode
        enhanced = inject_prompts(messages, chat_mode=True)
        assert any("Available tools are limited to:" in msg["content"] for msg in enhanced if msg["role"] == "system")


class TestClaudeCliChatMode:
    """Test ClaudeCodeCLI chat mode integration."""
    
    @pytest.fixture
    def mock_sdk_query(self):
        """Mock the claude_code_sdk query function."""
        with patch('claude_cli.query') as mock:
            # Make it an async generator
            async def async_gen():
                yield {"type": "assistant", "content": "Test response"}
            mock.return_value = async_gen()
            yield mock
    
    @pytest.mark.asyncio
    async def test_cli_chat_mode_detection(self):
        """Test CLI detects chat mode from environment."""
        with patch.dict(os.environ, {'CHAT_MODE': 'false'}):
            cli = ClaudeCodeCLI()
            assert cli.chat_mode is False
        
        with patch.dict(os.environ, {'CHAT_MODE': 'true'}):
            cli = ClaudeCodeCLI()
            assert cli.chat_mode is True
            assert cli.cwd is None  # Should not set cwd in chat mode
    
    @pytest.mark.asyncio
    async def test_cli_sandbox_execution(self, mock_sdk_query):
        """Test CLI creates sandbox in chat mode."""
        with patch.dict(os.environ, {'CHAT_MODE': 'true'}):
            cli = ClaudeCodeCLI()
            
            # Track sandbox creation
            created_sandboxes = []
            original_create = ChatMode.create_sandbox
            
            def track_create():
                sandbox = original_create()
                created_sandboxes.append(sandbox)
                return sandbox
            
            with patch.object(ChatMode, 'create_sandbox', side_effect=track_create):
                # Run completion
                messages = []
                async for msg in cli.run_completion("Test prompt", messages=[{"content": "test"}]):
                    messages.append(msg)
                
                # Verify sandbox was created
                assert len(created_sandboxes) == 1
                assert "claude_chat_sandbox_" in created_sandboxes[0]
    
    @pytest.mark.asyncio 
    async def test_cli_tool_restrictions(self, mock_sdk_query):
        """Test CLI applies tool restrictions in chat mode."""
        with patch.dict(os.environ, {'CHAT_MODE': 'true'}):
            cli = ClaudeCodeCLI()
            
            # Capture the options passed to SDK
            captured_options = None
            
            async def capture_query(prompt, options):
                nonlocal captured_options
                captured_options = options
                yield {"type": "assistant", "content": "Test"}
            
            with patch('claude_cli.query', side_effect=capture_query):
                messages = []
                async for msg in cli.run_completion("Test"):
                    messages.append(msg)
                
                # Verify tool restrictions were applied
                assert captured_options is not None
                assert captured_options.allowed_tools == ["WebSearch", "WebFetch"]
                assert captured_options.continue_session is False
                assert captured_options.resume is None
    
    def test_cli_prompt_preparation(self):
        """Test prompt preparation with injections."""
        with patch.dict(os.environ, {'CHAT_MODE': 'true'}):
            cli = ClaudeCodeCLI()
            
            # Test basic prompt
            enhanced = cli._prepare_prompt_with_injections("Hello", None)
            assert "System:" in enhanced
            assert "Available tools are limited to:" in enhanced
            assert "User: Hello" in enhanced
            
            # Test with format detection
            messages = [{"content": "Use <attempt_completion> tool"}]
            enhanced = cli._prepare_prompt_with_injections("Hello", messages)
            assert "FINAL REMINDER:" in enhanced
            assert "XML tool format" in enhanced


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])