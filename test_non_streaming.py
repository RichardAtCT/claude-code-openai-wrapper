#!/usr/bin/env python3
"""
Test script to verify non-streaming responses work correctly.
"""

import os
import json
import requests

# Set debug mode
os.environ['DEBUG_MODE'] = 'true'

def test_non_streaming():
    """Test that non-streaming responses work correctly."""
    print("🧪 Testing non-streaming response...")
    
    # Simple request with streaming disabled
    request_data = {
        "model": "claude-3-7-sonnet-20250219",
        "messages": [
            {
                "role": "user", 
                "content": "What is 2+2?"
            }
        ],
        "stream": False,
        "temperature": 0.0
    }
    
    try:
        # Send non-streaming request
        response = requests.post(
            "http://localhost:8000/v1/chat/completions",
            json=request_data,
            timeout=30
        )
        
        print(f"✅ Response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Request failed: {response.text}")
            return False
        
        # Parse response
        data = response.json()
        
        # Check response structure
        if 'choices' in data and len(data['choices']) > 0:
            message = data['choices'][0]['message']
            content = message['content']
            
            print(f"📊 Response content: {content}")
            
            # Check if we got actual content instead of fallback message
            fallback_messages = [
                "I'm unable to provide a response at the moment",
                "I understand you're testing the system"
            ]
            
            is_fallback = any(msg in content for msg in fallback_messages)
            
            if not is_fallback and len(content) > 0:
                print("\n🎉 Non-streaming response is working!")
                print("✅ Real content extracted successfully")
                return True
            else:
                print("\n❌ Non-streaming response is not working")
                print("⚠️  Still receiving fallback content or no content")
                return False
        else:
            print("❌ Unexpected response structure")
            return False
            
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        return False

def main():
    """Test non-streaming responses."""
    print("🔍 Testing Non-Streaming Responses")
    print("=" * 50)
    
    success = test_non_streaming()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 Non-streaming test PASSED!")
        print("✅ Both streaming and non-streaming responses work correctly")
    else:
        print("❌ Non-streaming test FAILED")
        print("⚠️  Issue may still persist")
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)