# Claude Code OpenAI API Wrapper

An OpenAI API-compatible wrapper for Claude Code, allowing you to use Claude Code with any OpenAI client library. **Now powered by the official Claude Code Python SDK** with enhanced authentication and features.

## Status

🎉 **Production Ready** - All core features working and tested:
- ✅ Chat completions endpoint with **official Claude Code Python SDK**
- ✅ Streaming and non-streaming responses  
- ✅ Full OpenAI SDK compatibility
- ✅ **Multi-provider authentication** (API key, Bedrock, Vertex AI, CLI auth)
- ✅ **System prompt support** via SDK options
- ✅ Model selection support with validation
- ✅ **Fast by default** - Tools disabled for OpenAI compatibility (5-10x faster)
- ✅ Optional tool usage (Read, Write, Bash, etc.) when explicitly enabled
- ✅ **Real-time cost and token tracking** from SDK
- ✅ **Session continuity** with conversation history across requests 🆕
- ✅ **Session management endpoints** for full session control 🆕
- ✅ Health, auth status, and models endpoints
- ✅ **Development mode** with auto-reload

## Features

### 🔥 **Core API Compatibility**
- OpenAI-compatible `/v1/chat/completions` endpoint
- Support for both streaming and non-streaming responses
- Compatible with OpenAI Python SDK and all OpenAI client libraries
- Automatic model validation and selection

### 🛠 **Claude Code SDK Integration**
- **Official Claude Code Python SDK** integration (v0.0.14)
- **Real-time cost tracking** - actual costs from SDK metadata
- **Accurate token counting** - input/output tokens from SDK
- **Session management** - proper session IDs and continuity
- **Enhanced error handling** with detailed authentication diagnostics

### 🔐 **Multi-Provider Authentication**
- **Automatic detection** of authentication method
- **Claude CLI auth** - works with existing `claude auth` setup
- **Direct API key** - `ANTHROPIC_API_KEY` environment variable
- **AWS Bedrock** - enterprise authentication with AWS credentials
- **Google Vertex AI** - GCP authentication support

### ⚡ **Advanced Features**
- **System prompt support** via SDK options
- **Optional tool usage** - Enable Claude Code tools (Read, Write, Bash, etc.) when needed
- **Fast default mode** - Tools disabled by default for OpenAI API compatibility
- **Development mode** with auto-reload (`uvicorn --reload`)
- **Interactive API key protection** - Optional security with auto-generated tokens
- **Comprehensive logging** and debugging capabilities

## Quick Start

Get started in under 2 minutes:

```bash
# 1. Install Claude Code CLI (if not already installed)
npm install -g @anthropic-ai/claude-code

# 2. Authenticate (choose one method)
claude auth login  # Recommended for development
# OR set: export ANTHROPIC_API_KEY=your-api-key

# 3. Clone and setup the wrapper
git clone https://github.com/RichardAtCT/claude-code-openai-wrapper
cd claude-code-openai-wrapper
poetry install

# 4. Start the server
poetry run uvicorn main:app --reload --port 8000

# 5. Test it works
poetry run python test_endpoints.py
```

🎉 **That's it!** Your OpenAI-compatible Claude Code API is running on `http://localhost:8000`

## Prerequisites

1. **Claude Code CLI**: Install Claude Code CLI
   ```bash
   # Install Claude Code (follow Anthropic's official guide)
   npm install -g @anthropic-ai/claude-code
   ```

2. **Authentication**: Choose one method:
   - **Option A**: Authenticate via CLI (Recommended for development)
     ```bash
     claude auth login
     ```
   - **Option B**: Set environment variable
     ```bash
     export ANTHROPIC_API_KEY=your-api-key
     ```
   - **Option C**: Use AWS Bedrock or Google Vertex AI (see Configuration section)

3. **Python 3.10+**: Required for the server

4. **Poetry**: For dependency management
   ```bash
   # Install Poetry (if not already installed)
   curl -sSL https://install.python-poetry.org | python3 -
   ```

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/RichardAtCT/claude-code-openai-wrapper
   cd claude-code-openai-wrapper
   ```

2. Install dependencies with Poetry:
   ```bash
   poetry install
   ```

   This will create a virtual environment and install all dependencies.

3. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your preferences
   ```

