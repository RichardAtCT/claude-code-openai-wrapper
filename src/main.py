import os
import json
import asyncio
import logging
import secrets
import string
import time
import uuid
from typing import Optional, AsyncGenerator, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
import httpx
from dotenv import load_dotenv
from src import __version__

from src.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionStreamResponse,
    Choice,
    Message,
    Usage,
    StreamChoice,
    SessionListResponse,
    ToolListResponse,
    ToolMetadataResponse,
    ToolConfigurationResponse,
    ToolConfigurationRequest,
    MCPServerConfigRequest,
    MCPServerInfoResponse,
    MCPServersListResponse,
    MCPConnectionRequest,
    # Anthropic API compatible models
    AnthropicMessagesRequest,
    AnthropicMessagesResponse,
    AnthropicTextBlock,
    AnthropicUsage,
)
from src.claude_cli import ClaudeCodeCLI, ClaudeResultError
from src.circuit_breaker import sdk_circuit_breaker
from src.message_adapter import MessageAdapter, JsonFenceStripper
from src.function_calling import (
    build_tools_system_prompt,
    parse_tool_calls,
    format_tool_calls,
    convert_tool_messages,
)
from src.cpu_watchdog import cpu_watchdog
from src.auth import (
    verify_api_key,
    security,
    validate_claude_code_auth,
    get_claude_code_auth_info,
)

# Import the module (not the singletons) so reloads of src.auth in tests stay
# in sync with main.py's view of _auth.cli_health / auth_manager / probe_cli_auth.
from src import auth as _auth
from src.auth import _classify_probe_error  # pure function, safe to bind once
from src.parameter_validator import ParameterValidator, CompatibilityReporter
from src.session_manager import session_manager
from src.tool_manager import tool_manager
from src.mcp_client import mcp_client, MCPServerConfig
from src.rate_limiter import (
    limiter,
    rate_limit_exceeded_handler,
    rate_limit_endpoint,
)
from datetime import datetime, timezone

from src import constants
from src.constants import (
    ANTHROPIC_MODELS_URL,
    ANTHROPIC_VERSION,
    CLAUDE_MODELS,
    CLAUDE_TOOLS,
    DEFAULT_ALLOWED_TOOLS,
    DEFAULT_MODEL_FALLBACK,
    MODEL_LIST_CACHE_TTL_SECONDS,
    MODEL_LIST_ERROR_TTL_SECONDS,
    MODEL_LIST_REQUEST_TIMEOUT_SECONDS,
    SESSION_CLEANUP_INTERVAL_MINUTES,
)
from src.model_service import model_service
from src.request_cache import request_cache
from src.cost_tracker import cost_tracker, UsageRecord

# Load environment variables
load_dotenv()

# Configure logging based on debug mode
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() in ("true", "1", "yes", "on")
VERBOSE = os.getenv("VERBOSE", "false").lower() in ("true", "1", "yes", "on")

# Default max_turns applied when the request does not enable tools. A value of 1
# causes the Claude Agent SDK to return error_max_turns whenever the agent
# engages extended thinking and then needs a second turn to emit the final
# assistant message, which silently produced bad output for OpenAI clients.
DEFAULT_MAX_TURNS_NO_TOOLS = int(os.getenv("WRAPPER_DEFAULT_MAX_TURNS", "3"))


def _kv(event: str, **fields: Any) -> str:
    """Format a structured log line as "event key=value key=value ...".

    The wrapper's default logging format is plain text (see logging.basicConfig
    above) and drops ``logger.xxx(msg, extra={...})`` payloads entirely. That
    sent every structured log line to /dev/null -- we'd emit
    ``circuit_breaker_open`` with no breaker state attached, forcing ops to
    inspect response bodies to see what happened. Building the key=value pairs
    into the message string itself is the cheapest way to keep the data
    visible without reaching for a full JSON logger.

    ``None`` values are skipped so we don't spam ``stop_reason=None``. Values
    are repr'd when they contain whitespace or equals signs so a grep for
    ``key=value`` still works unambiguously.
    """
    parts = [event]
    for key, value in fields.items():
        if value is None:
            continue
        text = str(value)
        if any(ch.isspace() or ch == "=" for ch in text):
            text = repr(text)
        parts.append(f"{key}={text}")
    return " ".join(parts)


# Set logging level based on debug/verbose mode
log_level = logging.DEBUG if (DEBUG_MODE or VERBOSE) else logging.INFO
logging.basicConfig(level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Global variable to store runtime-generated API key
runtime_api_key = None

# Best-effort cache for Anthropic's live Models API.  The static constants remain
# the fallback so /v1/models keeps working for Claude CLI, Bedrock, Vertex, local
# development, and transient Anthropic API outages.
_model_list_cache: Dict[str, Any] = {"expires_at": 0.0, "models": None}
# Serializes cache refreshes so concurrent /v1/models requests at TTL expiry
# don't all stampede the upstream Anthropic API.
_model_list_lock = asyncio.Lock()


def _iso_to_unix(value: Any) -> Optional[int]:
    """Convert an Anthropic ISO-8601 'created_at' string to a unix timestamp."""
    if not isinstance(value, str):
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _openai_model_from_anthropic(model_info: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an Anthropic ModelInfo object to OpenAI-compatible model metadata."""
    created = _iso_to_unix(model_info.get("created_at"))
    model: Dict[str, Any] = {
        "id": model_info["id"],
        "object": "model",
        "created": created if created is not None else int(datetime.now(timezone.utc).timestamp()),
        "owned_by": "anthropic",
    }

    # Preserve useful Anthropic metadata for clients that want it.  OpenAI clients
    # ignore unknown keys, and the existing id/object/owned_by shape is retained.
    for key in (
        "display_name",
        "created_at",
        "max_input_tokens",
        "max_tokens",
        "capabilities",
        "type",
    ):
        if key in model_info:
            model[key] = model_info[key]

    return model


def _fallback_model_payload() -> List[Dict[str, Any]]:
    now = int(datetime.now(timezone.utc).timestamp())
    return [
        {"id": model_id, "object": "model", "created": now, "owned_by": "anthropic"}
        for model_id in CLAUDE_MODELS
    ]


async def _fetch_anthropic_models() -> Optional[List[Dict[str, Any]]]:
    """Fetch all available models from Anthropic, returning None on fallback-worthy errors."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    headers = {
        "anthropic-version": ANTHROPIC_VERSION,
        "x-api-key": api_key,
    }
    beta_header = os.getenv("ANTHROPIC_BETA") or os.getenv("ANTHROPIC_BETA_HEADER")
    if beta_header:
        headers["anthropic-beta"] = beta_header

    params: Dict[str, Any] = {"limit": 1000}
    models: List[Dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(timeout=MODEL_LIST_REQUEST_TIMEOUT_SECONDS) as client:
            while True:
                response = await client.get(ANTHROPIC_MODELS_URL, headers=headers, params=params)
                response.raise_for_status()
                payload = response.json()
                models.extend(
                    _openai_model_from_anthropic(model)
                    for model in payload.get("data", [])
                    if model.get("id")
                )

                if not payload.get("has_more") or not payload.get("last_id"):
                    break
                params["after_id"] = payload["last_id"]
    except Exception as exc:  # noqa: BLE001 - endpoint should degrade gracefully
        logger.warning("Failed to fetch Anthropic model list, using fallback: %s", exc)
        return None

    return models or None


async def get_available_models() -> List[Dict[str, Any]]:
    """Return live Anthropic models when possible, with cached static fallback."""
    if os.getenv("CLAUDE_MODELS_OVERRIDE", "").strip():
        return _fallback_model_payload()

    now = time.time()
    cached_models = _model_list_cache.get("models")
    if cached_models and now < float(_model_list_cache.get("expires_at", 0)):
        return cached_models

    async with _model_list_lock:
        # Recheck inside the lock so the first waiter populates the cache and
        # subsequent waiters return without re-fetching.
        now = time.time()
        cached_models = _model_list_cache.get("models")
        if cached_models and now < float(_model_list_cache.get("expires_at", 0)):
            return cached_models

        live_models = await _fetch_anthropic_models()
        if live_models:
            _model_list_cache.update(
                {"models": live_models, "expires_at": now + MODEL_LIST_CACHE_TTL_SECONDS}
            )
            return live_models

        fallback_models = _fallback_model_payload()
        # Use a short TTL on failure so transient outages don't suppress live
        # discovery for the full MODEL_LIST_CACHE_TTL_SECONDS window.
        _model_list_cache.update(
            {"models": fallback_models, "expires_at": now + MODEL_LIST_ERROR_TTL_SECONDS}
        )
        return fallback_models


def _pick_latest_sonnet(models: List[Dict[str, Any]]) -> Optional[str]:
    """Return the id of the newest Sonnet model in `models`, or None."""
    sonnets = [m for m in models if isinstance(m.get("id"), str) and "sonnet" in m["id"].lower()]
    if not sonnets:
        return None
    # Prefer Anthropic-provided created_at; fall back to the int `created` we set,
    # then to id-sort (date-suffixed ids sort correctly newest-last).
    sonnets.sort(
        key=lambda m: (
            _iso_to_unix(m.get("created_at")) or m.get("created") or 0,
            m["id"],
        )
    )
    return sonnets[-1]["id"]


async def resolve_default_model() -> Optional[str]:
    """Pick the latest Sonnet from /v1/models and store it as the default.

    Skipped when the operator pinned DEFAULT_MODEL via env var, or when no
    ANTHROPIC_API_KEY is configured (live discovery is the only auth-aware
    path; Bedrock, Vertex, and Claude CLI subscription users get the static
    DEFAULT_MODEL_FALLBACK).
    """
    if constants.DEFAULT_MODEL_ENV:
        return constants.DEFAULT_MODEL_ENV

    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.info(
            "Live model discovery disabled (no ANTHROPIC_API_KEY); " "using fallback default %s",
            DEFAULT_MODEL_FALLBACK,
        )
        return None

    try:
        models = await get_available_models()
    except Exception as exc:  # noqa: BLE001 - startup should never abort on this
        logger.warning("Could not resolve default model from /v1/models: %s", exc)
        return None

    latest = _pick_latest_sonnet(models)
    if latest:
        constants.RESOLVED_DEFAULT_MODEL = latest
        logger.info("Resolved default model from Anthropic Models API: %s", latest)
        return latest

    logger.info(
        "No Sonnet model found in /v1/models response; using fallback %s",
        DEFAULT_MODEL_FALLBACK,
    )
    return None


def log_json_structure(content: str, log: logging.Logger) -> None:
    """Log the structure of a JSON response for debugging."""
    try:
        data = json.loads(content)
        if isinstance(data, list):
            log.debug(f"JSON array with {len(data)} items")
            if len(data) > 0 and isinstance(data[0], dict):
                log.debug(f"First item fields: {list(data[0].keys())}")
        elif isinstance(data, dict):
            log.debug(f"JSON object fields: {list(data.keys())}")
    except json.JSONDecodeError:
        log.debug("Response is not valid JSON")


def generate_secure_token(length: int = 32) -> str:
    """Generate a secure random token for API authentication."""
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def prompt_for_api_protection() -> Optional[str]:
    """
    Interactively ask user if they want API key protection.
    Returns the generated token if user chooses protection, None otherwise.
    """
    # Don't prompt if API_KEY is already set via environment variable
    if os.getenv("API_KEY"):
        return None

    print("\n" + "=" * 60)
    print("🔐 API Endpoint Security Configuration")
    print("=" * 60)
    print("Would you like to protect your API endpoint with an API key?")
    print("This adds a security layer when accessing your server remotely.")
    print("")

    while True:
        try:
            choice = input("Enable API key protection? (y/N): ").strip().lower()

            if choice in ["", "n", "no"]:
                print("✅ API endpoint will be accessible without authentication")
                print("=" * 60)
                return None

            elif choice in ["y", "yes"]:
                token = generate_secure_token()
                print("")
                print("🔑 API Key Generated!")
                print("=" * 60)
                print(f"API Key: {token}")
                print("=" * 60)
                print("📋 IMPORTANT: Save this key - you'll need it for API calls!")
                print("   Example usage:")
                print(f'   curl -H "Authorization: Bearer {token}" \\')
                print("        http://localhost:8000/v1/models")
                print("=" * 60)
                return token

            else:
                print("Please enter 'y' for yes or 'n' for no (or press Enter for no)")

        except (EOFError, KeyboardInterrupt):
            print("\n✅ Defaulting to no authentication")
            return None


# Initialize Claude CLI
claude_cli = ClaudeCodeCLI(
    timeout=int(os.getenv("MAX_TIMEOUT", "600000")), cwd=os.getenv("CLAUDE_CWD")
)


def _log_build_info() -> None:
    """Log the SDK and bundled CLI versions baked into the image at build time.

    Lets ops tell from Loki which SDK shipped in a given container without
    shelling in. If /app/BUILD_INFO is missing (e.g. running from source),
    we fall back to asking the installed package for its version.
    """
    try:
        with open("/app/BUILD_INFO", "r") as f:
            contents = f.read().strip()
        logger.info(f"Build info:\n{contents}")
        return
    except FileNotFoundError:
        pass
    try:
        import importlib.metadata

        sdk_version = importlib.metadata.version("claude-agent-sdk")
        logger.info(f"Build info: claude-agent-sdk={sdk_version} (no BUILD_INFO file)")
    except Exception as e:
        logger.warning(f"Build info unavailable: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify Claude Code authentication and CLI on startup."""
    _log_build_info()
    logger.info("Verifying Claude Code authentication and CLI...")

    # Initialize model service (fetch models from API or use fallback)
    await model_service.initialize()

    # Validate authentication first
    auth_valid, auth_info = validate_claude_code_auth()

    if not auth_valid:
        logger.error("❌ Claude Code authentication failed!")
        for error in auth_info.get("errors", []):
            logger.error(f"  - {error}")
        logger.warning("Authentication setup guide:")
        logger.warning("  1. For Anthropic API: Set ANTHROPIC_API_KEY")
        logger.warning("  2. For Bedrock: Set CLAUDE_CODE_USE_BEDROCK=1 + AWS credentials")
        logger.warning("  3. For Vertex AI: Set CLAUDE_CODE_USE_VERTEX=1 + GCP credentials")
    else:
        logger.info(f"✅ Claude Code authentication validated: {auth_info['method']}")

    # Verify Claude Agent SDK with timeout for graceful degradation
    try:
        logger.info("Testing Claude Agent SDK connection...")
        # Use asyncio.wait_for to enforce timeout (30 seconds)
        cli_verified = await asyncio.wait_for(claude_cli.verify_cli(), timeout=30.0)

        if cli_verified:
            logger.info("✅ Claude Agent SDK verified successfully")
            _auth.cli_health.mark_ok()
        else:
            logger.warning("⚠️  Claude Agent SDK verification returned False")
            logger.warning("The server will start, but requests may fail.")
            _auth.cli_health.mark_failed("unknown", "startup verify_cli returned False")
    except asyncio.TimeoutError:
        logger.warning("⚠️  Claude Agent SDK verification timed out (30s)")
        logger.warning("This may indicate network issues or SDK configuration problems.")
        logger.warning("The server will start, but first request may be slow.")
        _auth.cli_health.mark_failed("unknown", "startup verify_cli timed out after 30s")
    except Exception as e:
        logger.error(f"⚠️  Claude Agent SDK verification failed: {e}")
        logger.warning("The server will start, but requests may fail.")
        logger.warning("Check that Claude Code CLI is properly installed and authenticated.")
        _auth.cli_health.mark_failed(_classify_probe_error(str(e)), str(e))

    # Log debug information if debug mode is enabled
    if DEBUG_MODE or VERBOSE:
        logger.debug("🔧 Debug mode enabled - Enhanced logging active")
        logger.debug("🔧 Environment variables:")
        logger.debug(f"   DEBUG_MODE: {DEBUG_MODE}")
        logger.debug(f"   VERBOSE: {VERBOSE}")
        logger.debug(f"   PORT: {os.getenv('PORT', '8000')}")
        cors_origins_val = os.getenv("CORS_ORIGINS", '["*"]')
        logger.debug(f"   CORS_ORIGINS: {cors_origins_val}")
        logger.debug(f"   MAX_TIMEOUT: {os.getenv('MAX_TIMEOUT', '600000')}")
        logger.debug(f"   CLAUDE_CWD: {os.getenv('CLAUDE_CWD', 'Not set')}")
        logger.debug("🔧 Available endpoints:")
        logger.debug("   POST /v1/chat/completions - Main chat endpoint")
        logger.debug("   GET  /v1/models - List available models")
        logger.debug("   POST /v1/debug/request - Debug request validation")
        logger.debug("   GET  /v1/auth/status - Authentication status")
        logger.debug("   GET  /health - Health check")
        logger.debug(
            f"🔧 API Key protection: {'Enabled' if (os.getenv('API_KEY') or runtime_api_key) else 'Disabled'}"
        )

    # Resolve the default model from the live Anthropic Models API so /v1/chat
    # uses the latest Sonnet without a code change. Best-effort: any failure
    # leaves the static fallback in place.
    try:
        await resolve_default_model()
    except Exception as e:
        logger.warning(f"Default model resolution skipped: {e}")

    # Start session cleanup task
    session_manager.start_cleanup_task()

    # Start cost tracker cleanup task (mirrors session cleanup interval)
    async def cost_cleanup_loop():
        try:
            while True:
                await asyncio.sleep(SESSION_CLEANUP_INTERVAL_MINUTES * 60)
                await cost_tracker.cleanup_expired()
        except asyncio.CancelledError:
            pass

    cost_cleanup_task = asyncio.get_running_loop().create_task(cost_cleanup_loop())

    # Periodic CLI auth probe. Only runs when auth_method == claude_cli because
    # API key / Bedrock / Vertex failures already surface as
    # assistant_authentication_failed via _ASSISTANT_ERROR_STATUS. Set the
    # interval to 0 to disable. Each probe is a 1-turn query and costs ~$0.001
    # at Sonnet pricing; default 10 min keeps the bill low while still bounding
    # the stale window.
    async def cli_auth_probe_loop():
        interval = int(os.getenv("CLI_AUTH_PROBE_INTERVAL_SECONDS", "600"))
        if interval <= 0:
            logger.info("cli_auth_probe disabled (interval=%s)", interval)
            return
        try:
            while True:
                await asyncio.sleep(interval)
                if _auth.auth_manager.auth_method != "claude_cli":
                    continue
                await _auth.probe_cli_auth()
        except asyncio.CancelledError:
            pass

    cli_auth_probe_task = asyncio.get_running_loop().create_task(cli_auth_probe_loop())

    # Start CPU watchdog (Linux/Docker only)
    cpu_watchdog.start()

    yield

    cpu_watchdog.stop()
    cost_cleanup_task.cancel()
    cli_auth_probe_task.cancel()

    # Cleanup on shutdown
    logger.info("Shutting down session manager...")
    session_manager.shutdown()

    # Shutdown model service
    await model_service.shutdown()


# Create FastAPI app
app = FastAPI(
    title="Claude Code OpenAI API Wrapper",
    description="OpenAI-compatible API for Claude Code",
    version=__version__,
    lifespan=lifespan,
)

# Configure CORS
cors_origins = json.loads(os.getenv("CORS_ORIGINS", '["*"]'))
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add rate limiting error handler
if limiter:
    app.state.limiter = limiter
    app.add_exception_handler(429, rate_limit_exceeded_handler)

# Security configuration
MAX_REQUEST_SIZE = int(os.getenv("MAX_REQUEST_SIZE", str(10 * 1024 * 1024)))  # 10MB default

# Add middleware
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add unique request ID to each request for audit trails."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit request body size to prevent DoS attacks."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_SIZE:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "message": f"Request body too large. Maximum size is {MAX_REQUEST_SIZE} bytes.",
                        "type": "request_too_large",
                        "code": 413,
                    }
                },
            )
        return await call_next(request)


