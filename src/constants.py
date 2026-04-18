"""
Constants and configuration for Claude Code OpenAI Wrapper.

Single source of truth for tool names, models, and other configuration values.

Usage Examples:
    # Check if a model is supported
    from src.constants import CLAUDE_MODELS
    if model_name in CLAUDE_MODELS:
        # proceed with request

    # Get default allowed tools
    from src.constants import DEFAULT_ALLOWED_TOOLS
    options = {"allowed_tools": DEFAULT_ALLOWED_TOOLS}

    # Use rate limits in FastAPI
    from src.constants import RATE_LIMIT_CHAT
    @limiter.limit(f"{RATE_LIMIT_CHAT}/minute")
    async def chat_endpoint(): ...

Note:
    - Tool configurations are managed by ToolManager (see tool_manager.py)
    - Model validation uses graceful degradation (warns but allows unknown models)
    - Rate limits can be overridden via environment variables
"""

import os

# Claude Agent SDK Tool Names
# These are the built-in tools available in the Claude Agent SDK
# See: https://docs.anthropic.com/en/docs/claude-code/sdk
CLAUDE_TOOLS = [
    "Task",  # Launch agents for complex tasks
    "Bash",  # Execute bash commands
    "Glob",  # File pattern matching
    "Grep",  # Search file contents
    "Read",  # Read files
    "Edit",  # Edit files
    "Write",  # Write files
    "NotebookEdit",  # Edit Jupyter notebooks
    "WebFetch",  # Fetch web content
    "TodoWrite",  # Manage todo lists
    "WebSearch",  # Search the web
    "BashOutput",  # Get bash output
    "KillShell",  # Kill bash shells
    "Skill",  # Execute skills
    "SlashCommand",  # Execute slash commands
]

# Default tools to allow when tools are enabled
# Subset of CLAUDE_TOOLS that are safe and commonly used
DEFAULT_ALLOWED_TOOLS = [
    "Read",
    "Glob",
    "Grep",
    "Bash",
    "Write",
    "Edit",
]

# Tools to disallow by default (potentially dangerous or slow)
DEFAULT_DISALLOWED_TOOLS = [
    "Task",  # Can spawn sub-agents
    "WebFetch",  # External network access
    "WebSearch",  # External network access
]

# Claude Models currently generally available per Anthropic's model docs.
# Order is used as-is by /v1/models, so the first entry is what clients
# (e.g. Open WebUI) pick as the default.
CLAUDE_MODELS = [
    "claude-opus-4-7",            # Most capable
    "claude-sonnet-4-6",          # Best speed/intelligence balance
    "claude-haiku-4-5-20251001",  # Fastest, near-frontier
]

# Default model used when a request omits `model`. Overridable via env.
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-6")

# Fast model (for speed/cost optimization)
FAST_MODEL = "claude-haiku-4-5-20251001"

# System Prompt Types
SYSTEM_PROMPT_TYPE_TEXT = "text"
SYSTEM_PROMPT_TYPE_PRESET = "preset"

# System Prompt Presets
SYSTEM_PROMPT_PRESET_CLAUDE_CODE = "claude_code"

# API Configuration
DEFAULT_MAX_TURNS = 10
DEFAULT_TIMEOUT_MS = 600000  # 10 minutes
DEFAULT_PORT = 8000

# Session Management
SESSION_CLEANUP_INTERVAL_MINUTES = 5
SESSION_MAX_AGE_MINUTES = 60

# Rate Limiting (requests per minute)
RATE_LIMIT_DEFAULT = 60
RATE_LIMIT_CHAT = 30
RATE_LIMIT_MODELS = 100
RATE_LIMIT_HEALTH = 200