## Configuration

Edit the `.env` file:

```env
# Claude CLI path (usually just "claude")
CLAUDE_CLI_PATH=claude

# Optional API key for client authentication
# If not set, server will prompt for interactive API key protection on startup
# API_KEY=your-optional-api-key

# Server port
PORT=8000

# Timeout in milliseconds
MAX_TIMEOUT=600000

# CORS origins
CORS_ORIGINS=["*"]
```

### 🔐 **API Security Configuration**

The server supports **interactive API key protection** for secure remote access:

1. **No API key set**: Server prompts "Enable API key protection? (y/N)" on startup
   - Choose **No** (default): Server runs without authentication
   - Choose **Yes**: Server generates and displays a secure API key

2. **Environment API key set**: Uses the configured `API_KEY` without prompting

```bash
# Example: Interactive protection enabled
poetry run python main.py

# Output:
# ============================================================
# 🔐 API Endpoint Security Configuration
# ============================================================
# Would you like to protect your API endpoint with an API key?
# This adds a security layer when accessing your server remotely.
# 
# Enable API key protection? (y/N): y
# 
# 🔑 API Key Generated!
# ============================================================
# API Key: Xf8k2mN9-vLp3qR5_zA7bW1cE4dY6sT0uI
# ============================================================
# 📋 IMPORTANT: Save this key - you'll need it for API calls!
#    Example usage:
#    curl -H "Authorization: Bearer Xf8k2mN9-vLp3qR5_zA7bW1cE4dY6sT0uI" \
#         http://localhost:8000/v1/models
# ============================================================
```

**Perfect for:**
- 🏠 **Local development** - No authentication needed
- 🌐 **Remote access** - Secure with generated tokens
- 🔒 **VPN/Tailscale** - Add security layer for remote endpoints

## Running the Server

1. Verify Claude Code is installed and working:
   ```bash
   claude --version
   claude --print --model claude-3-5-haiku-20241022 "Hello"  # Test with fastest model
   ```

2. Start the server:

   **Development mode (recommended - auto-reloads on changes):**
   ```bash
   poetry run uvicorn main:app --reload --port 8000
   ```

   **Production mode:**
   ```bash
   poetry run python main.py
   ```

   **Port Options for production mode:**
   - Default: Uses port 8000 (or PORT from .env)
   - If port is in use, automatically finds next available port
   - Specify custom port: `poetry run python main.py 9000`
   - Set in environment: `PORT=9000 poetry run python main.py`

## Usage Examples

### Using curl

```bash
# Basic chat completion (no auth)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [
      {"role": "user", "content": "What is 2 + 2?"}
    ]
  }'

# With API key protection (when enabled)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-generated-api-key" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [
      {"role": "user", "content": "Write a Python hello world script"}
    ],
    "stream": true
  }'
```

### Using OpenAI Python SDK

