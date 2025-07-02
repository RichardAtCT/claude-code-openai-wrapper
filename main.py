import os
import json
import asyncio
import logging
import secrets
import string
from typing import Optional, AsyncGenerator, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from dotenv import load_dotenv

from models import (
    ChatCompletionRequest, 
    ChatCompletionResponse, 
    ChatCompletionStreamResponse,
    Choice, 
    Message, 
    Usage,
    StreamChoice,
    ErrorResponse,
    ErrorDetail,
    SessionInfo,
    SessionListResponse
)
from claude_cli import ClaudeCodeCLI
from message_adapter import MessageAdapter
from auth import verify_api_key, security, validate_claude_code_auth, get_claude_code_auth_info
from parameter_validator import ParameterValidator, CompatibilityReporter
from session_manager import session_manager

# Load environment variables
load_dotenv()

# Configure logging based on debug mode
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() in ('true', '1', 'yes', 'on')
VERBOSE = os.getenv('VERBOSE', 'false').lower() in ('true', '1', 'yes', 'on')

# Set logging level based on debug/verbose mode
log_level = logging.DEBUG if (DEBUG_MODE or VERBOSE) else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variable to store runtime-generated API key
runtime_api_key = None

def generate_secure_token(length: int = 32) -> str:
    """Generate a secure random token for API authentication."""
    alphabet = string.ascii_letters + string.digits + '-_'
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def prompt_for_api_protection() -> Optional[str]:
    """
    Interactively ask user if they want API key protection.
    Returns the generated token if user chooses protection, None otherwise.
    """
    # Don't prompt if API_KEY is already set via environment variable
    if os.getenv("API_KEY"):
        return None
    
    print("\n" + "="*60)
    print("🔐 API Endpoint Security Configuration")
    print("="*60)
    print("Would you like to protect your API endpoint with an API key?")
    print("This adds a security layer when accessing your server remotely.")
    print("")
    
    while True:
        try:
            choice = input("Enable API key protection? (y/N): ").strip().lower()
            
            if choice in ['', 'n', 'no']:
                print("✅ API endpoint will be accessible without authentication")
                print("="*60)
                return None
            
            elif choice in ['y', 'yes']:
                token = generate_secure_token()
                print("")
                print("🔑 API Key Generated!")
                print("="*60)
                print(f"API Key: {token}")
                print("="*60)
                print("📋 IMPORTANT: Save this key - you'll need it for API calls!")
                print("   Example usage:")
                print(f'   curl -H "Authorization: Bearer {token}" \\')
                print("        http://localhost:8000/v1/models")
                print("="*60)
                return token
            
            else:
                print("Please enter 'y' for yes or 'n' for no (or press Enter for no)")
                
        except (EOFError, KeyboardInterrupt):
            print("\n✅ Defaulting to no authentication")
            return None