# Add security middleware (order matters - first added = last executed)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)


class DebugLoggingMiddleware(BaseHTTPMiddleware):
    """ASGI-compliant middleware for logging request/response details when debug mode is enabled."""

    async def dispatch(self, request: Request, call_next):
        # Get request ID for correlation
        request_id = getattr(request.state, "request_id", "unknown")

        if not (DEBUG_MODE or VERBOSE):
            return await call_next(request)

        # Log request details
        start_time = asyncio.get_event_loop().time()

        # Log basic request info with request ID for correlation
        logger.debug(f"🔍 [{request_id}] Incoming request: {request.method} {request.url}")
        logger.debug(f"🔍 [{request_id}] Headers: {dict(request.headers)}")

        # For POST requests, try to log body (but don't break if we can't)
        body_logged = False
        if request.method == "POST" and request.url.path.startswith("/v1/"):
            try:
                # Only attempt to read body if it's reasonable size and content-type
                content_length = request.headers.get("content-length")
                if content_length and int(content_length) < 100000:  # Less than 100KB
                    body = await request.body()
                    if body:
                        try:
                            import json as json_lib

                            parsed_body = json_lib.loads(body.decode())
                            logger.debug(
                                f"🔍 Request body: {json_lib.dumps(parsed_body, indent=2)}"
                            )
                            body_logged = True
                        except:
                            logger.debug(f"🔍 Request body (raw): {body.decode()[:500]}...")
                            body_logged = True
            except Exception as e:
                logger.debug(f"🔍 Could not read request body: {e}")

        if not body_logged and request.method == "POST":
            logger.debug("🔍 Request body: [not logged - streaming or large payload]")

        # Process the request
        try:
            response = await call_next(request)

            # Log response details
            end_time = asyncio.get_event_loop().time()
            duration = (end_time - start_time) * 1000  # Convert to milliseconds

            logger.debug(f"🔍 Response: {response.status_code} in {duration:.2f}ms")

            return response

        except Exception as e:
            end_time = asyncio.get_event_loop().time()
            duration = (end_time - start_time) * 1000

            logger.debug(f"🔍 Request failed after {duration:.2f}ms: {e}")
            raise


# Add the debug middleware
app.add_middleware(DebugLoggingMiddleware)


# Custom exception handler for 422 validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors with detailed debugging information."""

    # Log the validation error details
    logger.error(f"❌ Request validation failed for {request.method} {request.url}")
    logger.error(f"❌ Validation errors: {exc.errors()}")

    # Create detailed error response
    error_details = []
    for error in exc.errors():
        location = " -> ".join(str(loc) for loc in error.get("loc", []))
        error_details.append(
            {
                "field": location,
                "message": error.get("msg", "Unknown validation error"),
                "type": error.get("type", "validation_error"),
                "input": error.get("input"),
            }
        )

    # If debug mode is enabled, include the raw request body
    debug_info = {}
    if DEBUG_MODE or VERBOSE:
        try:
            body = await request.body()
            if body:
                debug_info["raw_request_body"] = body.decode()
        except:
            debug_info["raw_request_body"] = "Could not read request body"

    error_response = {
        "error": {
            "message": "Request validation failed - the request body doesn't match the expected format",
            "type": "validation_error",
            "code": "invalid_request_error",
            "details": error_details,
            "help": {
                "common_issues": [
                    "Missing required fields (model, messages)",
                    "Invalid field types (e.g. messages should be an array)",
                    "Invalid role values (must be 'system', 'user', or 'assistant')",
                    "Invalid parameter ranges (e.g. temperature must be 0-2)",
                ],
                "debug_tip": "Set DEBUG_MODE=true or VERBOSE=true environment variable for more detailed logging",
            },
        }
    }

    # Add debug info if available
    if debug_info:
        error_response["error"]["debug"] = debug_info

    return JSONResponse(status_code=422, content=error_response)