```python
from openai import OpenAI

# Configure client (automatically detects auth requirements)
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-api-key-if-required"  # Only needed if protection enabled
)

# Alternative: Let examples auto-detect authentication
# The wrapper's example files automatically check server auth status

# Basic chat completion
response = client.chat.completions.create(
    model="claude-3-5-sonnet-20241022",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What files are in the current directory?"}
    ]
)

print(response.choices[0].message.content)
# Output: Fast response without tool usage (default behavior)

# Enable tools when you need them (e.g., to read files)
response = client.chat.completions.create(
    model="claude-3-5-sonnet-20241022",
    messages=[
        {"role": "user", "content": "What files are in the current directory?"}
    ],
    extra_body={"enable_tools": True}  # Enable tools for file access
)
print(response.choices[0].message.content)
# Output: Claude will actually read your directory and list the files!

# Check real costs and tokens
print(f"Cost: ${response.usage.total_tokens * 0.000003:.6f}")  # Real cost tracking
print(f"Tokens: {response.usage.total_tokens} ({response.usage.prompt_tokens} + {response.usage.completion_tokens})")

# Streaming
stream = client.chat.completions.create(
    model="claude-3-5-sonnet-20241022",
    messages=[
        {"role": "user", "content": "Explain quantum computing"}
    ],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

## Supported Models

- `claude-sonnet-4-20250514` (Recommended)
- `claude-opus-4-20250514`
- `claude-3-7-sonnet-20250219`
- `claude-3-5-sonnet-20241022`
- `claude-3-5-haiku-20241022`

The model parameter is passed to Claude Code via the `--model` flag.

## Session Continuity 🆕

The wrapper now supports **session continuity**, allowing you to maintain conversation context across multiple requests. This is a powerful feature that goes beyond the standard OpenAI API.

### How It Works

- **Stateless Mode** (default): Each request is independent, just like the standard OpenAI API
- **Session Mode**: Include a `session_id` to maintain conversation history across requests

### Using Sessions with OpenAI SDK

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

# Start a conversation with session continuity
response1 = client.chat.completions.create(
    model="claude-3-5-sonnet-20241022",
    messages=[
        {"role": "user", "content": "Hello! My name is Alice and I'm learning Python."}
    ],
    extra_body={"session_id": "my-learning-session"}
)

# Continue the conversation - Claude remembers the context
response2 = client.chat.completions.create(
    model="claude-3-5-sonnet-20241022", 
    messages=[
        {"role": "user", "content": "What's my name and what am I learning?"}
    ],
    extra_body={"session_id": "my-learning-session"}  # Same session ID
)
# Claude will remember: "Your name is Alice and you're learning Python."
```

### Using Sessions with curl

```bash
# First message (add -H "Authorization: Bearer your-key" if auth enabled)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [{"role": "user", "content": "My favorite color is blue."}],
    "session_id": "my-session"
  }'

# Follow-up message - context is maintained
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022", 
    "messages": [{"role": "user", "content": "What's my favorite color?"}],
    "session_id": "my-session"
  }'
```

### Session Management

The wrapper provides endpoints to manage active sessions:

- `GET /v1/sessions` - List all active sessions
- `GET /v1/sessions/{session_id}` - Get session details
- `DELETE /v1/sessions/{session_id}` - Delete a session
- `GET /v1/sessions/stats` - Get session statistics

```bash
# List active sessions
curl http://localhost:8000/v1/sessions

# Get session details
curl http://localhost:8000/v1/sessions/my-session

# Delete a session
curl -X DELETE http://localhost:8000/v1/sessions/my-session
```

### Session Features

- **Automatic Expiration**: Sessions expire after 1 hour of inactivity
- **Streaming Support**: Session continuity works with both streaming and non-streaming requests
- **Memory Persistence**: Full conversation history is maintained within the session
- **Efficient Storage**: Only active sessions are kept in memory

### Examples

See `examples/session_continuity.py` for comprehensive Python examples and `examples/session_curl_example.sh` for curl examples.

## API Endpoints

### Core Endpoints
- `POST /v1/chat/completions` - OpenAI-compatible chat completions (supports `session_id`)
- `GET /v1/models` - List available models
- `GET /v1/auth/status` - Check authentication status and configuration
- `GET /health` - Health check endpoint

### Session Management Endpoints 🆕
- `GET /v1/sessions` - List all active sessions
- `GET /v1/sessions/{session_id}` - Get detailed session information
- `DELETE /v1/sessions/{session_id}` - Delete a specific session
- `GET /v1/sessions/stats` - Get session manager statistics

## API Documentation (Swagger/OpenAPI)

### 🌐 Interactive Documentation

Access the interactive Swagger UI at: **http://localhost:8000/docs** (or http://192.168.1.11:8000/docs for Docker)

### 📋 Complete API Reference

#### **POST /v1/chat/completions**
Create a chat completion (OpenAI-compatible)

