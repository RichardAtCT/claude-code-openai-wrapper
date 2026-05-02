"""
Constants and configuration for Claude Code OpenAI Wrapper.
...
"""
import os

# Claude Agent SDK Tool Names
CLAUDE_TOOLS = [
    "Task",
    "Bash",
    "Glob",
    "Grep",
    "Read",
    "Edit",
    "Write",
    "NotebookEdit",
    "WebFetch",
    "TodoWrite",
    "WebSearch",
    "BashOutput",
    "KillShell",
    "Skill",
    "SlashCommand",
]

DEFAULT_ALLOWED_TOOLS = ["Read", "Glob", "Grep", "Bash", "Write", "Edit"]

DEFAULT_DISALLOWED_TOOLS = ["Task", "WebFetch", "WebSearch"]

# Claude Models
# Active models as of May 2026 per https://platform.claude.com/docs/en/about-claude/models/overview
# NOTE: claude-sonnet-4-20250514 and claude-opus-4-20250514 were retired April 20, 2026.
CLAUDE_MODELS = [
    # Claude 4.7 (Latest Opus - April 2026)
    "claude-opus-4-7",                   # Most capable; step-change agentic coding improvement

    # Claude 4.6 Family (February 2026) - RECOMMENDED for most use cases
    "claude-opus-4-6",                   # Max reasoning depth; complex multi-step tasks
    "claude-sonnet-4-6",                 # Best speed/intelligence balance; daily driver

    # Claude 4.5 Family (Fall 2025)
    "claude-opus-4-5-20250929",          # Opus 4.5 - deep reasoning, coding, computer use
    "claude-sonnet-4-5-20250929",        # Sonnet 4.5 - agents, coding, office files
    "claude-haiku-4-5-20251001",         # Fastest; cost-efficient; near-frontier intelligence

    # Claude 4.1
    "claude-opus-4-1-20250805",          # Opus 4.1 - agentic search, expert coding

    # Claude 4.0 Family - DEPRECATED, retiring June 15, 2026
    # "claude-opus-4-20250514",          # Retired April 20, 2026
    # "claude-sonnet-4-20250514",        # Retired April 20, 2026

    # Claude 3.x Family - NOT SUPPORTED by Claude Agent SDK
    # "claude-3-7-sonnet-20250219",
    # "claude-3-5-sonnet-20241022",
    # "claude-3-5-haiku-20241022",
]

# Default model — Sonnet 4.6 is preferred by ~70% of devs; Opus-level quality at Sonnet price
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-6")

# Fast model for speed/cost optimization
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
