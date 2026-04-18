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

# Claude models exposed by /v1/models. Order matters — first entry is what
# clients (e.g. Open WebUI) pick as the default.
#
# NOTE: Claude Agent SDK only supports Claude 4+ models, not Claude 3.x.
#
# The default list below is curated. If you just need to add or swap models
# without a fork edit + image rebuild, set CLAUDE_MODELS_OVERRIDE to a
# comma-separated list of slugs (e.g. in the Helm values):
#   CLAUDE_MODELS_OVERRIDE=claude-opus-4-7,claude-sonnet-4-6,claude-haiku-4-5
#
# TODO: /v1/models returns this list verbatim instead of proxying
# ${ANTHROPIC_BASE_URL}/v1/models. Future: proxy with a TTL cache and a
# filter (OpenRouter returns ~100 models; we want id.startswith("anthropic/")),
# falling back to this list when upstream is unreachable.
DEFAULT_CLAUDE_MODELS = [
    # Claude 4.7 Family (Latest - 2026) - RECOMMENDED
    "claude-opus-4-7",  # Most capable
    # Claude 4.6 Family
    "claude-opus-4-6",
    "claude-sonnet-4-6",  # Best speed/intelligence balance; best coding model
    # Claude 4.5 Family (Fall 2025)
    "claude-opus-4-5-20250929",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",  # Fastest, near-frontier
    # Claude 4.1
    "claude-opus-4-1-20250805",
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
    [m.strip() for m in _models_override.split(",") if m.strip()]
    if _models_override
    else DEFAULT_CLAUDE_MODELS
)

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

# Security Configuration
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "1000"))
MAX_SESSION_MESSAGES = int(os.getenv("MAX_SESSION_MESSAGES", "100"))
_trusted_proxies_raw = os.getenv("TRUSTED_PROXIES", "")
TRUSTED_PROXIES = [p.strip() for p in _trusted_proxies_raw.split(",") if p.strip()]
CLAUDE_CWD_ALLOWED_BASE = os.getenv("CLAUDE_CWD_ALLOWED_BASE", tempfile.gettempdir())