**Request Body:**
```json
{
  "model": "claude-3-5-sonnet-20241022",  // Required
  "messages": [                           // Required
    {
      "role": "system|user|assistant",    // Required
      "content": "string",                // Required
      "name": "string"                    // Optional
    }
  ],
  "temperature": 0.7,                     // Optional (0-2, default: 1.0)
  "top_p": 1.0,                          // Optional (0-1, default: 1.0)
  "n": 1,                                // Optional (must be 1)
  "stream": false,                       // Optional (default: false)
  "stop": ["string"],                    // Optional
  "max_tokens": null,                    // Optional (not supported by Claude Code)
  "presence_penalty": 0,                 // Optional (-2 to 2, default: 0)
  "frequency_penalty": 0,                // Optional (-2 to 2, default: 0)
  "logit_bias": {},                      // Optional (not supported)
  "user": "string",                      // Optional
  "session_id": "string",                // Optional (for conversation continuity)
  "enable_tools": false                  // Optional (enable Claude Code tools)
}
```

**Response (non-streaming):**
```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "claude-3-5-sonnet-20241022",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Hello! How can I help you?",
      "name": null
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 20,
    "total_tokens": 30
  },
  "system_fingerprint": null
}
```

**Response (streaming):**
```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"claude-3-5-sonnet-20241022","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"claude-3-5-sonnet-20241022","choices":[{"index":0,"delta":{"content":" there!"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"claude-3-5-sonnet-20241022","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

#### **GET /v1/models**
List available models

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "claude-sonnet-4-20250514",
      "object": "model",
      "owned_by": "anthropic"
    },
    {
      "id": "claude-opus-4-20250514",
      "object": "model",
      "owned_by": "anthropic"
    },
    {
      "id": "claude-3-5-sonnet-20241022",
      "object": "model",
      "owned_by": "anthropic"
    }
  ]
}
```

#### **GET /health**
Health check endpoint

**Response:**
```json
{
  "status": "healthy",
  "service": "claude-code-openai-wrapper"
}
```

#### **GET /v1/auth/status**
Check authentication status

**Response:**
```json
{
  "claude_code_auth": {
    "method": "browser|api_key|bedrock|vertex|claude_cli",
    "status": {
      "valid": true,
      "errors": [],
      "config": {
        "method": "Browser authentication",
        "note": "Authentication completed via browser"
      }
    },
    "environment_variables": ["DOCKER_CONTAINER"]
  },
  "server_info": {
    "api_key_required": false,
    "api_key_source": "none",
    "version": "1.0.0"
  }
}
```

#### **GET /v1/sessions**
List all active sessions

**Response:**
```json
{
  "sessions": [
    {
      "session_id": "my-session-123",
      "created_at": "2024-03-20T10:30:00Z",
      "last_active": "2024-03-20T11:45:00Z",
      "message_count": 5,
      "expires_at": "2024-03-20T12:45:00Z"
    }
  ],
  "count": 1
}
```

#### **GET /v1/sessions/{session_id}**
Get session details

**Response:**
```json
{
  "session_id": "my-session-123",
  "conversation": {
    "messages": [
      {
        "role": "user",
        "content": "Hello"
      },
      {
        "role": "assistant", 
        "content": "Hi! How can I help?"
      }
    ]
  },
  "metadata": {
    "created_at": "2024-03-20T10:30:00Z",
    "last_active": "2024-03-20T11:45:00Z",
    "message_count": 2,
    "expires_at": "2024-03-20T12:45:00Z"
  }
}
```

#### **DELETE /v1/sessions/{session_id}**
Delete a session

**Response:**
```json
{
  "message": "Session deleted successfully",
  "session_id": "my-session-123"
}
```

#### **GET /v1/sessions/stats**
Get session statistics

**Response:**
```json
{
  "active_sessions": 3,
  "total_messages": 45,
  "memory_usage_mb": 2.5,
  "oldest_session": "2024-03-20T09:00:00Z",
  "newest_session": "2024-03-20T11:30:00Z"
}
```

### 🔐 Authentication

If API key protection is enabled (via `API_KEY` environment variable), include the API key in the Authorization header:

```bash
curl -H "Authorization: Bearer your-api-key" http://localhost:8000/v1/models
```

### 🎯 Available Models

