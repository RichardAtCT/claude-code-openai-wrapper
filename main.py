import os
import json
import asyncio
import logging
import secrets
import string
import random
from typing import Optional, AsyncGenerator, Dict, Any, Tuple
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
from rate_limiter import limiter, rate_limit_exceeded_handler, get_rate_limit_for_endpoint, rate_limit_endpoint
from chat_mode import ChatMode, get_chat_mode_info

# Load environment variables
load_dotenv()

# Configure logging based on debug mode
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() in ('true', '1', 'yes', 'on')
VERBOSE = os.getenv('VERBOSE', 'false').lower() in ('true', '1', 'yes', 'on')
SHOW_PROGRESS_MARKERS = os.getenv('SHOW_PROGRESS_MARKERS', 'true').lower() in ('true', '1', 'yes', 'on')
SSE_KEEPALIVE_INTERVAL = int(os.getenv('SSE_KEEPALIVE_INTERVAL', '30'))  # seconds
CHAT_MODE_CLEANUP_SESSIONS = os.getenv('CHAT_MODE_CLEANUP_SESSIONS', 'true').lower() in ('true', '1', 'yes', 'on')

# Set logging level based on debug/verbose mode
log_level = logging.DEBUG if (DEBUG_MODE or VERBOSE) else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Claude SDK tool names - maintain this list to match SDK capabilities
ALL_CLAUDE_TOOLS = [
    'Task', 'Bash', 'Glob', 'Grep', 'LS', 'exit_plan_mode',
    'Read', 'Edit', 'MultiEdit', 'Write', 'NotebookRead',
    'NotebookEdit', 'WebFetch', 'TodoRead', 'TodoWrite', 'WebSearch'
]

# Global variable to store runtime-generated API key
runtime_api_key = None

# Check if chat mode is enabled
CHAT_MODE = ChatMode.is_enabled()


def create_error_response(error: Exception, context: str) -> Dict[str, Any]:
    """Create standardized error response."""
    logger.error(f"{context}: {type(error).__name__}: {str(error)}")
    return {
        "error": {
            "message": str(error),
            "type": type(error).__name__,
            "context": context
        }
    }
if CHAT_MODE:
    logger.info(f"🔒 Chat mode enabled - sessions disabled, sandboxed execution active, progress markers: {'enabled' if SHOW_PROGRESS_MARKERS else 'disabled'}")

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
        logger.debug(f"   SHOW_PROGRESS_MARKERS: {SHOW_PROGRESS_MARKERS}")
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
    
    # Start session cleanup task only if not in chat mode
    if not CHAT_MODE:
        session_manager.start_cleanup_task()
    else:
        logger.info("Session manager disabled in chat mode")
    
    yield
    
    # Cleanup on shutdown
    if not CHAT_MODE:
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

# Add rate limiting error handler
if limiter:
    app.state.limiter = limiter
    app.add_exception_handler(429, rate_limit_exceeded_handler)

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


def create_progress_chunk(request_id: str, model: str, content: str) -> str:
    """Create a progress indicator chunk in SSE format."""
    chunk = ChatCompletionStreamResponse(
        id=request_id,
        model=model,
        choices=[StreamChoice(
            index=0,
            delta={"content": content},
            finish_reason=None
        )]
    )
    return f"data: {chunk.model_dump_json()}\n\n"


def create_sse_keepalive() -> str:
    """Create an SSE comment for keep-alive. Comments are not shown to clients."""
    return ": keepalive\n\n"


async def create_keepalive_task(interval: int = None) -> Tuple[asyncio.Task, asyncio.Queue]:
    """Create a keepalive task that sends SSE comments periodically.
    
    Args:
        interval: Keepalive interval in seconds (defaults to SSE_KEEPALIVE_INTERVAL)
        
    Returns:
        Tuple of (keepalive_task, keepalive_queue)
    """
    if interval is None:
        interval = SSE_KEEPALIVE_INTERVAL
        
    keepalive_queue = asyncio.Queue()
    
    async def send_keepalives():
        """Send SSE keepalive comments periodically"""
        try:
            while True:
                await asyncio.sleep(interval)
                await keepalive_queue.put(create_sse_keepalive())
                logger.debug(f"Queued SSE keepalive comment")
        except asyncio.CancelledError:
            logger.debug("Keepalive task cancelled")
    
    keepalive_task = asyncio.create_task(send_keepalives())
    return keepalive_task, keepalive_queue


def extract_content_from_chunk(chunk: Dict[str, Any]) -> Optional[str]:
    """Extract text content from ANY SDK chunk format.
    Returns None only if the chunk genuinely has no content (not an error).
    """
    # Format 1: AssistantMessage with content array
    if "content" in chunk and isinstance(chunk["content"], list):
        text_parts = []
        for block in chunk["content"]:
            # Handle TextBlock objects from Claude Code SDK
            if hasattr(block, 'text'):
                text_parts.append(block.text)
            # Handle dictionary format
            elif isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        if text_parts:
            return "".join(text_parts)
    
    # Format 2: Old assistant message format
    if chunk.get("type") == "assistant" and "message" in chunk:
        message = chunk["message"]
        if isinstance(message, dict) and "content" in message:
            content = message["content"]
            # Recursively extract from message content
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if hasattr(block, 'text'):
                        text_parts.append(block.text)
                    elif isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                if text_parts:
                    return "".join(text_parts)
            elif isinstance(content, str):
                return content
    
    # Format 3: Result message
    if chunk.get("subtype") == "success" and "result" in chunk:
        return chunk["result"]
    
    # Format 4: Direct content string
    if "content" in chunk and isinstance(chunk["content"], str):
        return chunk["content"]
    
    # Format 5: Old format with type=assistant and direct content
    if chunk.get("type") == "assistant" and isinstance(chunk.get("content"), str):
        return chunk["content"]
    
    # Log unhandled format for investigation
    # Check both type and subtype fields for known non-content types
    chunk_type = chunk.get("type", "")
    chunk_subtype = chunk.get("subtype", "")
    known_non_content_types = ["init", "tool_use", "tool_result", "error", "progress"]
    known_non_content_subtypes = ["init", "error", "success"]
    
    if (chunk_type not in known_non_content_types and 
        chunk_subtype not in known_non_content_subtypes and
        (chunk_type or chunk_subtype)):  # Only warn if there's actually a type/subtype
        logger.warning(f"Unhandled chunk format for content extraction: {json.dumps(chunk)}")
    
    return None  # Only if chunk has no content field


