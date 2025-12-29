import os
import json
import asyncio
import logging
import secrets
import string
import uuid
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
)
from src.claude_cli import ClaudeCodeCLI
from src.message_adapter import MessageAdapter
from src.auth import verify_api_key, security, validate_claude_code_auth, get_claude_code_auth_info
from src.parameter_validator import ParameterValidator, CompatibilityReporter
from src.session_manager import session_manager
from src.tool_manager import tool_manager
from src.mcp_client import mcp_client, MCPServerConfig
from src.rate_limiter import (
    limiter,
    rate_limit_exceeded_handler,
    rate_limit_endpoint,
)
from src.constants import CLAUDE_MODELS, CLAUDE_TOOLS, DEFAULT_ALLOWED_TOOLS

# Load environment variables
load_dotenv()

# Configure logging based on debug mode
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() in ("true", "1", "yes", "on")
VERBOSE = os.getenv("VERBOSE", "false").lower() in ("true", "1", "yes", "on")

# Set logging level based on debug/verbose mode
log_level = logging.DEBUG if (DEBUG_MODE or VERBOSE) else logging.INFO
logging.basicConfig(level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify Claude Code authentication and CLI on startup."""
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

    # Verify Claude Agent SDK with timeout for graceful degradation
    try:
        logger.info("Testing Claude Agent SDK connection...")
        # Use asyncio.wait_for to enforce timeout (30 seconds)
        cli_verified = await asyncio.wait_for(claude_cli.verify_cli(), timeout=30.0)

        if cli_verified:
            logger.info("✅ Claude Agent SDK verified successfully")
        else:
            logger.warning("⚠️  Claude Agent SDK verification returned False")
            logger.warning("The server will start, but requests may fail.")
    except asyncio.TimeoutError:
        logger.warning("⚠️  Claude Agent SDK verification timed out (30s)")
        logger.warning("This may indicate network issues or SDK configuration problems.")
        logger.warning("The server will start, but first request may be slow.")
    except Exception as e:
        logger.error(f"⚠️  Claude Agent SDK verification failed: {e}")
        logger.warning("The server will start, but requests may fail.")
        logger.warning("Check that Claude Code CLI is properly installed and authenticated.")

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
    session_manager.shutdown()


# Create FastAPI app
app = FastAPI(
    title="Claude Code OpenAI API Wrapper",
    description="OpenAI-compatible API for Claude Code",
    version="1.0.0",
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


async def generate_streaming_response(
    request: ChatCompletionRequest, request_id: str, claude_headers: Optional[Dict[str, Any]] = None
) -> AsyncGenerator[str, None]:
    """Generate SSE formatted streaming response."""
    try:
        # Process messages with session management
        all_messages, actual_session_id = session_manager.process_messages(
            request.messages, request.session_id
        )

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

        # Filter content for unsupported features
        prompt = MessageAdapter.filter_content(prompt)
        if system_prompt:
            system_prompt = MessageAdapter.filter_content(system_prompt)

        # Get Claude Agent SDK options from request
        claude_options = request.to_claude_options()

        # Merge with Claude-specific headers if provided
        if claude_headers:
            claude_options.update(claude_headers)

        # Validate model
        if claude_options.get("model"):
            ParameterValidator.validate_model(claude_options["model"])

        # Handle tools - disabled by default for OpenAI compatibility
        if not request.enable_tools:
            # Disable all tools by using CLAUDE_TOOLS constant
            claude_options["disallowed_tools"] = CLAUDE_TOOLS
            claude_options["max_turns"] = 1  # Single turn for Q&A
            logger.info("Tools disabled (default behavior for OpenAI compatibility)")
        else:
            # Enable tools - use default safe subset (Read, Glob, Grep, Bash, Write, Edit)
            claude_options["allowed_tools"] = DEFAULT_ALLOWED_TOOLS
            # Set permission mode to bypass prompts (required for API/headless usage)
            claude_options["permission_mode"] = "bypassPermissions"
            logger.info(f"Tools enabled by user request: {DEFAULT_ALLOWED_TOOLS}")

        # Run Claude Code
        chunks_buffer = []
        role_sent = False  # Track if we've sent the initial role chunk
        content_sent = False  # Track if we've sent any content

        async for chunk in claude_cli.run_completion(
            prompt=prompt,
            system_prompt=system_prompt,
            model=claude_options.get("model"),
            max_turns=claude_options.get("max_turns", 10),
            allowed_tools=claude_options.get("allowed_tools"),
            disallowed_tools=claude_options.get("disallowed_tools"),
            permission_mode=claude_options.get("permission_mode"),
            stream=True,
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
                session_manager.add_assistant_response(actual_session_id, assistant_message)

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
            # Process messages with session management
            all_messages, actual_session_id = session_manager.process_messages(
                request_body.messages, request_body.session_id
            )

            logger.info(
                f"Chat completion: session_id={actual_session_id}, total_messages={len(all_messages)}"
            )

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

            # Filter content
            prompt = MessageAdapter.filter_content(prompt)
            if system_prompt:
                system_prompt = MessageAdapter.filter_content(system_prompt)

            # Get Claude Agent SDK options from request
            claude_options = request_body.to_claude_options()

            # Merge with Claude-specific headers
            if claude_headers:
                claude_options.update(claude_headers)

            # Validate model
            if claude_options.get("model"):
                ParameterValidator.validate_model(claude_options["model"])

            # Handle tools - disabled by default for OpenAI compatibility
            if not request_body.enable_tools:
                # Disable all tools by using CLAUDE_TOOLS constant
                claude_options["disallowed_tools"] = CLAUDE_TOOLS
                claude_options["max_turns"] = 1  # Single turn for Q&A
                logger.info("Tools disabled (default behavior for OpenAI compatibility)")
            else:
                # Enable tools - use default safe subset (Read, Glob, Grep, Bash, Write, Edit)
                claude_options["allowed_tools"] = DEFAULT_ALLOWED_TOOLS
                # Set permission mode to bypass prompts (required for API/headless usage)
                claude_options["permission_mode"] = "bypassPermissions"
                logger.info(f"Tools enabled by user request: {DEFAULT_ALLOWED_TOOLS}")

            # Collect all chunks
            chunks = []
            async for chunk in claude_cli.run_completion(
                prompt=prompt,
                system_prompt=system_prompt,
                model=claude_options.get("model"),
                max_turns=claude_options.get("max_turns", 10),
                allowed_tools=claude_options.get("allowed_tools"),
                disallowed_tools=claude_options.get("disallowed_tools"),
                permission_mode=claude_options.get("permission_mode"),
                stream=False,
            ):
                chunks.append(chunk)

            # Extract assistant message
            raw_assistant_content = claude_cli.parse_claude_message(chunks)

            if not raw_assistant_content:
                raise HTTPException(status_code=500, detail="No response from Claude Code")

            # Filter out tool usage and thinking blocks
            assistant_content = MessageAdapter.filter_content(raw_assistant_content)

            # Add assistant response to session if using session mode
            if actual_session_id:
                assistant_message = Message(role="assistant", content=assistant_content)
                session_manager.add_assistant_response(actual_session_id, assistant_message)

            # Estimate tokens (rough approximation)
            prompt_tokens = MessageAdapter.estimate_tokens(prompt)
            completion_tokens = MessageAdapter.estimate_tokens(assistant_content)

            # Create response
            response = ChatCompletionResponse(
                id=request_id,
                model=request_body.model,
                choices=[
                    Choice(
                        index=0,
                        message=Message(role="assistant", content=assistant_content),
                        finish_reason="stop",
                    )
                ],
                usage=Usage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                ),
            )

            return response

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

        # Extract assistant message
        raw_assistant_content = claude_cli.parse_claude_message(chunks)

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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/models")
async def list_models(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """List available models."""
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
    from src import __version__

    auth_info = get_claude_code_auth_info()
    auth_method = auth_info.get("method", "unknown")
    auth_valid = auth_info.get("status", {}).get("valid", False)
    status_color = "#22c55e" if auth_valid else "#ef4444"
    status_text = "Connected" if auth_valid else "Not Connected"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en" data-theme="dark">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="color-scheme" content="light dark">
        <title>Claude Code OpenAI Wrapper</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
        <style>
            :root {{
                --pico-font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                --accent-color: #16a34a;
            }}
            /* Light mode colors */
            [data-theme="light"] {{
                --card-bg: #ffffff;
                --subtle-bg: #f1f5f9;
                --border-color: #e2e8f0;
                --page-bg: #f8fafc;
            }}
            /* Dark mode colors */
            [data-theme="dark"] {{
                --card-bg: #1e293b;
                --subtle-bg: #334155;
                --border-color: #475569;
                --page-bg: #0f172a;
            }}
            /* Page background */
            body {{ background: var(--page-bg); }}
            /* GLOBAL FIX: Remove Pico's default code styling everywhere */
            code:not(pre code) {{
                background: transparent !important;
                padding: 0 !important;
                border-radius: 0 !important;
                color: inherit !important;
            }}
            /* Only style code green where we explicitly want it */
            .green-code {{ color: var(--accent-color) !important; }}
            /* Constrain page width - wider for modern screens */
            .container {{
                max-width: 1100px;
                margin: 0 auto;
                padding: 1.5rem 2rem;
            }}
            /* Override Pico article styling */
            article {{
                background: var(--card-bg);
                border: 1px solid var(--border-color);
                border-radius: 0.75rem;
                margin-bottom: 1rem;
                padding: 1rem 1.25rem;
            }}
            article header {{
                padding: 0;
                margin-bottom: 0.75rem;
                background: transparent;
                border: none;
            }}
            /* Section headers with icons - matches status-flex layout */
            .section-header {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                margin-bottom: 0.75rem;
            }}
            .section-icon {{
                width: 1rem;
                height: 1rem;
                color: var(--accent-color);
                flex-shrink: 0;
            }}
            /* Status indicator */
            .status-dot {{
                width: 0.75rem;
                height: 0.75rem;
                border-radius: 50%;
                display: inline-block;
                animation: pulse 2s infinite;
            }}
            @keyframes pulse {{
                0%, 100% {{ opacity: 1; }}
                50% {{ opacity: 0.5; }}
            }}
            /* Method badges */
            .badge {{
                display: inline-block;
                padding: 0.25rem 0.5rem;
                font-size: 0.7rem;
                font-weight: 700;
                border-radius: 0.25rem;
                text-transform: uppercase;
            }}
            .badge-post {{ background: rgba(34, 197, 94, 0.15); color: #16a34a; }}
            .badge-get {{ background: rgba(59, 130, 246, 0.15); color: #2563eb; }}
            /* Header layout */
            .header-flex {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 1rem;
                margin-bottom: 1rem;
            }}
            .header-left {{
                display: flex;
                align-items: center;
                gap: 1rem;
                flex-shrink: 0;
            }}
            .header-right {{
                display: flex;
                align-items: center;
                gap: 0.75rem;
                flex-shrink: 0;
            }}
            .icon-btn {{
                padding: 0.5rem;
                border-radius: 0.5rem;
                background: var(--subtle-bg);
                border: 1px solid var(--border-color);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: inherit;
            }}
            .icon-btn:hover {{ opacity: 0.8; }}
            .icon-btn svg {{ width: 1.25rem; height: 1.25rem; }}
            .version-badge {{
                padding: 0.25rem 0.75rem;
                background: var(--subtle-bg);
                border: 1px solid var(--border-color);
                border-radius: 0.5rem;
                font-family: monospace;
                font-size: 0.875rem;
            }}
            /* Logo container */
            .logo-container {{
                background: linear-gradient(135deg, #22c55e 0%, #0ea5e9 100%);
                padding: 2px;
                border-radius: 0.75rem;
            }}
            .logo-inner {{
                background: var(--card-bg);
                border-radius: calc(0.75rem - 2px);
                padding: 0.75rem;
                display: flex;
                align-items: center;
                justify-content: center;
            }}
            .logo-inner svg {{ width: 2rem; height: 2rem; color: #22c55e; }}
            /* Endpoint list */
            .endpoint-item {{
                display: flex;
                align-items: center;
                gap: 0.75rem;
                padding: 0.5rem 0;
                border-bottom: 1px solid var(--pico-muted-border-color);
            }}
            .endpoint-item:last-child {{ border-bottom: none; }}
            .endpoint-item code {{ flex: 1; }}
            .endpoint-desc {{ color: var(--pico-muted-color); font-size: 0.85rem; }}
            /* Details accordion styling */
            details {{
                border: 1px solid var(--border-color);
                border-radius: 0.5rem;
                margin-bottom: 0.4rem;
                background: var(--subtle-bg);
            }}
            details summary {{
                padding: 0.5rem 0.75rem;
                display: flex;
                align-items: center;
                gap: 0.75rem;
                cursor: pointer;
                list-style: none;
            }}
            details summary::-webkit-details-marker {{ display: none; }}
            details summary::after {{
                content: "";
                margin-left: auto;
                width: 0.5rem;
                height: 0.5rem;
                border-right: 2px solid currentColor;
                border-bottom: 2px solid currentColor;
                transform: rotate(-45deg);
                transition: transform 0.2s;
            }}
            details[open] summary::after {{ transform: rotate(45deg); }}
            details .content {{ padding: 0 1rem 1rem; }}
            details .content pre {{
                margin: 0;
                font-size: 0.875rem;
                overflow-x: auto;
            }}
            /* Config grid */
            .config-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 0.75rem;
            }}
            .config-item {{
                padding: 0.75rem;
                background: var(--subtle-bg);
                border: 1px solid var(--border-color);
                border-radius: 0.5rem;
            }}
            .config-item code {{ font-weight: 600; }}
            .config-item p {{ margin: 0.25rem 0 0; font-size: 0.875rem; color: var(--pico-muted-color); }}
            /* Footer */
            footer nav {{
                display: flex;
                justify-content: center;
                gap: 2rem;
            }}
            footer a {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }}
            footer svg {{ width: 1rem; height: 1rem; }}
            /* Quick start */
            .quickstart-wrapper {{ position: relative; }}
            .copy-btn {{
                position: absolute;
                top: 0.5rem;
                right: 0.5rem;
                padding: 0.5rem;
                background: var(--subtle-bg);
                border: 1px solid var(--border-color);
                border-radius: 0.5rem;
                cursor: pointer;
                z-index: 1;
                color: inherit;
            }}
            .copy-btn:hover {{ opacity: 0.8; }}
            .copy-btn svg {{ width: 1rem; height: 1rem; }}
            .hidden {{ display: none !important; }}
            /* Shiki code styling */
            .shiki {{ padding: 1rem; border-radius: 0.5rem; overflow-x: auto; }}
            .shiki code {{ white-space: pre-wrap; word-break: break-word; }}
            /* Status card layout */
            .status-flex {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
                gap: 1rem;
            }}
            .status-left {{
                display: flex;
                align-items: center;
                gap: 0.75rem;
            }}
            .auth-badge {{
                padding: 0.25rem 0.75rem;
                background: var(--subtle-bg);
                border: 1px solid var(--border-color);
                border-radius: 1rem;
                font-size: 0.875rem;
            }}
        </style>
        <script type="module">
            import {{ codeToHtml }} from 'https://esm.sh/shiki@3.0.0';

            const lightTheme = 'github-light';
            const darkTheme = 'github-dark';

            function isDark() {{
                return document.documentElement.getAttribute('data-theme') === 'dark';
            }}

            async function highlightJson(json, targetId) {{
                const code = typeof json === 'string' ? json : JSON.stringify(json, null, 2);
                const theme = isDark() ? darkTheme : lightTheme;
                try {{
                    const html = await codeToHtml(code, {{ lang: 'json', theme }});
                    document.getElementById(targetId).innerHTML = html;
                }} catch (e) {{
                    document.getElementById(targetId).innerHTML = '<pre style="color:red;">Error: ' + e.message + '</pre>';
                }}
            }}

            // Lazy load data when details opens
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
                                dataContainer.innerHTML = '<span style="color:red;">Error: ' + e.message + '</span>';
                            }}
                            loader.classList.add('hidden');
                        }}
                    }}
                }});
            }});

            // Re-highlight on theme change
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
  -d '{{"model": "claude-sonnet-4-5-20250929", "messages": [{{"role": "user", "content": "Hello!"}}]}}'`;

            async function highlightQuickstart() {{
                const theme = isDark() ? darkTheme : lightTheme;
                try {{
                    const html = await codeToHtml(quickstartCode, {{ lang: 'bash', theme }});
                    document.getElementById('quickstart-code').innerHTML = html;
                }} catch (e) {{
                    document.getElementById('quickstart-code').innerHTML = '<pre>' + quickstartCode + '</pre>';
                }}
            }}

            window.highlightQuickstart = highlightQuickstart;
            highlightQuickstart();
        </script>
        <script>
            const quickstartText = 'curl -X POST http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -d \\'{{"model": "claude-sonnet-4-5-20250929", "messages": [{{"role": "user", "content": "Hello!"}}]}}\\'';

            function copyQuickstart() {{
                if (navigator.clipboard && navigator.clipboard.writeText) {{
                    navigator.clipboard.writeText(quickstartText).then(showCopySuccess).catch(fallbackCopy);
                }} else {{
                    fallbackCopy();
                }}
            }}

            function fallbackCopy() {{
                const textarea = document.createElement('textarea');
                textarea.value = quickstartText;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                try {{ document.execCommand('copy'); showCopySuccess(); }} catch (e) {{ console.error('Copy failed:', e); }}
                document.body.removeChild(textarea);
            }}

            function showCopySuccess() {{
                const copyIcon = document.getElementById('copy-icon');
                const checkIcon = document.getElementById('check-icon');
                copyIcon.classList.add('hidden');
                checkIcon.classList.remove('hidden');
                setTimeout(() => {{
                    copyIcon.classList.remove('hidden');
                    checkIcon.classList.add('hidden');
                }}, 2000);
            }}

            function toggleTheme() {{
                const html = document.documentElement;
                const current = html.getAttribute('data-theme');
                const next = current === 'dark' ? 'light' : 'dark';
                html.setAttribute('data-theme', next);
                localStorage.setItem('theme', next);
                updateThemeIcon(next === 'dark');
                window.dispatchEvent(new Event('themeChanged'));
            }}

            function updateThemeIcon(isDark) {{
                document.getElementById('sun-icon').classList.toggle('hidden', isDark);
                document.getElementById('moon-icon').classList.toggle('hidden', !isDark);
            }}

            document.addEventListener('DOMContentLoaded', () => {{
                const saved = localStorage.getItem('theme');
                if (saved) {{
                    document.documentElement.setAttribute('data-theme', saved);
                    updateThemeIcon(saved === 'dark');
                }} else {{
                    updateThemeIcon(true);
                }}
            }});
        </script>
    </head>
    <body>
        <main class="container">
            <!-- Header -->
            <header class="header-flex">
                <div class="header-left">
                    <div class="logo-container">
                        <div class="logo-inner">
                            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
                            </svg>
                        </div>
                    </div>
                    <div>
                        <h1 style="margin:0;">Claude Code OpenAI Wrapper</h1>
                        <p style="margin:0;color:var(--pico-muted-color);">OpenAI-compatible API for Claude</p>
                    </div>
                </div>
                <div class="header-right">
                    <span class="version-badge">v{__version__}</span>
                    <button onclick="toggleTheme()" class="icon-btn" title="Toggle theme">
                        <svg id="sun-icon" class="hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/>
                        </svg>
                        <svg id="moon-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/>
                        </svg>
                    </button>
                    <a href="https://github.com/aaronlippold/claude-code-openai-wrapper" target="_blank" rel="noopener noreferrer" class="icon-btn" title="View on GitHub">
                        <svg fill="currentColor" viewBox="0 0 24 24">
                            <path fill-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clip-rule="evenodd"/>
                        </svg>
                    </a>
                </div>
            </header>

            <!-- Status Card -->
            <article>
                <div class="status-flex">
                    <div class="status-left">
                        <span class="status-dot" style="background-color: {status_color};"></span>
                        <strong>{status_text}</strong>
                    </div>
                    <span class="auth-badge">Auth: <code class="green-code">{auth_method}</code></span>
                </div>
            </article>

            <!-- Quick Start -->
            <article>
                <div class="section-header">
                    <svg class="section-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
                    <strong>Quick Start</strong>
                </div>
                <div class="quickstart-wrapper">
                    <button onclick="copyQuickstart()" class="copy-btn" title="Copy to clipboard">
                        <svg id="copy-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
                        </svg>
                        <svg id="check-icon" class="hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="color:#22c55e;">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                        </svg>
                    </button>
                    <div id="quickstart-code"></div>
                </div>
            </article>

            <!-- API Endpoints -->
            <article>
                <div class="section-header">
                    <svg class="section-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                    <strong>API Endpoints</strong>
                </div>

                <!-- Static POST endpoints -->
                <div class="endpoint-item">
                    <span class="badge badge-post">POST</span>
                    <code>/v1/chat/completions</code>
                    <span class="endpoint-desc">OpenAI-compatible chat</span>
                </div>
                <div class="endpoint-item">
                    <span class="badge badge-post">POST</span>
                    <code>/v1/messages</code>
                    <span class="endpoint-desc">Anthropic-compatible</span>
                </div>

                <!-- Expandable GET endpoints -->
                <details id="models" data-endpoint="/v1/models" name="endpoints">
                    <summary>
                        <span class="badge badge-get">GET</span>
                        <code>/v1/models</code>
                        <span class="endpoint-desc">List models</span>
                    </summary>
                    <div class="content">
                        <small id="loader-models" class="hidden">Loading...</small>
                        <div id="data-models"></div>
                    </div>
                </details>

                <details id="auth" data-endpoint="/v1/auth/status" name="endpoints">
                    <summary>
                        <span class="badge badge-get">GET</span>
                        <code>/v1/auth/status</code>
                        <span class="endpoint-desc">Auth status</span>
                    </summary>
                    <div class="content">
                        <small id="loader-auth" class="hidden">Loading...</small>
                        <div id="data-auth"></div>
                    </div>
                </details>

                <details id="sessions" data-endpoint="/v1/sessions" name="endpoints">
                    <summary>
                        <span class="badge badge-get">GET</span>
                        <code>/v1/sessions</code>
                        <span class="endpoint-desc">Active sessions</span>
                    </summary>
                    <div class="content">
                        <small id="loader-sessions" class="hidden">Loading...</small>
                        <div id="data-sessions"></div>
                    </div>
                </details>

                <details id="health" data-endpoint="/health" name="endpoints">
                    <summary>
                        <span class="badge badge-get">GET</span>
                        <code>/health</code>
                        <span class="endpoint-desc">Health check</span>
                    </summary>
                    <div class="content">
                        <small id="loader-health" class="hidden">Loading...</small>
                        <div id="data-health"></div>
                    </div>
                </details>

                <details id="version" data-endpoint="/version" name="endpoints">
                    <summary>
                        <span class="badge badge-get">GET</span>
                        <code>/version</code>
                        <span class="endpoint-desc">API version</span>
                    </summary>
                    <div class="content">
                        <small id="loader-version" class="hidden">Loading...</small>
                        <div id="data-version"></div>
                    </div>
                </details>
            </article>

            <!-- Configuration -->
            <article>
                <div class="section-header">
                    <svg class="section-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                    <strong>Configuration</strong>
                </div>
                <p>Set <code>CLAUDE_AUTH_METHOD</code> to choose authentication:</p>
                <div class="config-grid">
                    <div class="config-item">
                        <code class="green-code">cli</code>
                        <p>Claude CLI auth</p>
                    </div>
                    <div class="config-item">
                        <code class="green-code">api_key</code>
                        <p>ANTHROPIC_API_KEY</p>
                    </div>
                    <div class="config-item">
                        <code class="green-code">bedrock</code>
                        <p>AWS Bedrock</p>
                    </div>
                    <div class="config-item">
                        <code class="green-code">vertex</code>
                        <p>Google Vertex AI</p>
                    </div>
                </div>
            </article>

            <!-- Footer -->
            <footer>
                <nav>
                    <a href="/docs">
                        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                        </svg>
                        API Docs
                    </a>
                    <a href="/redoc">
                        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/>
                        </svg>
                        ReDoc
                    </a>
                </nav>
            </footer>
        </main>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.post("/v1/debug/request")
@rate_limit_endpoint("debug")
async def debug_request_validation(request: Request):
    """Debug endpoint to test request validation and see what's being sent."""
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
                    "model": "claude-3-sonnet-20240229",
                    "messages": [{"role": "user", "content": "Hello, world!"}],
                    "stream": False,
                },
            }
        }

    except Exception as e:
        return {
            "debug_info": {
                "error": f"Debug endpoint error: {str(e)}",
                "headers": dict(request.headers),
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


def run_server(port: int = None):
    """Run the server - used as Poetry script entry point."""
    import uvicorn

    # Handle interactive API key protection
    global runtime_api_key
    runtime_api_key = prompt_for_api_protection()

    # Priority: CLI arg > ENV var > default
    if port is None:
        port = int(os.getenv("PORT", "8000"))
    preferred_port = port

    try:
        # Try the preferred port first
        uvicorn.run(app, host="0.0.0.0", port=preferred_port)
    except OSError as e:
        if "Address already in use" in str(e) or e.errno == 48:
            logger.warning(f"Port {preferred_port} is already in use. Finding alternative port...")
            try:
                available_port = find_available_port(preferred_port + 1)
                logger.info(f"Starting server on alternative port {available_port}")
                print(f"\n🚀 Server starting on http://localhost:{available_port}")
                print(f"📝 Update your client base_url to: http://localhost:{available_port}/v1")
                uvicorn.run(app, host="0.0.0.0", port=available_port)
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
