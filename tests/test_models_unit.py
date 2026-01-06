#!/usr/bin/env python3
"""
Unit tests for src/models.py

Tests all Pydantic models including validators and methods.
These are pure unit tests that don't require a running server.
"""

import pytest
from datetime import datetime
from unittest.mock import patch

from src.models import (
    ContentPart,
    Message,
    StreamOptions,
    ChatCompletionRequest,
    Choice,
    Usage,
    ChatCompletionResponse,
    StreamChoice,
    ChatCompletionStreamResponse,
    ErrorDetail,
    ErrorResponse,
    SessionInfo,
    SessionListResponse,
    ToolMetadataResponse,
    ToolListResponse,
    ToolConfigurationResponse,
    ToolConfigurationRequest,
    ToolValidationResponse,
    MCPServerConfigRequest,
    MCPServerInfoResponse,
    MCPServersListResponse,
    MCPConnectionRequest,
    MCPToolCallRequest,
    AnthropicTextBlock,
    AnthropicMessage,
    AnthropicMessagesRequest,
    AnthropicUsage,
    AnthropicMessagesResponse,
)


class TestContentPart:
    """Test ContentPart model."""

    def test_create_text_content_part(self):
        """Can create a text content part."""
        part = ContentPart(type="text", text="Hello world")
        assert part.type == "text"
        assert part.text == "Hello world"


class TestMessage:
    """Test Message model."""

    def test_create_user_message(self):
        """Can create a user message."""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_create_assistant_message(self):
        """Can create an assistant message."""
        msg = Message(role="assistant", content="Hi there")
        assert msg.role == "assistant"
        assert msg.content == "Hi there"

    def test_create_system_message(self):
        """Can create a system message."""
        msg = Message(role="system", content="You are helpful")
        assert msg.role == "system"
        assert msg.content == "You are helpful"

    def test_message_with_name(self):
        """Can create a message with a name."""
        msg = Message(role="user", content="Hello", name="alice")
        assert msg.name == "alice"

    def test_message_normalizes_array_content(self):
        """Array content is normalized to string."""
        content_parts = [
            ContentPart(type="text", text="Part 1"),
            ContentPart(type="text", text="Part 2"),
        ]
        msg = Message(role="user", content=content_parts)
        assert msg.content == "Part 1\nPart 2"

    def test_message_normalizes_dict_content(self):
        """Dict content parts are normalized to string."""
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"},
        ]
        msg = Message(role="user", content=content)
        assert msg.content == "Hello\nWorld"

    def test_empty_array_content_becomes_empty_string(self):
        """Empty array content becomes empty string."""
        msg = Message(role="user", content=[])
        assert msg.content == ""


class TestStreamOptions:
    """Test StreamOptions model."""

    def test_default_include_usage_is_false(self):
        """Default include_usage is False."""
        options = StreamOptions()
        assert options.include_usage is False

    def test_can_set_include_usage(self):
        """Can set include_usage to True."""
        options = StreamOptions(include_usage=True)
        assert options.include_usage is True