# Initialize Claude CLI
claude_cli = ClaudeCodeCLI(
    timeout=int(os.getenv("MAX_TIMEOUT", "600000")),
    cwd=os.getenv("CLAUDE_CWD")
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify Claude Code authentication and CLI on startup."""
    logger.info("Verifying Claude Code authentication and CLI...")
    
    # Validate authentication first
    auth_valid, auth_info = validate_claude_code_auth()
    
    if not auth_valid:
        logger.error("❌ Claude Code authentication failed!")
        for error in auth_info.get('errors', []):
            logger.error(f"  - {error}")
        logger.warning("Authentication setup guide:")
        logger.warning("  1. For Anthropic API: Set ANTHROPIC_API_KEY")
        logger.warning("  2. For Bedrock: Set CLAUDE_CODE_USE_BEDROCK=1 + AWS credentials")
        logger.warning("  3. For Vertex AI: Set CLAUDE_CODE_USE_VERTEX=1 + GCP credentials")
    else:
        logger.info(f"✅ Claude Code authentication validated: {auth_info['method']}")
    
    # Then verify CLI
    cli_verified = await claude_cli.verify_cli()
    
    if cli_verified:
        logger.info("✅ Claude Code CLI verified successfully")
    else:
        logger.warning("⚠️  Claude Code CLI verification failed!")
        logger.warning("The server will start, but requests may fail.")
    
    # Log debug information if debug mode is enabled
    if DEBUG_MODE or VERBOSE:
        logger.debug("🔧 Debug mode enabled - Enhanced logging active")
        logger.debug(f"🔧 Environment variables:")
        logger.debug(f"   DEBUG_MODE: {DEBUG_MODE}")
        logger.debug(f"   VERBOSE: {VERBOSE}")
        logger.debug(f"   PORT: {os.getenv('PORT', '8000')}")
        logger.debug(f"   CORS_ORIGINS: {os.getenv('CORS_ORIGINS', '[\"*\"]')}")
        logger.debug(f"   MAX_TIMEOUT: {os.getenv('MAX_TIMEOUT', '600000')}")
        logger.debug(f"   CLAUDE_CWD: {os.getenv('CLAUDE_CWD', 'Not set')}")
        logger.debug(f"🔧 Available endpoints:")
        logger.debug(f"   POST /v1/chat/completions - Main chat endpoint")
        logger.debug(f"   GET  /v1/models - List available models")
        logger.debug(f"   POST /v1/debug/request - Debug request validation")
        logger.debug(f"   GET  /v1/auth/status - Authentication status")
        logger.debug(f"   GET  /health - Health check")
        logger.debug(f"🔧 API Key protection: {'Enabled' if (os.getenv('API_KEY') or runtime_api_key) else 'Disabled'}")
    
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
    lifespan=lifespan
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

# Add debug logging middleware
from starlette.middleware.base import BaseHTTPMiddleware

class DebugLoggingMiddleware(BaseHTTPMiddleware):
    """ASGI-compliant middleware for logging request/response details when debug mode is enabled."""
    
    async def dispatch(self, request: Request, call_next):
        if not (DEBUG_MODE or VERBOSE):
            return await call_next(request)
        
        # Log request details
        start_time = asyncio.get_event_loop().time()
        
        # Log basic request info
        logger.debug(f"🔍 Incoming request: {request.method} {request.url}")
        logger.debug(f"🔍 Headers: {dict(request.headers)}")
        
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
                            logger.debug(f"🔍 Request body: {json_lib.dumps(parsed_body, indent=2)}")
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
        error_details.append({
            "field": location,
            "message": error.get("msg", "Unknown validation error"),
            "type": error.get("type", "validation_error"),
            "input": error.get("input")
        })
    
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
                    "Invalid parameter ranges (e.g. temperature must be 0-2)"
                ],
                "debug_tip": "Set DEBUG_MODE=true or VERBOSE=true environment variable for more detailed logging"
            }
        }
    }
    
    # Add debug info if available
    if debug_info:
        error_response["error"]["debug"] = debug_info
    
    return JSONResponse(
        status_code=422,
        content=error_response
    )


async def generate_streaming_response(
    request: ChatCompletionRequest,
    request_id: str,
    claude_headers: Optional[Dict[str, Any]] = None
) -> AsyncGenerator[str, None]:
    """Generate SSE formatted streaming response."""
    try:
        # Process messages with session management
        all_messages, actual_session_id = session_manager.process_messages(
            request.messages, request.session_id
        )
        
        # Convert messages to prompt
        prompt, system_prompt = MessageAdapter.messages_to_prompt(all_messages)
        
        # Filter content for unsupported features
        prompt = MessageAdapter.filter_content(prompt)
        if system_prompt:
            system_prompt = MessageAdapter.filter_content(system_prompt)
        
        # Get Claude Code SDK options from request
        claude_options = request.to_claude_options()
        
        # Merge with Claude-specific headers if provided
        if claude_headers:
            claude_options.update(claude_headers)
        
        # Validate model
        if claude_options.get('model'):
            ParameterValidator.validate_model(claude_options['model'])
        
        # Handle tools - disabled by default for OpenAI compatibility
        if not request.enable_tools:
            # Set disallowed_tools to all available tools to disable them
            disallowed_tools = ['Task', 'Bash', 'Glob', 'Grep', 'LS', 'exit_plan_mode', 
                                'Read', 'Edit', 'MultiEdit', 'Write', 'NotebookRead', 
                                'NotebookEdit', 'WebFetch', 'TodoRead', 'TodoWrite', 'WebSearch']
            claude_options['disallowed_tools'] = disallowed_tools
            claude_options['max_turns'] = 1  # Single turn for Q&A
            logger.info("Tools disabled (default behavior for OpenAI compatibility)")
        else:
            logger.info("Tools enabled by user request")
        
        # Run Claude Code
        chunks_buffer = []
        role_sent = False  # Track if we've sent the initial role chunk
        content_sent = False  # Track if we've sent any content
        
        async for chunk in claude_cli.run_completion(
            prompt=prompt,
            system_prompt=system_prompt,
            model=claude_options.get('model'),
            max_turns=claude_options.get('max_turns', 10),
            allowed_tools=claude_options.get('allowed_tools'),
            disallowed_tools=claude_options.get('disallowed_tools'),
            stream=True
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
                        choices=[StreamChoice(
                            index=0,
                            delta={"role": "assistant", "content": ""},
                            finish_reason=None
                        )]
                    )
                    yield f"data: {initial_chunk.model_dump_json()}\n\n"
                    role_sent = True
                
                # Handle content blocks
                if isinstance(content, list):
                    for block in content:
                        # Handle TextBlock objects from Claude Code SDK
                        if hasattr(block, 'text'):
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
                                choices=[StreamChoice(
                                    index=0,
                                    delta={"content": filtered_text},
                                    finish_reason=None
                                )]
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
                            choices=[StreamChoice(
                                index=0,
                                delta={"content": filtered_content},
                                finish_reason=None
                            )]
                        )
                        
                        yield f"data: {stream_chunk.model_dump_json()}\n\n"
                        content_sent = True
        
        # Handle case where no role was sent (send at least role chunk)
        if not role_sent:
            # Send role chunk with empty content if we never got any assistant messages
            initial_chunk = ChatCompletionStreamResponse(
                id=request_id,
                model=request.model,
                choices=[StreamChoice(
                    index=0,
                    delta={"role": "assistant", "content": ""},
                    finish_reason=None
                )]
            )
            yield f"data: {initial_chunk.model_dump_json()}\n\n"
            role_sent = True
        
        # If we sent role but no content, send a minimal response
        if role_sent and not content_sent:
            fallback_chunk = ChatCompletionStreamResponse(
                id=request_id,
                model=request.model,
                choices=[StreamChoice(
                    index=0,
                    delta={"content": "I'm unable to provide a response at the moment."},
                    finish_reason=None
                )]
            )
            yield f"data: {fallback_chunk.model_dump_json()}\n\n"
        
        # Extract assistant response from all chunks for session storage
        if actual_session_id and chunks_buffer:
            assistant_content = claude_cli.parse_claude_message(chunks_buffer)
            if assistant_content:
                assistant_message = Message(role="assistant", content=assistant_content)
                session_manager.add_assistant_response(actual_session_id, assistant_message)
        
        # Send final chunk with finish reason
        final_chunk = ChatCompletionStreamResponse(
            id=request_id,
            model=request.model,
            choices=[StreamChoice(
                index=0,
                delta={},
                finish_reason="stop"
            )]
        )
        yield f"data: {final_chunk.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        error_chunk = {
            "error": {
                "message": str(e),
                "type": "streaming_error"
            }
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(
    request_body: ChatCompletionRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """OpenAI-compatible chat completions endpoint."""
    # Check FastAPI API key if configured
    await verify_api_key(request, credentials)
    
    # Validate Claude Code authentication
    auth_valid, auth_info = validate_claude_code_auth()
    
    if not auth_valid:
        error_detail = {
            "message": "Claude Code authentication failed",
            "errors": auth_info.get('errors', []),
            "method": auth_info.get('method', 'none'),
            "help": "Check /v1/auth/status for detailed authentication information"
        }
        raise HTTPException(
            status_code=503,
            detail=error_detail
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
                }
            )
        else:
            # Non-streaming response
            # Process messages with session management
            all_messages, actual_session_id = session_manager.process_messages(
                request_body.messages, request_body.session_id
            )
            
            logger.info(f"Chat completion: session_id={actual_session_id}, total_messages={len(all_messages)}")
            
            # Convert messages to prompt
            prompt, system_prompt = MessageAdapter.messages_to_prompt(all_messages)
            
            # Filter content
            prompt = MessageAdapter.filter_content(prompt)
            if system_prompt:
                system_prompt = MessageAdapter.filter_content(system_prompt)
            
            # Get Claude Code SDK options from request
            claude_options = request_body.to_claude_options()
            
            # Merge with Claude-specific headers
            if claude_headers:
                claude_options.update(claude_headers)
            
            # Validate model
            if claude_options.get('model'):
                ParameterValidator.validate_model(claude_options['model'])
            
            # Handle tools - disabled by default for OpenAI compatibility
            if not request_body.enable_tools:
                # Set disallowed_tools to all available tools to disable them
                disallowed_tools = ['Task', 'Bash', 'Glob', 'Grep', 'LS', 'exit_plan_mode', 
                                    'Read', 'Edit', 'MultiEdit', 'Write', 'NotebookRead', 
                                    'NotebookEdit', 'WebFetch', 'TodoRead', 'TodoWrite', 'WebSearch']
                claude_options['disallowed_tools'] = disallowed_tools
                claude_options['max_turns'] = 1  # Single turn for Q&A
                logger.info("Tools disabled (default behavior for OpenAI compatibility)")
            else:
                logger.info("Tools enabled by user request")
            
            # Collect all chunks
            chunks = []
            async for chunk in claude_cli.run_completion(
                prompt=prompt,
                system_prompt=system_prompt,
                model=claude_options.get('model'),
                max_turns=claude_options.get('max_turns', 10),
                allowed_tools=claude_options.get('allowed_tools'),
                disallowed_tools=claude_options.get('disallowed_tools'),
                stream=False
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
                choices=[Choice(
                    index=0,
                    message=Message(role="assistant", content=assistant_content),
                    finish_reason="stop"
                )],
                usage=Usage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens
                )
            )
            
            return response
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat completion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/models")
async def list_models():
    """List available models."""
    return {
        "object": "list",
        "data": [
            {"id": "claude-sonnet-4-20250514", "object": "model", "owned_by": "anthropic"},
            {"id": "claude-opus-4-20250514", "object": "model", "owned_by": "anthropic"},
            {"id": "claude-3-7-sonnet-20250219", "object": "model", "owned_by": "anthropic"},
            {"id": "claude-3-5-sonnet-20241022", "object": "model", "owned_by": "anthropic"},
            {"id": "claude-3-5-haiku-20241022", "object": "model", "owned_by": "anthropic"},
        ]
    }


@app.post("/v1/compatibility")
async def check_compatibility(request_body: ChatCompletionRequest):
    """Check OpenAI API compatibility for a request."""
    report = CompatibilityReporter.generate_compatibility_report(request_body)
    return {
        "compatibility_report": report,
        "claude_code_sdk_options": {
            "supported": [
                "model", "system_prompt", "max_turns", "allowed_tools", 
                "disallowed_tools", "permission_mode", "max_thinking_tokens",
                "continue_conversation", "resume", "cwd"
            ],
            "custom_headers": [
                "X-Claude-Max-Turns", "X-Claude-Allowed-Tools", 
                "X-Claude-Disallowed-Tools", "X-Claude-Permission-Mode",
                "X-Claude-Max-Thinking-Tokens"
            ]
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "claude-code-openai-wrapper"}


@app.post("/v1/debug/request")
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
                            "input": error.get("input")
                        }
                        for error in e.errors()
                    ]
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
                    "messages": [
                        {"role": "user", "content": "Hello, world!"}
                    ],
                    "stream": False
                }
            }
        }
        
    except Exception as e:
        return {
            "debug_info": {
                "error": f"Debug endpoint error: {str(e)}",
                "headers": dict(request.headers),
                "method": request.method,
                "url": str(request.url)
            }
        }


@app.get("/v1/auth/status")
async def get_auth_status():
    """Get Claude Code authentication status."""
    from auth import auth_manager
    
    auth_info = get_claude_code_auth_info()
    active_api_key = auth_manager.get_api_key()
    
    return {
        "claude_code_auth": auth_info,
        "server_info": {
            "api_key_required": bool(active_api_key),
            "api_key_source": "environment" if os.getenv("API_KEY") else ("runtime" if runtime_api_key else "none"),
            "version": "1.0.0"
        }
    }


@app.get("/v1/sessions/stats")
async def get_session_stats(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Get session manager statistics."""
    stats = session_manager.get_stats()
    return {
        "session_stats": stats,
        "cleanup_interval_minutes": session_manager.cleanup_interval_minutes,
        "default_ttl_hours": session_manager.default_ttl_hours
    }


@app.get("/v1/sessions")
async def list_sessions(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """List all active sessions."""
    sessions = session_manager.list_sessions()
    return SessionListResponse(sessions=sessions, total=len(sessions))


@app.get("/v1/sessions/{session_id}")
async def get_session(
    session_id: str,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Get information about a specific session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return session.to_session_info()


@app.delete("/v1/sessions/{session_id}")
async def delete_session(
    session_id: str,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Delete a specific session."""
    deleted = session_manager.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"message": f"Session {session_id} deleted successfully"}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Format HTTP exceptions as OpenAI-style errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.detail,
                "type": "api_error",
                "code": str(exc.status_code)
            }
        }
    )


def find_available_port(start_port: int = 8000, max_attempts: int = 10) -> int:
    """Find an available port starting from start_port."""
    import socket
    
    for port in range(start_port, start_port + max_attempts):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            result = sock.connect_ex(('127.0.0.1', port))
            if result != 0:  # Port is available
                return port
        except Exception:
            return port
        finally:
            sock.close()
    
    raise RuntimeError(f"No available ports found in range {start_port}-{start_port + max_attempts - 1}")


def run_server(port: int = None):
    """Run the server - used as Poetry script entry point."""
    import uvicorn
    import socket
    
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