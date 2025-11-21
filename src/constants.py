"""
Constants and configuration for Claude Code OpenAI Wrapper.

Single source of truth for tool names, models, and other configuration values.
"""

# Claude Agent SDK Tool Names
# These are the built-in tools available in the Claude Agent SDK
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
# Models supported by Claude Agent SDK (as of November 2025)
# NOTE: Claude Agent SDK only supports Claude 4+ models, not Claude 3.x
CLAUDE_MODELS = [
    # Claude 4.5 Family (Latest - Fall 2025) - RECOMMENDED
    "claude-sonnet-4-5-20250929",  # Recommended - best coding model
    "claude-haiku-4-5-20251001",  # Fast & cheap
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

# Default model (recommended for most use cases)
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

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

# Batch Processing
BATCH_STORAGE_DIR = "./batch_storage"
BATCH_MAX_FILE_SIZE_MB = 100  # Maximum size for uploaded JSONL files
BATCH_FILE_RETENTION_DAYS = 7  # How long to keep batch files before cleanup
BATCH_CLEANUP_INTERVAL_MINUTES = 60  # How often to run cleanup task
BATCH_DEFAULT_TIMEOUT_HOURS = 24  # Default completion window
BATCH_MAX_REQUESTS_PER_BATCH = 50000  # Maximum number of requests in a single batch
BATCH_REQUEST_TIMEOUT_SECONDS = 300  # Timeout for individual batch requests (5 minutes)