class TestChatCompletionRequest:
    """Test ChatCompletionRequest model."""

    def test_minimal_request(self):
        """Can create request with just messages."""
        request = ChatCompletionRequest(messages=[Message(role="user", content="Hi")])
        assert len(request.messages) == 1

    def test_default_model(self):
        """Default model is set from constants."""
        request = ChatCompletionRequest(messages=[Message(role="user", content="Hi")])
        assert request.model is not None

    def test_temperature_range_validation(self):
        """Temperature must be between 0 and 2."""
        # Valid range
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hi")], temperature=1.5
        )
        assert request.temperature == 1.5

        # Invalid - too high
        with pytest.raises(ValueError):
            ChatCompletionRequest(messages=[Message(role="user", content="Hi")], temperature=3.0)

        # Invalid - too low
        with pytest.raises(ValueError):
            ChatCompletionRequest(messages=[Message(role="user", content="Hi")], temperature=-1.0)

    def test_top_p_range_validation(self):
        """top_p must be between 0 and 1."""
        request = ChatCompletionRequest(messages=[Message(role="user", content="Hi")], top_p=0.5)
        assert request.top_p == 0.5

        with pytest.raises(ValueError):
            ChatCompletionRequest(messages=[Message(role="user", content="Hi")], top_p=1.5)

    def test_n_must_be_1(self):
        """n > 1 raises validation error."""
        with pytest.raises(ValueError) as exc_info:
            ChatCompletionRequest(messages=[Message(role="user", content="Hi")], n=3)
        assert "multiple choices" in str(exc_info.value).lower()

    def test_presence_penalty_range(self):
        """presence_penalty must be between -2 and 2."""
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hi")], presence_penalty=1.0
        )
        assert request.presence_penalty == 1.0

        with pytest.raises(ValueError):
            ChatCompletionRequest(
                messages=[Message(role="user", content="Hi")], presence_penalty=3.0
            )

    def test_frequency_penalty_range(self):
        """frequency_penalty must be between -2 and 2."""
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hi")], frequency_penalty=-1.0
        )
        assert request.frequency_penalty == -1.0

        with pytest.raises(ValueError):
            ChatCompletionRequest(
                messages=[Message(role="user", content="Hi")], frequency_penalty=5.0
            )

    def test_stream_options(self):
        """Can set stream_options."""
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hi")],
            stream_options=StreamOptions(include_usage=True),
        )
        assert request.stream_options.include_usage is True

    def test_log_parameter_info(self):
        """log_parameter_info logs warnings for unsupported params."""
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hi")],
            temperature=0.5,
            presence_penalty=0.5,
            stop=["END"],
        )
        with patch("src.models.logger") as mock_logger:
            request.log_parameter_info()
            # Should have info for temperature, warnings for penalty and stop
            assert mock_logger.info.called
            assert mock_logger.warning.called

    def test_get_sampling_instructions_low_temperature(self):
        """Low temperature produces focused instructions."""
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hi")], temperature=0.2
        )
        instructions = request.get_sampling_instructions()
        assert instructions is not None
        assert "deterministic" in instructions.lower() or "focused" in instructions.lower()

    def test_get_sampling_instructions_high_temperature(self):
        """High temperature produces creative instructions."""
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hi")], temperature=1.8
        )
        instructions = request.get_sampling_instructions()
        assert instructions is not None
        assert "creative" in instructions.lower()

    def test_get_sampling_instructions_low_top_p(self):
        """Low top_p produces focused instructions."""
        request = ChatCompletionRequest(messages=[Message(role="user", content="Hi")], top_p=0.3)
        instructions = request.get_sampling_instructions()
        assert instructions is not None
        assert "probable" in instructions.lower() or "mainstream" in instructions.lower()

    def test_get_sampling_instructions_default_returns_none(self):
        """Default values return no instructions."""
        request = ChatCompletionRequest(messages=[Message(role="user", content="Hi")])
        instructions = request.get_sampling_instructions()
        assert instructions is None

    def test_to_claude_options_basic(self):
        """to_claude_options() returns model."""
        request = ChatCompletionRequest(
            model="claude-sonnet-4-5-20250929",
            messages=[Message(role="user", content="Hi")],
        )
        options = request.to_claude_options()
        assert options["model"] == "claude-sonnet-4-5-20250929"

    def test_to_claude_options_with_max_tokens(self):
        """to_claude_options() maps max_tokens to max_thinking_tokens."""
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hi")], max_tokens=500
        )
        options = request.to_claude_options()
        assert options.get("max_thinking_tokens") == 500

    def test_to_claude_options_prefers_max_completion_tokens(self):
        """max_completion_tokens takes precedence over max_tokens."""
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hi")],
            max_tokens=500,
            max_completion_tokens=1000,
        )
        options = request.to_claude_options()
        assert options.get("max_thinking_tokens") == 1000


