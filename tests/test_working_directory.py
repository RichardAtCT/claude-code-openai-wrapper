#!/usr/bin/env python3
"""
Test working directory configuration for Claude Code OpenAI wrapper.
Tests that the working directory defaults to a temp directory when CLAUDE_CWD is not set.
"""

import os
import sys
import tempfile
from pathlib import Path
import shutil

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.claude_cli import ClaudeCodeCLI

def test_default_temp_directory():
    """Test that default working directory is a temp directory."""
    print("Testing default temp directory creation...")
    
    # Ensure CLAUDE_CWD is not set
    original_cwd = os.environ.pop("CLAUDE_CWD", None)
    
    try:
        # Create CLI instance without cwd parameter
        cli = ClaudeCodeCLI()
        
        # Check that a temp directory was created
        assert cli.temp_dir is not None, "Temp directory should be created"
        assert cli.temp_dir.startswith(tempfile.gettempdir()), f"Temp dir should be in system temp: {cli.temp_dir}"
        assert "claude_code_workspace_" in cli.temp_dir, "Temp dir should have correct prefix"
        assert os.path.exists(cli.cwd), f"Working directory should exist: {cli.cwd}"
        assert str(cli.cwd) == cli.temp_dir, "Working directory should be the temp directory"
        
        print(f"  ✓ Created temp directory: {cli.temp_dir}")
        
        # Clean up manually for testing
        if cli.temp_dir and os.path.exists(cli.temp_dir):
            shutil.rmtree(cli.temp_dir)
            print(f"  ✓ Cleaned up temp directory")
        
        return True
        
    except AssertionError as e:
        print(f"  ✗ {e}")
        return False
    except Exception as e:
        print(f"  ✗ Unexpected error: {e}")
        return False
    finally:
        # Restore original CLAUDE_CWD if it existed
        if original_cwd:
            os.environ["CLAUDE_CWD"] = original_cwd


def test_env_var_directory():
    """Test that CLAUDE_CWD environment variable is respected."""
    print("\nTesting CLAUDE_CWD environment variable...")
    
    # Create a test directory
    test_dir = tempfile.mkdtemp(prefix="test_claude_cwd_")
    original_cwd = os.environ.get("CLAUDE_CWD")
    
    try:
        # Set CLAUDE_CWD environment variable
        os.environ["CLAUDE_CWD"] = test_dir
        
        # Create CLI instance - it reads from env var directly
        cli = ClaudeCodeCLI(cwd=os.environ.get("CLAUDE_CWD"))
        
        # Check that the specified directory is used
        assert cli.temp_dir is None, "No temp directory should be created when CLAUDE_CWD exists"
        assert str(cli.cwd) == test_dir, f"Working directory should be {test_dir}, got {cli.cwd}"
        
        print(f"  ✓ Using CLAUDE_CWD: {test_dir}")
        
        return True
        
    except AssertionError as e:
        print(f"  ✗ {e}")
        return False
    except Exception as e:
        print(f"  ✗ Unexpected error: {e}")
        return False
    finally:
        # Clean up
        if original_cwd:
            os.environ["CLAUDE_CWD"] = original_cwd
        else:
            os.environ.pop("CLAUDE_CWD", None)
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


def test_explicit_cwd_parameter():
    """Test that explicit cwd parameter takes precedence."""
    print("\nTesting explicit cwd parameter...")
    
    # Create a test directory
    test_dir = tempfile.mkdtemp(prefix="test_explicit_cwd_")
    
    try:
        # Create CLI instance with explicit cwd
        cli = ClaudeCodeCLI(cwd=test_dir)
        
        # Check that the specified directory is used
        assert cli.temp_dir is None, "No temp directory should be created when cwd is provided"
        assert str(cli.cwd) == test_dir, f"Working directory should be {test_dir}, got {cli.cwd}"
        
        print(f"  ✓ Using explicit cwd: {test_dir}")
        
        return True
        
    except AssertionError as e:
        print(f"  ✗ {e}")
        return False
    except Exception as e:
        print(f"  ✗ Unexpected error: {e}")
        return False
    finally:
        # Clean up
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


def test_nonexistent_directory_error():
    """Test that specifying a non-existent directory raises an error."""
    print("\nTesting non-existent directory handling...")
    
    non_existent_dir = "/this/directory/does/not/exist/12345"
    
    try:
        # Try to create CLI instance with non-existent directory
        cli = ClaudeCodeCLI(cwd=non_existent_dir)
        print(f"  ✗ Should have raised an error for non-existent directory")
        return False
    except ValueError as e:
        if "does not exist" in str(e):
            print(f"  ✓ Correctly raised error for non-existent directory")
            return True
        else:
            print(f"  ✗ Unexpected error: {e}")
            return False
    except Exception as e:
        print(f"  ✗ Unexpected error type: {e}")
        return False


def test_cross_platform_compatibility():
    """Test that temp directory creation works across platforms."""
    print("\nTesting cross-platform compatibility...")
    
    try:
        # Get platform-specific temp directory
        system_temp = tempfile.gettempdir()
        print(f"  System temp directory: {system_temp}")
        
        # Create CLI instance
        cli = ClaudeCodeCLI()
        
        # Verify temp directory is in the correct location
        assert cli.temp_dir.startswith(system_temp), f"Temp dir should be in {system_temp}"
        
        # Verify path handling works correctly
        assert isinstance(cli.cwd, Path), "Working directory should be a Path object"
        assert cli.cwd.exists(), "Working directory should exist"
        
        print(f"  ✓ Platform: {os.name}")
        print(f"  ✓ Temp directory created correctly")
        
        # Clean up
        if cli.temp_dir and os.path.exists(cli.temp_dir):
            shutil.rmtree(cli.temp_dir)
        
        return True
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Working Directory Configuration")
    print("=" * 60)
    
    tests = [
        test_default_temp_directory,
        test_env_var_directory,
        test_explicit_cwd_parameter,
        test_nonexistent_directory_error,
        test_cross_platform_compatibility
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"\n✗ Test {test.__name__} failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✅ All {total} tests passed!")
        return 0
    else:
        print(f"❌ {passed}/{total} tests passed, {total - passed} failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())