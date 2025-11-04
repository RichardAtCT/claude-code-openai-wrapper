#!/usr/bin/env python3
"""
Test script demonstrating OpenAI to Claude Code SDK parameter mapping.
"""

import asyncio
import json
import requests
from typing import Dict, Any

# Test server URL
BASE_URL = "http://localhost:8000"

def test_basic_completion():
    """Test basic chat completion with OpenAI parameters."""
    print("=== Testing Basic Completion ===")
    
    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say hello in a creative way."}
        ],
        "temperature": 0.7,  # Will be ignored with warning
        "max_tokens": 100,   # Will be ignored with warning
        "stream": False
    }
    
    response = requests.post(f"{BASE_URL}/v1/chat/completions", json=payload)
    
    if response.status_code == 200:
        print("✅ Request successful")
        result = response.json()
        print(f"Response: {result['choices'][0]['message']['content'][:100]}...")
    else:
        print(f"❌ Request failed: {response.status_code}")
        print(response.text)

def test_with_claude_headers():
    """Test completion with Claude-specific headers."""
    print("\n=== Testing with Claude-Specific Headers ===")
    
    payload = {
        "model": "claude-3-5-sonnet-20241022", 
        "messages": [
            {"role": "user", "content": "List the files in the current directory"}
        ],
        "stream": False
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-Claude-Max-Turns": "5",
        "X-Claude-Allowed-Tools": "ls,pwd,cat",
        "X-Claude-Permission-Mode": "acceptEdits"
    }
    
    response = requests.post(
        f"{BASE_URL}/v1/chat/completions", 
        json=payload, 
        headers=headers
    )
    
    if response.status_code == 200:
        print("✅ Request with Claude headers successful")
        result = response.json()
        print(f"Response: {result['choices'][0]['message']['content'][:100]}...")
    else:
        print(f"❌ Request failed: {response.status_code}")
        print(response.text)

def test_compatibility_check():
    """Test the compatibility endpoint."""
    print("\n=== Testing Compatibility Check ===")
    
    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.8,
        "top_p": 0.9,
        "max_tokens": 150,
        "presence_penalty": 0.1,
        "frequency_penalty": 0.2,
        "logit_bias": {"hello": 2.0},
        "stop": ["END"],
        "n": 1,
        "user": "test_user"
    }
    
    response = requests.post(f"{BASE_URL}/v1/compatibility", json=payload)
    
    if response.status_code == 200:
        print("✅ Compatibility check successful")
        result = response.json()
        print(json.dumps(result, indent=2))
    else:
        print(f"❌ Compatibility check failed: {response.status_code}")
        print(response.text)

def test_parameter_validation():
    """Test parameter validation (should fail)."""
    print("\n=== Testing Parameter Validation ===")
    
    # Test with n > 1 (should fail)
    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": [{"role": "user", "content": "Hello"}],
        "n": 3  # Should fail validation
    }
    
    response = requests.post(f"{BASE_URL}/v1/chat/completions", json=payload)
    
    if response.status_code == 422:
        print("✅ Validation correctly rejected n > 1")
        print(response.json())
    else:
        print(f"❌ Expected validation error, got: {response.status_code}")

def test_streaming_with_parameters():
    """Test streaming response with unsupported parameters."""
    print("\n=== Testing Streaming with Unsupported Parameters ===")
    
    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": [
            {"role": "user", "content": "Write a short poem about programming"}
        ],
        "temperature": 0.9,  # Will be warned about
        "max_tokens": 200,   # Will be warned about
        "stream": True
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/v1/chat/completions", 
            json=payload, 
            stream=True
        )
        
        if response.status_code == 200:
            print("✅ Streaming request successful")
            print("First few chunks:")
            count = 0
            for line in response.iter_lines():
                if line and count < 5:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: ') and not line_str.endswith('[DONE]'):
                        print(f"  {line_str}")
                        count += 1
        else:
            print(f"❌ Streaming request failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Streaming test error: {e}")

def main():
    """Run all tests."""
    print("OpenAI to Claude Code SDK Parameter Mapping Tests")
    print("=" * 50)
    
    try:
        # Check if server is running
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code != 200:
            print("❌ Server is not running. Start it with: poetry run python main.py")
            return
        print("✅ Server is running")
        
        # Run tests
        test_basic_completion()
        test_with_claude_headers()
        test_compatibility_check()
        test_parameter_validation()
        test_streaming_with_parameters()
        
        print("\n" + "=" * 50)
        print("🎉 All tests completed!")
        print("\nTo see parameter warnings in detail, run the server with:")
        print("PYTHONPATH=. poetry run python -c \"import logging; logging.basicConfig(level=logging.DEBUG); exec(open('main.py').read())\"")
        
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server. Make sure it's running on port 8000")
    except Exception as e:
        print(f"❌ Test error: {e}")

if __name__ == "__main__":
    main()