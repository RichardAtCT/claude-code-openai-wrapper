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
- ✅ **Chat mode** for sandboxed, secure chat-only operation 🔒
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
- **Chat mode** - Sandboxed execution with no file system access for secure chat APIs
- **Progress markers** - Optional streaming progress indicators ("Working on it...", "Still processing...") with exponential backoff
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
# Claude CLI Configuration
CLAUDE_CLI_PATH=claude

# API Configuration
# If API_KEY is not set, server will prompt for interactive API key protection on startup
# Leave commented out to enable interactive prompt, or uncomment to use a fixed API key
# API_KEY=your-optional-api-key-here
PORT=8000

# Timeout Configuration (milliseconds)
MAX_TIMEOUT=600000

# CORS Configuration
CORS_ORIGINS=["*"]

# Chat Mode Configuration
# Set to true to enable sandboxed execution with no file system access
# This disables sessions and restricts tools to WebSearch and WebFetch only
CHAT_MODE=false

# Chat Mode Session Cleanup
# Set to false to disable automatic Claude Code session cleanup in chat mode
# When disabled, sessions will appear in Claude's /resume command
CHAT_MODE_CLEANUP_SESSIONS=true

# Cleanup delay in minutes (default: 720 = 12 hours)
# Sessions are tracked and cleaned up after this delay
# Set to 0 for immediate cleanup after request completion
# Note: Claude Code tracks token usage per session. For accurate usage monitoring,
# sessions should persist long enough to capture complete usage data.
# 12 hours ensures sessions span daily usage boundaries for better tracking.
CHAT_MODE_CLEANUP_DELAY_MINUTES=720

# Progress Markers Configuration
# Set to true to show progress indicators during streaming (⏳ followed by rotating circles ◐◓◑◒ with dots ·)
# Set to false to buffer and only stream the final response (filters out all intermediate tool uses)
SHOW_PROGRESS_MARKERS=true

# SSE Keep-alive Configuration
# Interval in seconds between SSE keepalive comments to prevent connection timeouts
# These are invisible comments (lines starting with ':') that keep the connection alive
SSE_KEEPALIVE_INTERVAL=30

# Rate Limiting Configuration
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=30
RATE_LIMIT_CHAT_PER_MINUTE=10
RATE_LIMIT_DEBUG_PER_MINUTE=2
RATE_LIMIT_AUTH_PER_MINUTE=10
RATE_LIMIT_SESSION_PER_MINUTE=15
RATE_LIMIT_HEALTH_PER_MINUTE=30
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

### 📊 **Progress Markers**

Control streaming progress indicators for long-running operations:

- **Enabled by default** (`SHOW_PROGRESS_MARKERS=true`)
  - Shows progress messages like "Working on it", "Still processing", "Crafting your response"
  - Uses exponential backoff to avoid being too chatty
  - Perfect for user-facing applications where feedback is important

- **Disable for cleaner output** (`SHOW_PROGRESS_MARKERS=false`)
  - **Only streams the final response** without any intermediate content
  - Filters out ALL intermediate tool uses, thinking steps, and preliminary responses
  - Waits for completion then sends only the final assistant message
  - SSE keepalives are sent every `SSE_KEEPALIVE_INTERVAL` seconds during SDK buffering
  - Ideal for programmatic usage or when you only need the final result
  - Note: This buffers the entire response, so initial latency will be higher

### 🔄 **SSE Keepalive Configuration**

Prevents connection timeouts during long-running requests by sending invisible keepalive comments:

- **Default interval**: 30 seconds (`SSE_KEEPALIVE_INTERVAL=30`)
- **How it works**: Sends SSE comments (lines starting with `:`) that are automatically ignored by clients
- **When it's used**: During any pause in streaming longer than the configured interval
- **Invisible to clients**: Keepalive comments don't appear in the response content

This feature ensures that:
- Long Claude processing times don't cause connection timeouts
- Proxies and load balancers don't close "idle" connections
- Works identically in both progress marker modes:
  - With progress markers: Keepalives sent between progress updates
  - Without progress markers: Keepalives sent during SDK response buffering
