import os
import json
import asyncio
import logging
import secrets
import string
import uuid
from pathlib import Path
from typing import Optional, AsyncGenerator, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from dotenv import load_dotenv

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
    AnthropicMessageStartEvent,
    AnthropicContentBlockStartEvent,
    AnthropicContentBlockDeltaEvent,
    AnthropicContentBlockStopEvent,
    AnthropicMessageDeltaEvent,
    AnthropicMessageStopEvent,
)
from src.claude_cli import ClaudeCodeCLI
from src.message_adapter import MessageAdapter
from src.auth import verify_api_key, security, validate_claude_code_auth, get_claude_code_auth_info
from src.parameter_validator import ParameterValidator, CompatibilityReporter
from src.session_manager import session_manager, SessionLimitExceeded
from src.tool_manager import tool_manager
from src.mcp_client import mcp_client, MCPServerConfig
from src.rate_limiter import (
    limiter,
    rate_limit_exceeded_handler,
    rate_limit_endpoint,
)
from src.constants import CLAUDE_MODELS, CLAUDE_TOOLS, DEFAULT_ALLOWED_TOOLS, DEFAULT_MODEL
from src import __version__

# Load environment variables
load_dotenv()

# Configure logging based on debug mode
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() in ("true", "1", "yes", "on")
VERBOSE = os.getenv("VERBOSE", "false").lower() in ("true", "1", "yes", "on")

