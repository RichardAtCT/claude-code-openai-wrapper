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
from typing import Optional

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

# Claude Models
# Static fallback models exposed by /v1/models and accepted by validation when
# the live Anthropic Models API is unavailable or not configured.
# NOTE: Claude Agent SDK only supports Claude 4+ models, not Claude 3.x.
#
# Operators can override the advertised model list without rebuilding the image:
#   CLAUDE_MODELS_OVERRIDE=claude-sonnet-4-6,claude-opus-4-6
DEFAULT_CLAUDE_MODELS = [
    # Claude 4.6 Family (Latest) - RECOMMENDED
    "claude-opus-4-6",  # Most capable
    "claude-sonnet-4-6",  # Recommended - best coding model
    # Claude 4.5 Family (Fall 2025)
    "claude-opus-4-5-20250929",  # Opus 4.5 - deep reasoning and coding
    "claude-sonnet-4-5-20250929",  # Sonnet 4.5 - agents and coding
    "claude-haiku-4-5-20251001",  # Fast and cheap
    # Claude 4.1
    "claude-opus-4-1-20250805",  # Upgraded Opus 4
    # Claude 4.0 Family (Original - May 2025)
    "claude-opus-4-20250514",
    "claude-sonnet-4-20250514",
    # Claude 3.x Family - NOT SUPPORTED by Claude Agent SDK
    # These models work with Anthropic API but NOT with Claude Code
    # Uncomment only if using direct Anthropic API (not Claude Agent SDK)
    # "claude-3-7-sonnet-20250219",
    # "claude-3-5-sonnet-20241022",
    # "claude-3-5-haiku-20241022",
]

_models_override = os.getenv("CLAUDE_MODELS_OVERRIDE", "").strip()
CLAUDE_MODELS = (
    [model.strip() for model in _models_override.split(",") if model.strip()]
    if _models_override
    else DEFAULT_CLAUDE_MODELS
)

# Default model (recommended for most use cases)
# DEFAULT_MODEL_ENV is the explicit operator override; when unset, the wrapper
# resolves the latest Sonnet from Anthropic's live Models API at startup and
# stores it in RESOLVED_DEFAULT_MODEL. DEFAULT_MODEL_FALLBACK is used until/if
# that resolution succeeds.
DEFAULT_MODEL_ENV: Optional[str] = os.getenv("DEFAULT_MODEL")
DEFAULT_MODEL_FALLBACK = "claude-sonnet-4-6"
DEFAULT_MODEL = DEFAULT_MODEL_ENV or DEFAULT_MODEL_FALLBACK
RESOLVED_DEFAULT_MODEL: Optional[str] = None

# Fast model (for speed/cost optimization)
# Can be overridden via FAST_MODEL environment variable
FAST_MODEL = os.getenv("FAST_MODEL", "claude-haiku-4-5-20251001")

# Anthropic Models API configuration for dynamically refreshing /v1/models
ANTHROPIC_MODELS_URL = os.getenv("ANTHROPIC_MODELS_URL", "https://api.anthropic.com/v1/models")
ANTHROPIC_VERSION = os.getenv("ANTHROPIC_VERSION", "2023-06-01")
MODEL_LIST_CACHE_TTL_SECONDS = int(os.getenv("MODEL_LIST_CACHE_TTL_SECONDS", "3600"))
# Shorter TTL applied when the live fetch fails so a transient blip doesn't
# suppress live discovery for a full hour.
MODEL_LIST_ERROR_TTL_SECONDS = int(os.getenv("MODEL_LIST_ERROR_TTL_SECONDS", "60"))
MODEL_LIST_REQUEST_TIMEOUT_SECONDS = float(os.getenv("MODEL_LIST_REQUEST_TIMEOUT_SECONDS", "5"))

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
