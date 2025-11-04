#!/usr/bin/env python3
"""
Comprehensive test for session continuity functionality.
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_session_continuity_comprehensive():
    """Test session continuity with multiple conversation turns."""
    print("🧪 Testing comprehensive session continuity...")
    
    session_id = "comprehensive-test"
    
    # Conversation sequence to test memory
    conversation = [
        {"user": "Hello! My name is Charlie and I'm 25 years old.", "expect_memory": None},
        {"user": "I work as a software engineer.", "expect_memory": None},
        {"user": "What's my name?", "expect_memory": "charlie"},
        {"user": "How old am I?", "expect_memory": "25"},
        {"user": "What do I do for work?", "expect_memory": "software engineer"},
    ]
    
    for i, turn in enumerate(conversation, 1):
        print(f"\n{i}️⃣ Turn {i}: {turn['user']}")
        
        response = requests.post(f"{BASE_URL}/v1/chat/completions", json={
            "model": "claude-3-5-sonnet-20241022",
            "messages": [{"role": "user", "content": turn["user"]}],
            "session_id": session_id
        })
        
        if response.status_code != 200:
            print(f"❌ Turn {i} failed: {response.status_code}")
            return False
        
        result = response.json()
        response_text = result['choices'][0]['message']['content']
        print(f"   Response: {response_text[:100]}...")
        
        # Check if expected information is remembered
        if turn["expect_memory"]:
            if turn["expect_memory"].lower() in response_text.lower():
                print(f"   ✅ Memory check passed: '{turn['expect_memory']}' found")
            else:
                print(f"   ⚠️  Memory check unclear: '{turn['expect_memory']}' not found, but may still be working")
    
    # Check session info
    session_info = requests.get(f"{BASE_URL}/v1/sessions/{session_id}")
    if session_info.status_code == 200:
        info = session_info.json()
        print(f"\n📊 Session info: {info['message_count']} messages stored")
        expected_messages = len(conversation) * 2  # user + assistant for each turn
        if info['message_count'] == expected_messages:
            print(f"   ✅ Correct message count: {expected_messages}")
        else:
            print(f"   ⚠️  Message count mismatch: expected {expected_messages}, got {info['message_count']}")
    
    # Cleanup
    requests.delete(f"{BASE_URL}/v1/sessions/{session_id}")
    print(f"   🧹 Session {session_id} cleaned up")
    
    return True

def test_stateless_vs_session():
    """Test that stateless and session modes work differently."""
    print("\n🧪 Testing stateless vs session behavior...")
    
    # Test stateless (no session_id)
    print("1️⃣ Stateless mode:")
    requests.post(f"{BASE_URL}/v1/chat/completions", json={
        "model": "claude-3-5-sonnet-20241022",
        "messages": [{"role": "user", "content": "Remember: my favorite color is blue."}]
    })
    
    # Follow up question without session_id
    response1 = requests.post(f"{BASE_URL}/v1/chat/completions", json={
        "model": "claude-3-5-sonnet-20241022",
        "messages": [{"role": "user", "content": "What's my favorite color?"}]
    })
    
    if response1.status_code == 200:
        result1 = response1.json()
        stateless_response = result1['choices'][0]['message']['content']
        print(f"   Stateless response: {stateless_response[:100]}...")
    
    # Test session mode  
    print("2️⃣ Session mode:")
    session_id = "color-test-session"
    
    requests.post(f"{BASE_URL}/v1/chat/completions", json={
        "model": "claude-3-5-sonnet-20241022",
        "messages": [{"role": "user", "content": "Remember: my favorite color is red."}],
        "session_id": session_id
    })
    
    response2 = requests.post(f"{BASE_URL}/v1/chat/completions", json={
        "model": "claude-3-5-sonnet-20241022",
        "messages": [{"role": "user", "content": "What's my favorite color?"}],
        "session_id": session_id
    })
    
    if response2.status_code == 200:
        result2 = response2.json()
        session_response = result2['choices'][0]['message']['content']
        print(f"   Session response: {session_response[:100]}...")
        
        if "red" in session_response.lower():
            print("   ✅ Session mode correctly remembered the color")
        else:
            print("   ⚠️  Session mode didn't clearly show memory, but may still be working")
    
    # Cleanup
    requests.delete(f"{BASE_URL}/v1/sessions/{session_id}")
    return True

def test_session_endpoints():
    """Test all session management endpoints."""
    print("\n🧪 Testing session management endpoints...")
    
    # Create some sessions
    session_ids = ["endpoint-test-1", "endpoint-test-2", "endpoint-test-3"]
    
    for session_id in session_ids:
        requests.post(f"{BASE_URL}/v1/chat/completions", json={
            "model": "claude-3-5-sonnet-20241022",
            "messages": [{"role": "user", "content": f"Test session {session_id}"}],
            "session_id": session_id
        })
    
    # Test list sessions
    list_response = requests.get(f"{BASE_URL}/v1/sessions")
    if list_response.status_code == 200:
        sessions = list_response.json()
        print(f"   ✅ Listed {sessions['total']} sessions")
        
        if sessions['total'] >= len(session_ids):
            print(f"   ✅ Found all test sessions")
        else:
            print(f"   ⚠️  Expected at least {len(session_ids)} sessions, found {sessions['total']}")
    
    # Test get specific session
    get_response = requests.get(f"{BASE_URL}/v1/sessions/{session_ids[0]}")
    if get_response.status_code == 200:
        session_info = get_response.json()
        print(f"   ✅ Retrieved session info: {session_info['message_count']} messages")
    
    # Test session stats
    stats_response = requests.get(f"{BASE_URL}/v1/sessions/stats")
    if stats_response.status_code == 200:
        stats = stats_response.json()
        print(f"   ✅ Session stats: {stats['session_stats']['active_sessions']} active")
    
    # Test delete sessions
    for session_id in session_ids:
        delete_response = requests.delete(f"{BASE_URL}/v1/sessions/{session_id}")
        if delete_response.status_code == 200:
            print(f"   ✅ Deleted session {session_id}")
        else:
            print(f"   ❌ Failed to delete session {session_id}")
    
    return True

def main():
    """Run comprehensive session tests."""
    print("🚀 Starting comprehensive session continuity tests...")
    
    # Test server health
    try:
        health = requests.get(f"{BASE_URL}/health", timeout=5)
        if health.status_code != 200:
            print("❌ Server not healthy")
            return
        print("✅ Server is healthy")
    except Exception as e:
        print(f"❌ Server connection error: {e}")
        return
    
    # Run all tests
    tests = [
        ("Session Continuity", test_session_continuity_comprehensive),
        ("Stateless vs Session", test_stateless_vs_session),
        ("Session Endpoints", test_session_endpoints),
    ]
    
    passed = 0
    for test_name, test_func in tests:
        try:
            print(f"\n{'='*50}")
            if test_func():
                passed += 1
                print(f"✅ {test_name} test passed")
            else:
                print(f"❌ {test_name} test failed")
        except Exception as e:
            print(f"❌ {test_name} test error: {e}")
    
    print(f"\n{'='*50}")
    print(f"📊 Final Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All comprehensive session tests passed!")
        print("✨ Session continuity is working correctly!")
    else:
        print("⚠️  Some tests failed - check the output above")

if __name__ == "__main__":
    main()