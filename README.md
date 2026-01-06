# Claude Code OpenAI API Wrapper

An OpenAI API-compatible wrapper for Claude Code, allowing you to use Claude Code with any OpenAI client library. **Now powered by the official Claude Agent SDK v0.1.18** with enhanced authentication and features.

## Version

**Current Version:** 2.2.0
- **Interactive Landing Page:** API explorer at root URL with live endpoint testing
- **Anthropic Messages API:** Native `/v1/messages` endpoint alongside OpenAI format
- **Explicit Auth Selection:** New `CLAUDE_AUTH_METHOD` env var for auth control
- **Tool Execution Fix:** `enable_tools: true` now properly enables Claude Code tools

**Upgrading from v1.x?**
1. Pull latest code: `git pull origin main`
2. Update dependencies: `poetry install`
3. Restart server - that's it!

**Migration Resources:**
- [MIGRATION_STATUS.md](./MIGRATION_STATUS.md) - Detailed v2.0.0 migration status
- [UPGRADE_PLAN.md](./UPGRADE_PLAN.md) - Comprehensive migration strategy and technical details

## Status

🎉 **Production Ready** - All core features working and tested:
- ✅ Chat completions endpoint with **official Claude Agent SDK v0.1.18**
- ✅ **Anthropic Messages API** (`/v1/messages`) for native compatibility
- ✅ Streaming and non-streaming responses
- ✅ Full OpenAI SDK compatibility
- ✅ **Interactive landing page** with API explorer
- ✅ **Multi-provider authentication** (API key, Bedrock, Vertex AI, CLI auth)
- ✅ **System prompt support** via SDK options
- ✅ Model selection support with validation
- ✅ **Fast by default** - Tools disabled for OpenAI compatibility (5-10x faster)
- ✅ Optional tool usage (Read, Write, Bash, etc.) when explicitly enabled
- ✅ **Real-time cost and token tracking** from SDK
- ✅ **Session continuity** with conversation history across requests
- ✅ **Session management endpoints** for full session control
- ✅ Health, auth status, and models endpoints
- ✅ **Development mode** with auto-reload

## Features

### 🔥 **Core API Compatibility**
- OpenAI-compatible `/v1/chat/completions` endpoint
- Anthropic-compatible `/v1/messages` endpoint
- Support for both streaming and non-streaming responses
- Compatible with OpenAI Python SDK and all OpenAI client libraries
- Automatic model validation and selection

### 🛠 **Claude Agent SDK Integration**
- **Official Claude Agent SDK** integration (v0.1.18) 🆕
- **Real-time cost tracking** - actual costs from SDK metadata
- **Accurate token counting** - input/output tokens from SDK
- **Session management** - proper session IDs and continuity
- **Enhanced error handling** with detailed authentication diagnostics
- **Modern SDK features** - Latest capabilities and improvements

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

### 🌐 **Interactive Landing Page**
- **API Explorer** at root URL (`http://localhost:8000/`)
- **Live endpoint testing** - Expandable accordions fetch real-time data
- **Light/dark theme toggle** - Persists preference in localStorage
- **Copy-to-clipboard** - One-click copy for Quick Start commands
- **Version badge** and GitHub link

## Quick Start

Get started in under 2 minutes:

```bash
# 1. Clone and setup the wrapper
git clone https://github.com/RichardAtCT/claude-code-openai-wrapper
cd claude-code-openai-wrapper
poetry install  # Installs SDK with bundled Claude Code CLI

# 2. Authenticate (choose one method)
export ANTHROPIC_API_KEY=your-api-key  # Recommended
# OR use CLI auth: claude auth login

# 3. Start the server
poetry run uvicorn src.main:app --reload --port 8000

# 4. Test it works
poetry run python test_endpoints.py
```

🎉 **That's it!** Your OpenAI-compatible Claude Code API is running on `http://localhost:8000`

## Prerequisites

1. **Python 3.10+**: Required for the server (supports Python 3.10, 3.11, 3.12, 3.13)

2. **Poetry**: For dependency management
   ```bash
   # Install Poetry (if not already installed)
   curl -sSL https://install.python-poetry.org | python3 -
   ```

3. **Authentication**: Choose one method:
   - **Option A**: Set environment variable (Recommended)
     ```bash
     export ANTHROPIC_API_KEY=your-api-key
     ```
   - **Option B**: Authenticate via CLI
     ```bash
     claude auth login
     ```
   - **Option C**: Use AWS Bedrock or Google Vertex AI (see Configuration section)

> **Note:** The Claude Code CLI is bundled with the SDK (v0.1.18+). No separate Node.js or npm installation required!

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

# Explicit authentication method (optional)
# Options: cli, api_key, bedrock, vertex
# If not set, auto-detects based on available credentials
# CLAUDE_AUTH_METHOD=cli

# Optional API key for client authentication
# If not set, server will prompt for interactive API key protection on startup
# API_KEY=your-optional-api-key

# Server port
PORT=8000

# Timeout in milliseconds
MAX_TIMEOUT=600000

# CORS origins
CORS_ORIGINS=["*"]