def cleanup_claude_session(sandbox_dir: str, session_id: str) -> bool:
    """Delete Claude Code session file for chat mode requests.
    
    Args:
        sandbox_dir: The sandbox directory path (e.g., /private/var/folders/.../claude_chat_sandbox_xxx)
        session_id: The Claude session ID (UUID format)
        
    Returns:
        True if cleanup was successful, False otherwise
    """
    try:
        # Two places to check for session files:
        # 1. In the sandbox-specific project directory
        # 2. In the main wrapper project directory (if running from the wrapper directory)
        
        files_removed = []
        
        # First check sandbox-specific directory
        # Claude transforms the path by:
        # 1. Replacing all slashes with dashes
        # 2. Replacing underscores with dashes
        # 3. Prepending a dash to the whole path
        transformed_path = sandbox_dir.replace('/', '-').replace('_', '-')
        if not transformed_path.startswith('-'):
            transformed_path = '-' + transformed_path
            
        claude_project_dir = os.path.expanduser(f"~/.claude/projects/{transformed_path}")
        session_file = os.path.join(claude_project_dir, f"{session_id}.jsonl")
        
        if os.path.exists(session_file):
            os.remove(session_file)
            files_removed.append(session_file)
            logger.info(f"Deleted Claude session file: {session_file}")
            
            # Try to remove the project directory if empty
            try:
                if os.path.exists(claude_project_dir) and not os.listdir(claude_project_dir):
                    os.rmdir(claude_project_dir)
                    logger.info(f"Removed empty Claude project directory: {claude_project_dir}")
            except Exception as dir_err:
                logger.debug(f"Could not remove project directory (may not be empty): {dir_err}")
        
        # Also check the main wrapper project directory
        # This handles cases where Claude creates sessions in the current working directory
        wrapper_project_dir = os.path.expanduser("~/.claude/projects/-Users-val-claude-code-openai-wrapper")
        wrapper_session_file = os.path.join(wrapper_project_dir, f"{session_id}.jsonl")
        
        if os.path.exists(wrapper_session_file):
            # Check if this is a chat mode session by reading first line
            try:
                with open(wrapper_session_file, 'r') as f:
                    first_line = f.readline()
                    if first_line:
                        data = json.loads(first_line)
                        # Only remove if it's a Hello session or has our chat mode markers
                        content = data.get('message', {}).get('content', '')
                        if (content == 'Hello' or 
                            'digital black hole' in str(content) or
                            'sandboxed environment' in str(content)):
                            os.remove(wrapper_session_file)
                            files_removed.append(wrapper_session_file)
                            logger.info(f"Deleted wrapper project session: {wrapper_session_file}")
            except Exception as e:
                logger.debug(f"Could not check/remove wrapper session: {e}")
        
        if not files_removed:
            logger.debug(f"No session files found to remove for session {session_id}")
            
        return True
    except Exception as e:
        logger.error(f"Failed to cleanup Claude session {session_id}: {e}")
        return False