def _build_claude_options(
    request: ChatCompletionRequest,
    claude_headers: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build validated Claude SDK options from a request and optional headers.

    Shared by both the streaming and non-streaming code paths.
    """
    claude_options = request.to_claude_options()

    if claude_headers:
        claude_options.update(claude_headers)

    if claude_options.get("model"):
        ParameterValidator.validate_model(claude_options["model"])

    if request.max_tokens and claude_options.get("model"):
        validated = ParameterValidator.validate_max_tokens(
            claude_options["model"], request.max_tokens
        )
        if validated is not None:
            claude_options["max_tokens"] = validated

    if not request.enable_tools:
        claude_options["disallowed_tools"] = CLAUDE_TOOLS
        claude_options["max_turns"] = DEFAULT_MAX_TURNS_NO_TOOLS
        logger.info(
            f"Tools disabled (default behavior for OpenAI compatibility); "
            f"max_turns={DEFAULT_MAX_TURNS_NO_TOOLS} "
            f"(override via WRAPPER_DEFAULT_MAX_TURNS)"
        )
    else:
        claude_options["allowed_tools"] = DEFAULT_ALLOWED_TOOLS
        claude_options["permission_mode"] = "bypassPermissions"
        logger.info(f"Tools enabled by user request: {DEFAULT_ALLOWED_TOOLS}")

    return claude_options


def _build_error_max_turns_response(
    request_id: str, model: str, err: ClaudeResultError
) -> JSONResponse:
    """Translate error_max_turns into a valid OpenAI chat completion with
    finish_reason='length' and empty content. Clients see a well-formed
    response and can decide whether to retry with different parameters
    rather than receiving silent garbage."""
    logger.warning(
        _kv(
            "claude_sdk_error_max_turns",
            request_id=request_id,
            num_turns=err.num_turns,
            stop_reason=err.stop_reason,
            errors=err.errors,
        )
    )
    response = ChatCompletionResponse(
        id=request_id,
        model=model,
        choices=[
            Choice(
                index=0,
                message=Message(role="assistant", content=""),
                finish_reason="length",
            )
        ],
        usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
    )
    return JSONResponse(status_code=200, content=response.model_dump())


def _build_sdk_error_response(request_id: str, model: str, err: ClaudeResultError) -> JSONResponse:
    """Non-recoverable SDK result: return 502 so clients know to retry with
    backoff. Structured body includes the SDK subtype and any errors so
    callers can tell the difference between a max-turns overflow and a
    transport failure.

    Defense-in-depth for the CLI-auth probe loop: when stderr_tail (or the
    error_message) matches the known auth-failure markers, return 401 instead
    and seed _auth.cli_health so the next request fails fast without a round-trip.
    """
    logger.error(
        _kv(
            "claude_sdk_error",
            request_id=request_id,
            subtype=err.subtype,
            num_turns=err.num_turns,
            errors=err.errors,
            error_message=err.error_message,
            stderr_tail_chars=len(err.stderr_tail or ""),
        )
    )
    if err.stderr_tail:
        logger.error(
            f"claude_sdk_error stderr tail (request_id={request_id}):\n" f"{err.stderr_tail}"
        )

    blob = " ".join(filter(None, [err.error_message, err.stderr_tail]))
    if _classify_probe_error(blob) == "auth_failure":
        _auth.cli_health.mark_failed("auth_failure", blob)
        logger.warning(
            _kv(
                "claude_sdk_cli_auth_failed",
                request_id=request_id,
                model=model,
                subtype=err.subtype,
            )
        )
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": (
                        "Claude CLI is not authenticated. Run `claude /login` "
                        "on the wrapper host and restart, or set "
                        "ANTHROPIC_API_KEY."
                    ),
                    "type": "authentication_error",
                    "code": "claude_cli_not_authenticated",
                }
            },
        )

    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "message": err.error_message
                or (err.errors[0] if err.errors else f"SDK returned {err.subtype}"),
                "type": "upstream_sdk_error",
                "code": err.subtype or "unknown",
            }
        },
    )


# Map AssistantMessage error literals to HTTP status codes so each upstream
# failure mode surfaces with the right semantics instead of collapsing to 502:
#   rate_limit -> 429 (retryable with backoff; callers should honor Retry-After)
#   billing_error -> 402 (permanent until billing is resolved)
#   authentication_failed -> 401 (permanent until auth is fixed)
#   invalid_request -> 400 (client bug)
#   server_error / unknown -> 502 (retry with backoff)
_ASSISTANT_ERROR_STATUS = {
    "assistant_rate_limit": 429,
    "assistant_billing_error": 402,
    "assistant_authentication_failed": 401,
    "assistant_invalid_request": 400,
    "assistant_server_error": 502,
    "assistant_unknown": 502,
}

_ASSISTANT_ERROR_MESSAGE = {
    "assistant_rate_limit": "Upstream rate limit exceeded",
    "assistant_billing_error": "Upstream billing error",
    "assistant_authentication_failed": "Upstream authentication failed",
    "assistant_invalid_request": "Upstream rejected the request as invalid",
    "assistant_server_error": "Upstream server error",
    "assistant_unknown": "Upstream request failed",
}


def _safe_assistant_error_message(subtype: Optional[str]) -> str:
    """Return a client-safe message that does not leak exception detail."""
    return _ASSISTANT_ERROR_MESSAGE.get(subtype or "", "Upstream request failed")


def _build_assistant_error_response(
    request_id: str, model: str, err: ClaudeResultError
) -> JSONResponse:
    """Translate an AssistantMessage error to a status-coded OpenAI error."""
    status = _ASSISTANT_ERROR_STATUS.get(err.subtype or "", 502)
    headers = None
    if status == 429:
        # Conservative default. Callers that want a smarter backoff should
        # inspect upstream rate-limit headers once the SDK exposes them.
        headers = {"Retry-After": "30"}
    logger.warning(
        _kv(
            "claude_sdk_assistant_error",
            request_id=request_id,
            subtype=err.subtype,
            errors=err.errors,
            status=status,
        )
    )
    return JSONResponse(
        status_code=status,
        headers=headers,
        content={
            "error": {
                "message": _safe_assistant_error_message(err.subtype),
                "type": "upstream_api_error",
                "code": err.subtype or "unknown",
            }
        },
    )


def _handle_claude_result_error(
    request_id: str, model: str, err: ClaudeResultError
) -> JSONResponse:
    """Route a ClaudeResultError to the right OpenAI-shaped response.

    Records the outcome against the circuit breaker so a burst of SDK
    failures across many requests trips the breaker and fails-fast future
    traffic for a short cool-off period.
    """
    # error_max_turns still returned a 200 to the caller with finish_reason=
    # length; treat it as upstream "bad" for breaker purposes because from a
    # reliability perspective it's a failed completion.
    sdk_circuit_breaker.record(success=False)
    if err.subtype == "error_max_turns":
        return _build_error_max_turns_response(request_id, model, err)
    if err.subtype in _ASSISTANT_ERROR_STATUS:
        return _build_assistant_error_response(request_id, model, err)
    return _build_sdk_error_response(request_id, model, err)


def _run_completion_kwargs(
    claude_options: Dict[str, Any], prompt: str, system_prompt: Optional[str], stream: bool
) -> Dict[str, Any]:
    """Extract run_completion keyword arguments from claude_options."""
    return {
        "prompt": prompt,
        "system_prompt": system_prompt,
        "model": claude_options.get("model"),
        "max_turns": claude_options.get("max_turns", 10),
        "allowed_tools": claude_options.get("allowed_tools"),
        "disallowed_tools": claude_options.get("disallowed_tools"),
        "permission_mode": claude_options.get("permission_mode"),
        "effort": claude_options.get("effort"),
        "thinking": claude_options.get("thinking"),
        "stream": stream,
    }


async def generate_streaming_response(
    request: ChatCompletionRequest, request_id: str, claude_headers: Optional[Dict[str, Any]] = None
) -> AsyncGenerator[str, None]:
    """Generate SSE formatted streaming response."""
    try:
        # Process messages with session management
        all_messages, actual_session_id = session_manager.process_messages(
            request.messages, request.session_id
        )

        # Convert tool role messages for Claude compatibility
        if request.tools:
            all_messages = convert_tool_messages(all_messages)

        # Convert messages to prompt
        prompt, system_prompt = MessageAdapter.messages_to_prompt(all_messages)

        # Add sampling instructions from temperature/top_p if present
        sampling_instructions = request.get_sampling_instructions()
        if sampling_instructions:
            if system_prompt:
                system_prompt = f"{system_prompt}\n\n{sampling_instructions}"
            else:
                system_prompt = sampling_instructions
            logger.debug(f"Added sampling instructions: {sampling_instructions}")

        # Function calling: inject tool definitions into system prompt
        has_tools = request.tools and len(request.tools) > 0
        if has_tools:
            tools_dicts = [t.model_dump() for t in request.tools]
            tools_prompt = build_tools_system_prompt(tools_dicts, request.tool_choice)
            if tools_prompt:
                if system_prompt:
                    system_prompt = f"{system_prompt}\n\n{tools_prompt}"
                else:
                    system_prompt = tools_prompt
                logger.info(
                    f"Function calling (streaming): injected {len(request.tools)} tool definitions"
                )

        # Check for JSON mode
        json_mode = request.response_format and request.response_format.type in (
            "json_object",
            "json_schema",
        )
        if json_mode:
            if (
                request.response_format.type == "json_schema"
                and request.response_format.json_schema
            ):
                schema = request.response_format.json_schema
                schema_json = json.dumps(schema.schema_ or {}, indent=2)
                schema_instructions = MessageAdapter.JSON_SCHEMA_TEMPLATE.format(
                    schema_json=schema_json
                )
                prompt = f"{schema_instructions}\n\n{prompt}"
                logger.info(f"JSON schema mode (streaming): injected schema into prompt")
            else:
                if system_prompt:
                    system_prompt = f"{MessageAdapter.JSON_MODE_INSTRUCTION}\n\n{system_prompt}"
                else:
                    system_prompt = MessageAdapter.JSON_MODE_INSTRUCTION
                prompt = prompt + MessageAdapter.JSON_PROMPT_SUFFIX
                logger.info(
                    "JSON mode enabled (streaming) - instruction added to system and user prompt"
                )

        # Filter content for unsupported features
        prompt = MessageAdapter.filter_content(prompt)
        if system_prompt:
            system_prompt = MessageAdapter.filter_content(system_prompt)

        claude_options = _build_claude_options(request, claude_headers)

        # Run Claude Code
        chunks_buffer = []
        role_sent = False  # Track if we've sent the initial role chunk
        content_sent = False  # Track if we've sent any content
        json_mode_buffer = []  # Buffer for JSON mode - accumulate all content
        tool_call_buffer = []  # Buffer when tools are defined - parse at end
        fence_stripper = JsonFenceStripper() if json_mode else None

        if has_tools and json_mode:
            logger.info("Both tools and JSON mode active -- tools take priority for buffering")

        async for chunk in claude_cli.run_completion(
            **_run_completion_kwargs(claude_options, prompt, system_prompt, stream=True),
        ):
            chunks_buffer.append(chunk)

            # Check if we have an assistant message
            # Handle both old format (type/message structure) and new format (direct content)
            content = None
            if chunk.get("type") == "assistant" and "message" in chunk:
                # Old format: {"type": "assistant", "message": {"content": [...]}}
                message = chunk["message"]
                if isinstance(message, dict) and "content" in message:
                    content = message["content"]
            elif "content" in chunk and isinstance(chunk["content"], list):
                # New format: {"content": [TextBlock(...)]}  (converted AssistantMessage)
                content = chunk["content"]

            if content is not None:
                # Send initial role chunk if we haven't already
                if not role_sent:
                    initial_chunk = ChatCompletionStreamResponse(
                        id=request_id,
                        model=request.model,
                        choices=[
                            StreamChoice(
                                index=0,
                                delta={"role": "assistant", "content": ""},
                                finish_reason=None,
                            )
                        ],
                    )
                    yield f"data: {initial_chunk.model_dump_json()}\n\n"
                    role_sent = True

                # Handle content blocks
                if isinstance(content, list):
                    for block in content:
                        # Handle TextBlock objects from Claude Agent SDK
                        if hasattr(block, "text"):
                            raw_text = block.text
                        # Handle dictionary format for backward compatibility
                        elif isinstance(block, dict) and block.get("type") == "text":
                            raw_text = block.get("text", "")
                        else:
                            continue

                        # Filter out tool usage and thinking blocks
                        filtered_text = MessageAdapter.filter_content(raw_text)

                        if filtered_text and not filtered_text.isspace():
                            if has_tools:
                                # Buffer when tools defined -- parse tool_calls at end
                                tool_call_buffer.append(filtered_text)
                            elif json_mode and fence_stripper:
                                # Stream through fence stripper
                                stripped = fence_stripper.process_delta(filtered_text)
                                if stripped:
                                    stream_chunk = ChatCompletionStreamResponse(
                                        id=request_id,
                                        model=request.model,
                                        choices=[
                                            StreamChoice(
                                                index=0,
                                                delta={"content": stripped},
                                                finish_reason=None,
                                            )
                                        ],
                                    )
                                    yield f"data: {stream_chunk.model_dump_json()}\n\n"
                                    content_sent = True
                            elif json_mode:
                                json_mode_buffer.append(filtered_text)
                            else:
                                stream_chunk = ChatCompletionStreamResponse(
                                    id=request_id,
                                    model=request.model,
                                    choices=[
                                        StreamChoice(
                                            index=0,
                                            delta={"content": filtered_text},
                                            finish_reason=None,
                                        )
                                    ],
                                )
                                yield f"data: {stream_chunk.model_dump_json()}\n\n"
                                content_sent = True

                elif isinstance(content, str):
                    filtered_content = MessageAdapter.filter_content(content)

                    if filtered_content and not filtered_content.isspace():
                        if has_tools:
                            tool_call_buffer.append(filtered_content)
                        elif json_mode and fence_stripper:
                            stripped = fence_stripper.process_delta(filtered_content)
                            if stripped:
                                stream_chunk = ChatCompletionStreamResponse(
                                    id=request_id,
                                    model=request.model,
                                    choices=[
                                        StreamChoice(
                                            index=0, delta={"content": stripped}, finish_reason=None
                                        )
                                    ],
                                )
                                yield f"data: {stream_chunk.model_dump_json()}\n\n"
                                content_sent = True
                        elif json_mode:
                            json_mode_buffer.append(filtered_content)
                        else:
                            stream_chunk = ChatCompletionStreamResponse(
                                id=request_id,
                                model=request.model,
                                choices=[
                                    StreamChoice(
                                        index=0,
                                        delta={"content": filtered_content},
                                        finish_reason=None,
                                    )
                                ],
                            )
                            yield f"data: {stream_chunk.model_dump_json()}\n\n"
                            content_sent = True

        # Flush fence stripper if used
        if json_mode and fence_stripper:
            remaining = fence_stripper.flush()
            if remaining:
                if not role_sent:
                    initial_chunk = ChatCompletionStreamResponse(
                        id=request_id,
                        model=request.model,
                        choices=[
                            StreamChoice(
                                index=0,
                                delta={"role": "assistant", "content": ""},
                                finish_reason=None,
                            )
                        ],
                    )
                    yield f"data: {initial_chunk.model_dump_json()}\n\n"
                    role_sent = True
                flush_chunk = ChatCompletionStreamResponse(
                    id=request_id,
                    model=request.model,
                    choices=[
                        StreamChoice(index=0, delta={"content": remaining}, finish_reason=None)
                    ],
                )
                yield f"data: {flush_chunk.model_dump_json()}\n\n"
                content_sent = True

        # Handle tool call buffer: parse and emit tool_calls
        if has_tools and tool_call_buffer:
            combined = "".join(tool_call_buffer)
            parsed_calls, remaining_text = parse_tool_calls(combined)
            if not role_sent:
                initial_chunk = ChatCompletionStreamResponse(
                    id=request_id,
                    model=request.model,
                    choices=[
                        StreamChoice(
                            index=0, delta={"role": "assistant", "content": ""}, finish_reason=None
                        )
                    ],
                )
                yield f"data: {initial_chunk.model_dump_json()}\n\n"
                role_sent = True
            if parsed_calls:
                formatted = format_tool_calls(parsed_calls)
                tc_delta = {"tool_calls": [tc.model_dump() for tc in formatted]}
                if remaining_text.strip():
                    tc_delta["content"] = remaining_text.strip()
                tc_chunk = ChatCompletionStreamResponse(
                    id=request_id,
                    model=request.model,
                    choices=[StreamChoice(index=0, delta=tc_delta, finish_reason=None)],
                )
                yield f"data: {tc_chunk.model_dump_json()}\n\n"
                content_sent = True
            elif combined.strip():
                text_chunk = ChatCompletionStreamResponse(
                    id=request_id,
                    model=request.model,
                    choices=[
                        StreamChoice(index=0, delta={"content": combined}, finish_reason=None)
                    ],
                )
                yield f"data: {text_chunk.model_dump_json()}\n\n"
                content_sent = True

        # Handle JSON mode: emit accumulated content as single JSON-formatted chunk
        if json_mode and json_mode_buffer:
            # Send role chunk first if not sent
            if not role_sent:
                initial_chunk = ChatCompletionStreamResponse(
                    id=request_id,
                    model=request.model,
                    choices=[
                        StreamChoice(
                            index=0, delta={"role": "assistant", "content": ""}, finish_reason=None
                        )
                    ],
                )
                yield f"data: {initial_chunk.model_dump_json()}\n\n"
                role_sent = True

            # Combine buffered content and enforce JSON format
            combined_content = "".join(json_mode_buffer)

            if DEBUG_MODE or VERBOSE:
                raw_preview = (
                    combined_content[:50] if len(combined_content) > 50 else combined_content
                )
                raw_end = combined_content[-30:] if len(combined_content) > 30 else combined_content
                logger.debug(f"Raw response: starts='{raw_preview}' ends='...{raw_end}'")

            json_content, extraction_metadata = MessageAdapter.enforce_json_format_with_metadata(
                combined_content, strict=True
            )

            if DEBUG_MODE or VERBOSE:
                logger.debug(f"JSON extraction metadata: {extraction_metadata}")
                logger.debug(f"Extracted JSON preview: {json_content[:200]}")
                log_json_structure(json_content, logger)

            # Emit as single chunk
            json_chunk = ChatCompletionStreamResponse(
                id=request_id,
                model=request.model,
                choices=[
                    StreamChoice(index=0, delta={"content": json_content}, finish_reason=None)
                ],
            )
            yield f"data: {json_chunk.model_dump_json()}\n\n"
            content_sent = True

        # Handle case where no role was sent (send at least role chunk)
        if not role_sent:
            # Send role chunk with empty content if we never got any assistant messages
            initial_chunk = ChatCompletionStreamResponse(
                id=request_id,
                model=request.model,
                choices=[
                    StreamChoice(
                        index=0, delta={"role": "assistant", "content": ""}, finish_reason=None
                    )
                ],
            )
            yield f"data: {initial_chunk.model_dump_json()}\n\n"
            role_sent = True

        # If we sent role but no content, send a minimal response
        if role_sent and not content_sent:
            fallback_content = (
                "[]" if json_mode else "I'm unable to provide a response at the moment."
            )
            fallback_chunk = ChatCompletionStreamResponse(
                id=request_id,
                model=request.model,
                choices=[
                    StreamChoice(
                        index=0,
                        delta={"content": fallback_content},
                        finish_reason=None,
                    )
                ],
            )
            yield f"data: {fallback_chunk.model_dump_json()}\n\n"

        # Extract assistant response from all chunks. parse_claude_message
        # raises ClaudeResultError on SDK error_max_turns / error_during_execution;
        # emit a terminal SSE event with finish_reason='length' (max_turns) or an
        # error payload (other), then close. Do NOT let sentinel text stream out.
        assistant_content = None
        sdk_error: Optional[ClaudeResultError] = None
        if chunks_buffer:
            try:
                assistant_content = claude_cli.parse_claude_message(chunks_buffer)
            except ClaudeResultError as err:
                sdk_error = err

            # Store in session if applicable
            if actual_session_id and assistant_content:
                assistant_message = Message(role="assistant", content=assistant_content)
                session_manager.add_assistant_response(actual_session_id, assistant_message)

        if sdk_error is not None:
            if sdk_error.subtype == "error_max_turns":
                final_chunk = ChatCompletionStreamResponse(
                    id=request_id,
                    model=request.model,
                    choices=[StreamChoice(index=0, delta={}, finish_reason="length")],
                )
                logger.warning(
                    _kv(
                        "claude_sdk_error_max_turns_stream",
                        request_id=request_id,
                        num_turns=sdk_error.num_turns,
                    )
                )
                yield f"data: {final_chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
            else:
                logger.error(
                    _kv(
                        "claude_sdk_error_stream",
                        request_id=request_id,
                        subtype=sdk_error.subtype,
                        errors=sdk_error.errors,
                    )
                )
                err_payload = {
                    "error": {
                        "message": sdk_error.error_message
                        or (
                            sdk_error.errors[0]
                            if sdk_error.errors
                            else f"SDK returned {sdk_error.subtype}"
                        ),
                        "type": "upstream_sdk_error",
                        "code": sdk_error.subtype or "unknown",
                    }
                }
                yield f"data: {json.dumps(err_payload)}\n\n"
                yield "data: [DONE]\n\n"
            return

        # Prepare usage data if requested
        usage_data = None
        if request.stream_options and request.stream_options.include_usage:
            # Estimate token usage based on prompt and completion
            completion_text = assistant_content or ""
            token_usage = claude_cli.estimate_token_usage(prompt, completion_text, request.model)
            usage_data = Usage(
                prompt_tokens=token_usage["prompt_tokens"],
                completion_tokens=token_usage["completion_tokens"],
                total_tokens=token_usage["total_tokens"],
            )
            logger.debug(f"Estimated usage: {usage_data}")

            await cost_tracker.record_usage(
                session_id=actual_session_id or request_id,
                model=request.model,
                usage=UsageRecord(
                    input_tokens=token_usage["prompt_tokens"],
                    output_tokens=token_usage["completion_tokens"],
                ),
            )

        # Send final chunk with finish reason and optionally usage data
        final_chunk = ChatCompletionStreamResponse(
            id=request_id,
            model=request.model,
            choices=[StreamChoice(index=0, delta={}, finish_reason="stop")],
            usage=usage_data,
        )
        yield f"data: {final_chunk.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Streaming error: {e}")
        error_chunk = {"error": {"message": "Streaming failed", "type": "streaming_error"}}
        yield f"data: {json.dumps(error_chunk)}\n\n"


def _check_cli_auth_or_401() -> Optional[JSONResponse]:
    """Gate request handlers on the latest CLI-auth probe + the auth manager.

    Returns a JSONResponse with HTTP 401 (or 503 for non-cli auth methods)
    when authentication is unhealthy, else None.

    Returning a JSONResponse directly - rather than raising HTTPException -
    is intentional: the global http_exception_handler wraps all detail bodies
    as `error.type=api_error`, which clobbers the OpenAI-shaped
    `authentication_error` literal that clients route on.
    """
    if _auth.auth_manager.auth_method == "claude_cli" and not _auth.cli_health.ok:
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": (
                        "Claude CLI authentication is not healthy. "
                        "Run `claude /login` on the wrapper host and restart, "
                        "or set ANTHROPIC_API_KEY."
                    ),
                    "type": "authentication_error",
                    "code": "claude_cli_not_authenticated",
                    "last_probed_at": (
                        _auth.cli_health.last_probed_at.isoformat()
                        if _auth.cli_health.last_probed_at
                        else None
                    ),
                    "error_kind": _auth.cli_health.error_kind,
                    "error_message": _auth.cli_health.error_message,
                }
            },
        )

    auth_valid, auth_info = validate_claude_code_auth()
    if not auth_valid:
        status = 401 if _auth.auth_manager.auth_method == "claude_cli" else 503
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "message": "Claude Code authentication failed",
                    "type": "authentication_error" if status == 401 else "service_unavailable",
                    "code": "claude_cli_not_authenticated" if status == 401 else "auth_unavailable",
                    "errors": auth_info.get("errors", []),
                    "method": auth_info.get("method", "none"),
                }
            },
        )

    return None


@app.post("/v1/chat/completions")
@rate_limit_endpoint("chat")
async def chat_completions(
    request_body: ChatCompletionRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """OpenAI-compatible chat completions endpoint."""
    # Check FastAPI API key if configured
    await verify_api_key(request, credentials)

    # Gate on Claude CLI probe + config-level auth validation.
    auth_block = _check_cli_auth_or_401()
    if auth_block is not None:
        return auth_block

    # Circuit breaker check: if the SDK has been failing at >50% for a minute,
    # fail-fast with 503 instead of forwarding another doomed request. The
    # breaker half-opens after open_seconds and lets a single probe through.
    if not sdk_circuit_breaker.allow_request():
        snapshot = sdk_circuit_breaker.snapshot()
        logger.warning(_kv("circuit_breaker_open", **snapshot))
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "30"},
            content={
                "error": {
                    "message": (
                        "Upstream SDK is unhealthy (circuit breaker open). "
                        "Retry after the window resets."
                    ),
                    "type": "circuit_breaker_open",
                    "code": "circuit_open",
                    "breaker": snapshot,
                }
            },
        )

    try:
        request_id = f"chatcmpl-{os.urandom(8).hex()}"

        # Extract Claude-specific parameters from headers
        claude_headers = ParameterValidator.extract_claude_headers(dict(request.headers))

        # Log compatibility info
        if logger.isEnabledFor(logging.DEBUG):
            compatibility_report = CompatibilityReporter.generate_compatibility_report(request_body)
            logger.debug(f"Compatibility report: {compatibility_report}")

        if request_body.stream:
            # Return streaming response
            return StreamingResponse(
                generate_streaming_response(request_body, request_id, claude_headers),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )
        else:
            # Non-streaming response
            # Check cache if enabled and requested via header
            cache_enabled = request.headers.get("X-Enable-Cache", "").lower() in (
                "true",
                "1",
                "yes",
            )
            if cache_enabled and request_cache.enabled:
                request_dict = request_body.model_dump()
                cached_response = request_cache.get(request_dict)
                if cached_response:
                    logger.info(f"Cache hit for request {request_id}")
                    # Return cached response with updated request ID
                    cached_response["id"] = request_id
                    return cached_response

            # Process messages with session management
            all_messages, actual_session_id = session_manager.process_messages(
                request_body.messages, request_body.session_id
            )

            logger.info(
                f"Chat completion: session_id={actual_session_id}, total_messages={len(all_messages)}"
            )

            # Convert tool role messages for Claude compatibility
            if request_body.tools:
                all_messages = convert_tool_messages(all_messages)

            # Convert messages to prompt
            prompt, system_prompt = MessageAdapter.messages_to_prompt(all_messages)

            # Add sampling instructions from temperature/top_p if present
            sampling_instructions = request_body.get_sampling_instructions()
            if sampling_instructions:
                if system_prompt:
                    system_prompt = f"{system_prompt}\n\n{sampling_instructions}"
                else:
                    system_prompt = sampling_instructions
                logger.debug(f"Added sampling instructions: {sampling_instructions}")

            # Function calling: inject tool definitions into system prompt
            has_tools = request_body.tools and len(request_body.tools) > 0
            if has_tools:
                tools_dicts = [t.model_dump() for t in request_body.tools]
                tools_prompt = build_tools_system_prompt(tools_dicts, request_body.tool_choice)
                if tools_prompt:
                    if system_prompt:
                        system_prompt = f"{system_prompt}\n\n{tools_prompt}"
                    else:
                        system_prompt = tools_prompt
                    logger.info(
                        f"Function calling: injected {len(request_body.tools)} tool definitions"
                    )

            # Check for JSON mode
            json_mode = request_body.response_format and request_body.response_format.type in (
                "json_object",
                "json_schema",
            )
            if json_mode:
                if (
                    request_body.response_format.type == "json_schema"
                    and request_body.response_format.json_schema
                ):
                    # JSON schema mode: inject schema into prompt (not system_prompt)
                    schema = request_body.response_format.json_schema
                    schema_json = json.dumps(schema.schema_ or {}, indent=2)
                    schema_instructions = MessageAdapter.JSON_SCHEMA_TEMPLATE.format(
                        schema_json=schema_json
                    )
                    prompt = f"{schema_instructions}\n\n{prompt}"
                    logger.info(
                        f"JSON schema mode: injected schema ({len(schema_json)} chars) into prompt"
                    )
                else:
                    # Basic JSON object mode
                    if system_prompt:
                        system_prompt = f"{MessageAdapter.JSON_MODE_INSTRUCTION}\n\n{system_prompt}"
                    else:
                        system_prompt = MessageAdapter.JSON_MODE_INSTRUCTION
                    prompt = prompt + MessageAdapter.JSON_PROMPT_SUFFIX
                    logger.info("JSON mode enabled - instruction added to system and user prompt")

            # Filter content
            prompt = MessageAdapter.filter_content(prompt)
            if system_prompt:
                system_prompt = MessageAdapter.filter_content(system_prompt)

            claude_options = _build_claude_options(request_body, claude_headers)

            # Collect all chunks
            chunks = []
            async for chunk in claude_cli.run_completion(
                **_run_completion_kwargs(claude_options, prompt, system_prompt, stream=False),
            ):
                chunks.append(chunk)

            # Extract assistant message. parse_claude_message raises
            # ClaudeResultError when the SDK emits error_max_turns or other
            # non-success ResultMessage, which we must surface as a proper
            # OpenAI error response rather than HTTP 200 with sentinel text.
            try:
                raw_assistant_content = claude_cli.parse_claude_message(chunks)
            except ClaudeResultError as err:
                return _handle_claude_result_error(request_id, request_body.model, err)

            if not raw_assistant_content:
                raise HTTPException(status_code=500, detail="No response from Claude Code")

            # Filter out tool usage and thinking blocks
            assistant_content = MessageAdapter.filter_content(raw_assistant_content)

            # Enforce JSON format if JSON mode is enabled
            if json_mode:
                original_len = len(assistant_content)

                if DEBUG_MODE or VERBOSE:
                    raw_preview = (
                        assistant_content[:50] if len(assistant_content) > 50 else assistant_content
                    )
                    raw_end = (
                        assistant_content[-30:]
                        if len(assistant_content) > 30
                        else assistant_content
                    )
                    logger.debug(f"Raw response: starts='{raw_preview}' ends='...{raw_end}'")

                assistant_content, extraction_metadata = (
                    MessageAdapter.enforce_json_format_with_metadata(assistant_content, strict=True)
                )

                logger.info(
                    f"JSON enforcement: {original_len} chars -> {len(assistant_content)} chars "
                    f"(method={extraction_metadata.get('method', 'unknown')})"
                )

                if DEBUG_MODE or VERBOSE:
                    logger.debug(f"JSON extraction metadata: {extraction_metadata}")
                    logger.debug(f"Extracted JSON preview: {assistant_content[:200]}")
                    log_json_structure(assistant_content, logger)

            # Parse function calls from response if tools were provided
            tool_calls_list = None
            finish_reason = "stop"
            if has_tools:
                parsed_calls, remaining_text = parse_tool_calls(assistant_content)
                if parsed_calls:
                    tool_calls_list = format_tool_calls(parsed_calls)
                    assistant_content = remaining_text.strip() if remaining_text.strip() else None
                    finish_reason = "tool_calls"
                    logger.info(f"Function calling: parsed {len(parsed_calls)} tool call(s)")

            # Add assistant response to session if using session mode
            if actual_session_id:
                assistant_message = Message(
                    role="assistant",
                    content=assistant_content,
                    tool_calls=tool_calls_list,
                )
                session_manager.add_assistant_response(actual_session_id, assistant_message)

            # Estimate tokens (rough approximation)
            prompt_tokens = MessageAdapter.estimate_tokens(prompt)
            completion_tokens = MessageAdapter.estimate_tokens(assistant_content or "")

            await cost_tracker.record_usage(
                session_id=actual_session_id or request_id,
                model=request_body.model,
                usage=UsageRecord(
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens,
                ),
            )

            # Create response
            response_message = Message(
                role="assistant",
                content=assistant_content,
                tool_calls=tool_calls_list,
            )
            response = ChatCompletionResponse(
                id=request_id,
                model=request_body.model,
                choices=[
                    Choice(
                        index=0,
                        message=response_message,
                        finish_reason=finish_reason,
                    )
                ],
                usage=Usage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                ),
            )

            # Store in cache if enabled
            if cache_enabled and request_cache.enabled:
                request_dict = request_body.model_dump()
                response_dict = response.model_dump()
                request_cache.set(request_dict, response_dict)
                logger.debug(f"Cached response for request {request_id}")

            # One structured info line per successful completion. Makes Grafana
            # triage a single `| json | subtype=...` query instead of grepping
            # DEBUG for num_turns and friends.
            metadata = claude_cli.extract_metadata(chunks)
            logger.info(
                _kv(
                    "completion_result",
                    request_id=request_id,
                    session_id=metadata.get("session_id") or actual_session_id,
                    subtype="success",
                    num_turns=metadata.get("num_turns"),
                    duration_ms=metadata.get("duration_ms"),
                    total_cost_usd=metadata.get("total_cost_usd"),
                    is_error=False,
                    finish_reason=finish_reason,
                    model=request_body.model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            )
            sdk_circuit_breaker.record(success=True)

            return response

    except HTTPException:
        # HTTPException often represents a validated client error (401, 422);
        # do not record it as an SDK-side failure on the breaker.
        raise
    except Exception as e:
        sdk_circuit_breaker.record(success=False)
        logger.error(f"Chat completion error: {e}")
        raise HTTPException(status_code=500, detail="Chat completion failed")


@app.post("/v1/messages")
@rate_limit_endpoint("chat")
async def anthropic_messages(
    request_body: AnthropicMessagesRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Anthropic Messages API compatible endpoint.

    This endpoint provides compatibility with the native Anthropic SDK,
    allowing tools like VC to use this wrapper via the VC_API_BASE setting.
    """
    # Check FastAPI API key if configured
    await verify_api_key(request, credentials)

    # Gate on Claude CLI probe + config-level auth validation.
    auth_block = _check_cli_auth_or_401()
    if auth_block is not None:
        return auth_block

    try:
        logger.info(f"Anthropic Messages API request: model={request_body.model}")

        # Convert Anthropic messages to internal format
        messages = request_body.to_openai_messages()

        # Build prompt from messages
        prompt_parts = []
        for msg in messages:
            if msg.role == "user":
                prompt_parts.append(msg.content)
            elif msg.role == "assistant":
                prompt_parts.append(f"Assistant: {msg.content}")

        prompt = "\n\n".join(prompt_parts)
        system_prompt = request_body.system

        # Filter content
        prompt = MessageAdapter.filter_content(prompt)
        if system_prompt:
            system_prompt = MessageAdapter.filter_content(system_prompt)

        # Run Claude Code - tools enabled by default for Anthropic SDK clients
        # (they're typically using this for agentic workflows)
        chunks = []
        async for chunk in claude_cli.run_completion(
            prompt=prompt,
            system_prompt=system_prompt,
            model=request_body.model,
            max_turns=10,
            allowed_tools=DEFAULT_ALLOWED_TOOLS,
            permission_mode="bypassPermissions",
            stream=False,
        ):
            chunks.append(chunk)

        # Extract assistant message. On SDK error_max_turns, map to the
        # Anthropic stop_reason="max_tokens"; on any other SDK error, surface
        # it as HTTP 502 instead of returning sentinel text as content.
        try:
            raw_assistant_content = claude_cli.parse_claude_message(chunks)
        except ClaudeResultError as err:
            if err.subtype == "error_max_turns":
                logger.warning(
                    _kv(
                        "claude_sdk_error_max_turns_anthropic",
                        num_turns=err.num_turns,
                    )
                )
                return AnthropicMessagesResponse(
                    model=request_body.model,
                    content=[AnthropicTextBlock(text="")],
                    stop_reason="max_tokens",
                    usage=AnthropicUsage(input_tokens=0, output_tokens=0),
                )
            raise HTTPException(
                status_code=502,
                detail={
                    "type": "upstream_sdk_error",
                    "code": err.subtype or "unknown",
                    "message": err.error_message
                    or (err.errors[0] if err.errors else f"SDK returned {err.subtype}"),
                },
            )

        if not raw_assistant_content:
            raise HTTPException(status_code=500, detail="No response from Claude Code")

        # Filter out tool usage and thinking blocks
        assistant_content = MessageAdapter.filter_content(raw_assistant_content)

        # Estimate tokens
        prompt_tokens = MessageAdapter.estimate_tokens(prompt)
        completion_tokens = MessageAdapter.estimate_tokens(assistant_content)

        # Create Anthropic-format response
        response = AnthropicMessagesResponse(
            model=request_body.model,
            content=[AnthropicTextBlock(text=assistant_content)],
            stop_reason="end_turn",
            usage=AnthropicUsage(
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
            ),
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Anthropic Messages API error: {e}")
        raise HTTPException(status_code=500, detail="Messages request failed")


@app.get("/v1/models")
async def list_models(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """List available models, preferring Anthropic's live Models API when configured."""
    # Check FastAPI API key if configured
    await verify_api_key(request, credentials)

    return {"object": "list", "data": await get_available_models()}


@app.post("/v1/models/refresh")
@rate_limit_endpoint("general")
async def refresh_models_endpoint(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Refresh the models list from the Anthropic API.

    Requires ANTHROPIC_API_KEY to be set. If the API call fails,
    the existing cached models are preserved.

    Returns:
        On success: {"success": true, "count": N, "source": "api", "models": [...]}
        On failure: {"success": false, "message": "...", "current_count": N, "source": "..."}
    """
    await verify_api_key(request, credentials)
    result = await model_service.refresh_models()
    return result


@app.get("/v1/models/status")
@rate_limit_endpoint("general")
async def get_models_status(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Get model service status including source and last refresh time.

    Returns:
        {"initialized": bool, "source": "api"|"fallback", "model_count": N, "last_refresh": timestamp|null}
    """
    await verify_api_key(request, credentials)
    return model_service.get_status()


@app.post("/v1/compatibility")
async def check_compatibility(request_body: ChatCompletionRequest):
    """Check OpenAI API compatibility for a request."""
    report = CompatibilityReporter.generate_compatibility_report(request_body)
    return {
        "compatibility_report": report,
        "claude_agent_sdk_options": {
            "supported": [
                "model",
                "system_prompt",
                "max_turns",
                "allowed_tools",
                "disallowed_tools",
                "permission_mode",
                "max_thinking_tokens",
                "continue_conversation",
                "resume",
                "cwd",
            ],
            "custom_headers": [
                "X-Claude-Max-Turns",
                "X-Claude-Allowed-Tools",
                "X-Claude-Disallowed-Tools",
                "X-Claude-Permission-Mode",
                "X-Claude-Max-Thinking-Tokens",
            ],
        },
    }


@app.get("/health")
@rate_limit_endpoint("health")
async def health_check(request: Request):
    """Health check endpoint."""
    return {"status": "healthy", "service": "claude-code-openai-wrapper"}


# Rolling window of recent /healthz/deep probe outcomes used to compute a
# short-term failure rate. Fixed-size deque keeps memory bounded.
import collections  # noqa: E402 - placed here to keep the deep-health section self-contained

_DEEP_HEALTH_WINDOW = collections.deque(maxlen=10)
_DEEP_HEALTH_FAILURE_THRESHOLD = 0.20  # open breaker above 20% failure


@app.get("/healthz/deep")
async def healthz_deep(request: Request):
    """End-to-end probe that actually exercises the completion path.

    The existing /health endpoint only checks process liveness, which stayed
    green during the week MinusPod was receiving '[Request interrupted by user]'
    as chapter content. This probe sends a canned prompt, parses the
    response, and reports unhealthy (HTTP 503) when the rolling failure
    rate exceeds _DEEP_HEALTH_FAILURE_THRESHOLD. Use from an orchestrator's
    livenessProbe / healthcheck to fail fast during upstream incidents.
    """
    started = asyncio.get_event_loop().time()
    probe_ok = False
    detail: Dict[str, Any] = {}

    try:
        chunks = []
        async for chunk in claude_cli.run_completion(
            prompt="Reply with the single word OK.",
            system_prompt=None,
            model=None,
            stream=False,
            max_turns=DEFAULT_MAX_TURNS_NO_TOOLS,
            disallowed_tools=CLAUDE_TOOLS,
        ):
            chunks.append(chunk)

        try:
            content = claude_cli.parse_claude_message(chunks) or ""
        except ClaudeResultError as err:
            content = ""
            detail["sdk_error_subtype"] = err.subtype

        normalized = content.strip().rstrip(".").upper()
        probe_ok = "OK" in normalized
        detail["content_excerpt"] = content[:120]
    except Exception as e:
        # Exception message may leak paths/config; log it, expose only the class.
        detail["exception"] = type(e).__name__
        logger.warning(f"Deep health probe raised: {e}")

    _DEEP_HEALTH_WINDOW.append(probe_ok)

    duration_ms = int((asyncio.get_event_loop().time() - started) * 1000)
    recent = list(_DEEP_HEALTH_WINDOW)
    failure_rate = (recent.count(False) / len(recent)) if recent else 0.0
    status_healthy = failure_rate <= _DEEP_HEALTH_FAILURE_THRESHOLD

    payload = {
        "status": "healthy" if status_healthy else "unhealthy",
        "probe_ok": probe_ok,
        "rolling_window_size": len(recent),
        "rolling_failure_rate": round(failure_rate, 3),
        "threshold": _DEEP_HEALTH_FAILURE_THRESHOLD,
        "duration_ms": duration_ms,
        "detail": detail,
    }
    http_status = 200 if status_healthy else 503
    return JSONResponse(status_code=http_status, content=payload)


@app.get("/version")
@rate_limit_endpoint("health")
async def version_info(request: Request):
    """Version information endpoint."""
    from src import __version__

    return {
        "version": __version__,
        "service": "claude-code-openai-wrapper",
        "api_version": "v1",
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    """Landing page with API documentation."""
    auth_info = get_claude_code_auth_info()
    auth_method = auth_info.get("method", "unknown")
    auth_valid = auth_info.get("status", {}).get("valid", False)
    status_color = "#22c55e" if auth_valid else "#ef4444"
    status_text = "Connected" if auth_valid else "Disconnected"

    html_content = f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="light dark">
    <title>Claude Code OpenAI Wrapper</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
        :root {{
            --font-sans: 'DM Sans', sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }}
        [data-theme="dark"] {{
            --bg: #111111;
            --surface: #1a1a1a;
            --surface-alt: #222222;
            --border: #2a2a2a;
            --text: #e0e0e0;
            --text-muted: #888888;
            --accent: #3b82f6;
            --code-bg: #161616;
        }}
        [data-theme="light"] {{
            --bg: #f5f5f4;
            --surface: #ffffff;
            --surface-alt: #fafaf9;
            --border: #e5e5e5;
            --text: #1a1a1a;
            --text-muted: #666666;
            --accent: #2563eb;
            --code-bg: #f5f5f4;
        }}
        html {{ font-size: 15px; }}
        body {{
            font-family: var(--font-sans);
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
        }}
        a {{ color: var(--accent); text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        code, pre {{ font-family: var(--font-mono); }}
        .wrap {{
            max-width: 860px;
            margin: 0 auto;
            padding: 2.5rem 1.5rem;
        }}
        .hdr {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 1rem;
            margin-bottom: 2rem;
            flex-wrap: wrap;
        }}
        .hdr h1 {{
            font-size: 1.4rem;
            font-weight: 600;
            letter-spacing: -0.02em;
        }}
        .hdr-right {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}
        .ver {{
            font-family: var(--font-mono);
            font-size: 0.8rem;
            color: var(--text-muted);
        }}
        .ibtn {{
            width: 2rem;
            height: 2rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: 1px solid var(--border);
            border-radius: 6px;
            background: var(--surface);
            color: var(--text-muted);
            cursor: pointer;
            transition: color 0.15s;
        }}
        .ibtn:hover {{ color: var(--text); }}
        .ibtn svg {{ width: 1rem; height: 1rem; }}
        .status-bar {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.75rem 1rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            margin-bottom: 2rem;
            font-size: 0.85rem;
        }}
        .status-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            flex-shrink: 0;
        }}
        .status-bar .sep {{
            width: 1px;
            height: 1rem;
            background: var(--border);
        }}
        .status-bar code {{
            font-size: 0.8rem;
            color: var(--accent);
        }}
        .section {{
            margin-bottom: 2rem;
        }}
        .section-title {{
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border);
        }}
        .qs {{
            position: relative;
            background: var(--code-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
        }}
        .qs .copy-btn {{
            position: absolute;
            top: 0.5rem;
            right: 0.5rem;
            padding: 0.35rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 4px;
            cursor: pointer;
            color: var(--text-muted);
            z-index: 1;
            transition: color 0.15s;
        }}
        .qs .copy-btn:hover {{ color: var(--text); }}
        .qs .copy-btn svg {{ width: 0.85rem; height: 0.85rem; display: block; }}
        .shiki {{ padding: 1rem; border-radius: 0; overflow-x: auto; }}
        .shiki code {{ white-space: pre-wrap; word-break: break-word; font-size: 0.8rem; }}
        .hidden {{ display: none !important; }}
        .ep-group {{ margin-bottom: 1.25rem; }}
        .ep-group-label {{
            font-size: 0.7rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--text-muted);
            padding: 0.35rem 0;
            margin-bottom: 0.25rem;
        }}
        .ep {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.45rem 0.5rem;
            border-radius: 6px;
            font-size: 0.85rem;
            transition: background 0.1s;
        }}
        .ep:hover {{ background: var(--surface-alt); }}
        .ep .method {{
            font-family: var(--font-mono);
            font-size: 0.65rem;
            font-weight: 500;
            width: 3.2rem;
            text-align: center;
            padding: 0.2rem 0;
            border-radius: 3px;
            flex-shrink: 0;
        }}
        .m-get {{ background: rgba(59,130,246,0.12); color: #60a5fa; }}
        .m-post {{ background: rgba(245,158,11,0.12); color: #fbbf24; }}
        .m-delete {{ background: rgba(239,68,68,0.12); color: #f87171; }}
        [data-theme="light"] .m-get {{ background: rgba(37,99,235,0.1); color: #2563eb; }}
        [data-theme="light"] .m-post {{ background: rgba(217,119,6,0.1); color: #b45309; }}
        [data-theme="light"] .m-delete {{ background: rgba(220,38,38,0.1); color: #dc2626; }}
        .ep .path {{
            font-family: var(--font-mono);
            font-size: 0.8rem;
            flex: 1;
        }}
        .ep .desc {{
            color: var(--text-muted);
            font-size: 0.8rem;
            text-align: right;
            flex-shrink: 0;
        }}
        details.ep-detail {{
            border-radius: 6px;
        }}
        details.ep-detail summary {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.45rem 0.5rem;
            border-radius: 6px;
            font-size: 0.85rem;
            cursor: pointer;
            list-style: none;
            transition: background 0.1s;
        }}
        details.ep-detail summary::-webkit-details-marker {{ display: none; }}
        details.ep-detail summary:hover {{ background: var(--surface-alt); }}
        details.ep-detail summary::after {{
            content: "";
            width: 0.4rem;
            height: 0.4rem;
            border-right: 1.5px solid var(--text-muted);
            border-bottom: 1.5px solid var(--text-muted);
            transform: rotate(-45deg);
            transition: transform 0.15s;
            flex-shrink: 0;
        }}
        details.ep-detail[open] summary::after {{ transform: rotate(45deg); }}
        details.ep-detail .detail-body {{
            margin: 0.25rem 0 0.5rem 4.5rem;
            padding: 0.75rem;
            background: var(--code-bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            overflow-x: auto;
        }}
        details.ep-detail .detail-body pre {{
            margin: 0;
            font-size: 0.8rem;
        }}
        .btn-sm {{
            font-family: var(--font-sans);
            font-size: 0.75rem;
            font-weight: 500;
            padding: 0.35rem 0.75rem;
            border: 1px solid var(--border);
            border-radius: 4px;
            background: var(--surface);
            color: var(--text);
            cursor: pointer;
            transition: background 0.15s;
        }}
        .btn-sm:hover {{ background: var(--surface-alt); }}
        .ftr {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            padding-top: 1.5rem;
            border-top: 1px solid var(--border);
            font-size: 0.8rem;
            color: var(--text-muted);
        }}
        .ftr-links {{
            display: flex;
            gap: 1.25rem;
        }}
        .ftr-links a {{ color: var(--text-muted); }}
        .ftr-links a:hover {{ color: var(--text); text-decoration: none; }}
        .ftr-auth {{
            font-family: var(--font-mono);
            font-size: 0.75rem;
        }}
    </style>
    <script type="module">
        import {{ codeToHtml }} from 'https://esm.sh/shiki@3.0.0';
        const lightTheme = 'github-light';
        const darkTheme = 'github-dark';
        function isDark() {{ return document.documentElement.getAttribute('data-theme') === 'dark'; }}

        async function highlightJson(json, targetId) {{
            const code = typeof json === 'string' ? json : JSON.stringify(json, null, 2);
            const theme = isDark() ? darkTheme : lightTheme;
            try {{
                const html = await codeToHtml(code, {{ lang: 'json', theme }});
                document.getElementById(targetId).innerHTML = html;
            }} catch (e) {{
                document.getElementById(targetId).textContent = 'Error: ' + e.message;
            }}
        }}

        document.querySelectorAll('details[data-endpoint]').forEach(details => {{
            details.addEventListener('toggle', async () => {{
                if (details.open) {{
                    const id = details.id;
                    const endpoint = details.dataset.endpoint;
                    const dataContainer = document.getElementById('data-' + id);
                    const loader = document.getElementById('loader-' + id);
                    if (dataContainer.innerHTML === '' || dataContainer.dataset.theme !== (isDark() ? 'dark' : 'light')) {{
                        loader.classList.remove('hidden');
                        try {{
                            const response = await fetch(endpoint);
                            const json = await response.json();
                            await highlightJson(json, 'data-' + id);
                            dataContainer.dataset.theme = isDark() ? 'dark' : 'light';
                        }} catch (e) {{
                            dataContainer.textContent = 'Error: ' + e.message;
                        }}
                        loader.classList.add('hidden');
                    }}
                }}
            }});
        }});

        window.addEventListener('themeChanged', async () => {{
            await highlightQuickstart();
            document.querySelectorAll('details[open][data-endpoint]').forEach(async details => {{
                const id = details.id;
                const endpoint = details.dataset.endpoint;
                const dataContainer = document.getElementById('data-' + id);
                if (dataContainer && dataContainer.innerHTML) {{
                    const response = await fetch(endpoint);
                    const json = await response.json();
                    await highlightJson(json, 'data-' + id);
                    dataContainer.dataset.theme = isDark() ? 'dark' : 'light';
                }}
            }});
        }});

        const quickstartCode = `curl -X POST http://localhost:8000/v1/chat/completions \\\\
  -H "Content-Type: application/json" \\\\
  -d '{{"model": "claude-sonnet-4-6", "messages": [{{"role": "user", "content": "Hello!"}}]}}'`;

        async function highlightQuickstart() {{
            const theme = isDark() ? darkTheme : lightTheme;
            try {{
                const html = await codeToHtml(quickstartCode, {{ lang: 'bash', theme }});
                document.getElementById('quickstart-code').innerHTML = html;
            }} catch (e) {{
                document.getElementById('quickstart-code').textContent = quickstartCode;
            }}
        }}
        window.highlightQuickstart = highlightQuickstart;
        highlightQuickstart();
    </script>
    <script>
        const quickstartText = 'curl -X POST http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -d \\'{{"model": "claude-sonnet-4-6", "messages": [{{"role": "user", "content": "Hello!"}}]}}\\'';

        function copyQuickstart() {{
            if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(quickstartText).then(showCopySuccess).catch(fallbackCopy);
            }} else {{ fallbackCopy(); }}
        }}
        function fallbackCopy() {{
            const ta = document.createElement('textarea');
            ta.value = quickstartText;
            ta.style.cssText = 'position:fixed;opacity:0';
            document.body.appendChild(ta);
            ta.select();
            try {{ document.execCommand('copy'); showCopySuccess(); }} catch (e) {{}}
            document.body.removeChild(ta);
        }}
        function showCopySuccess() {{
            document.getElementById('copy-icon').classList.add('hidden');
            document.getElementById('check-icon').classList.remove('hidden');
            setTimeout(() => {{
                document.getElementById('copy-icon').classList.remove('hidden');
                document.getElementById('check-icon').classList.add('hidden');
            }}, 2000);
        }}
        function toggleTheme() {{
            const html = document.documentElement;
            const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
            document.getElementById('sun-icon').classList.toggle('hidden', next === 'dark');
            document.getElementById('moon-icon').classList.toggle('hidden', next !== 'dark');
            window.dispatchEvent(new Event('themeChanged'));
        }}
        async function refreshModels() {{
            const el = document.getElementById('data-models-refresh');
            el.textContent = 'Refreshing...';
            try {{
                const r = await fetch('/v1/models/refresh', {{ method: 'POST' }});
                const d = await r.json();
                el.textContent = JSON.stringify(d, null, 2);
            }} catch (e) {{
                el.textContent = 'Error: ' + e.message;
            }}
        }}
        document.addEventListener('DOMContentLoaded', () => {{
            const saved = localStorage.getItem('theme');
            if (saved) {{
                document.documentElement.setAttribute('data-theme', saved);
                document.getElementById('sun-icon').classList.toggle('hidden', saved === 'dark');
                document.getElementById('moon-icon').classList.toggle('hidden', saved !== 'dark');
            }} else {{
                document.getElementById('sun-icon').classList.add('hidden');
            }}
        }});
    </script>
</head>
<body>
<div class="wrap">

    <header class="hdr">
        <h1>Claude Code OpenAI Wrapper</h1>
        <div class="hdr-right">
            <span class="ver">v{__version__}</span>
            <button onclick="toggleTheme()" class="ibtn" title="Toggle theme">
                <svg id="sun-icon" class="hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
                <svg id="moon-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/></svg>
            </button>
            <a href="https://github.com/ttlequals0/claude-code-openai-wrapper" target="_blank" rel="noopener noreferrer" class="ibtn" title="View on GitHub">
                <svg fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clip-rule="evenodd"/></svg>
            </a>
        </div>
    </header>

    <div class="status-bar">
        <span class="status-dot" style="background:{status_color};"></span>
        <span>{status_text}</span>
        <span class="sep"></span>
        <span>Auth: <code>{auth_method}</code></span>
    </div>

    <div class="section">
        <div class="section-title">Quick Start</div>
        <div class="qs">
            <button onclick="copyQuickstart()" class="copy-btn" title="Copy to clipboard">
                <svg id="copy-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
                <svg id="check-icon" class="hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="color:#22c55e;"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
            </button>
            <div id="quickstart-code"></div>
        </div>
    </div>

    <div class="section">
        <div class="section-title">Endpoints</div>

        <div class="ep-group">
            <div class="ep-group-label">Core API</div>
            <div class="ep">
                <span class="method m-post">POST</span>
                <span class="path">/v1/chat/completions</span>
                <span class="desc">OpenAI-compatible chat</span>
            </div>
            <div class="ep">
                <span class="method m-post">POST</span>
                <span class="path">/v1/messages</span>
                <span class="desc">Anthropic-compatible</span>
            </div>
        </div>

        <div class="ep-group">
            <div class="ep-group-label">Models</div>
            <details id="models" data-endpoint="/v1/models" class="ep-detail">
                <summary>
                    <span class="method m-get">GET</span>
                    <span class="path">/v1/models</span>
                    <span class="desc">List available models</span>
                </summary>
                <div class="detail-body">
                    <small id="loader-models" class="hidden">Loading...</small>
                    <div id="data-models"></div>
                </div>
            </details>
            <details id="models-status" data-endpoint="/v1/models/status" class="ep-detail">
                <summary>
                    <span class="method m-get">GET</span>
                    <span class="path">/v1/models/status</span>
                    <span class="desc">Model service status</span>
                </summary>
                <div class="detail-body">
                    <small id="loader-models-status" class="hidden">Loading...</small>
                    <div id="data-models-status"></div>
                </div>
            </details>
            <details id="models-refresh" class="ep-detail">
                <summary>
                    <span class="method m-post">POST</span>
                    <span class="path">/v1/models/refresh</span>
                    <span class="desc">Refresh from API</span>
                </summary>
                <div class="detail-body">
                    <p style="margin-bottom:0.5rem;font-size:0.8rem;color:var(--text-muted);">Requires api_key auth with ANTHROPIC_API_KEY set.</p>
                    <button onclick="refreshModels()" class="btn-sm">Refresh Models</button>
                    <div id="data-models-refresh" style="margin-top:0.5rem;"></div>
                </div>
            </details>
        </div>

        <div class="ep-group">
            <div class="ep-group-label">Sessions</div>
            <details id="sessions" data-endpoint="/v1/sessions" class="ep-detail">
                <summary>
                    <span class="method m-get">GET</span>
                    <span class="path">/v1/sessions</span>
                    <span class="desc">List active sessions</span>
                </summary>
                <div class="detail-body">
                    <small id="loader-sessions" class="hidden">Loading...</small>
                    <div id="data-sessions"></div>
                </div>
            </details>
            <details id="sessions-stats" data-endpoint="/v1/sessions/stats" class="ep-detail">
                <summary>
                    <span class="method m-get">GET</span>
                    <span class="path">/v1/sessions/stats</span>
                    <span class="desc">Session statistics</span>
                </summary>
                <div class="detail-body">
                    <small id="loader-sessions-stats" class="hidden">Loading...</small>
                    <div id="data-sessions-stats"></div>
                </div>
            </details>
            <div class="ep">
                <span class="method m-get">GET</span>
                <span class="path">/v1/sessions/{{id}}</span>
                <span class="desc">Get session by ID</span>
            </div>
            <div class="ep">
                <span class="method m-delete">DELETE</span>
                <span class="path">/v1/sessions/{{id}}</span>
                <span class="desc">Delete session</span>
            </div>
        </div>

        <div class="ep-group">
            <div class="ep-group-label">Tools</div>
            <details id="tools" data-endpoint="/v1/tools" class="ep-detail">
                <summary>
                    <span class="method m-get">GET</span>
                    <span class="path">/v1/tools</span>
                    <span class="desc">List available tools</span>
                </summary>
                <div class="detail-body">
                    <small id="loader-tools" class="hidden">Loading...</small>
                    <div id="data-tools"></div>
                </div>
            </details>
            <details id="tools-config" data-endpoint="/v1/tools/config" class="ep-detail">
                <summary>
                    <span class="method m-get">GET</span>
                    <span class="path">/v1/tools/config</span>
                    <span class="desc">Tool configuration</span>
                </summary>
                <div class="detail-body">
                    <small id="loader-tools-config" class="hidden">Loading...</small>
                    <div id="data-tools-config"></div>
                </div>
            </details>
            <div class="ep">
                <span class="method m-post">POST</span>
                <span class="path">/v1/tools/config</span>
                <span class="desc">Update tool config</span>
            </div>
            <details id="tools-stats" data-endpoint="/v1/tools/stats" class="ep-detail">
                <summary>
                    <span class="method m-get">GET</span>
                    <span class="path">/v1/tools/stats</span>
                    <span class="desc">Tool usage stats</span>
                </summary>
                <div class="detail-body">
                    <small id="loader-tools-stats" class="hidden">Loading...</small>
                    <div id="data-tools-stats"></div>
                </div>
            </details>
        </div>

        <div class="ep-group">
            <div class="ep-group-label">MCP Servers</div>
            <details id="mcp-servers" data-endpoint="/v1/mcp/servers" class="ep-detail">
                <summary>
                    <span class="method m-get">GET</span>
                    <span class="path">/v1/mcp/servers</span>
                    <span class="desc">List MCP servers</span>
                </summary>
                <div class="detail-body">
                    <small id="loader-mcp-servers" class="hidden">Loading...</small>
                    <div id="data-mcp-servers"></div>
                </div>
            </details>
            <div class="ep">
                <span class="method m-post">POST</span>
                <span class="path">/v1/mcp/servers</span>
                <span class="desc">Register server</span>
            </div>
            <div class="ep">
                <span class="method m-post">POST</span>
                <span class="path">/v1/mcp/connect</span>
                <span class="desc">Connect to server</span>
            </div>
            <div class="ep">
                <span class="method m-post">POST</span>
                <span class="path">/v1/mcp/disconnect</span>
                <span class="desc">Disconnect server</span>
            </div>
            <details id="mcp-stats" data-endpoint="/v1/mcp/stats" class="ep-detail">
                <summary>
                    <span class="method m-get">GET</span>
                    <span class="path">/v1/mcp/stats</span>
                    <span class="desc">MCP statistics</span>
                </summary>
                <div class="detail-body">
                    <small id="loader-mcp-stats" class="hidden">Loading...</small>
                    <div id="data-mcp-stats"></div>
                </div>
            </details>
        </div>

        <div class="ep-group">
            <div class="ep-group-label">Cache</div>
            <details id="cache-stats" data-endpoint="/v1/cache/stats" class="ep-detail">
                <summary>
                    <span class="method m-get">GET</span>
                    <span class="path">/v1/cache/stats</span>
                    <span class="desc">Cache statistics</span>
                </summary>
                <div class="detail-body">
                    <small id="loader-cache-stats" class="hidden">Loading...</small>
                    <div id="data-cache-stats"></div>
                </div>
            </details>
            <div class="ep">
                <span class="method m-post">POST</span>
                <span class="path">/v1/cache/clear</span>
                <span class="desc">Clear request cache</span>
            </div>
        </div>

        <div class="ep-group">
            <div class="ep-group-label">Auth / Debug</div>
            <details id="auth" data-endpoint="/v1/auth/status" class="ep-detail">
                <summary>
                    <span class="method m-get">GET</span>
                    <span class="path">/v1/auth/status</span>
                    <span class="desc">Auth status</span>
                </summary>
                <div class="detail-body">
                    <small id="loader-auth" class="hidden">Loading...</small>
                    <div id="data-auth"></div>
                </div>
            </details>
            <div class="ep">
                <span class="method m-post">POST</span>
                <span class="path">/v1/compatibility</span>
                <span class="desc">Parameter compatibility check</span>
            </div>
            <div class="ep">
                <span class="method m-post">POST</span>
                <span class="path">/v1/debug/request</span>
                <span class="desc">Debug request validation</span>
            </div>
        </div>

        <div class="ep-group">
            <div class="ep-group-label">System</div>
            <details id="health" data-endpoint="/health" class="ep-detail">
                <summary>
                    <span class="method m-get">GET</span>
                    <span class="path">/health</span>
                    <span class="desc">Health check</span>
                </summary>
                <div class="detail-body">
                    <small id="loader-health" class="hidden">Loading...</small>
                    <div id="data-health"></div>
                </div>
            </details>
            <details id="version" data-endpoint="/version" class="ep-detail">
                <summary>
                    <span class="method m-get">GET</span>
                    <span class="path">/version</span>
                    <span class="desc">API version</span>
                </summary>
                <div class="detail-body">
                    <small id="loader-version" class="hidden">Loading...</small>
                    <div id="data-version"></div>
                </div>
            </details>
        </div>
    </div>

    <footer class="ftr">
        <div class="ftr-links">
            <a href="/docs">Swagger Docs</a>
            <a href="/redoc">ReDoc</a>
            <a href="https://github.com/ttlequals0/claude-code-openai-wrapper" target="_blank" rel="noopener noreferrer">GitHub</a>
        </div>
        <div class="ftr-auth">CLAUDE_AUTH_METHOD: cli | api_key | bedrock | vertex</div>
    </footer>

</div>
</body>
</html>"""
    return HTMLResponse(content=html_content)


@app.post("/v1/debug/request")
@rate_limit_endpoint("debug")
async def debug_request_validation(request: Request):
    """Debug endpoint to test request validation and see what's being sent.

    Returns a minimal response unless DEBUG_MODE or VERBOSE is enabled, so
    that exception/request detail is never emitted to production clients.
    """
    if not (DEBUG_MODE or VERBOSE):
        return {
            "debug_info": {
                "enabled": False,
                "hint": "Set DEBUG_MODE=true or VERBOSE=true to enable this endpoint",
            }
        }

    try:
        # Get the raw request body
        body = await request.body()
        raw_body = body.decode() if body else ""

        # Try to parse as JSON
        parsed_body = None
        json_error = None
        try:
            import json as json_lib

            parsed_body = json_lib.loads(raw_body) if raw_body else {}
        except Exception as e:
            # Only expose the exception type, never its message/stack trace.
            json_error = type(e).__name__
            logger.warning(f"Debug endpoint JSON parse error: {e}")

        # Try to validate against our model
        validation_result = {"valid": False, "errors": []}
        if parsed_body:
            try:
                chat_request = ChatCompletionRequest(**parsed_body)
                validation_result = {"valid": True, "validated_data": chat_request.model_dump()}
            except ValidationError as e:
                validation_result = {
                    "valid": False,
                    "errors": [
                        {
                            "field": " -> ".join(str(loc) for loc in error.get("loc", [])),
                            "message": error.get("msg", "Unknown error"),
                            "type": error.get("type", "validation_error"),
                            "input": error.get("input"),
                        }
                        for error in e.errors()
                    ],
                }

        return {
            "debug_info": {
                "headers": dict(request.headers),
                "method": request.method,
                "url": str(request.url),
                "raw_body": raw_body,
                "json_parse_error": json_error,
                "parsed_body": parsed_body,
                "validation_result": validation_result,
                "debug_mode_enabled": DEBUG_MODE or VERBOSE,
                "example_valid_request": {
                    "model": "claude-sonnet-4-6",
                    "messages": [{"role": "user", "content": "Hello, world!"}],
                    "stream": False,
                },
            }
        }

    except Exception as e:
        # Never echo str(e); log it server-side and return only the type.
        logger.error(f"Debug endpoint error: {e}")
        return {
            "debug_info": {
                "error_type": type(e).__name__,
                "method": request.method,
                "url": str(request.url),
            }
        }


@app.get("/v1/auth/status")
@rate_limit_endpoint("auth")
async def get_auth_status(request: Request):
    """Get Claude Code authentication status."""
    from src.auth import auth_manager

    auth_info = get_claude_code_auth_info()
    active_api_key = auth_manager.get_api_key()

    return {
        "claude_code_auth": auth_info,
        "cli_health": _auth.cli_health.as_dict(),
        "server_info": {
            "api_key_required": bool(active_api_key),
            "api_key_source": (
                "environment"
                if os.getenv("API_KEY")
                else ("runtime" if runtime_api_key else "none")
            ),
            "version": "1.0.0",
        },
    }


@app.get("/v1/sessions/stats")
async def get_session_stats(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Get session manager statistics."""
    stats = session_manager.get_stats()
    return {
        "session_stats": stats,
        "cleanup_interval_minutes": session_manager.cleanup_interval_minutes,
        "default_ttl_hours": session_manager.default_ttl_hours,
    }


@app.get("/v1/sessions")
async def list_sessions(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """List all active sessions."""
    sessions = session_manager.list_sessions()
    return SessionListResponse(sessions=sessions, total=len(sessions))


@app.get("/v1/sessions/{session_id}")
async def get_session(
    session_id: str, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Get information about a specific session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session.to_session_info()


@app.delete("/v1/sessions/{session_id}")
async def delete_session(
    session_id: str, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Delete a specific session."""
    deleted = session_manager.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"message": f"Session {session_id} deleted successfully"}


# Tool Management Endpoints


@app.get("/v1/tools", response_model=ToolListResponse)
@rate_limit_endpoint("general")
async def list_tools(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """List all available Claude Code tools with metadata."""
    await verify_api_key(request, credentials)

    tools = tool_manager.list_all_tools()
    tool_responses = [
        ToolMetadataResponse(
            name=tool.name,
            description=tool.description,
            category=tool.category,
            parameters=tool.parameters,
            examples=tool.examples,
            is_safe=tool.is_safe,
            requires_network=tool.requires_network,
        )
        for tool in tools
    ]

    return ToolListResponse(tools=tool_responses, total=len(tool_responses))


@app.get("/v1/tools/config", response_model=ToolConfigurationResponse)
@rate_limit_endpoint("general")
async def get_tool_config(
    request: Request,
    session_id: Optional[str] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Get tool configuration (global or per-session)."""
    await verify_api_key(request, credentials)

    config = tool_manager.get_effective_config(session_id)
    effective_tools = tool_manager.get_effective_tools(session_id)

    return ToolConfigurationResponse(
        allowed_tools=config.allowed_tools,
        disallowed_tools=config.disallowed_tools,
        effective_tools=effective_tools,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@app.post("/v1/tools/config", response_model=ToolConfigurationResponse)
@rate_limit_endpoint("general")
async def update_tool_config(
    config_request: ToolConfigurationRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Update tool configuration (global or per-session)."""
    await verify_api_key(request, credentials)

    # Validate tool names if provided
    all_tool_names = []
    if config_request.allowed_tools:
        all_tool_names.extend(config_request.allowed_tools)
    if config_request.disallowed_tools:
        all_tool_names.extend(config_request.disallowed_tools)

    if all_tool_names:
        validation = tool_manager.validate_tools(all_tool_names)
        invalid_tools = [name for name, valid in validation.items() if not valid]
        if invalid_tools:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid tool names: {', '.join(invalid_tools)}. Valid tools: {', '.join(CLAUDE_TOOLS)}",
            )

    # Update configuration
    if config_request.session_id:
        config = tool_manager.set_session_config(
            config_request.session_id, config_request.allowed_tools, config_request.disallowed_tools
        )
    else:
        config = tool_manager.update_global_config(
            config_request.allowed_tools, config_request.disallowed_tools
        )

    effective_tools = tool_manager.get_effective_tools(config_request.session_id)

    return ToolConfigurationResponse(
        allowed_tools=config.allowed_tools,
        disallowed_tools=config.disallowed_tools,
        effective_tools=effective_tools,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@app.get("/v1/tools/stats")
@rate_limit_endpoint("general")
async def get_tool_stats(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Get statistics about tool configuration and usage."""
    await verify_api_key(request, credentials)
    return tool_manager.get_stats()


# MCP (Model Context Protocol) Management Endpoints


@app.get("/v1/mcp/servers", response_model=MCPServersListResponse)
@rate_limit_endpoint("general")
async def list_mcp_servers(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """List all registered MCP servers."""
    await verify_api_key(request, credentials)

    if not mcp_client.is_available():
        raise HTTPException(
            status_code=503, detail="MCP SDK not available. Install with: pip install mcp"
        )

    servers = mcp_client.list_servers()
    connections = mcp_client.list_connected_servers()

    server_responses = []
    for server in servers:
        connection = mcp_client.get_connection(server.name)
        server_responses.append(
            MCPServerInfoResponse(
                name=server.name,
                command=server.command,
                args=server.args,
                description=server.description,
                enabled=server.enabled,
                connected=server.name in connections,
                tools_count=len(connection.available_tools) if connection else 0,
                resources_count=len(connection.available_resources) if connection else 0,
                prompts_count=len(connection.available_prompts) if connection else 0,
            )
        )

    return MCPServersListResponse(servers=server_responses, total=len(server_responses))


@app.post("/v1/mcp/servers")
@rate_limit_endpoint("general")
async def register_mcp_server(
    body: MCPServerConfigRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Register a new MCP server."""
    await verify_api_key(request, credentials)

    if not mcp_client.is_available():
        raise HTTPException(
            status_code=503, detail="MCP SDK not available. Install with: pip install mcp"
        )

    config = MCPServerConfig(
        name=body.name,
        command=body.command,
        args=body.args,
        env=body.env,
        description=body.description,
        enabled=body.enabled,
    )

    mcp_client.register_server(config)

    return {"message": f"MCP server '{body.name}' registered successfully"}


@app.post("/v1/mcp/connect")
@rate_limit_endpoint("general")
async def connect_mcp_server(
    body: MCPConnectionRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Connect to a registered MCP server."""
    await verify_api_key(request, credentials)

    if not mcp_client.is_available():
        raise HTTPException(
            status_code=503, detail="MCP SDK not available. Install with: pip install mcp"
        )

    success = await mcp_client.connect_server(body.server_name)

    if not success:
        raise HTTPException(
            status_code=500, detail=f"Failed to connect to MCP server '{body.server_name}'"
        )

    connection = mcp_client.get_connection(body.server_name)
    return {
        "message": f"Connected to MCP server '{body.server_name}'",
        "tools": len(connection.available_tools) if connection else 0,
        "resources": len(connection.available_resources) if connection else 0,
        "prompts": len(connection.available_prompts) if connection else 0,
    }


@app.post("/v1/mcp/disconnect")
@rate_limit_endpoint("general")
async def disconnect_mcp_server(
    body: MCPConnectionRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Disconnect from an MCP server."""
    await verify_api_key(request, credentials)

    if not mcp_client.is_available():
        raise HTTPException(
            status_code=503, detail="MCP SDK not available. Install with: pip install mcp"
        )

    success = await mcp_client.disconnect_server(body.server_name)

    if not success:
        raise HTTPException(
            status_code=404, detail=f"Not connected to MCP server '{body.server_name}'"
        )

    return {"message": f"Disconnected from MCP server '{body.server_name}'"}


@app.get("/v1/mcp/stats")
@rate_limit_endpoint("general")
async def get_mcp_stats(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Get statistics about MCP connections."""
    await verify_api_key(request, credentials)
    return mcp_client.get_stats()


# ============================================================================
# Cache Endpoints
# ============================================================================


@app.get("/v1/cache/stats")
@rate_limit_endpoint("general")
async def get_cache_stats(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Get request cache statistics.

    Returns information about cache configuration, current size, hit/miss rates,
    and eviction counts. Cache is opt-in and disabled by default.

    Enable cache by setting REQUEST_CACHE_ENABLED=true environment variable.
    """
    await verify_api_key(request, credentials)
    return request_cache.get_stats()


@app.post("/v1/cache/clear")
@rate_limit_endpoint("general")
async def clear_cache(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Clear all cached responses.

    Returns the number of entries that were cleared.
    """
    await verify_api_key(request, credentials)
    count = request_cache.clear()
    return {"message": f"Cleared {count} cache entries", "entries_cleared": count}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Format HTTP exceptions as OpenAI-style errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {"message": exc.detail, "type": "api_error", "code": str(exc.status_code)}
        },
    )


def find_available_port(start_port: int = 8000, max_attempts: int = 10) -> int:
    """Find an available port starting from start_port."""
    import socket

    for port in range(start_port, start_port + max_attempts):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            result = sock.connect_ex(("127.0.0.1", port))
            if result != 0:  # Port is available
                return port
        except Exception:
            return port
        finally:
            sock.close()

    raise RuntimeError(
        f"No available ports found in range {start_port}-{start_port + max_attempts - 1}"
    )


def run_server(port: int = None, host: str = None):
    """Run the server - used as Poetry script entry point."""
    import uvicorn

    # Handle interactive API key protection
    global runtime_api_key
    runtime_api_key = prompt_for_api_protection()

    # Priority: CLI arg > ENV var > default
    if port is None:
        port = int(os.getenv("PORT", "8000"))
    if host is None:
        # Default to 0.0.0.0 for container/development use (configurable via CLAUDE_WRAPPER_HOST env)
        host = os.getenv("CLAUDE_WRAPPER_HOST", "0.0.0.0")  # nosec B104
    preferred_port = port

    try:
        # Try the preferred port first
        # Binding to 0.0.0.0 is intentional for container/development use
        uvicorn.run(app, host=host, port=preferred_port)  # nosec B104
    except OSError as e:
        if "Address already in use" in str(e) or e.errno == 48:
            logger.warning(f"Port {preferred_port} is already in use. Finding alternative port...")
            try:
                available_port = find_available_port(preferred_port + 1)
                logger.info(f"Starting server on alternative port {available_port}")
                print(f"\n🚀 Server starting on http://localhost:{available_port}")
                print(f"📝 Update your client base_url to: http://localhost:{available_port}/v1")
                # Binding to 0.0.0.0 is intentional for container/development use
                uvicorn.run(app, host=host, port=available_port)  # nosec B104
            except RuntimeError as port_error:
                logger.error(f"Could not find available port: {port_error}")
                print(f"\n❌ Error: {port_error}")
                print("💡 Try setting a specific port with: PORT=9000 poetry run python main.py")
                raise
        else:
            raise


if __name__ == "__main__":
    import sys

    # Simple CLI argument parsing for port
    port = None
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
            print(f"Using port from command line: {port}")
        except ValueError:
            print(f"Invalid port number: {sys.argv[1]}. Using default.")

    run_server(port)
