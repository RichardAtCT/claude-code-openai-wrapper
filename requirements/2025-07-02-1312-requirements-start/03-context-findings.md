# Context Findings

## Current Codebase Analysis

### Authentication System
- **Current Methods Supported:**
  - Claude CLI auth (`claude auth login`) - stores credentials locally
  - Direct API key via `ANTHROPIC_API_KEY`
  - AWS Bedrock enterprise auth
  - Google Vertex AI auth
- **Key Files:**
  - `auth.py`: Authentication manager and validation
  - `claude_cli.py`: Claude Code SDK integration

### No Docker Support Currently
- No Dockerfile or docker-compose.yml exists
- No containerization references in codebase
- Application is containerization-ready (uses env vars, standard web patterns)

### No GUI/Browser Dependencies
- Current auth uses CLI commands only
- No browser automation or OAuth flows
- Interactive API key prompt uses terminal input

### Key Dependencies
- **Python**: FastAPI web server
- **Node.js/npm**: Required for Claude Code CLI
- **Claude Code CLI**: `@anthropic-ai/claude-code` npm package
- **Claude Code SDK**: Python SDK v0.0.14

## Research on Docker GUI Solutions

### Ubuntu Desktop in Docker (Webtop)
- **LinuxServer.io Webtop**: Full Ubuntu desktop in browser
- Accessible via web browser (VNC/noVNC)
- Can run GUI applications including web browsers
- Perfect for Unraid deployment

### Browser Automation Options
1. **Headless Chrome/Firefox in Docker**
   - Can be integrated for automated login flows
   - Puppeteer/Playwright support available
   
2. **Claude Computer Use Docker**
   - Anthropic provides Docker images with browser automation
   - Includes visual automation capabilities
   - Could be adapted for auth flows

### Unraid-Specific Considerations
1. **Storage**: Use `/mnt/user/appdata/` for persistent data
2. **Networking**: Bridge mode or custom Docker networks
3. **GUI Access**: Typically via VNC ports (5900/6080)
4. **Community Apps**: Can create Unraid template for easy deployment

## Technical Constraints

### Authentication Challenges
1. **Claude CLI Auth Storage**
   - Credentials stored in user home directory
   - Would need volume mount for persistence
   - Or switch to environment-based auth

2. **Browser-Based Login Requirements**
   - Claude auth login opens browser for OAuth
   - Needs display server (X11/Wayland) or virtual display
   - Can use Xvfb or full desktop environment

### Docker Multi-Stage Build Needed
```dockerfile
# Stage 1: Node.js for Claude CLI
FROM node:20-alpine AS claude-cli
RUN npm install -g @anthropic-ai/claude-code

# Stage 2: Python app with Ubuntu GUI
FROM ubuntu:22.04
# Install desktop environment, Python, etc.
```

## Integration Points

### Files That Need Modification
1. **New Files to Create:**
   - `Dockerfile`: Multi-stage build with GUI support
   - `docker-compose.yml`: Service configuration
   - `docker/entrypoint.sh`: Handle auth and startup
   - `docker/supervisord.conf`: Process management
   
2. **Existing Files to Modify:**
   - `auth.py`: Add browser-based auth support
   - `claude_cli.py`: Handle Docker environment
   - `README.md`: Add Docker instructions
   - `.env.example`: Docker-specific variables

### Environment Variables for Docker
```env
# Display settings for GUI
DISPLAY=:1
VNC_PASSWORD=changeme
RESOLUTION=1920x1080

# Claude auth method selection
AUTH_METHOD=browser|api_key|cli
ANTHROPIC_API_KEY=sk-ant-...

# Persistent storage paths
CLAUDE_AUTH_PATH=/config/claude
```

## Similar Features Analyzed

### Docker Implementations Found
1. **deepworks-net/docker.claude-code**
   - Windows-focused but adaptable
   - Handles permissions and mounts
   - No GUI support

2. **VishalJ99/claude-docker**
   - Basic Claude in Docker
   - No browser auth support

3. **Claude Computer Use Docker**
   - Has browser automation
   - Could be reference for auth flow

## Best Practices from Research

1. **Security**: Run browser in isolated container
2. **Performance**: Use lightweight desktop (XFCE/LXDE)
3. **Persistence**: Mount volumes for auth tokens
4. **Networking**: Use Docker networks for service communication
5. **Logging**: Centralize logs for debugging auth issues