# Set logging level based on debug/verbose mode
log_level = logging.DEBUG if (DEBUG_MODE or VERBOSE) else logging.INFO
logging.basicConfig(level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

if DEBUG_MODE:
    logger.warning(
        "DEBUG_MODE is enabled — request/response details will be logged. Disable in production."
    )

# Global variable to store runtime-generated API key
runtime_api_key = None


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

# Global semaphore for limiting concurrent CLI processes
# Default to 3 concurrent processes to avoid resource exhaustion
MAX_CONCURRENT_PROCESSES = int(os.getenv("MAX_CONCURRENT_PROCESSES", "3"))
process_semaphore = None

# Landing page template. Loaded once at module init; uses $-style placeholders
# (string.Template) to avoid colliding with JS/CSS braces in the HTML body.
_LANDING_TEMPLATE = string.Template(
    (Path(__file__).parent / "templates" / "landing.html").read_text()
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify Claude Code authentication and CLI on startup."""
    global process_semaphore
    
    # Initialize the semaphore within the event loop
    process_semaphore = asyncio.Semaphore(MAX_CONCURRENT_PROCESSES)
    logger.info(f"Initialized process concurrency cap: {MAX_CONCURRENT_PROCESSES}")
    
    logger.info("Verifying Claude Code authentication and CLI...")

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

    # Prewarm the Claude Agent SDK so the first real request isn't slow
    prewarm_prompt = os.getenv("PREWARM_PROMPT", "Hello")
    logger.info(f"Prewarming Claude Agent SDK with prompt: '{prewarm_prompt}'...")
    try:
        claude_result = await asyncio.wait_for(
            claude_cli.verify_cli(prompt=prewarm_prompt), timeout=45.0
        )
        if not claude_result:
            logger.warning("⚠️ Claude prewarm returned False")
        else:
            logger.info("✅ Claude prewarm complete")
    except Exception as e:
        logger.error(f"⚠️ Claude prewarm failed: {e}")
        logger.warning("The server will start, but first requests might be slow.")

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

    # Start session cleanup task
    session_manager.start_cleanup_task()

    yield

    # Cleanup on shutdown
    logger.info("Shutting down session manager...")
    await session_manager.shutdown()


# Create FastAPI app
app = FastAPI(
    title="Claude Code OpenAI API Wrapper",
    description="OpenAI-compatible API for Claude Code",
    version=__version__,
    lifespan=lifespan,
)

# Configure CORS
try:
    cors_origins = json.loads(os.getenv("CORS_ORIGINS", '["*"]'))
    if not isinstance(cors_origins, list):
        logger.warning("CORS_ORIGINS must be a JSON array, falling back to ['*']")
        cors_origins = ["*"]
except (json.JSONDecodeError, TypeError):
    logger.warning("Invalid CORS_ORIGINS value, falling back to ['*']")
    cors_origins = ["*"]
allow_creds = "*" not in cors_origins  # No credentials with wildcard
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_creds,
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


def redact_request_headers(headers: dict) -> dict:
    """Redact sensitive values from request headers for safe logging."""
    redacted = dict(headers)
    for key in list(redacted.keys()):
        if key.lower() == "authorization":
            redacted[key] = "[REDACTED]"
    return redacted


def redact_request_body(body: dict) -> dict:
    """Redact sensitive fields from request body for safe logging."""
    import copy

    redacted = copy.deepcopy(body)
    sensitive_fields = {"api_key", "authorization", "token", "secret", "password"}
    for key in list(redacted.keys()):
        if key.lower() in sensitive_fields:
            redacted[key] = "[REDACTED]"
    return redacted


class DebugLoggingMiddleware(BaseHTTPMiddleware):
    """ASGI-compliant middleware for logging request/response details when debug mode is enabled."""

    async def dispatch(self, request: Request, call_next):
        # Get request ID for correlation
        request_id = getattr(request.state, "request_id", "unknown")

        if not (DEBUG_MODE or VERBOSE):
            return await call_next(request)

        # Log request details
        start_time = asyncio.get_running_loop().time()

        # Log basic request info with request ID for correlation
        logger.debug(f"🔍 [{request_id}] Incoming request: {request.method} {request.url}")
        logger.debug(f"🔍 [{request_id}] Headers: {redact_request_headers(dict(request.headers))}")

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
                                f"🔍 Request body: {json_lib.dumps(redact_request_body(parsed_body), indent=2)}"
                            )
                            body_logged = True
                        except Exception:
                            logger.debug("🔍 Request body: [non-JSON, redacted]")
                            body_logged = True
            except Exception as e:
                logger.debug(f"🔍 Could not read request body: {e}")

        if not body_logged and request.method == "POST":
            logger.debug("🔍 Request body: [not logged - streaming or large payload]")

        # Process the request
        try:
            response = await call_next(request)

            # Log response details
            end_time = asyncio.get_running_loop().time()
            duration = (end_time - start_time) * 1000  # Convert to milliseconds

            logger.debug(f"🔍 Response: {response.status_code} in {duration:.2f}ms")

            return response

        except Exception as e:
            end_time = asyncio.get_running_loop().time()
            duration = (end_time - start_time) * 1000

            logger.debug(f"🔍 Request failed after {duration:.2f}ms: {e}")
            raise


# Add the debug middleware
app.add_middleware(DebugLoggingMiddleware)


# Custom exception handler for 422 validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors with detailed debugging information."""

    # Log validation error without raw input values (may contain credentials)
    logger.error(f"Request validation failed for {request.method} {request.url}")
    logger.error(
        f"Validation errors: {[{k: v for k, v in e.items() if k != 'input'} for e in exc.errors()]}"
    )

    # Create detailed error response — omit raw input values to prevent credential leaks
    error_details = []
    for error in exc.errors():
        location = " -> ".join(str(loc) for loc in error.get("loc", []))
        error_details.append(
            {
                "field": location,
                "message": error.get("msg", "Unknown validation error"),
                "type": error.get("type", "validation_error"),
            }
        )

    # If debug mode is enabled, include redacted request info (never expose raw body)
    debug_info = {}
    if DEBUG_MODE or VERBOSE:
        try:
            body = await request.body()
            if body:
                import json as json_lib

                try:
                    parsed = json_lib.loads(body.decode())
                    debug_info["request_body"] = redact_request_body(parsed)
                except Exception:
                    debug_info["request_body"] = "[REDACTED — unparseable]"
        except Exception:
            debug_info["request_body"] = "[REDACTED — unreadable]"

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


def get_prompt_messages(all_messages: List[Message], is_resuming: bool) -> List[Message]:
    """
    Get the messages to send as the prompt.

    Wrapper-managed `session_id` values are not native Claude resume tokens,
    so session continuity is preserved by replaying the full conversation history.
    """
    return all_messages


async def generate_streaming_response(
    request: ChatCompletionRequest, request_id: str, claude_headers: Optional[Dict[str, Any]] = None
) -> AsyncGenerator[str, None]:
    """Generate SSE formatted streaming response."""
    try:
        # Process messages with session management
        all_messages, actual_session_id = await session_manager.process_messages(
            request.messages, request.session_id
        )

        # Only send last message if we are resuming an existing session
        prompt_messages = get_prompt_messages(all_messages, bool(actual_session_id))

        # Convert messages to prompt (pass model for optimized formatting)
        prompt, system_prompt = MessageAdapter.messages_to_prompt(prompt_messages, request.model)

        # Add sampling instructions from temperature/top_p if present
        sampling_instructions = request.get_sampling_instructions()
        if sampling_instructions:
            if system_prompt:
                system_prompt = f"{system_prompt}\n\n{sampling_instructions}"
            else:
                system_prompt = sampling_instructions
            logger.debug(f"Added sampling instructions: {sampling_instructions}")

        # Get options from request
        options = request.to_claude_options()

        # Merge with specific headers if provided
        if claude_headers:
            options.update(claude_headers)

        # Validate model
        if options.get("model"):
            ParameterValidator.validate_model(options["model"])

        # Handle tools
        if not request.enable_tools:
            # Disable all tools
            options["disallowed_tools"] = CLAUDE_TOOLS
            options["max_turns"] = 1  # Single turn for Q&A
            logger.info("Tools disabled (default behavior for OpenAI compatibility)")
        else:
            # Enable tools
            options["allowed_tools"] = DEFAULT_ALLOWED_TOOLS
            # Set permission mode to bypass prompts (required for API/headless usage)
            options["permission_mode"] = "bypassPermissions"
            logger.info(f"Tools enabled by user request: {DEFAULT_ALLOWED_TOOLS}")

        # Run CLI
        chunks_buffer = []
        role_sent = False  # Track if we've sent the initial role chunk
        content_sent = False  # Track if we've sent any content

        # Call the CLI within the process semaphore to limit concurrency
        async with (process_semaphore or asyncio.Semaphore(MAX_CONCURRENT_PROCESSES)):
            completion_gen = claude_cli.run_completion(
                prompt=prompt,
                system_prompt=system_prompt,
                stream=True,
                session_id=None,
                claude_options=options,
            )

            async for chunk in completion_gen:
                chunks_buffer.append(chunk)
                
                if DEBUG_MODE or VERBOSE:
                    logger.debug(f"Streaming chunk: type={chunk.get('type')}, subtype={chunk.get('subtype')}, keys={list(chunk.keys())}")

                # Check if we have an assistant message
                content = None
                if (chunk.get("type") == "assistant" or chunk.get("type") == "assistant_message") and "message" in chunk:
                    # Claude format: {"type": "assistant", "message": {"content": [...]}}
                    message = chunk["message"]
                    if isinstance(message, dict) and "content" in message:
                        content = message["content"]
                elif chunk.get("type") == "content_block_delta" and "delta" in chunk:
                    # Claude SDK delta format: {"type": "content_block_delta", "delta": {"text": "..."}}
                    delta = chunk["delta"]
                    if isinstance(delta, dict) and "text" in delta:
                        content = delta["text"]
                elif "content" in chunk and isinstance(chunk["content"], list):
                    # Claude SDK format: {"content": [TextBlock(...)]}
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

                            if DEBUG_MODE or VERBOSE:
                                logger.debug(f"Raw content block: {raw_text[:200]}...")

                            # Filter out tool usage and thinking blocks
                            filtered_text = MessageAdapter.filter_content(raw_text)

                            if filtered_text and not filtered_text.isspace():
                                # Create streaming chunk
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
                        if DEBUG_MODE or VERBOSE:
                            logger.debug(f"Raw content string: {content[:200]}...")
                            
                        # Filter out tool usage and thinking blocks
                        filtered_content = MessageAdapter.filter_content(content)

                        if filtered_content and not filtered_content.isspace():
                            # Create streaming chunk
                            stream_chunk = ChatCompletionStreamResponse(
                                id=request_id,
                                model=request.model,
                                choices=[
                                    StreamChoice(
                                        index=0, delta={"content": filtered_content}, finish_reason=None
                                    )
                                ],
                            )

                            yield f"data: {stream_chunk.model_dump_json()}\n\n"
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
            logger.warning(f"No content generated for request {request_id} (role_sent={role_sent})")
            fallback_chunk = ChatCompletionStreamResponse(
                id=request_id,
                model=request.model,
                choices=[
                    StreamChoice(
                        index=0,
                        delta={"content": "I'm unable to provide a response at the moment."},
                        finish_reason=None,
                    )
                ],
            )
            yield f"data: {fallback_chunk.model_dump_json()}\n\n"

        # Extract assistant response from all chunks
        assistant_content = None
        if chunks_buffer:
            assistant_content = claude_cli.parse_claude_message(chunks_buffer)

            # Store in session if applicable
            if actual_session_id and assistant_content:
                assistant_message = Message(role="assistant", content=assistant_content)
                await session_manager.add_assistant_response(actual_session_id, assistant_message)

        # Extract real metadata (usage + stop_reason) from SDK messages
        metadata = claude_cli.extract_metadata(chunks_buffer)

        # Prepare usage data if requested
        usage_data = None
        if request.stream_options and request.stream_options.include_usage:
            sdk_usage = metadata.get("usage")
            if sdk_usage and isinstance(sdk_usage, dict):
                pt = sdk_usage.get("input_tokens", sdk_usage.get("prompt_tokens", 0))
                ct = sdk_usage.get("output_tokens", sdk_usage.get("completion_tokens", 0))
                usage_data = Usage(
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    total_tokens=pt + ct,
                )
            else:
                # Fall back to estimate
                completion_text = assistant_content or ""
                token_usage = claude_cli.estimate_token_usage(prompt, completion_text, request.model)
                usage_data = Usage(
                    prompt_tokens=token_usage["prompt_tokens"],
                    completion_tokens=token_usage["completion_tokens"],
                    total_tokens=token_usage["total_tokens"],
                )
            logger.debug(f"Usage: {usage_data}")

        # Send final chunk with mapped finish_reason and optionally usage data
        finish_reason = claude_cli.map_stop_reason_openai(metadata.get("stop_reason"))
        final_chunk = ChatCompletionStreamResponse(
            id=request_id,
            model=request.model,
            choices=[StreamChoice(index=0, delta={}, finish_reason=finish_reason)],  # type: ignore[arg-type]
            usage=usage_data,
        )
        yield f"data: {final_chunk.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

    except SessionLimitExceeded:
        error_chunk = {
            "error": {
                "message": f"Maximum session limit reached ({session_manager.max_sessions}). Try again later or close existing sessions.",
                "type": "rate_limit_exceeded",
                "code": "too_many_sessions",
            }
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        error_chunk = {"error": {"message": str(e), "type": "streaming_error"}}
        yield f"data: {json.dumps(error_chunk)}\n\n"


async def generate_anthropic_streaming_response(
    request: AnthropicMessagesRequest,
    request_id: str,
    claude_headers: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[str, None]:
    """Generate Anthropic SSE formatted streaming response."""
    try:
        # Convert messages and prepend system message
        messages = request.to_openai_messages()
        if request.system:
            messages = [Message(role="system", content=request.system)] + messages

        # Process messages with session management
        all_messages, actual_session_id = await session_manager.process_messages(
            messages, request.session_id
        )

        # Only send new messages if we are resuming an existing session
        prompt_messages = get_prompt_messages(all_messages, bool(actual_session_id))

        # Convert messages to prompt (pass model for optimized formatting)
        prompt, system_prompt = MessageAdapter.messages_to_prompt(prompt_messages, request.model)

        # Add sampling instructions
        sampling_instructions = request.get_sampling_instructions()
        if sampling_instructions:
            if system_prompt:
                system_prompt = f"{system_prompt}\n\n{sampling_instructions}"
            else:
                system_prompt = sampling_instructions

        # Build options
        options: Dict[str, Any] = {"model": request.model}
        if claude_headers:
            options.update(claude_headers)

        # Validate model
        if options.get("model"):
            ParameterValidator.validate_model(options["model"])

        # Configure tools
        if not request.enable_tools:
            options["disallowed_tools"] = CLAUDE_TOOLS
            options["max_turns"] = 1
        else:
            options["allowed_tools"] = DEFAULT_ALLOWED_TOOLS
            options["permission_mode"] = "bypassPermissions"

        # Emit message_start
        start_event = AnthropicMessageStartEvent(
            message={
                "id": request_id,
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": request.model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        )
        yield f"event: message_start\ndata: {start_event.model_dump_json()}\n\n"

        # Emit content_block_start
        block_start = AnthropicContentBlockStartEvent(
            index=0, content_block={"type": "text", "text": ""}
        )
        yield f"event: content_block_start\ndata: {block_start.model_dump_json()}\n\n"

        chunks_buffer = []
        content_sent = False

        # Call the CLI within the process semaphore to limit concurrency
        async with (process_semaphore or asyncio.Semaphore(MAX_CONCURRENT_PROCESSES)):
            completion_gen = claude_cli.run_completion(
                prompt=prompt,
                system_prompt=system_prompt,
                stream=True,
                session_id=None,
                claude_options=options,
            )

            async for chunk in completion_gen:
                chunks_buffer.append(chunk)

                if DEBUG_MODE or VERBOSE:
                    logger.debug(f"Anthropic streaming chunk: type={chunk.get('type')}, subtype={chunk.get('subtype')}, keys={list(chunk.keys())}")

                content = None
                if (chunk.get("type") == "assistant" or chunk.get("type") == "assistant_message") and "message" in chunk:
                    message = chunk["message"]
                    if isinstance(message, dict) and "content" in message:
                        content = message["content"]
                elif chunk.get("type") == "content_block_delta" and "delta" in chunk:
                    # Claude SDK delta format: {"type": "content_block_delta", "delta": {"text": "..."}}
                    delta = chunk["delta"]
                    if isinstance(delta, dict) and "text" in delta:
                        content = delta["text"]
                elif "content" in chunk and isinstance(chunk["content"], list):
                    content = chunk["content"]

                if content is not None:
                    if isinstance(content, list):
                        for block in content:
                            if hasattr(block, "text"):
                                raw_text = block.text
                            elif isinstance(block, dict) and block.get("type") == "text":
                                raw_text = block.get("text", "")
                            else:
                                continue

                            if DEBUG_MODE or VERBOSE:
                                logger.debug(f"Raw anthropic content block: {raw_text[:200]}...")

                            filtered_text = MessageAdapter.filter_content(raw_text)
                            if filtered_text and not filtered_text.isspace():
                                delta_event = AnthropicContentBlockDeltaEvent(
                                    index=0,
                                    delta={"type": "text_delta", "text": filtered_text},
                                )
                                yield f"event: content_block_delta\ndata: {delta_event.model_dump_json()}\n\n"
                                content_sent = True

                    elif isinstance(content, str):
                        if DEBUG_MODE or VERBOSE:
                            logger.debug(f"Raw anthropic content string: {content[:200]}...")

                        filtered_content = MessageAdapter.filter_content(content)
                        if filtered_content and not filtered_content.isspace():
                            delta_event = AnthropicContentBlockDeltaEvent(
                                index=0,
                                delta={"type": "text_delta", "text": filtered_content},
                            )
                            yield f"event: content_block_delta\ndata: {delta_event.model_dump_json()}\n\n"
                            content_sent = True

            # If no content was sent, send a minimal response
            if not content_sent:
                delta_event = AnthropicContentBlockDeltaEvent(
                    index=0,
                    delta={"type": "text_delta", "text": "I'm unable to provide a response at the moment."},
                )
                yield f"event: content_block_delta\ndata: {delta_event.model_dump_json()}\n\n"

        # Emit content_block_stop
        block_stop = AnthropicContentBlockStopEvent(index=0)
        yield f"event: content_block_stop\ndata: {block_stop.model_dump_json()}\n\n"

        # Extract and store assistant content
        assistant_content = None
        if chunks_buffer:
            assistant_content = claude_cli.parse_claude_message(chunks_buffer)
            if actual_session_id and assistant_content:
                assistant_message = Message(role="assistant", content=assistant_content)
                await session_manager.add_assistant_response(actual_session_id, assistant_message)

        # Use real token counts from SDK metadata when available
        metadata = claude_cli.extract_metadata(chunks_buffer)
        sdk_usage = metadata.get("usage")
        if sdk_usage and isinstance(sdk_usage, dict):
            output_tokens = sdk_usage.get("output_tokens", sdk_usage.get("completion_tokens", 0))
        else:
            completion_text = assistant_content or ""
            output_tokens = MessageAdapter.estimate_tokens(completion_text)

        # Real stop_reason from SDK (Anthropic format: "end_turn", "max_tokens", etc.)
        stop_reason = metadata.get("stop_reason") or "end_turn"

        # Emit message_delta
        msg_delta = AnthropicMessageDeltaEvent(
            delta={"type": "message_delta", "stop_reason": stop_reason, "stop_sequence": None},
            usage={"output_tokens": output_tokens},
        )
        yield f"event: message_delta\ndata: {msg_delta.model_dump_json()}\n\n"

        # Emit message_stop
        msg_stop = AnthropicMessageStopEvent()
        yield f"event: message_stop\ndata: {msg_stop.model_dump_json()}\n\n"

    except Exception as e:
        logger.error(f"Anthropic streaming error: {e}")
        error_chunk = {"error": {"message": str(e), "type": "streaming_error"}}
        yield f"data: {json.dumps(error_chunk)}\n\n"


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

    # Validate Claude Code authentication
    auth_valid, auth_info = validate_claude_code_auth()

    if not auth_valid:
        error_detail = {
            "message": "Claude Code authentication failed",
            "errors": auth_info.get("errors", []),
            "method": auth_info.get("method", "none"),
            "help": "Check /v1/auth/status for detailed authentication information",
        }
        raise HTTPException(status_code=503, detail=error_detail)

    try:
        request_id = f"chatcmpl-{os.urandom(8).hex()}"

        # Extract Claude-specific parameters from headers
        claude_headers = ParameterValidator.extract_claude_headers(dict(request.headers))

        # Log compatibility info
        if logger.isEnabledFor(logging.DEBUG):
            compatibility_report = CompatibilityReporter.generate_compatibility_report(request_body)
            logger.debug(f"Compatibility report: {compatibility_report}")

        model_recognized = ParameterValidator.is_model_recognized(request_body.model)

        # Pre-check session limit before streaming branch (can't change HTTP status mid-stream)
        if request_body.session_id:
            try:
                await session_manager.check_session_limit(request_body.session_id)
            except SessionLimitExceeded:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "message": f"Maximum session limit reached ({session_manager.max_sessions}). Try again later or close existing sessions.",
                        "type": "rate_limit_exceeded",
                        "code": "too_many_sessions",
                    },
                    headers={"Retry-After": "60"},
                )

        if request_body.stream:
            # Return streaming response
            streaming_headers = {
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
            if not model_recognized:
                streaming_headers["X-Claude-Model-Warning"] = "unrecognized"
            return StreamingResponse(
                generate_streaming_response(request_body, request_id, claude_headers),
                media_type="text/event-stream",
                headers=streaming_headers,
            )
        else:
            # Non-streaming response
            # Process messages with session management
            all_messages, actual_session_id = await session_manager.process_messages(
                request_body.messages, request_body.session_id
            )

            # Only send new messages if we are resuming an existing session
            prompt_messages = get_prompt_messages(all_messages, bool(actual_session_id))

            logger.info(
                f"Chat completion: session_id={actual_session_id}, total_messages={len(all_messages)}, prompt_messages={len(prompt_messages)}"
            )

            # Convert messages to prompt (pass model for optimized formatting)
            prompt, system_prompt = MessageAdapter.messages_to_prompt(prompt_messages, request_body.model)

            # Add sampling instructions from temperature/top_p if present
            sampling_instructions = request_body.get_sampling_instructions()
            if sampling_instructions:
                if system_prompt:
                    system_prompt = f"{system_prompt}\n\n{sampling_instructions}"
                else:
                    system_prompt = sampling_instructions
                logger.debug(f"Added sampling instructions: {sampling_instructions}")

            # Filter content
            prompt = MessageAdapter.filter_content(prompt)
            if system_prompt:
                system_prompt = MessageAdapter.filter_content(system_prompt)

            # Get options from request
            options = request_body.to_claude_options()

            # Merge with headers
            if claude_headers:
                options.update(claude_headers)

            # Validate model
            if options.get("model"):
                ParameterValidator.validate_model(options["model"])

            # Handle tools
            if not request_body.enable_tools:
                options["disallowed_tools"] = CLAUDE_TOOLS
                options["max_turns"] = 1  # Single turn for Q&A
                logger.info("Tools disabled (default behavior for OpenAI compatibility)")
            else:
                options["allowed_tools"] = DEFAULT_ALLOWED_TOOLS
                # Set permission mode to bypass prompts (required for API/headless usage)
                options["permission_mode"] = "bypassPermissions"
                logger.info(f"Tools enabled by user request: {DEFAULT_ALLOWED_TOOLS}")

            # Collect all chunks
            chunks = []

            # Call the CLI within the process semaphore to limit concurrency
            async with (process_semaphore or asyncio.Semaphore(MAX_CONCURRENT_PROCESSES)):
                completion_gen = claude_cli.run_completion(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    stream=False,
                    session_id=None,
                    claude_options=options,
                )

                async for chunk in completion_gen:
                    chunks.append(chunk)

            # Extract assistant message
            raw_assistant_content = claude_cli.parse_claude_message(chunks)

            if not raw_assistant_content:
                raise HTTPException(status_code=500, detail="No response from Claude Code")

            # Filter out tool usage and thinking blocks, also handle potential echoes
            assistant_content = MessageAdapter.filter_content(raw_assistant_content, prompt_echo=prompt)

            # Add assistant response to session if using session mode
            if actual_session_id:
                assistant_message = Message(role="assistant", content=assistant_content)
                await session_manager.add_assistant_response(actual_session_id, assistant_message)

            # Use real token counts from SDK metadata when available
            metadata = claude_cli.extract_metadata(chunks)
            sdk_usage = metadata.get("usage")
            if sdk_usage and isinstance(sdk_usage, dict):
                prompt_tokens = sdk_usage.get("input_tokens", sdk_usage.get("prompt_tokens", 0))
                completion_tokens = sdk_usage.get("output_tokens", sdk_usage.get("completion_tokens", 0))
            else:
                prompt_tokens = MessageAdapter.estimate_tokens(prompt)
                completion_tokens = MessageAdapter.estimate_tokens(assistant_content)

            # Map stop_reason to OpenAI finish_reason
            finish_reason = claude_cli.map_stop_reason_openai(metadata.get("stop_reason"))

            # Create response
            response_data = ChatCompletionResponse(
                id=request_id,
                model=request_body.model,
                choices=[
                    Choice(
                        index=0,
                        message=Message(role="assistant", content=assistant_content),
                        finish_reason=finish_reason,  # type: ignore[arg-type]
                    )
                ],
                usage=Usage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                ),
            )

            response = JSONResponse(content=response_data.model_dump())
            if not model_recognized:
                response.headers["X-Claude-Model-Warning"] = "unrecognized"
            return response

    except SessionLimitExceeded:
        raise HTTPException(
            status_code=429,
            detail={
                "message": f"Maximum session limit reached ({session_manager.max_sessions}). Try again later or close existing sessions.",
                "type": "rate_limit_exceeded",
                "code": "too_many_sessions",
            },
            headers={"Retry-After": "60"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat completion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

    # Validate Claude Code authentication
    auth_valid, auth_info = validate_claude_code_auth()

    if not auth_valid:
        error_detail = {
            "message": "Claude Code authentication failed",
            "errors": auth_info.get("errors", []),
            "method": auth_info.get("method", "none"),
            "help": "Check /v1/auth/status for detailed authentication information",
        }
        raise HTTPException(status_code=503, detail=error_detail)

    print(f"[/v1/messages] Handler entered, model={request_body.model}", flush=True)
    try:
        request_id = f"msg_{os.urandom(12).hex()}"
        logger.info(f"Anthropic Messages API request: model={request_body.model}")

        # Extract Claude-specific parameters from headers
        claude_headers = ParameterValidator.extract_claude_headers(dict(request.headers))

        if request_body.stream:
            return StreamingResponse(
                generate_anthropic_streaming_response(request_body, request_id, claude_headers),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )

        # Non-streaming: convert messages and prepend system
        messages = request_body.to_openai_messages()
        if request_body.system:
            messages = [Message(role="system", content=request_body.system)] + messages

        # Process with session management
        all_messages, actual_session_id = await session_manager.process_messages(
            messages, request_body.session_id
        )

        # Only send new messages if we are resuming an existing session
        prompt_messages = get_prompt_messages(all_messages, bool(actual_session_id))

        # Convert to prompt (pass model for optimized formatting)
        prompt, system_prompt = MessageAdapter.messages_to_prompt(prompt_messages, request_body.model)

        # Add sampling instructions
        sampling_instructions = request_body.get_sampling_instructions()
        if sampling_instructions:
            if system_prompt:
                system_prompt = f"{system_prompt}\n\n{sampling_instructions}"
            else:
                system_prompt = sampling_instructions

        # Build options
        options: Dict[str, Any] = {"model": request_body.model}
        if claude_headers:
            options.update(claude_headers)

        # Validate model
        if options.get("model"):
            ParameterValidator.validate_model(options["model"])

        # Configure tools
        if not request_body.enable_tools:
            options["disallowed_tools"] = CLAUDE_TOOLS
            options["max_turns"] = 1
        else:
            options["allowed_tools"] = DEFAULT_ALLOWED_TOOLS
            options["permission_mode"] = "bypassPermissions"

        # Run CLI
        print(f"[/v1/messages] Calling run_completion, enable_tools={request_body.enable_tools}", flush=True)
        chunks = []

        async with (process_semaphore or asyncio.Semaphore(MAX_CONCURRENT_PROCESSES)):
            completion_gen = claude_cli.run_completion(
                prompt=prompt,
                system_prompt=system_prompt,
                stream=False,
                session_id=None,
                claude_options=options,
            )

            async for chunk in completion_gen:
                chunks.append(chunk)

        # Extract assistant message
        raw_assistant_content = claude_cli.parse_claude_message(chunks)

        if not raw_assistant_content:
            raise HTTPException(status_code=500, detail="No response from CLI")

        # Filter out tool usage and thinking blocks, also handle potential echoes
        assistant_content = MessageAdapter.filter_content(raw_assistant_content, prompt_echo=prompt)

        # Store in session
        if actual_session_id:
            assistant_message = Message(role="assistant", content=assistant_content)
            await session_manager.add_assistant_response(actual_session_id, assistant_message)

        # Use real token counts from metadata when available
        metadata = claude_cli.extract_metadata(chunks)
        sdk_usage = metadata.get("usage")
        if sdk_usage and isinstance(sdk_usage, dict):
            prompt_tokens = sdk_usage.get("input_tokens", sdk_usage.get("prompt_tokens", 0))
            completion_tokens = sdk_usage.get("output_tokens", sdk_usage.get("completion_tokens", 0))
        else:
            prompt_tokens = MessageAdapter.estimate_tokens(prompt)
            completion_tokens = MessageAdapter.estimate_tokens(assistant_content)

        # Real stop_reason from SDK
        stop_reason = metadata.get("stop_reason") or "end_turn"

        response_data = AnthropicMessagesResponse(
            model=request_body.model,
            content=[AnthropicTextBlock(text=assistant_content)],
            stop_reason=stop_reason,  # type: ignore[arg-type]
            usage=AnthropicUsage(
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
            ),
        )

        response = JSONResponse(content=response_data.model_dump())
        if not ParameterValidator.is_model_recognized(request_body.model):
            response.headers["X-Claude-Model-Warning"] = "unrecognized"
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Anthropic Messages API error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/models")
async def list_models(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """List available models.

    Returns src.constants.CLAUDE_MODELS — the curated default, or a
    CLAUDE_MODELS_OVERRIDE env-var list if set. Not proxied from
    ${ANTHROPIC_BASE_URL}/v1/models; see the comment above CLAUDE_MODELS
    in constants.py for why, and the migration path.
    """
    # Check FastAPI API key if configured
    await verify_api_key(request, credentials)

    # Use constants for single source of truth
    return {
        "object": "list",
        "data": [
            {"id": model_id, "object": "model", "owned_by": "anthropic"}
            for model_id in CLAUDE_MODELS
        ],
    }


@app.post("/v1/compatibility")
@rate_limit_endpoint("general")
async def check_compatibility(request: Request, request_body: ChatCompletionRequest):
    """Check OpenAI API compatibility for a request."""
    report = CompatibilityReporter.generate_compatibility_report(request_body)
    return JSONResponse(
        content={
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
    )


@app.get("/health")
@rate_limit_endpoint("health")
async def health_check(request: Request):
    """Health check endpoint."""
    return {"status": "healthy", "service": "claude-code-openai-wrapper"}


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
@rate_limit_endpoint("general")
async def root(request: Request):
    """Landing page with API documentation."""
    from src import __version__

    auth_info = get_claude_code_auth_info()
    auth_method = "configured"  # Do not reveal auth method to unauthenticated visitors (FR-7.2)
    auth_valid = auth_info.get("status", {}).get("valid", False)
    status_color = "#22c55e" if auth_valid else "#ef4444"
    status_text = "Connected" if auth_valid else "Not Connected"

    html_content = _LANDING_TEMPLATE.substitute(
        version=__version__,
        auth_method=auth_method,
        status_color=status_color,
        status_text=status_text,
    )
    return HTMLResponse(content=html_content)


@app.post("/v1/debug/request")
@rate_limit_endpoint("debug")
async def debug_request_validation(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Debug endpoint to test request validation and see what's being sent."""
    await verify_api_key(request, credentials)
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
            json_error = str(e)

        # Try to validate against our model
        validation_result = {"valid": False, "errors": []}
        if parsed_body:
            try:
                chat_request = ChatCompletionRequest(**parsed_body)
                validation_result = {
                    "valid": True,
                    "validated_data": redact_request_body(chat_request.model_dump()),
                }
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
                "headers": redact_request_headers(dict(request.headers)),
                "method": request.method,
                "url": str(request.url),
                "raw_body": "[REDACTED — use parsed_body]",
                "json_parse_error": json_error,
                "parsed_body": redact_request_body(parsed_body) if parsed_body else parsed_body,
                "validation_result": validation_result,
                "debug_mode_enabled": DEBUG_MODE or VERBOSE,
                "example_valid_request": {
                    "model": DEFAULT_MODEL,
                    "messages": [{"role": "user", "content": "Hello, world!"}],
                    "stream": False,
                },
            }
        }

    except Exception as e:
        return {
            "debug_info": {
                "error": f"Debug endpoint error: {str(e)}",
                "headers": redact_request_headers(dict(request.headers)),
                "method": request.method,
                "url": str(request.url),
            }
        }


@app.get("/v1/auth/status")
@rate_limit_endpoint("auth")
async def get_auth_status(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Get Claude Code authentication status."""
    auth_info = get_claude_code_auth_info()
    auth_valid = auth_info.get("status", {}).get("valid", False)
    return {"authenticated": auth_valid}


@app.get("/v1/sessions/stats")
async def get_session_stats(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Get session manager statistics."""
    stats = await session_manager.get_stats()
    return {
        "session_stats": stats,
        "cleanup_interval_minutes": session_manager.cleanup_interval_minutes,
        "default_ttl_hours": session_manager.default_ttl_hours,
    }


@app.get("/v1/sessions")
async def list_sessions(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """List all active sessions."""
    sessions = await session_manager.list_sessions()
    return SessionListResponse(sessions=sessions, total=len(sessions))


@app.get("/v1/sessions/{session_id}")
async def get_session(
    session_id: str, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Get information about a specific session."""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session.to_session_info()


@app.delete("/v1/sessions/{session_id}")
async def delete_session(
    session_id: str, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Delete a specific session."""
    deleted = await session_manager.delete_session(session_id)
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