- Connections remain active even when the SDK takes time to respond

The progress indicators use universal, language-agnostic symbols:
- Starts with ⏳ (hourglass) to indicate processing has begun
- Transitions to rotating circles (◐ ◓ ◑ ◒) for ongoing progress
- Adds dots (·) incrementally to show continued activity
- Example progression: ⏳ → ⏳· → ◐ → ◐· → ◐·· → ◓ → ◓·

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

## Docker Setup Guide for Claude Code OpenAI Wrapper

This guide provides a comprehensive overview of building, running, and configuring a Docker container for the Claude Code OpenAI Wrapper. Docker enables isolated, portable, and reproducible deployments of the wrapper, which acts as an OpenAI-compatible API server routing requests to Anthropic's Claude models via the official Claude Code Python SDK (v0.0.14+). This setup supports authentication methods like Claude subscriptions (e.g., Max plan via OAuth for fixed-cost quotas), direct API keys, AWS Bedrock, or Google Vertex AI.

By containerizing the application, you can run it locally for development, deploy it to remote servers or cloud platforms, and customize behavior through environment variables and volumes. This guide assumes you have already cloned the repository and have the `Dockerfile` in the root directory. For general repository setup (e.g., Claude Code CLI authentication), refer to the sections above.

## Prerequisites
Before building or running the container, ensure the following:
- **Docker Installed**: Docker Desktop (for macOS/Windows) or Docker Engine (for Linux). Verify with `docker --version` (version 20+ recommended). Test basic functionality with `docker run hello-world`.
- **Claude Authentication Configured**: For subscription-based access (e.g., Claude Max), ensure the Claude Code CLI is authenticated on your host machine, with tokens in `~/.claude/`. This directory will be mounted into the container. Refer to the Prerequisites section above for CLI setup if needed.
- **Hardware and Software**:
  - OS: macOS (10.15+), Linux (e.g., Ubuntu 20.04+), or Windows (10+ with WSL2 for optimal volume mounting).
  - Resources: At least 4GB RAM and 2 CPU cores (Claude requests can be compute-intensive; monitor with `docker stats`).
  - Disk: ~500MB for the image, plus space for volumes.
  - Network: Stable internet for builds (dependency downloads) and runtime (API calls to Anthropic).
- **Optional**:
  - Docker Compose: For multi-service or easier configuration management. Install via Docker Desktop or your package manager (e.g., `sudo apt install docker-compose`).
  - Tools for Remote Deployment: Access to a VPS (e.g., AWS EC2, DigitalOcean), cloud registry (e.g., Docker Hub), or platform (e.g., Heroku, Google Cloud Run) if planning remote use.

## Building the Docker Image
The `Dockerfile` in the root defines a lightweight Python 3.12-based image with all dependencies (Poetry, Node.js for CLI, FastAPI/Uvicorn, and the Claude Code SDK).

1. Navigate to the repository root (where the Dockerfile is).
2. Build the image:
   ```bash
   docker build -t claude-wrapper:latest .
   ```
   - `-t claude-wrapper:latest`: Tags the image (replace `:latest` with a version like `:v1.0` for production).
   - `.`: Builds from the current directory context.
   - Build Time: 5-15 minutes on first run (subsequent builds cache layers).
   - Size: Approximately 200-300MB.

3. Verify the Build:
   ```bash
   docker images | grep claude-wrapper
   ```
   This lists the image with its tag and size.

4. Advanced Build Options:
   - No Cache (for fresh builds): `docker build --no-cache -t claude-wrapper:latest .`.
   - Platform-Specific (e.g., ARM for Raspberry Pi): `docker build --platform linux/arm64 -t claude-wrapper:arm .`.
   - Multi-Stage for Smaller Size: If optimizing, modify the Dockerfile to use multi-stage builds (e.g., separate build and runtime stages).

If using Docker Compose (see below), build with `docker-compose build`.