- `claude-sonnet-4-20250514` - Latest and most capable
- `claude-opus-4-20250514` - Most intelligent model
- `claude-3-7-sonnet-20250219` - Extended context window
- `claude-3-5-sonnet-20241022` - Fast and capable
- `claude-3-5-haiku-20241022` - Fastest response times

### 💡 Special Features

#### Enable Claude Code Tools
Add `"enable_tools": true` to use Claude Code's file operations:
```json
{
  "model": "claude-3-5-sonnet-20241022",
  "messages": [{"role": "user", "content": "List files in current directory"}],
  "enable_tools": true
}
```

#### Session Continuity
Add `"session_id": "your-session-id"` to maintain conversation context:
```json
{
  "model": "claude-3-5-sonnet-20241022",
  "messages": [{"role": "user", "content": "Continue our discussion"}],
  "session_id": "my-conversation-123"
}
```

## Limitations & Roadmap

### 🚫 **Current Limitations**
- **Images in messages** are converted to text placeholders
- **Function calling** not supported (tools work automatically based on prompts)
- **OpenAI parameters** not yet mapped: `temperature`, `top_p`, `max_tokens`, `logit_bias`, `presence_penalty`, `frequency_penalty`
- **Multiple responses** (`n > 1`) not supported

### 🛣 **Planned Enhancements** 
- [ ] **Tool configuration** - allowed/disallowed tools endpoints  
- [ ] **OpenAI parameter mapping** - temperature, top_p, max_tokens support
- [ ] **Enhanced streaming** - better chunk handling
- [ ] **MCP integration** - Model Context Protocol server support

### ✅ **Recent Improvements**
- **✅ SDK Integration**: Official Python SDK replaces subprocess calls
- **✅ Real Metadata**: Accurate costs and token counts from SDK
- **✅ Multi-auth**: Support for CLI, API key, Bedrock, and Vertex AI authentication  
- **✅ Session IDs**: Proper session tracking and management
- **✅ System Prompts**: Full support via SDK options
- **✅ Session Continuity**: Conversation history across requests with session management

## Troubleshooting

1. **Claude CLI not found**:
   ```bash
   # Check Claude is in PATH
   which claude
   # Update CLAUDE_CLI_PATH in .env if needed
   ```

2. **Authentication errors**:
   ```bash
   # Test authentication with fastest model
   claude --print --model claude-3-5-haiku-20241022 "Hello"
   # If this fails, re-authenticate if needed
   ```

3. **Timeout errors**:
   - Increase `MAX_TIMEOUT` in `.env`
   - Note: Claude Code can take time for complex requests

## Testing

### 🧪 **Quick Test Suite**
Test all endpoints with a simple script:
```bash
# Make sure server is running first
poetry run python test_endpoints.py
```

### 📝 **Basic Test Suite**
Run the comprehensive test suite:
```bash
# Make sure server is running first  
poetry run python test_basic.py

# With API key protection enabled, set TEST_API_KEY:
TEST_API_KEY=your-generated-key poetry run python test_basic.py
```

The test suite automatically detects whether API key protection is enabled and provides helpful guidance for providing the necessary authentication.

### 🔍 **Authentication Test**
Check authentication status:
```bash
curl http://localhost:8000/v1/auth/status | python -m json.tool
```

### ⚙️ **Development Tools**
```bash
# Install development dependencies
poetry install --with dev

# Format code
poetry run black .

# Run full tests (when implemented)
poetry run pytest tests/
```

### ✅ **Expected Results**
All tests should show:
- **4/4 endpoint tests passing**
- **4/4 basic tests passing** 
- **Authentication method detected** (claude_cli, anthropic, bedrock, or vertex)
- **Real cost tracking** (e.g., $0.001-0.005 per test call)
- **Accurate token counts** from SDK metadata

## Docker Deployment 🐳

### Quick Start with Docker

The wrapper includes full Docker support with Ubuntu GUI for browser-based Claude authentication:

```bash
# Clone the repository
git clone https://github.com/jorge123255/claude-code-openai-wrapper
cd claude-code-openai-wrapper

# Build and run with docker-compose
docker-compose up -d

# Access the services:
# - API: http://localhost:8000
# - Desktop GUI: http://localhost:6080 (for authentication)
```

