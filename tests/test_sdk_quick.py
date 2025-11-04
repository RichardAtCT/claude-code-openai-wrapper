#!/usr/bin/env python3
"""Quick test of Claude Agent SDK to verify migration."""

import asyncio
import sys
import os

# Ensure we're in the right directory
sys.path.insert(0, os.path.dirname(__file__))

from claude_agent_sdk import query, ClaudeAgentOptions

async def test_simple_query():
    """Test a simple query with the new SDK."""
    print("Testing Claude Agent SDK with simple query...")
    print("-" * 60)

    try:
        messages = []
        async for message in query(
            prompt="Say 'Hello!' and nothing else.",
            options=ClaudeAgentOptions(
                max_turns=1,
                model="claude-3-5-haiku-20241022"  # Fastest model for testing
            )
        ):
            messages.append(message)
            print(f"Got message type: {type(message)}")

            # Try to extract content
            if hasattr(message, 'content'):
                print(f"Content: {message.content}")
            elif isinstance(message, dict):
                print(f"Message dict: {message}")

            # Break early if we get an assistant message
            msg_type = getattr(message, 'type', None) if hasattr(message, 'type') else message.get("type") if isinstance(message, dict) else None
            if msg_type == "assistant":
                print("✓ Got assistant response!")
                break

        print("-" * 60)
        if messages:
            print(f"✓ Test passed! Got {len(messages)} messages")
            return True
        else:
            print("✗ Test failed: No messages received")
            return False

    except Exception as e:
        print(f"✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_simple_query())
    sys.exit(0 if result else 1)