class TestChatCompletionResponse:
    """Test ChatCompletionResponse model."""

    def test_response_has_auto_generated_id(self):
        """Response has auto-generated ID starting with chatcmpl-."""
        response = ChatCompletionResponse(
            model="claude-3",
            choices=[
                Choice(
                    index=0,
                    message=Message(role="assistant", content="Hello"),
                    finish_reason="stop",
                )
            ],
        )
        assert response.id.startswith("chatcmpl-")

    def test_response_object_type(self):
        """Response object is chat.completion."""
        response = ChatCompletionResponse(
            model="claude-3",
            choices=[
                Choice(
                    index=0,
                    message=Message(role="assistant", content="Hello"),
                    finish_reason="stop",
                )
            ],
        )
        assert response.object == "chat.completion"

    def test_response_created_timestamp(self):
        """Response has created timestamp."""
        before = int(datetime.now().timestamp())
        response = ChatCompletionResponse(
            model="claude-3",
            choices=[
                Choice(
                    index=0,
                    message=Message(role="assistant", content="Hello"),
                    finish_reason="stop",
                )
            ],
        )
        after = int(datetime.now().timestamp())
        assert before <= response.created <= after


class TestChatCompletionStreamResponse:
    """Test ChatCompletionStreamResponse model."""

    def test_stream_response_object_type(self):
        """Stream response object is chat.completion.chunk."""
        response = ChatCompletionStreamResponse(
            model="claude-3",
            choices=[StreamChoice(index=0, delta={"content": "Hello"})],
        )
        assert response.object == "chat.completion.chunk"

    def test_stream_response_with_usage(self):
        """Stream response can include usage."""
        response = ChatCompletionStreamResponse(
            model="claude-3",
            choices=[StreamChoice(index=0, delta={}, finish_reason="stop")],
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )
        assert response.usage.total_tokens == 15


class TestErrorModels:
    """Test error response models."""

    def test_error_detail(self):
        """Can create ErrorDetail."""
        error = ErrorDetail(message="Something went wrong", type="invalid_request")
        assert error.message == "Something went wrong"
        assert error.type == "invalid_request"

    def test_error_response(self):
        """Can create ErrorResponse."""
        response = ErrorResponse(
            error=ErrorDetail(message="Bad request", type="invalid_request", code="400")
        )
        assert response.error.code == "400"


class TestSessionModels:
    """Test session-related models."""

    def test_session_info(self):
        """Can create SessionInfo."""
        now = datetime.utcnow()
        info = SessionInfo(
            session_id="test-123",
            created_at=now,
            last_accessed=now,
            message_count=5,
            expires_at=now,
        )
        assert info.session_id == "test-123"
        assert info.message_count == 5

    def test_session_list_response(self):
        """Can create SessionListResponse."""
        now = datetime.utcnow()
        response = SessionListResponse(
            sessions=[
                SessionInfo(
                    session_id="s1",
                    created_at=now,
                    last_accessed=now,
                    message_count=1,
                    expires_at=now,
                )
            ],
            total=1,
        )
        assert response.total == 1


class TestToolModels:
    """Test tool-related models."""

    def test_tool_metadata_response(self):
        """Can create ToolMetadataResponse."""
        tool = ToolMetadataResponse(
            name="Read",
            description="Read a file",
            category="filesystem",
            parameters={"path": "string"},
            examples=["Read file.txt"],
            is_safe=True,
            requires_network=False,
        )
        assert tool.name == "Read"

    def test_tool_list_response(self):
        """Can create ToolListResponse."""
        response = ToolListResponse(tools=[], total=0)
        assert response.total == 0

    def test_tool_configuration_response(self):
        """Can create ToolConfigurationResponse."""
        now = datetime.utcnow()
        response = ToolConfigurationResponse(
            allowed_tools=["Read"],
            effective_tools=["Read", "Write"],
            created_at=now,
            updated_at=now,
        )
        assert "Read" in response.allowed_tools

    def test_tool_configuration_request(self):
        """Can create ToolConfigurationRequest."""
        request = ToolConfigurationRequest(allowed_tools=["Read", "Write"], session_id="test")
        assert len(request.allowed_tools) == 2

    def test_tool_validation_response(self):
        """Can create ToolValidationResponse."""
        response = ToolValidationResponse(
            valid={"Read": True, "Invalid": False}, invalid_tools=["Invalid"]
        )
        assert "Invalid" in response.invalid_tools


