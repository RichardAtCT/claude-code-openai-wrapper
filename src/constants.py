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

Note:
    - Tool configurations are managed by ToolManager (see tool_manager.py)
    - Model validation uses graceful degradation (warns but allows unknown models)
    - Rate limits can be overridden via environment variables
"""

import os
import tempfile
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

# Tools to disallow when tools are enabled. Default empty; override via env
# with a comma-separated slug list, e.g.
#   DISALLOWED_TOOLS=Task,WebFetch,WebSearch
# Common tools worth considering: Task (spawns sub-agents), WebFetch,
# WebSearch (external network), Bash (shell execution).
_disallowed_raw = os.getenv("DISALLOWED_TOOLS", "").strip()
DEFAULT_DISALLOWED_TOOLS = [t.strip() for t in _disallowed_raw.split(",") if t.strip()]

# Claude Models
# Static fallback models exposed by /v1/models and accepted by validation when
# the live Anthropic Models API is unavailable or not configured.
# NOTE: Claude Agent SDK only supports Claude 4+ models, not Claude 3.x.
#
# Operators can override the advertised model list without rebuilding the image:
#   CLAUDE_MODELS_OVERRIDE=claude-opus-5-5,claude-sonnet-5-5
DEFAULT_CLAUDE_MODELS = [
    # Claude 5.5 Family (Latest) - RECOMMENDED
    "claude-opus-5-5",  # Most capable Opus
    "claude-sonnet-5-5",  # Best speed/intelligence balance
    "claude-haiku-5-5",  # Fastest, cheapest
    # Claude Fable 5.x (highest capability tier)
    "claude-fable-5-1",
    "claude-fable-5",
    # Claude 5 Family
    "claude-opus-5",
    "claude-sonnet-5",
    # Claude 4.x Family
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
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
DEFAULT_MODEL_FALLBACK = "claude-sonnet-5-5"
DEFAULT_MODEL = DEFAULT_MODEL_ENV or DEFAULT_MODEL_FALLBACK
RESOLVED_DEFAULT_MODEL: Optional[str] = None

# Fast model (for speed/cost optimization)
# Can be overridden via FAST_MODEL environment variable
FAST_MODEL = os.getenv("FAST_MODEL", "claude-haiku-5-5")

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

# Security Configuration
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "1000"))
MAX_SESSION_MESSAGES = int(os.getenv("MAX_SESSION_MESSAGES", "100"))
# SQLite file holding wrapper sessions and mirrored Claude SDK transcripts, so
# sessions (and native SDK resume) survive restarts. ":memory:" disables
# persistence.
SESSION_DB_PATH = os.path.expanduser(
    os.getenv("SESSION_DB_PATH", os.path.join("~", ".claude-wrapper", "sessions.db"))
)
_trusted_proxies_raw = os.getenv("TRUSTED_PROXIES", "")
TRUSTED_PROXIES = [p.strip() for p in _trusted_proxies_raw.split(",") if p.strip()]
CLAUDE_CWD_ALLOWED_BASE = os.getenv("CLAUDE_CWD_ALLOWED_BASE", tempfile.gettempdir())