async def stream_final_content_only(
    request: ChatCompletionRequest,
    request_id: str,
    claude_headers: Optional[Dict[str, Any]] = None
) -> AsyncGenerator[str, None]:
    """Generate SSE formatted streaming response with only final content (no intermediate tool uses)."""
    sandbox_dir = None
    session_id = None  # Track Claude session ID for cleanup
    final_content = ""
    buffered_chunks = []
    
    try:
        # Get session info
        if CHAT_MODE:
            all_messages = request.messages
            actual_session_id = None
            logger.info("Chat mode active - sessions disabled")
        else:
            all_messages, actual_session_id = session_manager.process_messages(
                request.messages, request.session_id
            )
        
        # Convert messages to prompt
        logger.debug(f"Converting {len(all_messages)} messages to prompt")
        prompt, system_prompt = MessageAdapter.messages_to_prompt(all_messages)
        logger.debug(f"Converted prompt length: {len(prompt)}, system prompt: {len(system_prompt) if system_prompt else 0} chars")
        
        
        # Filter content for unsupported features (skip in chat mode to preserve XML)
        if not CHAT_MODE:
            prompt = MessageAdapter.filter_content(prompt)
            if system_prompt:
                system_prompt = MessageAdapter.filter_content(system_prompt)
        else:
            logger.debug("Chat mode: Skipping content filtering to preserve XML tool definitions")
        
        # Get Claude Code SDK options from request
        claude_options = request.to_claude_options()
        
        # Merge with Claude-specific headers if provided
        if claude_headers:
            claude_options.update(claude_headers)
        
        # Handle tools
        if CHAT_MODE:
            logger.info("Chat mode: using restricted tool set")
            claude_options['allowed_tools'] = ChatMode.get_allowed_tools()
            claude_options['disallowed_tools'] = None
            claude_options['max_turns'] = claude_options.get('max_turns', 10)
        elif not request.enable_tools:
            claude_options['disallowed_tools'] = ALL_CLAUDE_TOOLS
            claude_options['max_turns'] = 1
            logger.info("Tools disabled (default behavior for OpenAI compatibility)")
        
        # Buffer SDK responses - Direct streaming without async task wrapper
        sdk_chunks_received = 0
        consume_start_time = asyncio.get_event_loop().time()
        
        # Track assistant messages separately to find the LAST one
        assistant_messages = []  # List of (index, content) tuples
        current_assistant_content = ""
        in_assistant_message = False
        
        # Direct SDK streaming - no async task wrapper
        logger.debug("Starting SDK stream for buffering")
        logger.debug(f"SDK call parameters - prompt length: {len(prompt)}, system_prompt: {len(system_prompt) if system_prompt else 0}")
        logger.debug(f"SDK call parameters - model: {claude_options.get('model')}, max_turns: {claude_options.get('max_turns', 10)}")
        logger.debug(f"SDK call parameters - allowed_tools: {claude_options.get('allowed_tools')}")
        logger.debug(f"SDK call parameters - disallowed_tools: {claude_options.get('disallowed_tools')}")
        logger.debug(f"SDK call parameters - messages count: {len(all_messages)}")
        
        # Log the exact prompt being sent
        logger.info("=== SDK PROMPT START ===")
        logger.info(f"Prompt (first 500 chars): {prompt[:500]}...")
        if len(prompt) > 500:
            logger.info(f"Prompt (last 500 chars): ...{prompt[-500:]}")
        logger.info(f"System prompt: {system_prompt[:200] if system_prompt else 'None'}")
        logger.info("=== SDK PROMPT END ===")
        
        # CRITICAL: Log if we expect XML format
        expects_xml = False
        if CHAT_MODE and prompt:
            prompt_lower = prompt.lower()
            expects_xml = any([
                "tool uses are formatted" in prompt_lower,
                "<tool_name>" in prompt_lower,
                "xml-style tags" in prompt_lower,
                "<attempt_completion>" in prompt_lower
            ])
            if expects_xml:
                logger.info("📋 Expecting XML tool format in response based on prompt patterns")
        
        # Use a queue to communicate between SDK stream and main loop
        chunk_queue = asyncio.Queue()
        stream_complete = asyncio.Event()
        last_keepalive_time = asyncio.get_event_loop().time()
        
        # Task to consume the SDK stream and put chunks in queue
        async def sdk_consumer():
            try:
                logger.debug("Starting SDK stream consumer loop")
                async for chunk in claude_cli.run_completion(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model=claude_options.get('model'),
                    max_turns=claude_options.get('max_turns', 10),
                    allowed_tools=claude_options.get('allowed_tools'),
                    disallowed_tools=claude_options.get('disallowed_tools'),
                    stream=True,
                    messages=[msg.model_dump() if hasattr(msg, 'model_dump') else msg for msg in all_messages]
                ):
                    await chunk_queue.put(chunk)
                logger.debug("SDK stream consumer completed normally")
            except asyncio.CancelledError:
                logger.warning("SDK stream consumer was cancelled")
                raise
            except Exception as e:
                logger.error(f"SDK stream consumer error: {type(e).__name__}: {e}")
                logger.error(f"Exception traceback: ", exc_info=True)
                raise
            finally:
                stream_complete.set()
                await chunk_queue.put(None)  # Sentinel value
        
        # Start the SDK consumer task
        consumer_task = asyncio.create_task(sdk_consumer())
        
        # Main loop that processes chunks and sends keepalives
        try:
            queue_task = asyncio.create_task(chunk_queue.get())
            keepalive_task = asyncio.create_task(asyncio.sleep(SSE_KEEPALIVE_INTERVAL))
            stream_ended = False
            
            while not stream_ended:
                # Wait for either a chunk or keepalive timeout
                done, pending = await asyncio.wait(
                    [queue_task, keepalive_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                for task in done:
                    if task == queue_task:
                        # Got a chunk from the SDK
                        chunk = task.result()
                        if chunk is None:
                            # Stream ended
                            if keepalive_task and not keepalive_task.done():
                                keepalive_task.cancel()
                                try:
                                    await keepalive_task
                                except asyncio.CancelledError:
                                    pass
                            stream_ended = True
                            break
                        
                        # Process the chunk
                        sdk_chunks_received += 1
                        current_time = asyncio.get_event_loop().time()
                        
                        # Log detailed chunk information
                        chunk_type = chunk.get('type', 'unknown')
                        chunk_subtype = chunk.get('subtype', 'unknown')
                        logger.debug(f"SDK chunk #{sdk_chunks_received} received - type: {chunk_type}, subtype: {chunk_subtype}")
                        
                        # Log full chunk for debugging
                        if chunk_type == 'system' or chunk_subtype == 'init':
                            logger.debug(f"Full chunk data: {chunk}")
                        elif chunk_type == 'assistant' or 'content' in chunk:
                            # Log content preview
                            content_preview = str(chunk).replace('\n', '\\n')[:200]
                            logger.debug(f"Chunk content preview: {content_preview}...")
                        
                        buffered_chunks.append(chunk)
                        
                        # Extract sandbox directory and session ID from init message in chat mode
                        if CHAT_MODE and chunk_subtype == "init":
                            data = chunk.get("data", {})
                            if isinstance(data, dict):
                                if "cwd" in data and not sandbox_dir:
                                    sandbox_dir = data["cwd"]
                                    logger.debug(f"Tracked sandbox directory: {sandbox_dir}")
                                if "session_id" in data and not session_id:
                                    session_id = data["session_id"]
                                    logger.debug(f"Tracked Claude session ID: {session_id}")
                            # Also check top-level session_id
                            if "session_id" in chunk and not session_id:
                                session_id = chunk["session_id"]
                                logger.debug(f"Tracked Claude session ID from chunk: {session_id}")
                        
                        # More precise detection of assistant messages
                        # Check for content that could be assistant text
                        extracted_text = extract_content_from_chunk(chunk)
                        
                        # Only process if we actually extracted text content
                        if extracted_text is not None and extracted_text.strip():
                            # Check if this is genuinely an assistant message (not tool results, etc.)
                            is_assistant_chunk = (
                                chunk_type == "assistant" or 
                                (chunk_type != "tool_use" and chunk_type != "system" and chunk_type != "result" and
                                 "content" in chunk and extracted_text)
                            )
                            
                            if is_assistant_chunk:
                                if not in_assistant_message:
                                    # Start of a new assistant message
                                    if current_assistant_content:
                                        # Save the previous assistant message
                                        assistant_messages.append(current_assistant_content)
                                        logger.debug(f"Completed assistant message #{len(assistant_messages)}: {len(current_assistant_content)} chars")
                                    current_assistant_content = extracted_text
                                    in_assistant_message = True
                                    logger.debug(f"Started new assistant message from chunk #{sdk_chunks_received}")
                                else:
                                    # Continue current assistant message
                                    current_assistant_content += extracted_text
                                logger.debug(f"Assistant content from chunk #{sdk_chunks_received}: {len(extracted_text)} chars, type={chunk_type}")
                        
                        # Check for message boundaries (tool use, system messages, etc.)
                        elif chunk_type in ["tool_use", "system", "result"] or chunk_subtype in ["tool_use", "init", "success"]:
                            if in_assistant_message and current_assistant_content:
                                # End of current assistant message
                                assistant_messages.append(current_assistant_content)
                                logger.debug(f"Completed assistant message #{len(assistant_messages)} due to {chunk_type}/{chunk_subtype}: {len(current_assistant_content)} chars")
                                current_assistant_content = ""
                                in_assistant_message = False
                        
                        # Create new task to wait for next chunk
                        queue_task = asyncio.create_task(chunk_queue.get())
                    
                    elif task == keepalive_task:
                        # Keepalive timeout - send keepalive
                        current_time = asyncio.get_event_loop().time()
                        yield create_sse_keepalive()
                        last_keepalive_time = current_time
                        logger.debug(f"📡 Sent SSE keepalive during SDK buffering (after {sdk_chunks_received} chunks)")
                        
                        # Create new keepalive task
                        keepalive_task = asyncio.create_task(asyncio.sleep(SSE_KEEPALIVE_INTERVAL))
            
            logger.info(f"SDK stream completed: {sdk_chunks_received} chunks processed")
            
        except asyncio.CancelledError:
            logger.warning("SDK stream was cancelled")
            raise
        except Exception as e:
            logger.error(f"SDK stream error: {type(e).__name__}: {e}")
            logger.error(f"Exception traceback: ", exc_info=True)
            raise
        
        # Ensure consumer task is complete
        logger.debug("Waiting for consumer task to complete...")
        await consumer_task
        logger.debug("Consumer task completed")
        
        # Don't forget the last assistant message if stream ended while in one
        if in_assistant_message and current_assistant_content:
            assistant_messages.append(current_assistant_content)
            logger.debug(f"Final assistant message #{len(assistant_messages)}: {len(current_assistant_content)} chars")
        
        # Use only the LAST assistant message as the final content
        if assistant_messages:
            final_content = assistant_messages[-1]  # Get the last message
            logger.info(f"Final content extracted: {len(final_content)} chars (from {len(assistant_messages)} assistant messages)")
            
            # Debug logging for all assistant messages if multiple found
            if len(assistant_messages) > 1:
                logger.debug("Multiple assistant messages found. Details:")
                for i, msg in enumerate(assistant_messages):
                    preview = msg[:200] + "..." if len(msg) > 200 else msg
                    logger.debug(f"  Message #{i+1}: {len(msg)} chars - Preview: {preview}")
                logger.debug(f"Selected final message preview: {final_content[:200]}...")
        else:
            final_content = ""
            logger.warning("No assistant messages found in SDK stream")
        
        consume_end_time = asyncio.get_event_loop().time()
        total_consume_time = consume_end_time - consume_start_time
        logger.info(f"Stream buffering completed: {sdk_chunks_received} chunks in {total_consume_time:.2f}s")
        logger.info(f"Assistant messages found: {len(assistant_messages)}")
        logger.info(f"Final content length: {len(final_content)}")
        
        # Log buffered chunks summary
        chunk_types = {}
        for chunk in buffered_chunks:
            chunk_type = f"{chunk.get('type', 'unknown')}/{chunk.get('subtype', 'unknown')}"
            chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1
        logger.info(f"Chunk type summary: {chunk_types}")
        
        
        # Validate XML format if expected
        if expects_xml and final_content:
            # Check if response uses XML tool format
            has_xml_format = MessageAdapter.validate_xml_tool_response(final_content)
            
            if not has_xml_format:
                logger.error(f"❌ Expected XML tool format but got plain text response!")
                logger.error(f"Response preview: {final_content[:200]}...")
                # Note: We can't retry here without changing the architecture significantly
                # But at least we log it for debugging
            else:
                logger.info(f"✅ Response correctly uses XML tool format")
        
        # Now yield the final response
        if final_content:
            # Send role chunk
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
            
            # Filter content if not in chat mode
            if CHAT_MODE:
                filtered_content = final_content
            else:
                filtered_content = MessageAdapter.filter_content(final_content)
            
            # Send content chunk
            content_chunk = ChatCompletionStreamResponse(
                id=request_id,
                model=request.model,
                choices=[StreamChoice(
                    index=0,
                    delta={"content": filtered_content},
                    finish_reason=None
                )]
            )
            yield f"data: {content_chunk.model_dump_json()}\n\n"
        else:
            # No content - send empty response
            logger.warning(f"No content found after buffering {sdk_chunks_received} SDK chunks")
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
        
        # Add to session if needed
        if actual_session_id and final_content:
            assistant_message = Message(role="assistant", content=final_content)
            session_manager.add_assistant_response(actual_session_id, assistant_message)
        
        # Send final chunk
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
        logger.error(f"Error in stream_final_content_only: {e}")
        # Yield error
        error_chunk = {
            "error": {
                "message": str(e),
                "type": "streaming_error"
            }
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
    finally:
        # Ensure consumer task is complete
        if 'consumer_task' in locals():
            if not consumer_task.done():
                consumer_task.cancel()
                try:
                    await consumer_task
                except asyncio.CancelledError:
                    pass
        
        # Cleanup sandbox directory and session if in chat mode
        if CHAT_MODE and sandbox_dir:
            # First cleanup Claude session file
            # Try to get session_id from claude_cli if we didn't get it from messages
            if not session_id and hasattr(claude_cli, 'get_last_session_id'):
                session_id = claude_cli.get_last_session_id()
                if session_id:
                    logger.debug(f"Got session ID from claude_cli: {session_id}")
            
            if session_id and CHAT_MODE_CLEANUP_SESSIONS:
                try:
                    cleanup_claude_session(sandbox_dir, session_id)
                except Exception as e:
                    logger.error(f"Failed to cleanup Claude session: {e}")
            elif session_id and not CHAT_MODE_CLEANUP_SESSIONS:
                logger.debug(f"Session cleanup disabled - session {session_id} retained")
            
            # Then cleanup sandbox directory
            try:
                ChatMode.cleanup_sandbox(sandbox_dir)
                logger.debug(f"Cleaned up sandbox directory: {sandbox_dir}")
            except Exception as e:
                logger.error(f"Failed to cleanup sandbox: {e}")


async def stream_with_progress_injection(
    original_stream: AsyncGenerator[str, None],
    request_id: str,
    model: str
) -> AsyncGenerator[str, None]:
    """Inject progress indicators during stream pauses without modifying the stream logic."""
    
    # Use a queue to communicate between SDK stream and progress injection
    chunk_queue = asyncio.Queue()
    stream_complete = asyncio.Event()
    
    # Task to consume the original stream and put chunks in queue
    async def stream_consumer():
        try:
            async for chunk in original_stream:
                await chunk_queue.put(chunk)
        finally:
            stream_complete.set()
            await chunk_queue.put(None)  # Sentinel value
    
    # Create a merged stream that combines queued chunks and progress indicators
    async def merged_stream():
        # Progress messages - universal rotating circles
        progress_messages = [
            "◐", "◓", "◑", "◒",  # Rotating circles
            "◐", "◓", "◑", "◒",  # Repeat pattern
            "◐", "◓", "◑", "◒",  # Continue
            "◐", "◓", "◑", "◒"   # Total 16 entries
        ]
        
        progress_sent = False
        any_content_sent = False  # Track if ANY content has been sent
        need_newline_before_progress = False  # Track if we need newline before next progress
        showing_hourglass = True  # Track if we're showing the initial hourglass
        last_activity_time = asyncio.get_event_loop().time()
        current_message_index = 0  # Will start at 0 after hourglass phase
        current_dots = 0  # Track number of dots (0-3)
        last_dot_time = 0  # Track when we last added a dot
        last_message_time = 0  # Track when we last changed message
        last_keepalive_time = 0  # Track when we last sent a keepalive
        
        # Timing configuration
        BASE_DOT_INTERVAL = 3.0  # Base interval for dots
        BASE_MESSAGE_INTERVAL = 15.0  # Base interval for message changes
        INITIAL_DELAY = 6.0  # Wait 6s before first progress
        MAX_DOTS = 3  # Maximum dots per message
        BACKOFF_MULTIPLIER = 1.2  # Exponential backoff multiplier
        BACKOFF_START_AFTER = 3  # Start backoff after this many updates
        MAX_DOT_INTERVAL = 20.0  # Maximum dot interval (cap)
        MAX_MESSAGE_INTERVAL = 60.0  # Maximum message interval (cap)
        
        # Dynamic intervals
        current_dot_interval = BASE_DOT_INTERVAL
        current_message_interval = BASE_MESSAGE_INTERVAL
        update_count = 0  # Track total updates for backoff
        
        # Create tasks for queue and progress
        queue_task = asyncio.create_task(chunk_queue.get())
        progress_task = asyncio.create_task(asyncio.sleep(INITIAL_DELAY))
        
        while True:
            # Wait for either a chunk or timeout
            done, pending = await asyncio.wait(
                [queue_task, progress_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Handle completed tasks
            for task in done:
                if task == queue_task:
                    # Got a chunk from the original stream
                    chunk = task.result()
                    if chunk is None:
                        # Stream ended - clean up progress task
                        if progress_task and not progress_task.done():
                            progress_task.cancel()
                            try:
                                await progress_task
                            except asyncio.CancelledError:
                                pass
                        return
                    
                    # Check if this is actual text content or just tool use
                    is_text_content = False
                    if "data: " in chunk:
                        try:
                            # Parse the SSE data
                            data_line = chunk.split("data: ", 1)[1].strip()
                            if data_line and data_line != "[DONE]":
                                import json
                                data = json.loads(data_line)
                                # Check if it has actual text content
                                if "choices" in data and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    if "content" in delta and delta["content"]:
                                        is_text_content = True
                        except:
                            pass
                    
                    # Only reset progress state for actual text content
                    if is_text_content:
                        logger.debug(f"Progress injection: Received text content, resetting progress state")
                        
                        # If we showed progress and now getting real content, add spacing
                        if progress_sent:
                            # Send a double newline chunk before the actual content
                            spacing_chunk = create_progress_chunk(request_id, model, "\n\n")
                            yield spacing_chunk
                            logger.debug("Progress injection: Added spacing before content")
                        
                        last_activity_time = asyncio.get_event_loop().time()
                        progress_sent = False
                        showing_hourglass = True  # Reset to hourglass for next pause
                        current_message_index = 0  # Will start at 0 after hourglass
                        current_dots = 0
                        last_dot_time = 0
                        last_message_time = 0
                        last_keepalive_time = asyncio.get_event_loop().time()  # Reset keepalive timer
                        any_content_sent = True  # Mark that we've seen content
                        need_newline_before_progress = True  # Need newline before next progress
                        # Reset intervals when we get actual content
                        current_dot_interval = BASE_DOT_INTERVAL
                        current_message_interval = BASE_MESSAGE_INTERVAL
                        update_count = 0
                    else:
                        logger.debug(f"Progress injection: Received non-text chunk (tool use or metadata)")
                    
                    # Cancel existing progress task to prevent it from firing
                    if progress_task and not progress_task.done():
                        progress_task.cancel()
                        try:
                            await progress_task
                        except asyncio.CancelledError:
                            pass
                    
                    # Yield the chunk
                    yield chunk
                    
                    # Create new task for next chunk
                    queue_task = asyncio.create_task(chunk_queue.get())
                    # Restart progress monitoring with dynamic interval
                    elapsed_time = asyncio.get_event_loop().time() - last_activity_time
                    if elapsed_time < 30:
                        check_interval = 0.5
                    elif elapsed_time < 120:
                        check_interval = 1.0
                    else:
                        check_interval = 2.0
                    progress_task = asyncio.create_task(asyncio.sleep(check_interval))
                    
                elif task == progress_task:
                    # Progress timeout fired - check what we need to update
                    current_time = asyncio.get_event_loop().time()
                    time_since_start = current_time - last_activity_time
                    
                    # Only proceed if we've waited the initial delay
                    if time_since_start >= INITIAL_DELAY:
                        time_since_last_dot = current_time - last_dot_time if last_dot_time > 0 else float('inf')
                        time_since_last_message = current_time - last_message_time if last_message_time > 0 else float('inf')
                        
                        # Determine what to update
                        should_update = False
                        update_message = False
                        
                        # Special handling for hourglass phase
                        if showing_hourglass and current_dots >= MAX_DOTS:
                            # Check if enough time has passed for a message change
                            if time_since_start >= BASE_MESSAGE_INTERVAL:
                                # Transition from hourglass to first circle
                                showing_hourglass = False
                                current_message_index = 0
                                current_dots = 0
                                last_message_time = current_time
                                last_dot_time = current_time
                                should_update = True
                                update_message = True
                                logger.debug("Progress injection: Transitioning from hourglass to circles")
                        # Check if we need to change the message (only when not showing hourglass and have all dots)
                        elif not showing_hourglass and current_dots >= MAX_DOTS:
                            # Calculate time since last message change
                            time_since_message_change = current_time - last_message_time if last_message_time > 0 else float('inf')
                            if time_since_message_change >= current_message_interval and current_message_index < len(progress_messages) - 1:
                                current_message_index += 1
                                current_dots = 0  # Reset dots when changing message
                                last_message_time = current_time
                                last_dot_time = current_time
                                should_update = True
                                update_message = True
                                
                                # Apply exponential backoff to message interval
                                if current_message_index >= BACKOFF_START_AFTER:
                                    current_message_interval = min(current_message_interval * BACKOFF_MULTIPLIER, MAX_MESSAGE_INTERVAL)
                                
                                logger.debug(f"Progress injection: Changing to message {current_message_index}, next interval: {current_message_interval:.1f}s")
                        # Check if we need to add a dot
                        if time_since_last_dot >= current_dot_interval and current_dots < MAX_DOTS and not update_message:
                            current_dots += 1
                            last_dot_time = current_time
                            should_update = True
                            
                            # Apply exponential backoff to dot interval
                            update_count += 1
                            if update_count >= BACKOFF_START_AFTER:
                                current_dot_interval = min(current_dot_interval * BACKOFF_MULTIPLIER, MAX_DOT_INTERVAL)
                            
                            logger.debug(f"Progress injection: Adding dot {current_dots}, next interval: {current_dot_interval:.1f}s")
                        # After exhausting all messages, continue with repeating pattern
                        elif not showing_hourglass and current_message_index >= len(progress_messages) - 1 and current_dots >= MAX_DOTS:
                            # Check if enough time for cycling back
                            time_since_message_change = current_time - last_message_time if last_message_time > 0 else float('inf')
                            if time_since_message_change >= current_message_interval:
                                # Cycle back to start of messages
                                current_message_index = 0
                                current_dots = 0
                                last_message_time = current_time
                                last_dot_time = current_time
                                should_update = True
                                update_message = True
                                logger.debug("Progress injection: Cycling back to first message")
                        # Initial message
                        elif not progress_sent:
                            last_message_time = current_time
                            last_dot_time = current_time
                            should_update = True
                            logger.debug("Progress injection: Sending initial message")
                        
                        if should_update:
                            # Determine what to send
                            if not progress_sent and not any_content_sent:
                                # First message at start of stream - show hourglass
                                formatted_message = "⏳"
                            elif not progress_sent:
                                # First message but there's already content - need newline with hourglass
                                formatted_message = "\n⏳"
                            elif update_message:
                                # Message change - send new circle message without space
                                message_text = progress_messages[current_message_index]
                                formatted_message = message_text
                            else:
                                # Just adding a dot - send only the dot
                                formatted_message = "·"
                            
                            # Check if we need to add a newline before progress
                            if need_newline_before_progress:
                                formatted_message = "\n" + formatted_message
                                need_newline_before_progress = False
                            
                            progress_chunk = create_progress_chunk(request_id, model, formatted_message)
                            yield progress_chunk
                            progress_sent = True
                            
                            # Increment update count for backoff tracking
                            if not should_update or update_message:
                                update_count += 1
                        else:
                            # No visible progress update needed - check if we need keepalive
                            time_since_keepalive = current_time - last_keepalive_time if last_keepalive_time > 0 else float('inf')
                            if time_since_keepalive >= SSE_KEEPALIVE_INTERVAL:
                                # Send invisible keepalive comment
                                yield create_sse_keepalive()
                                last_keepalive_time = current_time
                                logger.debug("Progress injection: Sent SSE keepalive comment")
                    
                    # Schedule next check with dynamic frequency
                    elapsed_time = current_time - last_activity_time
                    if elapsed_time < 30:
                        check_interval = 0.5  # Fast checks initially
                    elif elapsed_time < 120:
                        check_interval = 1.0  # Slower after 30s
                    else:
                        check_interval = 2.0  # Even slower after 2 minutes
                    
                    progress_task = asyncio.create_task(asyncio.sleep(check_interval))
            
            # Cancel any pending tasks if needed
            for task in pending:
                if task == progress_task and queue_task in done:
                    # Cancel progress if we got a chunk
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    # Resume checking with dynamic interval
                    elapsed_time = asyncio.get_event_loop().time() - last_activity_time
                    if elapsed_time < 30:
                        check_interval = 0.5
                    elif elapsed_time < 120:
                        check_interval = 1.0
                    else:
                        check_interval = 2.0
                    progress_task = asyncio.create_task(asyncio.sleep(check_interval))
    
    # Start the stream consumer task
    consumer_task = asyncio.create_task(stream_consumer())
    
    try:
        # Use the merged stream
        async for chunk in merged_stream():
            yield chunk
    finally:
        # Cancel consumer task if still running
        if not consumer_task.done():
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass
        
        # Ensure stream is complete
        stream_complete.set()
        
        logger.debug("Progress injection: Monitoring stopped")


async def generate_streaming_response(
    request: ChatCompletionRequest,
    request_id: str,
    claude_headers: Optional[Dict[str, Any]] = None
) -> AsyncGenerator[str, None]:
    """Generate SSE formatted streaming response."""
    sandbox_dir = None  # Track sandbox for cleanup
    session_id = None  # Track Claude session ID for cleanup
    try:
        # In chat mode, skip session management
        if CHAT_MODE:
            all_messages = request.messages  # Keep as Message objects
            actual_session_id = None
            logger.info("Chat mode active - sessions disabled")
        else:
            # Process messages with session management
            all_messages, actual_session_id = session_manager.process_messages(
                request.messages, request.session_id
            )
        
        # Convert messages to prompt
        logger.debug(f"Converting {len(all_messages)} messages to prompt")
        for i, msg in enumerate(all_messages):
            msg_preview = str(msg)[:200] + "..." if len(str(msg)) > 200 else str(msg)
            logger.debug(f"Message {i}: {msg_preview}")
        prompt, system_prompt = MessageAdapter.messages_to_prompt(all_messages)
        logger.debug(f"Converted prompt length: {len(prompt)}, system prompt: {len(system_prompt) if system_prompt else 0} chars")
        
        # Filter content for unsupported features (skip in chat mode to preserve XML)
        if not CHAT_MODE:
            prompt = MessageAdapter.filter_content(prompt)
            if system_prompt:
                system_prompt = MessageAdapter.filter_content(system_prompt)
        else:
            logger.debug("Chat mode: Skipping content filtering to preserve XML tool definitions")
        
        # Get Claude Code SDK options from request
        claude_options = request.to_claude_options()
        
        # Merge with Claude-specific headers if provided
        if claude_headers:
            claude_options.update(claude_headers)
        
        # Validate model
        if claude_options.get('model'):
            ParameterValidator.validate_model(claude_options['model'])
        
        # Handle tools - disabled by default for OpenAI compatibility
        if CHAT_MODE:
            # Chat mode overrides all tool settings
            logger.info("Chat mode: using restricted tool set")
            claude_options['allowed_tools'] = ChatMode.get_allowed_tools()
            claude_options['disallowed_tools'] = None
            claude_options['max_turns'] = claude_options.get('max_turns', 10)
        elif not request.enable_tools:
            # Set disallowed_tools to all available tools to disable them
            claude_options['disallowed_tools'] = ALL_CLAUDE_TOOLS
            claude_options['max_turns'] = 1  # Single turn for Q&A
            logger.info("Tools disabled (default behavior for OpenAI compatibility)")
        else:
            logger.info("Tools enabled by user request")
        
        # Run Claude Code with timeout protection
        chunks_buffer = []
        role_sent = False  # Track if we've sent the initial role chunk
        content_sent = False  # Track if we've sent any content
        
        # Create a wrapper for the SDK stream
        
        async def stream_with_timeout():
            """Wrap SDK stream with timeout detection"""
            try:
                async for chunk in claude_cli.run_completion(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model=claude_options.get('model'),
                    max_turns=claude_options.get('max_turns', 10),
                    allowed_tools=claude_options.get('allowed_tools'),
                    disallowed_tools=claude_options.get('disallowed_tools'),
                    stream=True,
                    messages=[msg.model_dump() if hasattr(msg, 'model_dump') else msg for msg in all_messages]  # Convert to dicts for format detection
                ):
                    yield chunk
            except asyncio.CancelledError:
                logger.warning("SDK stream was cancelled")
                raise
            except Exception as e:
                logger.error(f"SDK stream error: {type(e).__name__}: {e}")
                # Yield error as SDK format
                yield {
                    "type": "result",
                    "subtype": "error_during_execution",
                    "is_error": True,
                    "error_message": f"Stream error: {str(e)}"
                }
        
        stream_iter = stream_with_timeout()
        
        logger.debug("Starting SDK stream iteration")
        stream_start_time = asyncio.get_event_loop().time()
        chunk_count = 0
        last_chunk_time = stream_start_time
        
        async for chunk in stream_iter:
            chunk_count += 1
            current_time = asyncio.get_event_loop().time()
            time_since_last = current_time - last_chunk_time
            time_since_start = current_time - stream_start_time
            last_chunk_time = current_time
            
            # Log chunk info with timing
            chunk_type = chunk.get('type', 'unknown')
            chunk_subtype = chunk.get('subtype', '')
            logger.debug(f"SDK chunk #{chunk_count} at {time_since_start:.2f}s (delta: {time_since_last:.2f}s) - type: {chunk_type}, subtype: {chunk_subtype}")
            
            chunks_buffer.append(chunk)
            
            # Extract sandbox directory and session ID from init message in chat mode
            if CHAT_MODE and chunk.get("subtype") == "init":
                data = chunk.get("data", {})
                if isinstance(data, dict):
                    if "cwd" in data and not sandbox_dir:
                        sandbox_dir = data["cwd"]
                        logger.debug(f"Tracked sandbox directory: {sandbox_dir}")
                    if "session_id" in data and not session_id:
                        session_id = data["session_id"]
                        logger.debug(f"Tracked Claude session ID: {session_id}")
                # Also check top-level session_id
                if "session_id" in chunk and not session_id:
                    session_id = chunk["session_id"]
                    logger.debug(f"Tracked Claude session ID from chunk: {session_id}")
            
            # Extract content using unified method
            # Skip result messages to avoid duplication - they contain the full response
            if chunk.get("subtype") == "success":
                logger.debug("Skipping result message to avoid content duplication")
                continue
                
            extracted_text = extract_content_from_chunk(chunk)
            
            if extracted_text is not None:
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
                
                # Filter content if not in chat mode
                if CHAT_MODE:
                    filtered_text = extracted_text
                else:
                    filtered_text = MessageAdapter.filter_content(extracted_text)
                
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
        
        stream_end_time = asyncio.get_event_loop().time()
        total_stream_time = stream_end_time - stream_start_time
        logger.debug(f"SDK stream completed after {chunk_count} chunks in {total_stream_time:.2f}s")
        
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
        
        # If we sent role but no content, that's a genuine empty response
        if role_sent and not content_sent:
            logger.debug("Empty response - role sent but no content extracted")
        
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
    finally:
        # Cleanup sandbox directory and session if in chat mode
        if CHAT_MODE and sandbox_dir:
            # First cleanup Claude session file
            # Try to get session_id from claude_cli if we didn't get it from messages
            if not session_id and hasattr(claude_cli, 'get_last_session_id'):
                session_id = claude_cli.get_last_session_id()
                if session_id:
                    logger.debug(f"Got session ID from claude_cli: {session_id}")
            
            if session_id and CHAT_MODE_CLEANUP_SESSIONS:
                try:
                    cleanup_claude_session(sandbox_dir, session_id)
                except Exception as e:
                    logger.error(f"Failed to cleanup Claude session: {e}")
            elif session_id and not CHAT_MODE_CLEANUP_SESSIONS:
                logger.debug(f"Session cleanup disabled - session {session_id} retained")
            
            # Then cleanup sandbox directory
            try:
                ChatMode.cleanup_sandbox(sandbox_dir)
                logger.debug(f"Cleaned up sandbox directory: {sandbox_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup sandbox {sandbox_dir}: {e}")


@app.post("/v1/chat/completions")
@rate_limit_endpoint("chat")
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
            if CHAT_MODE and SHOW_PROGRESS_MARKERS:
                # In chat mode with progress markers enabled
                logger.info("Chat mode: Wrapping stream with progress indicators")
                stream_generator = stream_with_progress_injection(
                    generate_streaming_response(request_body, request_id, claude_headers),
                    request_id,
                    request_body.model
                )
            elif not SHOW_PROGRESS_MARKERS:
                # Progress markers disabled - show only final content
                logger.info("Progress markers disabled: Streaming final content only")
                stream_generator = stream_final_content_only(request_body, request_id, claude_headers)
            else:
                # Normal mode - all chunks without progress injection
                stream_generator = generate_streaming_response(request_body, request_id, claude_headers)
            
            return StreamingResponse(
                stream_generator,
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        else:
            # Non-streaming response
            # In chat mode, skip session management
            if CHAT_MODE:
                all_messages = request_body.messages  # Keep as Message objects
                actual_session_id = None
                logger.info("Chat mode active - sessions disabled")
            else:
                # Process messages with session management
                all_messages, actual_session_id = session_manager.process_messages(
                    request_body.messages, request_body.session_id
                )
                
                logger.info(f"Chat completion: session_id={actual_session_id}, total_messages={len(all_messages)}")
            
            # Convert messages to prompt
            prompt, system_prompt = MessageAdapter.messages_to_prompt(all_messages)
            
            # Filter content (skip in chat mode to preserve XML)
            if not CHAT_MODE:
                prompt = MessageAdapter.filter_content(prompt)
                if system_prompt:
                    system_prompt = MessageAdapter.filter_content(system_prompt)
            else:
                logger.debug("Chat mode: Skipping content filtering to preserve XML tool definitions")
            
            # Get Claude Code SDK options from request
            claude_options = request_body.to_claude_options()
            
            # Merge with Claude-specific headers
            if claude_headers:
                claude_options.update(claude_headers)
            
            # Validate model
            if claude_options.get('model'):
                ParameterValidator.validate_model(claude_options['model'])
            
            # Handle tools - disabled by default for OpenAI compatibility
            if CHAT_MODE:
                # Chat mode overrides all tool settings
                logger.info("Chat mode: using restricted tool set")
                claude_options['allowed_tools'] = ChatMode.get_allowed_tools()
                claude_options['disallowed_tools'] = None
                claude_options['max_turns'] = claude_options.get('max_turns', 10)
            elif not request_body.enable_tools:
                # Set disallowed_tools to all available tools to disable them
                claude_options['disallowed_tools'] = ALL_CLAUDE_TOOLS
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
                stream=False,
                messages=[msg.model_dump() if hasattr(msg, 'model_dump') else msg for msg in all_messages]  # Convert to dicts for format detection
            ):
                chunks.append(chunk)
            
            # Extract assistant message
            raw_assistant_content = claude_cli.parse_claude_message(chunks)
            
            if not raw_assistant_content:
                raise HTTPException(status_code=500, detail="No response from Claude Code")
            
            # Filter out tool usage and thinking blocks (skip in chat mode)
            if CHAT_MODE:
                # In chat mode, preserve the exact response format
                assistant_content = raw_assistant_content
                logger.debug(f"Chat mode: Preserving raw response format, length: {len(assistant_content)}")
            else:
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
async def list_models(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """List available models."""
    # Check FastAPI API key if configured
    await verify_api_key(request, credentials)
    
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
@rate_limit_endpoint("health")
async def health_check(request: Request):
    """Health check endpoint."""
    return {"status": "healthy", "service": "claude-code-openai-wrapper"}


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
@rate_limit_endpoint("auth")
async def get_auth_status(request: Request):
    """Get Claude Code authentication status."""
    from auth import auth_manager
    
    auth_info = get_claude_code_auth_info()
    active_api_key = auth_manager.get_api_key()
    
    return {
        "claude_code_auth": auth_info,
        "server_info": {
            "api_key_required": bool(active_api_key),
            "api_key_source": "environment" if os.getenv("API_KEY") else ("runtime" if runtime_api_key else "none"),
            "version": "1.0.0",
            "chat_mode": get_chat_mode_info(),
            "progress_markers_enabled": SHOW_PROGRESS_MARKERS
        }
    }


@app.get("/v1/sessions/stats")
async def get_session_stats(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Get session manager statistics."""
    if CHAT_MODE:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "Sessions are disabled in chat mode. Conversation continuity should be handled by your chat client.",
                    "type": "invalid_request_error",
                    "code": "chat_mode_active"
                }
            }
        )
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
    if CHAT_MODE:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "Sessions are disabled in chat mode. Conversation continuity should be handled by your chat client.",
                    "type": "invalid_request_error",
                    "code": "chat_mode_active"
                }
            }
        )
    sessions = session_manager.list_sessions()
    return SessionListResponse(sessions=sessions, total=len(sessions))


@app.get("/v1/sessions/{session_id}")
async def get_session(
    session_id: str,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Get information about a specific session."""
    if CHAT_MODE:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "Sessions are disabled in chat mode. Conversation continuity should be handled by your chat client.",
                    "type": "invalid_request_error",
                    "code": "chat_mode_active"
                }
            }
        )
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
    if CHAT_MODE:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "Sessions are disabled in chat mode. Conversation continuity should be handled by your chat client.",
                    "type": "invalid_request_error",
                    "code": "chat_mode_active"
                }
            }
        )
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