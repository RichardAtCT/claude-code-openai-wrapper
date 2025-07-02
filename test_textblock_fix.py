#!/usr/bin/env python3
"""
Test script to verify the TextBlock fix is working.
"""

import os
import json
import requests

# Set debug mode
os.environ['DEBUG_MODE'] = 'true'

def test_textblock_fix():
    """Test that TextBlock content extraction is working."""
    print("🧪 Testing TextBlock content extraction fix...")
    
    # Simple request that should trigger Claude to respond with normal text
    request_data = {
        "model": "claude-3-7-sonnet-20250219",
        "messages": [
            {
                "role": "user", 
                "content": "Hello! Can you briefly introduce yourself?"
            }
        ],
        "stream": True,
        "temperature": 0.0
    }
    
    try:
        # Send streaming request
        response = requests.post(
            "http://localhost:8000/v1/chat/completions",
            json=request_data,
            stream=True,
            timeout=30
        )
        
        print(f"✅ Response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Request failed: {response.text}")
            return False
        
        # Parse streaming chunks and collect content
        all_content = ""
        has_role_chunk = False
        has_content = False
        
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    data_str = line_str[6:]  # Remove "data: " prefix
                    
                    if data_str == "[DONE]":
                        break
                    
                    try:
                        chunk_data = json.loads(data_str)
                        
                        # Check chunk structure
                        if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                            choice = chunk_data['choices'][0]
                            delta = choice.get('delta', {})
                            
                            # Check for role chunk
                            if 'role' in delta:
                                has_role_chunk = True
                                print(f"✅ Found role chunk")
                            
                            # Check for content chunk  
                            if 'content' in delta:
                                content = delta['content']
                                all_content += content
                                has_content = True
                                print(f"✅ Found content: {content[:50]}...")
                                
                    except json.JSONDecodeError as e:
                        print(f"❌ Invalid JSON in chunk: {data_str}")
                        return False
        
        print(f"\n📊 Test Results:")
        print(f"   Has role chunk: {has_role_chunk}")
        print(f"   Has content: {has_content}")
        print(f"   Total content length: {len(all_content)}")
        print(f"   Content preview: {all_content[:200]}...")
        
        # Check if we got actual content instead of fallback message
        fallback_messages = [
            "I'm unable to provide a response at the moment",
            "I understand you're testing the system"
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