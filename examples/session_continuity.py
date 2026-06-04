#!/usr/bin/env python3
"""
Example demonstrating session continuity with the Claude Code OpenAI API Wrapper.

This example shows how to use the optional session_id parameter to maintain
conversation context across multiple requests.
"""

import openai

# Configure OpenAI client to use the wrapper
client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"  # The wrapper handles Claude authentication
)

def demo_session_continuity():
    """Demonstrate session continuity feature."""
    
    print("🌟 Session Continuity Demo")
    print("=" * 50)
    
    # Define a session ID - this can be any string
    session_id = "demo-conversation-123"
    
    # First interaction - introduce context
    print("\n📝 First Message (introducing context):")
    response1 = client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=[
            {"role": "user", "content": "Hello! I'm working on a Python web API project using FastAPI. My name is Alex."}
        ],
        # This is the key: include session_id for conversation continuity
        extra_body={"session_id": session_id}
    )
    
    print(f"Claude: {response1.choices[0].message.content}")
    
    # Second interaction - ask follow-up that requires memory
    print("\n🔄 Second Message (testing memory):")
    response2 = client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=[
            {"role": "user", "content": "What's my name and what type of project am I working on?"}
        ],
        # Same session_id maintains the conversation context
        extra_body={"session_id": session_id}
    )
    
    print(f"Claude: {response2.choices[0].message.content}")
    
    # Third interaction - continue the conversation
    print("\n🚀 Third Message (building on context):")
    response3 = client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=[
            {"role": "user", "content": "Can you help me add authentication to my FastAPI project?"}
        ],
        extra_body={"session_id": session_id}
    )
    
    print(f"Claude: {response3.choices[0].message.content}")
    
    print("\n✨ Session continuity demo complete!")
    print(f"   Session ID used: {session_id}")
    print("   All messages in this conversation were connected!")


def demo_stateless_vs_session():
    """Compare stateless vs session-based conversations."""
    
    print("\n🔍 Stateless vs Session Comparison")
    print("=" * 50)
    
    # Stateless mode (traditional OpenAI behavior)
    print("\n❌ Stateless Mode (no session_id):")
    print("Message 1:")
    client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=[{"role": "user", "content": "My favorite programming language is Python."}]
        # No session_id = stateless
    )
    print("Claude: [Responds to the message]")
    
    print("\nMessage 2 (separate request):")
    response_stateless = client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=[{"role": "user", "content": "What's my favorite programming language?"}]
        # No session_id = Claude has no memory of previous message
    )
    print(f"Claude: {response_stateless.choices[0].message.content[:100]}...")
    
    # Session mode (with continuity)
    print("\n✅ Session Mode (with session_id):")
    session_id = "comparison-demo"
    
    print("Message 1:")
    client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=[{"role": "user", "content": "My favorite programming language is JavaScript."}],
        extra_body={"session_id": session_id}
    )
    print("Claude: [Responds and remembers]")
    
    print("\nMessage 2 (same session):")
    response_session = client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=[{"role": "user", "content": "What's my favorite programming language?"}],
        extra_body={"session_id": session_id}
    )
    print(f"Claude: {response_session.choices[0].message.content[:100]}...")


def demo_session_management():
    """Demonstrate session management endpoints."""
    
    print("\n🛠  Session Management Demo")
    print("=" * 50)
    
    import requests
    
    base_url = "http://localhost:8000"
    
    # Create some sessions
    session_ids = ["demo-session-1", "demo-session-2"]
    
    for session_id in session_ids:
        client.chat.completions.create(
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": f"Hello from {session_id}!"}],
            extra_body={"session_id": session_id}
        )
    
    # List all sessions
    print("\n📋 Active Sessions:")
    sessions_response = requests.get(f"{base_url}/v1/sessions")
    if sessions_response.status_code == 200:
        sessions = sessions_response.json()
        print(f"   Total sessions: {sessions['total']}")
        for session in sessions['sessions']:
            print(f"   - {session['session_id']}: {session['message_count']} messages")
    
    # Get specific session info
    print(f"\n🔍 Session Details for {session_ids[0]}:")
    session_response = requests.get(f"{base_url}/v1/sessions/{session_ids[0]}")
    if session_response.status_code == 200:
        session_info = session_response.json()
        print(f"   Created: {session_info['created_at']}")
        print(f"   Messages: {session_info['message_count']}")
        print(f"   Expires: {session_info['expires_at']}")
    
    # Session statistics
    print("\n📊 Session Statistics:")
    stats_response = requests.get(f"{base_url}/v1/sessions/stats")
    if stats_response.status_code == 200:
        stats = stats_response.json()
        session_stats = stats['session_stats']
        print(f"   Active sessions: {session_stats['active_sessions']}")
        print(f"   Total messages: {session_stats['total_messages']}")
        print(f"   Cleanup interval: {stats['cleanup_interval_minutes']} minutes")
    
    # Clean up demo sessions
    print("\n🧹 Cleaning up demo sessions:")
    for session_id in session_ids:
        delete_response = requests.delete(f"{base_url}/v1/sessions/{session_id}")
        if delete_response.status_code == 200:
            print(f"   ✅ Deleted {session_id}")


def main():
    """Run all session demos."""
    print("🚀 Claude Code OpenAI Wrapper - Session Continuity Examples")
    print("=" * 60)
    
    try:
        # Test server connection
        health_response = client.chat.completions.create(
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": "Hello!"}]
        )
        print("✅ Server connection successful!")
        
        # Run demos
        demo_session_continuity()
        demo_stateless_vs_session()
        demo_session_management()
        
        print("\n" + "=" * 60)
        print("🎉 All session demos completed successfully!")
        print("\n💡 Key Takeaways:")
        print("   • Use session_id in extra_body for conversation continuity")
        print("   • Sessions automatically expire after 1 hour of inactivity")
        print("   • Session management endpoints provide full control")
        print("   • Stateless mode (no session_id) works like traditional OpenAI API")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Make sure the server is running: uv run python main.py")


if __name__ == "__main__":
    main()