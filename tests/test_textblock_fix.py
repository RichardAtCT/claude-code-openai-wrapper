#!/usr/bin/env python3
"""
Test script to verify the TextBlock fix is working.
"""

import os
import json
import requests

# Set debug mode
os.environ["DEBUG_MODE"] = "true"


def test_textblock_fix():
    """Test that TextBlock content extraction is working."""
    print("🧪 Testing TextBlock content extraction fix...")

    # Simple request that should trigger Claude to respond with normal text
    request_data = {
        "model": "claude-3-7-sonnet-20250219",
        "messages": [{"role": "user", "content": "Hello! Can you briefly introduce yourself?"}],
        "max_tokens": 4096,
        "stream": True,
        "temperature": 0.0,
    }

    try:
        # Send streaming request
        response = requests.post(
            "http://localhost:8000/v1/messages", json=request_data, stream=True, timeout=30
        )

        print(f"✅ Response status: {response.status_code}")

        if response.status_code != 200:
            print(f"❌ Request failed: {response.text}")
            return False

        # Parse Anthropic SSE streaming chunks and collect content
        all_content = ""
        has_content_block_start = False
        has_content = False
        current_event = None

        for line in response.iter_lines():
            if line:
                line_str = line.decode("utf-8")
                if line_str.startswith("event: "):
                    current_event = line_str[7:]
                    if current_event == "content_block_start":
                        has_content_block_start = True
                        print(f"✅ Found content_block_start event")
                elif line_str.startswith("data: "):
                    data_str = line_str[6:]

                    try:
                        chunk_data = json.loads(data_str)

                        if current_event == "content_block_delta":
                            delta = chunk_data.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                all_content += text
                                has_content = True
                                if len(all_content) <= 50:
                                    print(f"✅ Found content: {text[:50]}...")

                        elif current_event == "message_stop":
                            break

                    except json.JSONDecodeError as e:
                        print(f"❌ Invalid JSON in chunk: {data_str}")
                        return False

        print(f"\n📊 Test Results:")
        print(f"   Has content_block_start: {has_content_block_start}")
        print(f"   Has content: {has_content}")
        print(f"   Total content length: {len(all_content)}")
        print(f"   Content preview: {all_content[:200]}...")

        # Check if we got actual content instead of fallback message
        fallback_messages = [
            "I'm unable to provide a response at the moment",
            "I understand you're testing the system",
        ]

        is_fallback = any(msg in all_content for msg in fallback_messages)

        if has_content and not is_fallback and len(all_content) > 20:
            print("\n🎉 TextBlock fix is working!")
            print("✅ Real content extracted successfully")
            print("✅ No fallback messages")
            return True
        else:
            print("\n❌ TextBlock fix is not working")
            print("⚠️  Still receiving fallback content or no content")
            return False

    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        return False


def main():
    """Test the TextBlock fix."""
    print("🔍 Testing TextBlock Content Extraction Fix")
    print("=" * 50)

    success = test_textblock_fix()

    print("\n" + "=" * 50)
    if success:
        print("🎉 TextBlock fix test PASSED!")
        print("✅ RooCode should now receive proper content")
    else:
        print("❌ TextBlock fix test FAILED")
        print("⚠️  Issue may still persist")

    return success


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
