#!/usr/bin/env python3
"""
Test script demonstrating OpenAI to Claude Code SDK parameter mapping.

These are integration tests that require a running server.
Run with: poetry run pytest tests/test_parameter_mapping.py -v
"""

import asyncio
import json
import pytest
import requests
from typing import Dict, Any

from tests.conftest import requires_server, MAX_TOKENS

# Test server URL
BASE_URL = "http://localhost:8000"


@requires_server
def test_basic_completion():
    """Test basic chat completion with Anthropic parameters."""
    print("=== Testing Basic Completion ===")

    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "system": "You are a helpful assistant.",
        "messages": [
            {"role": "user", "content": "Say hello in a creative way."},
        ],
        "temperature": 0.7,
        "max_tokens": MAX_TOKENS,
    }

    response = requests.post(f"{BASE_URL}/v1/messages", json=payload)

    if response.status_code == 200:
        print("✅ Request successful")
        result = response.json()
        print(f"Response: {result['content'][0]['text'][:100]}...")
    else:
        print(f"❌ Request failed: {response.status_code}")
        print(response.text)


@requires_server
def test_with_claude_headers():
    """Test completion with Claude-specific headers."""
    print("\n=== Testing with Claude-Specific Headers ===")

    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": [{"role": "user", "content": "List the files in the current directory"}],
        "stream": False,
    }

    headers = {
        "Content-Type": "application/json",
        "X-Claude-Max-Turns": "5",
        "X-Claude-Allowed-Tools": "ls,pwd,cat",
        "X-Claude-Permission-Mode": "acceptEdits",
    }

    response = requests.post(f"{BASE_URL}/v1/chat/completions", json=payload, headers=headers)

    if response.status_code == 200:
        print("✅ Request with Claude headers successful")
        result = response.json()
        print(f"Response: {result['choices'][0]['message']['content'][:100]}...")
    else:
        print(f"❌ Request failed: {response.status_code}")
        print(response.text)


@requires_server
def test_compatibility_check():
    """Test the compatibility endpoint."""
    print("\n=== Testing Compatibility Check ===")

    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.8,
        "top_p": 0.9,
        "max_tokens": 150,
        "presence_penalty": 0.1,
        "frequency_penalty": 0.2,
        "logit_bias": {"hello": 2.0},
        "stop": ["END"],
        "n": 1,
        "user": "test_user",
    }

    response = requests.post(f"{BASE_URL}/v1/compatibility", json=payload)

    if response.status_code == 200:
        print("✅ Compatibility check successful")
        result = response.json()
        print(json.dumps(result, indent=2))
    else:
        print(f"❌ Compatibility check failed: {response.status_code}")
        print(response.text)


def test_streaming_with_parameters():
    """Test streaming response with Anthropic SSE format."""
    print("\n=== Testing Streaming with Parameters ===")

    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": [{"role": "user", "content": "Write a short poem about programming"}],
        "temperature": 0.9,
        "max_tokens": MAX_TOKENS,
        "stream": True,
    }

    try:
        response = requests.post(f"{BASE_URL}/v1/messages", json=payload, stream=True)

        if response.status_code == 200:
            print("✅ Streaming request successful")
            print("First few chunks:")
            count = 0
            current_event = None
            for line in response.iter_lines():
                if line and count < 5:
                    line_str = line.decode("utf-8")
                    if line_str.startswith("event: "):
                        current_event = line_str[7:]
                    elif line_str.startswith("data: ") and current_event == "content_block_delta":
                        print(f"  [{current_event}] {line_str}")
                        count += 1
        else:
            print(f"❌ Streaming request failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Streaming test error: {e}")


def main():
    """Run all tests."""
    print("OpenAI to Claude Code SDK Parameter Mapping Tests")
    print("=" * 50)

    try:
        # Check if server is running
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code != 200:
            print("❌ Server is not running. Start it with: poetry run python main.py")
            return
        print("✅ Server is running")

        # Run tests
        test_basic_completion()
        test_with_claude_headers()
        test_compatibility_check()
        test_streaming_with_parameters()

        print("\n" + "=" * 50)
        print("🎉 All tests completed!")
        print("\nTo see parameter warnings in detail, run the server with:")
        print(
            "PYTHONPATH=. poetry run python -c \"import logging; logging.basicConfig(level=logging.DEBUG); exec(open('main.py').read())\""
        )

    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server. Make sure it's running on port 8000")
    except Exception as e:
        print(f"❌ Test error: {e}")


if __name__ == "__main__":
    main()
