#!/usr/bin/env python3
"""
Simple test to verify environment model configuration works correctly.
"""

import os
import sys
import json

# Test 1: Default model from environment
print("Test 1: Default model from environment")
os.environ["DEFAULT_MODEL"] = "test-model-from-env"

try:
    from src.models import ChatCompletionRequest
    from src.constants import DEFAULT_MODEL
    
    # Test DEFAULT_MODEL constant
    print(f"DEFAULT_MODEL constant: {DEFAULT_MODEL}")
    assert DEFAULT_MODEL == "test-model-from-env", f"Expected 'test-model-from-env', got '{DEFAULT_MODEL}'"
    
    # Test ChatCompletionRequest default
    request = ChatCompletionRequest(messages=[{"role": "user", "content": "test"}])
    print(f"Request model: {request.model}")
    assert request.model == "test-model-from-env", f"Expected 'test-model-from-env', got '{request.model}'"
    
    print("✅ Test 1 passed")
except Exception as e:
    print(f"❌ Test 1 failed: {e}")
    sys.exit(1)

# Test 2: Explicit model overrides default
print("\nTest 2: Explicit model overrides default")
try:
    request = ChatCompletionRequest(
        model="claude-opus-4-5-20250929",
        messages=[{"role": "user", "content": "test"}]
    )
    print(f"Request model: {request.model}")
    assert request.model == "claude-opus-4-5-20250929", f"Expected 'claude-opus-4-5-20250929', got '{request.model}'"
    
    print("✅ Test 2 passed")
except Exception as e:
    print(f"❌ Test 2 failed: {e}")
    sys.exit(1)

# Test 3: Parameter validation allows unknown models
print("\nTest 3: Parameter validation allows unknown models")
try:
    from src.parameter_validator import ParameterValidator
    
    # Test with known model
    result = ParameterValidator.validate_model("claude-sonnet-4-5-20250929")
    assert result == True, f"Expected True for known model, got {result}"
    
    # Test with unknown model (should still return True but log warning)
    result = ParameterValidator.validate_model("unknown-model-123")
    assert result == True, f"Expected True for unknown model (graceful degradation), got {result}"
    
    print("✅ Test 3 passed")
except Exception as e:
    print(f"❌ Test 3 failed: {e}")
    sys.exit(1)

print("\n🎉 All tests passed! Environment model configuration is working correctly.")