# Working directory for Claude Code (optional)
# If not set, uses an isolated temporary directory for security
# CLAUDE_CWD=/path/to/your/workspace
```

### 📁 **Working Directory Configuration**

By default, Claude Code runs in an **isolated temporary directory** to prevent it from accessing the wrapper's source code. This enhances security by ensuring Claude Code only has access to the workspace you intend.

**Configuration Options:**

1. **Default (Recommended)**: Automatically creates a temporary isolated workspace
   ```bash
   # No configuration needed - secure by default
   poetry run python main.py
   ```

2. **Custom Directory**: Set a specific workspace directory
   ```bash
   export CLAUDE_CWD=/path/to/your/project
   poetry run python main.py
   ```

3. **Via .env file**: Add to your `.env` file
   ```env
   CLAUDE_CWD=/home/user/my-workspace
   ```

**Important Notes:**
- The temporary directory is automatically cleaned up when the server stops
- This prevents Claude Code from accidentally modifying the wrapper's own code
- Cross-platform compatible (Windows, macOS, Linux)

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

### 🛡️ **Rate Limiting**

Built-in rate limiting protects against abuse and ensures fair usage:

- **Chat Completions** (`/v1/chat/completions`): 10 requests/minute
- **Debug Requests** (`/v1/debug/request`): 2 requests/minute
- **Auth Status** (`/v1/auth/status`): 10 requests/minute
- **Health Check** (`/health`): 30 requests/minute

Rate limits are applied per IP address using a fixed window algorithm. When exceeded, the API returns HTTP 429 with a structured error response:

```json
{
  "error": {
    "message": "Rate limit exceeded. Try again in 60 seconds.",
    "type": "rate_limit_exceeded",
    "code": "too_many_requests",
    "retry_after": 60
  }
}
```

Configure rate limiting through environment variables:

```bash
RATE_LIMIT_ENABLED=true
RATE_LIMIT_CHAT_PER_MINUTE=10
RATE_LIMIT_DEBUG_PER_MINUTE=2
RATE_LIMIT_AUTH_PER_MINUTE=10
RATE_LIMIT_HEALTH_PER_MINUTE=30
```

## Running the Server

1. Verify Claude Code is installed and working:
   ```bash
   claude --version
   claude --print --model claude-haiku-4-5-20251001 "Hello"  # Test with fastest model
   ```

2. Start the server:

   **Development mode (recommended - auto-reloads on changes):**
   ```bash
   poetry run uvicorn src.main:app --reload --port 8000
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

## Docker

Build and run the wrapper in a Docker container.

### Build

```bash
docker build -t claude-wrapper:latest .
```

### Run

**Production:**
```bash
docker run -d -p 8000:8000 \
  -v ~/.claude:/root/.claude \
  --name claude-wrapper \
  claude-wrapper:latest
```

**With custom workspace:**
```bash
docker run -d -p 8000:8000 \
  -v ~/.claude:/root/.claude \
  -v /path/to/project:/workspace \
  -e CLAUDE_CWD=/workspace \
  claude-wrapper:latest
```

**Development (hot reload):**
```bash
docker run -d -p 8000:8000 \
  -v ~/.claude:/root/.claude \
  -v $(pwd):/app \
  claude-wrapper:latest \
  poetry run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker Compose

```yaml
version: '3.8'
services:
  claude-wrapper:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ~/.claude:/root/.claude
    environment:
      - PORT=8000
      - MAX_TIMEOUT=600
    restart: unless-stopped
```

Run: `docker-compose up -d` | Stop: `docker-compose down`

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Server port | `8000` |
| `MAX_TIMEOUT` | Request timeout (seconds) | `300` |
| `CLAUDE_CWD` | Working directory | temp dir |
| `CLAUDE_AUTH_METHOD` | Auth method: `cli`, `api_key`, `bedrock`, `vertex` | auto-detect |
| `ANTHROPIC_API_KEY` | Direct API key | - |
| `API_KEYS` | Comma-separated client API keys | - |

### Management

```bash
docker logs -f claude-wrapper        # View logs
docker stop claude-wrapper           # Stop
docker start claude-wrapper          # Start
docker rm claude-wrapper             # Remove
```

### Test

```bash
curl http://localhost:8000/health
curl http://localhost:8000/v1/models
```

## Usage Examples

### Using curl

```bash
# Basic chat completion (no auth)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5-20250929",
    "messages": [
      {"role": "user", "content": "What is 2 + 2?"}
    ]
  }'

# With API key protection (when enabled)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-generated-api-key" \
  -d '{
    "model": "claude-sonnet-4-5-20250929",
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
    model="claude-sonnet-4-5-20250929",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What files are in the current directory?"}
    ]
)

print(response.choices[0].message.content)
# Output: Fast response without tool usage (default behaviour)

