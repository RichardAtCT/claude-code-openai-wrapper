"""
Chat mode implementation for Claude Code OpenAI wrapper.

This module provides secure sandboxed execution when CHAT_MODE=true,
disabling file system access and limiting available tools.
"""

import os
import tempfile
import shutil
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class ChatMode:
    """Core chat mode functionality."""
    
    @staticmethod
    def is_enabled() -> bool:
        """Check if chat mode is enabled via environment variable."""
        return os.getenv('CHAT_MODE', 'false').lower() == 'true'
    
    @staticmethod
    def get_allowed_tools() -> List[str]:
        """Get the list of tools allowed in chat mode."""
        # Only web-based tools - no file system access
        return ["WebSearch", "WebFetch"]
    
    @staticmethod
    def create_sandbox() -> str:
        """Create a temporary sandbox directory for isolated execution."""
        sandbox_dir = tempfile.mkdtemp(prefix="claude_chat_sandbox_")
        logger.debug(f"Created sandbox directory: {sandbox_dir}")
        return sandbox_dir
    
    @staticmethod
    def cleanup_sandbox(path: str) -> None:
        """Remove sandbox directory and all contents."""
        try:
            if os.path.exists(path) and path.startswith(tempfile.gettempdir()):
                shutil.rmtree(path, ignore_errors=True)
                logger.debug(f"Cleaned up sandbox directory: {path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup sandbox {path}: {e}")


@contextmanager
def sanitized_environment():
    """
    Context manager to temporarily remove sensitive environment variables.
    
    Removes path-revealing variables during execution and restores them after.
    """
    original_env = {}
    
    # Variables that might reveal system paths
    sensitive_vars = ['PWD', 'OLDPWD', 'HOME', 'USER', 'LOGNAME']
    
    # Claude-specific variables that might contain paths
    claude_vars = [k for k in os.environ.keys() if k.startswith('CLAUDE_') and 'DIR' in k]
    
    # Store and remove sensitive variables
    for var in sensitive_vars + claude_vars:
        if var in os.environ:
            original_env[var] = os.environ.pop(var)
            logger.debug(f"Temporarily removed environment variable: {var}")
    
    try:
        yield
    finally:
        # Restore original environment
        for var, value in original_env.items():
            os.environ[var] = value
            logger.debug(f"Restored environment variable: {var}")


def get_chat_mode_info() -> Dict[str, Any]:
    """Get current chat mode configuration and status."""
    return {
        "enabled": ChatMode.is_enabled(),
        "allowed_tools": ChatMode.get_allowed_tools(),
        "sandbox_enabled": True,
        "sessions_disabled": True,
        "file_operations_disabled": True
    }