class TestMCPModels:
    """Test MCP-related models."""

    def test_mcp_server_config_request(self):
        """Can create MCPServerConfigRequest."""
        config = MCPServerConfigRequest(
            name="test-server",
            command="node",
            args=["server.js"],
            description="Test MCP server",
        )
        assert config.name == "test-server"

    def test_mcp_server_name_validation(self):
        """Server name is validated."""
        # Valid name
        config = MCPServerConfigRequest(name="my-server.v1", command="node")
        assert config.name == "my-server.v1"

        # Empty name
        with pytest.raises(ValueError):
            MCPServerConfigRequest(name="", command="node")

        # Invalid characters
        with pytest.raises(ValueError):
            MCPServerConfigRequest(name="server name with spaces", command="node")

    def test_mcp_server_command_validation(self):
        """Server command is validated."""
        with pytest.raises(ValueError):
            MCPServerConfigRequest(name="server", command="")

    def test_mcp_server_info_response(self):
        """Can create MCPServerInfoResponse."""
        info = MCPServerInfoResponse(
            name="test",
            command="node",
            args=[],
            description="Test",
            enabled=True,
            connected=False,
            tools_count=5,
        )
        assert info.tools_count == 5

    def test_mcp_servers_list_response(self):
        """Can create MCPServersListResponse."""
        response = MCPServersListResponse(servers=[], total=0)
        assert response.total == 0

    def test_mcp_connection_request(self):
        """Can create MCPConnectionRequest."""
        request = MCPConnectionRequest(server_name="my-server")
        assert request.server_name == "my-server"

    def test_mcp_connection_request_validation(self):
        """Server name in connection request is validated."""
        with pytest.raises(ValueError):
            MCPConnectionRequest(server_name="")

    def test_mcp_tool_call_request(self):
        """Can create MCPToolCallRequest."""
        request = MCPToolCallRequest(
            server_name="server", tool_name="read_file", arguments={"path": "/tmp/test"}
        )
        assert request.tool_name == "read_file"

    def test_mcp_tool_call_request_validation(self):
        """Tool call request validates names."""
        with pytest.raises(ValueError):
            MCPToolCallRequest(server_name="", tool_name="tool")

        with pytest.raises(ValueError):
            MCPToolCallRequest(server_name="server", tool_name="")


class TestAnthropicModels:
    """Test Anthropic API compatible models."""

    def test_anthropic_text_block(self):
        """Can create AnthropicTextBlock."""
        block = AnthropicTextBlock(text="Hello world")
        assert block.type == "text"
        assert block.text == "Hello world"

    def test_anthropic_message(self):
        """Can create AnthropicMessage."""
        msg = AnthropicMessage(role="user", content="Hello")
        assert msg.role == "user"

    def test_anthropic_message_with_blocks(self):
        """Can create AnthropicMessage with content blocks."""
        msg = AnthropicMessage(role="assistant", content=[AnthropicTextBlock(text="Hi there")])
        assert len(msg.content) == 1

    def test_anthropic_messages_request(self):
        """Can create AnthropicMessagesRequest."""
        request = AnthropicMessagesRequest(
            model="claude-3-opus",
            messages=[AnthropicMessage(role="user", content="Hello")],
            max_tokens=1000,
        )
        assert request.model == "claude-3-opus"
        assert request.max_tokens == 1000

    def test_anthropic_messages_request_to_openai(self):
        """to_openai_messages() converts correctly."""
        request = AnthropicMessagesRequest(
            model="claude-3",
            messages=[
                AnthropicMessage(role="user", content="Hello"),
                AnthropicMessage(
                    role="assistant",
                    content=[
                        AnthropicTextBlock(text="Part 1"),
                        AnthropicTextBlock(text="Part 2"),
                    ],
                ),
            ],
        )
        openai_msgs = request.to_openai_messages()
        assert len(openai_msgs) == 2
        assert openai_msgs[0].content == "Hello"
        assert openai_msgs[1].content == "Part 1\nPart 2"

    def test_anthropic_usage(self):
        """Can create AnthropicUsage."""
        usage = AnthropicUsage(input_tokens=100, output_tokens=50)
        assert usage.input_tokens == 100

    def test_anthropic_messages_response(self):
        """Can create AnthropicMessagesResponse."""
        response = AnthropicMessagesResponse(
            model="claude-3",
            content=[AnthropicTextBlock(text="Response text")],
            usage=AnthropicUsage(input_tokens=10, output_tokens=5),
        )
        assert response.type == "message"
        assert response.role == "assistant"
        assert response.stop_reason == "end_turn"
        assert response.id.startswith("msg_")
