#!/usr/bin/env python3
"""
Claude Code OpenAI API Wrapper - OpenAI SDK Example

This example demonstrates how to use the OpenAI Python SDK
with the Claude Code wrapper.
"""

from openai import OpenAI
import os
import requests
from typing import Optional

# Configuration
BASE_URL = "http://localhost:8000/v1"


def get_api_key(base_url: str = "http://localhost:8000") -> Optional[str]:
    """Get the appropriate API key based on server configuration."""
    # Check if user provided API key via environment
    if os.getenv("API_KEY"):
        return os.getenv("API_KEY")

    # Check server auth status
    try:
        response = requests.get(f"{base_url}/v1/auth/status")
        if response.status_code == 200:
            auth_data = response.json()
            server_info = auth_data.get("server_info", {})

            if not server_info.get("api_key_required", False):
                # No auth required
                return "no-auth-required"
            else:
                # Auth required but no key provided
                print("⚠️  Server requires API key but none provided.")
                print("   Set API_KEY environment variable with your server's API key")
                print("   Example: API_KEY=your-server-key python openai_sdk.py")
                return None
    except Exception as e:
        print(f"⚠️  Could not check server auth status: {e}")
        print("   Assuming no authentication required")

    return "fallback-key"


def create_client(base_url: str = BASE_URL, api_key: Optional[str] = None) -> OpenAI:
    """Create OpenAI client configured for Claude Code wrapper."""
    if api_key is None:
        # Auto-detect API key based on server configuration
        server_base = base_url.replace("/v1", "")
        api_key = get_api_key(server_base)

        if api_key is None:
            raise ValueError(
                "Server requires API key but none was provided. Set the API_KEY environment variable."
            )

    return OpenAI(base_url=base_url, api_key=api_key)


def basic_chat_example(client: OpenAI):
    """Basic chat completion example."""
    print("=== Basic Chat Completion ===")

    response = client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=[{"role": "user", "content": "What is the capital of France?"}],
    )

    print(f"Response: {response.choices[0].message.content}")
    print(f"Model: {response.model}")
    print(f"Usage: {response.usage}")
    print()


def system_message_example(client: OpenAI):
    """Chat with system message example."""
    print("=== Chat with System Message ===")

    response = client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=[
            {"role": "system", "content": "You are a helpful coding assistant. Be concise."},
            {"role": "user", "content": "How do I read a file in Python?"},
        ],
    )

    print(f"Response: {response.choices[0].message.content}")
    print()


def conversation_example(client: OpenAI):
    """Multi-turn conversation example."""
    print("=== Multi-turn Conversation ===")

    messages = [
        {"role": "user", "content": "My name is Alice."},
        {"role": "assistant", "content": "Nice to meet you, Alice! How can I help you today?"},
        {"role": "user", "content": "What's my name?"},
    ]

    response = client.chat.completions.create(model="claude-3-5-sonnet-20241022", messages=messages)

    print(f"Response: {response.choices[0].message.content}")
    print()


def streaming_example(client: OpenAI):
    """Streaming response example."""
    print("=== Streaming Response ===")

    stream = client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=[{"role": "user", "content": "Write a haiku about programming"}],
        stream=True,
    )

    print("Response: ", end="", flush=True)
    for chunk in stream:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print("\n")


def file_operation_example(client: OpenAI):
    """Example using Claude Code's file capabilities."""
    print("=== File Operation Example ===")

    response = client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=[{"role": "user", "content": "List the files in the current directory"}],
    )

    print(f"Response: {response.choices[0].message.content}")
    print()


def code_generation_example(client: OpenAI):
    """Code generation example."""
    print("=== Code Generation Example ===")

    response = client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=[
            {"role": "user", "content": "Write a Python function that calculates fibonacci numbers"}
        ],
        temperature=0.7,
    )

    print(f"Response:\n{response.choices[0].message.content}")
    print()


def list_models_example(client: OpenAI):
    """List available models."""
    print("=== Available Models ===")

    models = client.models.list()
    for model in models.data:
        print(f"- {model.id} (owned by: {model.owned_by})")
    print()


def error_handling_example(client: OpenAI):
    """Error handling example."""
    print("=== Error Handling Example ===")

    try:
        # This might fail if Claude Code has issues
        response = client.chat.completions.create(
            model="invalid-model", messages=[{"role": "user", "content": "Test"}]
        )
    except Exception as e:
        print(f"Error occurred: {type(e).__name__}: {e}")
    print()


def main():
    """Run all examples."""
    print("Claude Code OpenAI SDK Examples")
    print("=" * 50)

    # Check authentication status
    api_key = get_api_key()
    if api_key:
        if api_key == "no-auth-required":
            print("🔓 Server authentication: Not required")
        else:
            print("🔑 Server authentication: Required (using provided key)")
    else:
        print("❌ Server authentication: Required but no key available")
        return

    print("=" * 50)

    # Create client
    client = create_client()

    # Run examples
    try:
        basic_chat_example(client)
        system_message_example(client)
        conversation_example(client)
        streaming_example(client)
        file_operation_example(client)
        code_generation_example(client)
        list_models_example(client)
        error_handling_example(client)

    except Exception as e:
        print(f"Failed to run examples: {e}")
        print("Make sure the Claude Code wrapper server is running on port 8000")


if __name__ == "__main__":
    main()
