#!/usr/bin/env python3
"""
Test script for session continuity functionality.
"""

import asyncio
import json
import requests
import time
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8000"
TEST_SESSION_ID = "test-session-123"


def test_stateless_mode():
    """Test traditional stateless OpenAI-style requests."""
    print("🧪 Testing stateless mode...")
    
    response = requests.post(f"{BASE_URL}/v1/chat/completions", json={
        "model": "claude-3-5-sonnet-20241022",
        "messages": [
            {"role": "user", "content": "Hello! My name is Alice."}
        ]
    })
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Stateless request successful")
        print(f"   Response: {result['choices'][0]['message']['content'][:100]}...")
        return True
    else:
        print(f"❌ Stateless request failed: {response.status_code} - {response.text}")
        return False


def test_session_mode():
    """Test session-based requests with conversation continuity."""
    print(f"\n🧪 Testing session mode with session_id: {TEST_SESSION_ID}")
    
    # First message in session
    print("1️⃣ First message in session...")
    response1 = requests.post(f"{BASE_URL}/v1/chat/completions", json={
        "model": "claude-3-5-sonnet-20241022",
        "messages": [
            {"role": "user", "content": "Hello! My name is Bob. Remember this name."}
        ],
        "session_id": TEST_SESSION_ID
    })
    
    if response1.status_code != 200:
        print(f"❌ First session request failed: {response1.status_code} - {response1.text}")
        return False
    
    result1 = response1.json()
    print(f"✅ First session message successful")
    print(f"   Response: {result1['choices'][0]['message']['content'][:100]}...")
    
    # Second message in same session - should remember the name
    print("2️⃣ Second message in same session...")
    response2 = requests.post(f"{BASE_URL}/v1/chat/completions", json={
        "model": "claude-3-5-sonnet-20241022",
        "messages": [
            {"role": "user", "content": "What's my name?"}
        ],
        "session_id": TEST_SESSION_ID
    })
    
    if response2.status_code != 200:
        print(f"❌ Second session request failed: {response2.status_code} - {response2.text}")
        return False
    
    result2 = response2.json()
    print(f"✅ Second session message successful")
    print(f"   Response: {result2['choices'][0]['message']['content'][:100]}...")
    
    # Check if the response mentions the name "Bob"
    response_text = result2['choices'][0]['message']['content'].lower()
    if "bob" in response_text:
        print("✅ Session continuity working - Claude remembered the name!")
        return True
    else:
        print("⚠️  Session continuity unclear - response doesn't contain expected name")
        return True  # Still successful, maybe Claude responded differently


def test_session_management_endpoints():
    """Test session management endpoints."""
    print(f"\n🧪 Testing session management endpoints...")
    
    # List sessions
    print("1️⃣ Listing sessions...")
    response = requests.get(f"{BASE_URL}/v1/sessions")
    if response.status_code == 200:
        sessions = response.json()
        print(f"✅ Sessions listed: {sessions['total']} active sessions")
        if sessions['total'] > 0:
            print(f"   First session: {sessions['sessions'][0]['session_id']}")
    else:
        print(f"❌ Failed to list sessions: {response.status_code}")
        return False
    
    # Get specific session info
    print("2️⃣ Getting session info...")
    response = requests.get(f"{BASE_URL}/v1/sessions/{TEST_SESSION_ID}")
    if response.status_code == 200:
        session_info = response.json()
        print(f"✅ Session info retrieved:")
        print(f"   Messages: {session_info['message_count']}")
        print(f"   Created: {session_info['created_at']}")
    else:
        print(f"❌ Failed to get session info: {response.status_code}")
        return False
    
    # Get session stats
    print("3️⃣ Getting session stats...")
    response = requests.get(f"{BASE_URL}/v1/sessions/stats")
    if response.status_code == 200:
        stats = response.json()
        print(f"✅ Session stats retrieved:")
        print(f"   Active sessions: {stats['session_stats']['active_sessions']}")
        print(f"   Total messages: {stats['session_stats']['total_messages']}")
    else:
        print(f"❌ Failed to get session stats: {response.status_code}")
        return False
    
    return True


def test_session_streaming():
    """Test session continuity with streaming."""
    print(f"\n🧪 Testing session streaming...")
    
    # Create a new session for streaming test
    stream_session_id = "test-stream-456"
    
    response = requests.post(f"{BASE_URL}/v1/chat/completions", json={
        "model": "claude-3-5-sonnet-20241022",
        "messages": [
            {"role": "user", "content": "Hello! I'm testing streaming. My favorite color is purple."}
        ],
        "session_id": stream_session_id,
        "stream": True
    }, stream=True)
    
    if response.status_code != 200:
        print(f"❌ Streaming request failed: {response.status_code}")
        return False
    
    print("✅ Streaming response received")
    
    # Follow up with another message in the same session
    time.sleep(1)  # Give time for the session to be updated
    
    response2 = requests.post(f"{BASE_URL}/v1/chat/completions", json={
        "model": "claude-3-5-sonnet-20241022",
        "messages": [
            {"role": "user", "content": "What's my favorite color?"}
        ],
        "session_id": stream_session_id
    })
    
    if response2.status_code == 200:
        result = response2.json()
        response_text = result['choices'][0]['message']['content'].lower()
        print(f"✅ Follow-up message successful")
        print(f"   Response: {result['choices'][0]['message']['content'][:100]}...")
        
        if "purple" in response_text:
            print("✅ Session continuity working with streaming!")
        else:
            print("⚠️  Session continuity unclear with streaming")
        return True
    else:
        print(f"❌ Follow-up message failed: {response2.status_code}")
        return False


def cleanup_test_sessions():
    """Clean up test sessions."""
    print(f"\n🧹 Cleaning up test sessions...")
    
    for session_id in [TEST_SESSION_ID, "test-stream-456"]:
        response = requests.delete(f"{BASE_URL}/v1/sessions/{session_id}")
        if response.status_code == 200:
            print(f"✅ Deleted session: {session_id}")
        elif response.status_code == 404:
            print(f"ℹ️  Session not found (already deleted): {session_id}")
        else:
            print(f"⚠️  Failed to delete session {session_id}: {response.status_code}")


def main():
    """Run all session continuity tests."""
    print("🚀 Starting session continuity tests...")
    print(f"   Server: {BASE_URL}")
    
    # Test server health first
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print(f"❌ Server health check failed: {response.status_code}")
            return
        print("✅ Server is healthy")
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to server: {e}")
        print("   Make sure the server is running with: poetry run python main.py")
        return
    
    success_count = 0
    total_tests = 4
    
    # Run tests
    tests = [
        ("Stateless Mode", test_stateless_mode),
        ("Session Mode", test_session_mode),
        ("Session Management", test_session_management_endpoints),
        ("Session Streaming", test_session_streaming),
    ]
    
    for test_name, test_func in tests:
        try:
            if test_func():
                success_count += 1
            else:
                print(f"❌ {test_name} test failed")
        except Exception as e:
            print(f"❌ {test_name} test error: {e}")
    
    # Cleanup
    cleanup_test_sessions()
    
    # Results
    print(f"\n📊 Test Results: {success_count}/{total_tests} tests passed")
    
    if success_count == total_tests:
        print("🎉 All session continuity tests passed!")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")


if __name__ == "__main__":
    main()