## Running the Container Locally
Once built, run the container to start the API server. The default port is 8000, and the API is accessible at `http://localhost:8000/v1` (e.g., `/v1/chat/completions` for requests).

### Basic Production Run
For stable, background operation:
```bash
docker run -d -p 8000:8000 \
  -v ~/.claude:/root/.claude \
  -v ~/.claude-wrapper:/root/.claude-wrapper \
  --name claude-wrapper-container \
  claude-wrapper:latest
```
- `-d`: Detached mode (runs in background).
- `-p 8000:8000`: Maps host port 8000 to the container's 8000 (change left side for host conflicts, e.g., `-p 9000:8000`).
- `-v ~/.claude:/root/.claude`: Mounts your host's authentication directory for persistent subscription tokens (essential for Claude Max access).
- `-v ~/.claude-wrapper:/root/.claude-wrapper`: Mounts session tracking directory for chat mode cleanup functionality.
- `--name claude-wrapper-container`: Names the container for easy management.

### Development Run with Hot Reload
For coding/debugging (auto-reloads on file changes):
```bash
docker run -d -p 8000:8000 \
  -v ~/.claude:/root/.claude \
  -v ~/.claude-wrapper:/root/.claude-wrapper \
  -v $(pwd):/app \
  --name claude-wrapper-container \
  claude-wrapper:latest \
  poetry run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
- `-v $(pwd):/app`: Mounts the current directory (repo root) into the container for live code edits.
- Command Override: Uses Uvicorn with `--reload` for development.

### Using Docker Compose for Simplified Runs
Create or use an existing `docker-compose.yml` in the root for declarative configuration:
```yaml
version: '3'
services:
  claude-wrapper:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ~/.claude:/root/.claude
      - ~/.claude-wrapper:/root/.claude-wrapper  # For session tracking
      # - .:/app  # Optional for dev - uncomment to mount code for hot reload
    environment:
      # Claude CLI Configuration
      - CLAUDE_CLI_PATH=${CLAUDE_CLI_PATH:-claude}
      # API Configuration
      - PORT=${PORT:-8000}
      - API_KEY=${API_KEY:-}
      # Timeout Configuration
      - MAX_TIMEOUT=${MAX_TIMEOUT:-600000}
      # CORS Configuration
      - CORS_ORIGINS=${CORS_ORIGINS:-["*"]}
      # Chat Mode Configuration
      - CHAT_MODE=${CHAT_MODE:-false}
      - CHAT_MODE_CLEANUP_SESSIONS=${CHAT_MODE_CLEANUP_SESSIONS:-true}
      - CHAT_MODE_CLEANUP_DELAY_MINUTES=${CHAT_MODE_CLEANUP_DELAY_MINUTES:-720}
      # Progress Markers
      - SHOW_PROGRESS_MARKERS=${SHOW_PROGRESS_MARKERS:-true}
      # SSE Keep-alive
      - SSE_KEEPALIVE_INTERVAL=${SSE_KEEPALIVE_INTERVAL:-30}
      # Rate Limiting Configuration
      - RATE_LIMIT_ENABLED=${RATE_LIMIT_ENABLED:-true}
      - RATE_LIMIT_PER_MINUTE=${RATE_LIMIT_PER_MINUTE:-30}
      - RATE_LIMIT_CHAT_PER_MINUTE=${RATE_LIMIT_CHAT_PER_MINUTE:-10}
      - RATE_LIMIT_DEBUG_PER_MINUTE=${RATE_LIMIT_DEBUG_PER_MINUTE:-2}
      - RATE_LIMIT_AUTH_PER_MINUTE=${RATE_LIMIT_AUTH_PER_MINUTE:-10}
      - RATE_LIMIT_SESSION_PER_MINUTE=${RATE_LIMIT_SESSION_PER_MINUTE:-15}
      - RATE_LIMIT_HEALTH_PER_MINUTE=${RATE_LIMIT_HEALTH_PER_MINUTE:-30}
    # Dev example with hot reload - uncomment the line below and comment out the default CMD in Dockerfile
    # command: ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    restart: unless-stopped