### Important Notes for Docker Setup

**Node.js Version**: The container requires Node.js 20+ for Claude CLI. The Dockerfile automatically installs the correct version.

**First Run Authentication**:
1. Access the desktop at http://localhost:6080 (default VNC password: `changeme`)
2. Open a terminal in the desktop
3. Run `claude auth login` 
4. Copy the URL and paste it into Firefox to complete authentication
5. Start the API server: `echo "n" | python3 /app/main.py &`

**Known Issues & Solutions**:
- If you get syntax errors with f-strings, the main.py file has been fixed
- The API server prompts for API key protection - answer "n" for no protection or set `API_KEY=""` environment variable
- Browser authentication requires manual intervention on first run

### Docker Features

- **Ubuntu Desktop Environment**: XFCE desktop accessible via web browser
- **Automatic Authentication**: Browser opens automatically when auth is needed
- **Persistent Storage**: Authentication tokens survive container restarts
- **Multiple Auth Methods**: Browser, API key, Bedrock, or Vertex AI
- **noVNC Web Access**: No VNC client needed - access desktop through browser

### First-Time Setup

1. **Access the Desktop**: Navigate to http://localhost:6080
2. **Complete Authentication**: 
   - Firefox will open automatically if authentication is needed
   - Log in to Claude when prompted
   - Authentication is saved persistently
3. **Use the API**: Once authenticated, the API is available at http://localhost:8000

### Docker Configuration

#### Environment Variables

```env
# Display settings
VNC_PASSWORD=changeme        # Change this!
RESOLUTION=1920x1080x24      # Desktop resolution

# Authentication method
AUTH_METHOD=browser          # Options: browser, api_key, bedrock, vertex
ANTHROPIC_API_KEY=           # For api_key method

# API protection (optional)
API_KEY=                     # Protect wrapper endpoints
```

#### Volumes

The container uses these persistent volumes:
- `/config/claude`: Authentication data
- `/config/api`: API configuration
- `/data`: User projects/data
- `/var/log/supervisor`: Logs

#### Building from Source

```bash
# Build the image
docker build -f docker/Dockerfile -t claude-code-wrapper .

# Run with custom settings
docker run -d \
  -p 8000:8000 \
  -p 6080:6080 \
  -e VNC_PASSWORD=mysecurepassword \
  -v claude_auth:/config/claude \
  claude-code-wrapper
```

### Unraid Deployment

For Unraid users, a Community App template is included:

1. **Add Template Repository** (if not using Community Apps):
   ```
   https://github.com/jorge123255/claude-code-openai-wrapper/tree/main/docker/unraid
   ```
   
2. **Network Configuration**: 
   - Use bridge network with custom IP (e.g., 192.168.1.11)
   - Or use `br0` network type for direct LAN access

2. **Install from Community Apps**:
   - Search for "Claude Code Wrapper"
   - Configure paths and passwords
   - Start the container

3. **Default Paths**:
   - Config: `/mnt/user/appdata/claude-code-wrapper/`
   - Ports: 8000 (API), 6080 (GUI)

### Security Considerations

- **Change VNC Password**: Always set a secure VNC password
- **API Protection**: Use `API_KEY` environment variable for endpoint security
- **Network Isolation**: Consider using Docker networks for additional security
- **Volume Permissions**: Ensure proper permissions on mounted volumes

### Troubleshooting Docker

1. **Authentication Issues**:
   ```bash
   # Check auth handler logs
   docker-compose logs -f claude-code-wrapper | grep auth-handler
   
   # Manually trigger auth check
   docker exec claude-code-wrapper touch /tmp/need_auth
   ```

2. **Desktop Not Loading**:
   ```bash
   # Check VNC password was set correctly
   docker-compose exec claude-code-wrapper cat /root/.vnc/passwd
   
   # Restart desktop services
   docker-compose exec claude-code-wrapper supervisorctl restart desktop:*
   ```

3. **Container Health**:
   ```bash
   # Check container status
   docker-compose ps
   
   # View all logs
   docker-compose logs -f
   ```

## License

MIT License

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.