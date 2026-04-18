#!/usr/bin/env python3
"""
Start the wrapper server, send a message, print the response, and shut down.

Usage:
    python scripts/test_message.py "What is the capital of France?"
    python scripts/test_message.py --max-tokens 1024 "Write a haiku"
"""

import argparse
import os
import sys
import time
import subprocess

import httpx

SERVER_URL = "http://localhost:8000"
MODEL = "claude-sonnet-4-5-20250929"
API_KEY = "test"


def wait_for_server(timeout: int = 30) -> None:
    for _ in range(timeout):
        try:
            httpx.get(f"{SERVER_URL}/health", timeout=2).raise_for_status()
            return
        except Exception:
            time.sleep(1)
    raise TimeoutError(f"Server did not become ready within {timeout}s")


def send_message(message: str, max_tokens: int) -> str:
    with httpx.Client() as client:
        response = client.post(
            f"{SERVER_URL}/v1/messages",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": message}],
                "max_tokens": max_tokens,
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a message to the Claude wrapper server.")
    parser.add_argument("message", help="The message to send")
    parser.add_argument(
        "--max-tokens", type=int, default=4096, help="Maximum tokens to generate (default: 4096)"
    )
    args = parser.parse_args()

    env = {**os.environ, "API_KEY": API_KEY, "DEBUG_MODE": "true"}

    server = subprocess.Popen(
        [sys.executable, "-m", "src.main"],
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stderr=sys.stderr,
        stdout=sys.stderr,
    )

    try:
        wait_for_server()
        print(send_message(args.message, args.max_tokens))
    finally:
        server.terminate()
        server.wait()


if __name__ == "__main__":
    main()