```
- Run: `docker-compose up -d` (builds if needed, runs detached).
- Stop: `docker-compose down`.

### Post-Run Management
- View Logs: `docker logs claude-wrapper-container` (add `-f` for real-time tailing).
- Check Status: `docker ps` (lists running containers) or `docker stats` (resource usage).
- Stop/Restart: `docker stop claude-wrapper-container` and `docker start claude-wrapper-container`.
- Remove: `docker rm claude-wrapper-container` (after stopping; use `-f` to force).
- Cleanup: `docker system prune` to remove unused images/volumes.

## Custom Configuration Options
Customize the container's behavior through environment variables, volumes, and runtime flags. Most changes don't require rebuilding—just restart the container.

### Environment Variables
Env vars override defaults and can be set at runtime with `-e` flags or in `docker-compose.yml` under `environment`. They control auth, server settings, and SDK behavior.

- **Core Server Settings**:
  - `CLAUDE_CLI_PATH=claude`: Path to Claude CLI executable (default: claude).
  - `PORT=9000`: Changes the internal listening port (default: 8000; update port mapping accordingly).
  - `MAX_TIMEOUT=600000`: Sets the request timeout in milliseconds (default: 600000 = 10 minutes; increase for complex Claude queries).
  - `CORS_ORIGINS=["*"]`: CORS allowed origins (default: ["*"] allows all origins).

- **Authentication and Providers**:
  - `ANTHROPIC_API_KEY=sk-your-key`: Enables direct API key auth (overrides subscription; generate at console.anthropic.com).
  - `CLAUDE_CODE_USE_VERTEX=true`: Switches to Google Vertex AI (requires additional vars like `GOOGLE_APPLICATION_CREDENTIALS=/path/to/creds.json`—mount the file as a volume).
  - `CLAUDE_CODE_USE_BEDROCK=true`: Enables AWS Bedrock (set `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, etc.).
  - `CLAUDE_USE_SUBSCRIPTION=true`: Forces subscription mode (default behavior; set to ensure no API fallback).

- **Security and API Protection**:
  - `API_KEY=your-key`: Single API key required for endpoint access (clients must send `Authorization: Bearer <key>`). Leave unset for interactive prompt.
  - `CHAT_MODE=true`: Enable chat mode for sandboxed execution with no file system access (disables sessions, restricts tools).
  - `CHAT_MODE_CLEANUP_SESSIONS=true`: Enable automatic Claude Code session cleanup in chat mode (default: true).
  - `CHAT_MODE_CLEANUP_DELAY_MINUTES=720`: Minutes to wait before cleanup (default: 720 = 12 hours). Set to 0 for immediate cleanup.
  - `SHOW_PROGRESS_MARKERS=false`: Disable streaming progress indicators (default: true). When false, buffers the entire response and only streams the final assistant message, filtering out all intermediate tool uses and preliminary responses.
  - `SSE_KEEPALIVE_INTERVAL=30`: Interval in seconds for sending SSE keepalive comments to prevent connection timeouts (default: 30).

- **Rate Limiting Configuration**:
  - `RATE_LIMIT_ENABLED=true`: Enable rate limiting for all endpoints (default: true).
  - `RATE_LIMIT_PER_MINUTE=30`: General rate limit per minute (default: 30).
  - `RATE_LIMIT_CHAT_PER_MINUTE=10`: Chat completions rate limit per minute (default: 10).
  - `RATE_LIMIT_DEBUG_PER_MINUTE=2`: Debug endpoint rate limit per minute (default: 2).
  - `RATE_LIMIT_AUTH_PER_MINUTE=10`: Auth endpoint rate limit per minute (default: 10).
  - `RATE_LIMIT_SESSION_PER_MINUTE=15`: Session endpoint rate limit per minute (default: 15).
  - `RATE_LIMIT_HEALTH_PER_MINUTE=30`: Health check rate limit per minute (default: 30).

