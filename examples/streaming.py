#!/usr/bin/env python3
"""
Claude Code OpenAI API Wrapper - Advanced Streaming Example

This example demonstrates advanced streaming functionality including
error handling, chunk processing, and real-time display.
"""

from openai import OpenAI
import time
import sys
import os
import requests
from typing import Optional, Generator
import json


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
                print("   Example: API_KEY=your-server-key python streaming.py")
                return None
    except Exception as e:
        print(f"⚠️  Could not check server auth status: {e}")
        print("   Assuming no authentication required")

    return "fallback-key"


class StreamingClient:
    """Client for handling streaming responses."""

    def __init__(self, base_url: str = "http://localhost:8000/v1", api_key: Optional[str] = None):
        if api_key is None:
            # Auto-detect API key based on server configuration
            server_base = base_url.replace("/v1", "")
            api_key = get_api_key(server_base)

            if api_key is None:
                raise ValueError(
                    "Server requires API key but none was provided. Set the API_KEY environment variable."
                )

        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def stream_with_timing(self, messages: list, model: str = "claude-3-5-sonnet-20241022"):
        """Stream response with timing information."""
        start_time = time.time()
        first_token_time = None
        token_count = 0

        print("Streaming response...")
        print("-" * 50)

        try:
            stream = self.client.chat.completions.create(
                model=model, messages=messages, stream=True
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    if first_token_time is None:
                        first_token_time = time.time()
                        time_to_first_token = first_token_time - start_time
                        print(f"[Time to first token: {time_to_first_token:.2f}s]\n")

                    content = chunk.choices[0].delta.content
                    print(content, end="", flush=True)
                    token_count += 1

                if chunk.choices[0].finish_reason:
                    total_time = time.time() - start_time
                    print(f"\n\n[Streaming completed]")
                    print(f"[Total time: {total_time:.2f}s]")
                    print(f"[Approximate tokens: {token_count}]")
                    print(f"[Finish reason: {chunk.choices[0].finish_reason}]")

        except KeyboardInterrupt:
            print("\n\n[Streaming interrupted by user]")
        except Exception as e:
            print(f"\n\n[Streaming error: {e}]")

    def stream_with_processing(self, messages: list, process_func=None):
        """Stream response with custom processing function."""
        if process_func is None:
            process_func = lambda x: x  # Default: no processing

        stream = self.client.chat.completions.create(
            model="claude-3-5-sonnet-20241022", messages=messages, stream=True
        )

        buffer = ""
        for chunk in stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                buffer += content

                # Process complete sentences
                if any(punct in content for punct in [".", "!", "?", "\n"]):
                    processed = process_func(buffer)
                    yield processed
                    buffer = ""

        # Process remaining buffer
        if buffer:
            yield process_func(buffer)

    def parallel_streams(self, prompts: list):
        """Demo of handling multiple prompts (sequential, not truly parallel)."""
        for i, prompt in enumerate(prompts):
            print(f"\n{'='*50}")
            print(f"Prompt {i+1}: {prompt}")
            print("=" * 50)

            messages = [{"role": "user", "content": prompt}]
            self.stream_with_timing(messages)
            print()


def typing_effect_demo():
    """Demonstrate a typing effect with streaming."""
    client = StreamingClient()

    print("=== Typing Effect Demo ===")
    messages = [
        {"role": "system", "content": "You are a storyteller."},
        {
            "role": "user",
            "content": "Tell me a very short story (2-3 sentences) about a robot learning to paint.",
        },
    ]

    stream = client.client.chat.completions.create(
        model="claude-3-5-sonnet-20241022", messages=messages, stream=True
    )

    for chunk in stream:
        if chunk.choices[0].delta.content:
            for char in chunk.choices[0].delta.content:
                print(char, end="", flush=True)
                time.sleep(0.05)  # Typing delay
    print("\n")


def word_highlighting_demo():
    """Demonstrate processing stream to highlight specific words."""
    client = StreamingClient()

    print("=== Word Highlighting Demo ===")
    print("(Technical terms will be CAPITALIZED)")

    def highlight_technical_terms(text: str) -> str:
        """Highlight technical terms by capitalizing them."""
        technical_terms = [
            "python",
            "javascript",
            "api",
            "function",
            "variable",
            "class",
            "method",
            "algorithm",
            "data",
            "code",
        ]

        for term in technical_terms:
            text = text.replace(term, term.upper())
            text = text.replace(term.capitalize(), term.upper())

        return text

    messages = [{"role": "user", "content": "Explain what an API is in simple terms."}]

    for processed_chunk in client.stream_with_processing(messages, highlight_technical_terms):
        print(processed_chunk, end="", flush=True)
    print("\n")


def progress_bar_demo():
    """Demonstrate a progress bar with streaming (estimated)."""
    client = StreamingClient()

    print("=== Progress Bar Demo ===")
    messages = [
        {"role": "user", "content": "Count from 1 to 10, with a brief pause between each number."}
    ]

    # This is a simple demo - real progress would need token counting
    stream = client.client.chat.completions.create(
        model="claude-3-5-sonnet-20241022", messages=messages, stream=True
    )

    print("Response: ", end="", flush=True)
    response_text = ""

    for chunk in stream:
        if chunk.choices[0].delta.content:
            content = chunk.choices[0].delta.content
            response_text += content
            print(content, end="", flush=True)

    print("\n")


def error_recovery_demo():
    """Demonstrate error handling in streaming."""
    client = StreamingClient()

    print("=== Error Recovery Demo ===")

    # This might cause an error if the model doesn't exist
    messages = [{"role": "user", "content": "Hello!"}]

    try:
        stream = client.client.chat.completions.create(
            model="non-existent-model", messages=messages, stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)

    except Exception as e:
        print(f"Error encountered: {e}")
        print("Retrying with valid model...")

        # Retry with valid model
        stream = client.client.chat.completions.create(
            model="claude-3-5-sonnet-20241022", messages=messages, stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)

    print("\n")


def main():
    """Run all streaming demos."""
    client = StreamingClient()

    # Basic streaming with timing
    print("=== Basic Streaming with Timing ===")
    client.stream_with_timing(
        [{"role": "user", "content": "Write a one-line Python function to reverse a string."}]
    )

    print("\n" + "=" * 70 + "\n")

    # Run other demos
    typing_effect_demo()
    print("=" * 70 + "\n")

    word_highlighting_demo()
    print("=" * 70 + "\n")

    progress_bar_demo()
    print("=" * 70 + "\n")

    error_recovery_demo()
    print("=" * 70 + "\n")

    # Multiple prompts
    print("=== Multiple Prompts Demo ===")
    client.parallel_streams(["What is 2+2?", "Name a color.", "Say 'Hello, World!' in Python."])


if __name__ == "__main__":
    main()
