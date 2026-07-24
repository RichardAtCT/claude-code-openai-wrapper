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

# Claude Code tool inventory (sourced from open-sourced Claude Code CLI)
CLAUDE_TOOLS = [
    "Agent",
    "Task",
    "SendMessage",
    "ListPeers",
    "Bash",
    "Glob",
    "Grep",
    "Read",
    "Edit",
    "Write",
    "NotebookEdit",
    "WebFetch",
    "WebSearch",
    "TaskCreate",
    "TaskUpdate",
    "TaskGet",
    "TaskList",
    "TaskOutput",
    "TaskStop",
    "EnterPlanMode",
    "ExitPlanMode",
    "VerifyPlanExecution",
    "EnterWorktree",
    "ExitWorktree",
    "ToolSearch",
    "AskUserQuestion",
    "CronCreate",
    "CronDelete",
    "CronList",
    "RemoteTrigger",
    "TodoWrite",
    "Skill",
    "Brief",
    "Config",
    "REPL",
    "Sleep",
    "Monitor",
    "SendUserFile",
    "PushNotification",
    "ListMcpResources",
    "ReadMcpResource",
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

# Tools to disallow by default (potentially dangerous or resource-intensive)
DEFAULT_DISALLOWED_TOOLS = [
    "Agent",  # Can spawn sub-agents
    "Task",  # Alias for Agent
    "WebFetch",  # External network access
    "WebSearch",  # External network access
    "SendMessage",  # External communication
    "RemoteTrigger",  # Remote execution
]

# Model metadata (sourced from open-sourced Claude Code CLI)
# Only models that differ from the default are listed explicitly.
_DEFAULT_MODEL_META = {
    "context_window": 200_000,
    "default_max_output": 32_000,
    "max_output_limit": 64_000,
}

_MODEL_OVERRIDES = {
    "claude-fable-5": {
        "context_window": 1_000_000,
        "default_max_output": 64_000,
        "max_output_limit": 128_000,
    },
    "claude-opus-5": {
        "context_window": 1_000_000,
        "default_max_output": 64_000,
        "max_output_limit": 128_000,
    },
    "claude-sonnet-5": {
        "context_window": 1_000_000,
        "default_max_output": 64_000,
        "max_output_limit": 128_000,
    },
    "claude-opus-4-8": {
        "context_window": 1_000_000,
        "default_max_output": 64_000,
        "max_output_limit": 128_000,
    },
    "claude-opus-4-7": {
        "context_window": 1_000_000,
        "default_max_output": 64_000,
        "max_output_limit": 128_000,
    },
    "claude-opus-4-6": {
        "context_window": 1_000_000,
        "default_max_output": 64_000,
        "max_output_limit": 128_000,
    },
    "claude-sonnet-4-6": {"context_window": 1_000_000},
    "claude-opus-4-1-20250805": {"default_max_output": 32_000, "max_output_limit": 32_000},
    "claude-opus-4-20250514": {"default_max_output": 32_000, "max_output_limit": 32_000},
}

# Static fallback list (order: newest first). Exposed by /v1/models and
# accepted by validation when the live Anthropic Models API is unavailable
# or not configured. Operators can override the advertised list without
# rebuilding the image via CLAUDE_MODELS_OVERRIDE=model-a,model-b.
# NOTE: Claude Agent SDK only supports Claude 4+ models, not Claude 3.x.
_ALL_MODEL_IDS = [
    "claude-fable-5",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-opus-4-5-20251101",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-1-20250805",
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
]

MODEL_METADATA = {
    model_id: {**_DEFAULT_MODEL_META, **_MODEL_OVERRIDES.get(model_id, {})}
    for model_id in _ALL_MODEL_IDS
}

# CLAUDE_MODELS is derived from MODEL_METADATA so the metadata table is the
# single source of truth; CLAUDE_MODELS_OVERRIDE replaces the advertised list
# without touching the metadata catalog (validation still consults the catalog).
DEFAULT_CLAUDE_MODELS = list(MODEL_METADATA.keys())
_models_override = os.getenv("CLAUDE_MODELS_OVERRIDE", "").strip()
CLAUDE_MODELS = (
    [model.strip() for model in _models_override.split(",") if model.strip()]
    if _models_override
    else DEFAULT_CLAUDE_MODELS
)

# Default model selection.
# DEFAULT_MODEL_ENV is the explicit operator override; when unset, the wrapper
# resolves the latest Sonnet from Anthropic's live Models API at startup and
# stores it in RESOLVED_DEFAULT_MODEL. DEFAULT_MODEL_FALLBACK is used until/if
# that resolution succeeds.
DEFAULT_MODEL_ENV: Optional[str] = os.getenv("DEFAULT_MODEL")
DEFAULT_MODEL_FALLBACK = "claude-sonnet-5"
DEFAULT_MODEL = DEFAULT_MODEL_ENV or DEFAULT_MODEL_FALLBACK
RESOLVED_DEFAULT_MODEL: Optional[str] = None

# Fast model (for speed/cost optimization).
# Can be overridden via FAST_MODEL environment variable.
FAST_MODEL = os.getenv("FAST_MODEL", "claude-haiku-4-5-20251001")

# Anthropic Models API configuration for dynamically refreshing /v1/models.
ANTHROPIC_MODELS_URL = os.getenv("ANTHROPIC_MODELS_URL", "https://api.anthropic.com/v1/models")
ANTHROPIC_VERSION = os.getenv("ANTHROPIC_VERSION", "2023-06-01")
MODEL_LIST_CACHE_TTL_SECONDS = int(os.getenv("MODEL_LIST_CACHE_TTL_SECONDS", "3600"))
# Shorter TTL applied when the live fetch fails so a transient blip doesn't
# suppress live discovery for a full hour.
MODEL_LIST_ERROR_TTL_SECONDS = int(os.getenv("MODEL_LIST_ERROR_TTL_SECONDS", "60"))
MODEL_LIST_REQUEST_TIMEOUT_SECONDS = float(os.getenv("MODEL_LIST_REQUEST_TIMEOUT_SECONDS", "5"))

# Pricing tiers (per million tokens, USD)
# Sourced from open-sourced Claude Code CLI (src/utils/modelCost.ts)
_PRICING_SONNET = {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75}
_PRICING_OPUS = {"input": 5.0, "output": 25.0, "cache_read": 0.50, "cache_write": 6.25}
_PRICING_OPUS_LEGACY = {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_write": 18.75}
_PRICING_HAIKU_45 = {"input": 1.0, "output": 5.0, "cache_read": 0.10, "cache_write": 1.25}
# Fable 5: input/output ($10/$50 per MTok) are Anthropic's published rates.
# cache_read (0.1x input) and cache_write (1.25x input, 5-minute TTL) are
# derived from the same ratios the other tiers in this file use, pending a
# published Fable 5 cache price.
_PRICING_FABLE = {"input": 10.0, "output": 50.0, "cache_read": 1.00, "cache_write": 12.50}

MODEL_PRICING = {
    "claude-fable-5": _PRICING_FABLE,
    # Sonnet 5 standard pricing ($3/$15) matches the Sonnet tier. Introductory
    # pricing of $2/$10 per MTok applies through 2026-08-31 but is not encoded
    # here so the cost tracker reflects steady-state rates.
    "claude-sonnet-5": _PRICING_SONNET,
    "claude-opus-5": _PRICING_OPUS,
    "claude-opus-4-8": _PRICING_OPUS,
    "claude-opus-4-7": _PRICING_OPUS,
    "claude-opus-4-6": _PRICING_OPUS,
    "claude-opus-4-5-20251101": _PRICING_OPUS,
    "claude-opus-4-1-20250805": _PRICING_OPUS_LEGACY,
    "claude-opus-4-20250514": _PRICING_OPUS_LEGACY,
    "claude-sonnet-4-6": _PRICING_SONNET,
    "claude-sonnet-4-5-20250929": _PRICING_SONNET,
    "claude-sonnet-4-20250514": _PRICING_SONNET,
    "claude-haiku-4-5-20251001": _PRICING_HAIKU_45,
}

# Web search cost (per request, all models)
WEB_SEARCH_COST_USD = 0.01

# Fallback model mapping: when an Opus model is overloaded, fall back to Sonnet
# Sourced from Claude Code's FallbackTriggeredError pattern
MODEL_FALLBACK_MAP = {
    "claude-opus-5": "claude-sonnet-5",
    "claude-opus-4-8": "claude-sonnet-4-6",
    "claude-opus-4-7": "claude-sonnet-4-6",
    "claude-opus-4-6": "claude-sonnet-4-6",
    "claude-opus-4-5-20251101": "claude-sonnet-4-5-20250929",
    "claude-opus-4-1-20250805": "claude-sonnet-4-20250514",
    "claude-opus-4-20250514": "claude-sonnet-4-20250514",
}

# Effort levels supported by Claude API
VALID_EFFORT_LEVELS = {"low", "medium", "high", "max"}

# Thinking modes supported by Claude API
VALID_THINKING_MODES = {"adaptive", "enabled", "disabled"}

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
