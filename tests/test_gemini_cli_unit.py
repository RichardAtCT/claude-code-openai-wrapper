import pytest
import json
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from src.gemini_cli import GeminiCodeCLI

@pytest.fixture
def gemini_cli():
    return GeminiCodeCLI()

@pytest.mark.asyncio
async def test_verify_cli_success(gemini_cli):
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"gemini 1.0.0", b""))
        mock_process.returncode = 0
        mock_exec.return_value = mock_process
        
        result = await gemini_cli.verify_cli()
        assert result is True
        mock_exec.assert_called_once()

@pytest.mark.asyncio
async def test_verify_cli_failure(gemini_cli):
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"command not found"))
        mock_process.returncode = 127
        mock_exec.return_value = mock_process
        
        result = await gemini_cli.verify_cli()
        assert result is False

@pytest.mark.asyncio
async def test_run_completion_streaming(gemini_cli):
    # Mock NDJSON output from gemini CLI
    mock_output = [
        json.dumps({"type": "init", "session_id": "test-session", "model": "gemini-3-pro-preview"}),
        json.dumps({"type": "message", "content": "Hello"}),
        json.dumps({"type": "message", "content": " world"}),
        json.dumps({"type": "result", "usage": {"prompt_tokens": 10, "completion_tokens": 5}, "stop_reason": "STOP"}),
    ]
    
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = MagicMock()
        mock_process.stdout.readline = AsyncMock(side_effect=[line.encode() + b"\n" for line in mock_output] + [b""])
        mock_process.wait = AsyncMock()
        mock_process.returncode = 0
        mock_exec.return_value = mock_process
        
        chunks = []
        async for chunk in gemini_cli.run_completion("Hi"):
            chunks.append(chunk)
            
        assert len(chunks) == 4
        assert chunks[1]["content"] == "Hello"
        assert chunks[2]["content"] == " world"
        assert chunks[0]["session_id"] == "test-session"

def test_parse_message(gemini_cli):
    messages = [
        {"type": "message", "content": "Hello"},
        {"type": "message", "content": " world!"}
    ]
    assert gemini_cli.parse_message(messages) == "Hello world!"

def test_extract_metadata(gemini_cli):
    messages = [
        {"type": "init", "session_id": "uuid-123", "model": "gemini-3"},
        {"type": "result", "usage": {"input_tokens": 5, "output_tokens": 10}}
    ]
    metadata = gemini_cli.extract_metadata(messages)
    assert metadata["session_id"] == "uuid-123"
    assert metadata["model"] == "gemini-3"
    assert metadata["usage"]["input_tokens"] == 5

def test_map_stop_reason_openai(gemini_cli):
    assert gemini_cli.map_stop_reason_openai("MAX_TOKENS") == "length"
    assert gemini_cli.map_stop_reason_openai("STOP") == "stop"
    assert gemini_cli.map_stop_reason_openai(None) == "stop"