# Enable tools when you need them (e.g., to read files)
response = client.chat.completions.create(
    model="claude-sonnet-4-5-20250929",
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
    model="claude-sonnet-4-5-20250929",
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

All Claude models through November 2025 are supported:

### Claude 4.5 Family (Latest - Fall 2025)
- **`claude-opus-4-5-20250929`** 🎯 Most Capable - Latest Opus with enhanced reasoning and capabilities
- **`claude-sonnet-4-5-20250929`** ⭐ Recommended - Best coding model, superior reasoning and math
- **`claude-haiku-4-5-20251001`** ⚡ Fast & Cheap - Similar performance to Sonnet 4 at 1/3 cost

### Claude 4.1 & 4.0 Family
- **`claude-opus-4-1-20250805`** - Upgraded Opus 4 with improved agentic tasks and reasoning
- `claude-opus-4-20250514` - Original Opus 4 with extended thinking mode
- `claude-sonnet-4-20250514` - Original Sonnet 4 with hybrid reasoning

### Claude 3.x Family
- `claude-3-7-sonnet-20250219` - Hybrid model with rapid/thoughtful response modes
- `claude-3-5-sonnet-20241022` - Previous generation Sonnet
- `claude-3-5-haiku-20241022` - Previous generation fast model

**Note:** The model parameter is passed to Claude Code via the SDK's model selection.

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
    model="claude-sonnet-4-5-20250929",
    messages=[
        {"role": "user", "content": "Hello! My name is Alice and I'm learning Python."}
    ],
    extra_body={"session_id": "my-learning-session"}
)

# Continue the conversation - Claude remembers the context
response2 = client.chat.completions.create(
    model="claude-sonnet-4-5-20250929",
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
    "model": "claude-sonnet-4-5-20250929",
    "messages": [{"role": "user", "content": "My favourite color is blue."}],
    "session_id": "my-session"
  }'

# Follow-up message - context is maintained
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5-20250929",
    "messages": [{"role": "user", "content": "What's my favourite color?"}],
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
- `GET /` - Interactive landing page with API explorer
- `POST /v1/chat/completions` - OpenAI-compatible chat completions (supports `session_id`)
- `POST /v1/messages` - Anthropic-compatible messages endpoint
- `GET /v1/models` - List available models
- `GET /v1/auth/status` - Check authentication status and configuration
- `GET /version` - Get API version
- `GET /health` - Health check endpoint

### Session Management Endpoints 🆕
- `GET /v1/sessions` - List all active sessions
- `GET /v1/sessions/{session_id}` - Get detailed session information
- `DELETE /v1/sessions/{session_id}` - Delete a specific session
- `GET /v1/sessions/stats` - Get session manager statistics

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

### ✅ **Recent Improvements (v2.2.0)**
- **Interactive Landing Page**: API explorer with live endpoint testing
- **Anthropic Messages API**: Native `/v1/messages` endpoint
- **Explicit Auth Selection**: `CLAUDE_AUTH_METHOD` env var
- **Tool Execution Fix**: `enable_tools: true` now works correctly

### ✅ **v2.0.0 - v2.1.0 Features**
- Claude Agent SDK v0.1.18 with bundled CLI
- Multi-provider auth (CLI, API key, Bedrock, Vertex AI)
- Session continuity and management
- Real-time cost and token tracking
- System prompt support

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
   claude --print --model claude-haiku-4-5-20251001 "Hello"
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

## Terms Compliance

This wrapper is designed to be compliant with [Anthropic's Terms of Service](https://www.anthropic.com/legal).

### How This Wrapper Works

- **Uses the official Claude Agent SDK** - The same SDK Anthropic provides for developers
- **Each user authenticates individually** - No credential sharing or pooling
- **Format translation only** - Converts OpenAI-format requests to Claude SDK calls
- **No reselling** - Users access Claude through their own subscriptions/API keys

### Authentication Methods

| Method | Terms | Compliance |
|--------|-------|------------|
| `ANTHROPIC_API_KEY` | Commercial Terms | Explicitly allowed for programmatic access |
| AWS Bedrock | Commercial Terms | Explicitly allowed for programmatic access |
| Google Vertex AI | Commercial Terms | Explicitly allowed for programmatic access |
| CLI Auth (Pro/Max) | Consumer Terms | Uses official SDK with official auth methods |

### CLI Authentication Note

Using CLI auth (`claude auth login`) with this wrapper is functionally equivalent to using Claude Code directly - both use the Claude Agent SDK with your personal subscription. Anthropic provides the SDK with CLI auth support, and this wrapper simply provides an alternative interface format.

### What This Wrapper Does NOT Do

- Does not share or pool credentials between users
- Does not resell API access
- Does not train competing AI models
- Does not scrape or harvest data
- Does not bypass authentication or rate limits

### Disclaimer

This is an independent open-source project, not affiliated with or endorsed by Anthropic. Users are responsible for ensuring their own usage complies with Anthropic's terms. When in doubt, use `ANTHROPIC_API_KEY` authentication which is explicitly permitted for programmatic access under the Commercial Terms.

For Anthropic's official terms, see:
- [Usage Policy](https://www.anthropic.com/legal/aup)
- [Consumer Terms](https://www.anthropic.com/legal/consumer-terms)
- [Commercial Terms](https://www.anthropic.com/legal/commercial-terms)

## Licence

MIT Licence

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