- **Custom/Advanced Vars**:
  - `MAX_THINKING_TOKENS=4096`: Custom token budget for extended thinking (if implemented in code; e.g., for `budget_tokens` in SDK calls).
  - `ANTHROPIC_CUSTOM_HEADERS='{"anthropic-beta": "extended-thinking-2024-10-01"}'`: JSON string for custom SDK headers (parse in `main.py` if needed).
  - Add more by modifying `main.py` to read `os.getenv('YOUR_VAR')` and rebuild.

Example with Env Vars:
```bash
docker run ... -e PORT=9000 -e ANTHROPIC_API_KEY=sk-your-key ...
```

For persistence across runs, use a `.env` file in the root (e.g., `PORT=8000`) and mount it: `-v $(pwd)/.env:/app/.env`. Load vars in code if required.

### Volumes for Data Persistence and Customization
Volumes mount host directories/files into the container, enabling persistence and config overrides.

- **Authentication Volume (Required for Subscriptions)**: `-v ~/.claude:/root/.claude` – Shares tokens and `settings.json` (edit on host for defaults like `"max_tokens": 8192`; restart container to apply).
- **Session Tracking Volume**: `-v ~/.claude-wrapper:/root/.claude-wrapper` – Stores session tracking data for chat mode cleanup functionality.
- **Code Volume (Dev Only)**: `-v $(pwd):/app` – Allows live edits without rebuilds.
- **Custom Config Volumes**: 
  - Mount a custom config: `-v /path/to/custom.json:/app/config/custom.json` (load in code).
  - Logs: `-v /path/to/logs:/app/logs` for external log access.
- **Credential Files**: For Vertex/Bedrock, `-v /path/to/creds.json:/app/creds.json` and set env var to point to it.

Volumes survive container restarts but are deleted on `docker rm -v`. Use named volumes for better management (e.g., `docker volume create claude-auth` and `-v claude-auth:/root/.claude`).

### Runtime Flags and Overrides
- Resource Limits: `--cpus=2 --memory=2g` to cap CPU/RAM (prevent overconsumption).
- Network: `--network host` for host networking (useful for local integrations).
- Restart Policy: `--restart unless-stopped` for auto-recovery on crashes.
- User: `--user $(id -u):$(id -g)` to run as your host user (avoid root permissions).

Per-request configs (e.g., `max_tokens`, `model`) are handled in API payloads, not container flags.

## Using the Container Remotely
For remote access (e.g., from other machines or production deployment), extend the local setup.

### Exposing Locally for Remote Access
- Bind to All Interfaces: Already done with `--host 0.0.0.0`.
- Firewall: Open port 8000 on your host (e.g., `ufw allow 8000` on Ubuntu).
- Tunneling: Use ngrok for temporary exposure: Install ngrok, run `ngrok http 8000`, and use the public URL.
- Security: Always add `API_KEYS` and use HTTPS (via reverse proxy).

### Deploying to a Remote Server or VPS
1. Push Image to Registry: 
   ```bash
   docker tag claude-wrapper:latest yourusername/claude-wrapper:latest
   docker push yourusername/claude-wrapper:latest
   ```
   (Create a Docker Hub account if needed.)

2. On Remote Server (e.g., AWS EC2, DigitalOcean Droplet):
   - Install Docker.
   - Pull Image: `docker pull yourusername/claude-wrapper:latest`.
   - Run: Use the production command above, but copy `~/.claude/` to the server first (e.g., via scp) or re-auth CLI remotely.
   - Persistent Storage: Use server volumes (e.g., `-v /server/path/to/claude:/root/.claude`).
   - Background: Use systemd or screen for daemonization.

3. Cloud Platforms:
   - **Heroku**: Use `heroku container:push web` after installing Heroku CLI; set env vars in dashboard.
   - **Google Cloud Run**: `gcloud run deploy --image yourusername/claude-wrapper --port 8000 --allow-unauthenticated`.
   - **AWS ECS**: Create a task definition with the image, set env vars, and deploy as a service.
   - Scaling: Platforms like Kubernetes can auto-scale based on load.

4. HTTPS and Security for Remote:
   - Use a Reverse Proxy: Add Nginx/Apache in another container (e.g., via Compose) with SSL (Let's Encrypt).
   - Example Nginx Config (mount as volume): Redirect HTTP to HTTPS, proxy to 8000.
   - Monitoring: Integrate CloudWatch/Prometheus for logs/metrics.

Remote usage respects your Claude quotas (shared across instances). For high availability, use load balancers.

## Testing the Container
Validate setup post-run:
1. Health Check: `curl http://localhost:8000/health` (expect `{"status": "healthy"}`).
2. Models List: `curl http://localhost:8000/v1/models`.
3. Completion Request: 
   ```bash
   curl http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model": "claude-3-5-sonnet-20240620", "messages": [{"role": "user", "content": "Hello"}]}'
   ```
4. Tool/Subscription Test: Send multiple requests; check logs for auth mode.
5. Remote Test: From another machine, curl the server's IP/port.

Use `test_endpoints.py` from the repo (mount code and run inside container: `docker exec claude-wrapper-container poetry run python test_endpoints.py`).

## Troubleshooting
- **Build Fails**: Check Dockerfile syntax; clear cache (`--no-cache`); ensure internet.
- **Run Errors**:
  - Auth: Verify `~/.claude` mount; re-auth CLI.
  - Port in Use: Change mapping or kill processes (`lsof -i:8000`).
  - Dep Issues: Rebuild; check Poetry lock file.
- **Remote Access Problems**: Firewall rules, DNS, or use `--network host`.
- **Performance**: Increase resources (`--cpus`); switch models.
- **Logs/Debug**: `docker logs -f claude-wrapper-container`; enter shell `docker exec -it claude-wrapper-container /bin/bash`.
- **Cleanup**: `docker system prune -a` for full reset.

Report issues on GitHub with logs/image tag/OS details.

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

## Chat Mode 🔒

The wrapper supports a secure **chat mode** that transforms Claude Code into a sandboxed, chat-only AI with no file system access. This mode is perfect for exposing Claude as a general-purpose chat API while ensuring complete security isolation.

### Enabling Chat Mode

Set the `CHAT_MODE` environment variable to enable secure chat mode:

```bash
# Enable chat mode
export CHAT_MODE=true
python main.py
```

### Chat Mode Features

When chat mode is enabled:

- **No File System Access**: All file operations are completely blocked
- **Limited Tools**: Only WebSearch, WebFetch, and Task tools are available
- **Sandboxed Execution**: Each request runs in an isolated temporary directory
- **No Sessions**: Sessions are automatically disabled (clients should manage conversation state)
- **Format Support**: Automatic detection and support for XML tool formats and JSON responses
- **Prompt Engineering**: Multiple system prompts ensure chat-only behavior
- **Automatic Cleanup**: Session files created by Claude Code are automatically removed after each request

### Security Properties

- **Complete Isolation**: Each request is stateless and runs in a fresh sandbox
- **Path Hiding**: Environment variables that could reveal system paths are removed
- **Tool Restrictions**: Only web-based tools allowed, no local system access
- **Automatic Cleanup**: Temporary sandbox directories are cleaned immediately; Claude Code session files are cleaned based on configured delay
- **Time-Based Cleanup**: Sessions are tracked and cleaned after a delay (default: 12 hours for complete usage tracking)
- **No Session Persistence**: Sessions are removed after the delay period (configurable via `CHAT_MODE_CLEANUP_SESSIONS` and `CHAT_MODE_CLEANUP_DELAY_MINUTES`)

### Important Notes

- **Sessions Disabled**: When chat mode is active, all session endpoints return errors
- **Client Responsibility**: Chat clients should handle their own conversation continuity
- **No Persistence**: Nothing is saved between requests
- **Tool Override**: The `enable_tools` parameter is ignored; only chat mode tools are available

### Session Cleanup Configuration

The wrapper provides flexible session cleanup options:

- **`CHAT_MODE_CLEANUP_SESSIONS`**: Master on/off switch for session cleanup (default: `true`)
- **`CHAT_MODE_CLEANUP_DELAY_MINUTES`**: Minutes to wait before cleanup (default: `720` = 12 hours)
  - Set to `0` for immediate cleanup after request completion
  - Sessions are tracked and cleaned up by a background task
  - On startup, old sessions exceeding the delay are automatically cleaned

### Token Usage Tracking and Monitoring

Claude Code tracks token usage at the session level. Each session file contains the complete token consumption data for all requests within that session. This has important implications for usage monitoring:

- **Token Usage Aggregation**: Claude Code aggregates token usage per session, not per request
- **Daily Usage Tracking**: For accurate daily token consumption reports, sessions should persist across usage periods
- **12-Hour Default**: The 12-hour delay ensures sessions span daily usage boundaries, capturing complete usage patterns
- **Monitoring Tools**: Usage tracking dashboards and cost analysis tools need access to session files to calculate token consumption

### Monitoring Considerations

- **With delayed cleanup** (default 12 hours): Sessions remain available long enough for monitoring tools to capture complete daily usage data
- **Immediate cleanup** (`CHAT_MODE_CLEANUP_DELAY_MINUTES=0`): May result in incomplete usage statistics as sessions are deleted before aggregation
- **To preserve logs indefinitely**: Set `CHAT_MODE_CLEANUP_SESSIONS=false` - sessions accumulate but provide complete historical data
- **Recommended for monitoring**: Use at least 12-24 hours delay to ensure usage data spans daily boundaries

### Important Note on Existing Sessions

**Currently, sessions created while `CHAT_MODE_CLEANUP_SESSIONS=false` will NOT be automatically cleaned up when switching to `CHAT_MODE_CLEANUP_SESSIONS=true`.** Only new sessions created after enabling cleanup will be tracked and cleaned. To manually clean old sessions, you'll need to delete them from `~/.claude/projects/` directories containing "claude-chat-sandbox" in their names.

### Example Usage

```python
# Chat mode automatically handles format detection for compatibility
import openai

client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-api-key"
)

# Simple chat request - runs in complete isolation
response = client.chat.completions.create(
    model="claude-3-5-sonnet-20241022",
    messages=[
        {"role": "user", "content": "Write a Python function to calculate fibonacci numbers"}
    ]
)
# Claude will output the code in markdown blocks, cannot create files

# XML tool format automatically detected and supported
response = client.chat.completions.create(
    model="claude-3-5-sonnet-20241022",
    messages=[
        {"role": "system", "content": "Tool uses are formatted using XML-style tags..."},
        {"role": "user", "content": "Search for information about Python asyncio"}
    ]
)
# Claude will use the XML format if provided by the client
```

### Chat Mode vs Normal Mode

| Feature | Normal Mode | Chat Mode |
|---------|------------|-----------|
| File Operations | ✅ Available (when enabled) | ❌ Blocked |
| System Commands | ✅ Available (when enabled) | ❌ Blocked |
| Web Tools | ✅ Available | ✅ Available |
| Sessions | ✅ Supported | ❌ Disabled |
| Working Directory | Project directory | Temporary sandbox |
| Environment | Full environment | Sanitized environment |

### Use Cases

Chat mode is ideal for:
- **AI Coding Assistants**: Integration with tools like Roo Code, Cline, Cursor, and other AI coding assistants that expect OpenAI-compatible APIs
- **Public APIs**: Safely expose Claude as a chat service
- **Chat Applications**: Integration with chat clients that manage their own state
- **Restricted Environments**: When you need Claude's capabilities without system access
- **Multi-tenant Services**: Ensure complete isolation between requests
- **Development Tools**: IDEs and extensions that need AI assistance without file system access

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
   - SSE keepalive comments are sent every 30 seconds (configurable via `SSE_KEEPALIVE_INTERVAL`)
   - If you see connection timeouts after ~60 seconds, check your proxy/load balancer settings

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

## License

MIT License

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
