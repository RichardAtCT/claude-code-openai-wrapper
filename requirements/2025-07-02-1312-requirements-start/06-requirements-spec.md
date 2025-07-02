# Docker Ubuntu GUI Requirements Specification

## Problem Statement
The Claude Code OpenAI wrapper needs to run in a Docker container on Unraid with GUI support for browser-based Claude authentication. Currently, the application only supports CLI-based authentication which doesn't work well in containerized environments where browser access is needed for OAuth flows.

## Solution Overview
Create a Docker container with Ubuntu and XFCE desktop environment that:
1. Runs the Claude Code OpenAI wrapper API server
2. Provides web-based GUI access via noVNC
3. Automatically handles Claude browser authentication
4. Persists authentication between container restarts
5. Includes an Unraid Community App template for easy deployment

## Functional Requirements

### FR1: Docker Container with GUI
- Ubuntu 22.04 base with XFCE lightweight desktop
- Web-based access via noVNC on port 6080
- No VNC client required - access through web browser
- Firefox pre-installed for authentication flows

### FR2: Automated Authentication Flow
- Detect when Claude authentication is needed
- Automatically launch Firefox with authentication URL
- Handle OAuth callback and token storage
- Support fallback to API key authentication

### FR3: Service Management
- Supervisor to manage multiple processes:
  - XFCE desktop environment
  - noVNC web server
  - Claude Code OpenAI wrapper API
  - Authentication helper service
- Automatic service startup on container launch

### FR4: Persistence
- Mount volumes for:
  - `/config/claude` - Authentication tokens
  - `/config/api` - API configuration
  - `/data` - User data/projects
- Credentials survive container updates/restarts

### FR5: Unraid Integration
- Community App XML template
- Pre-configured paths and ports
- Environment variable configuration
- Clear documentation for users

## Technical Requirements

### TR1: Multi-Stage Dockerfile
```dockerfile
# Stage 1: Node.js for Claude CLI
FROM node:20-alpine AS claude-cli
RUN npm install -g @anthropic-ai/claude-code

# Stage 2: Ubuntu with GUI
FROM ubuntu:22.04
# Install XFCE, Python, Firefox, noVNC, etc.
```

### TR2: File Structure
```
docker/
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
├── supervisord.conf
├── auth_handler.py
└── unraid/
    └── claude-code-wrapper.xml
```

### TR3: Modified Authentication Flow
- Extend `auth.py` to support browser-based auth
- Add `BrowserAuthManager` class
- Detect Docker environment and use appropriate auth method
- Handle headless browser automation if needed

### TR4: Environment Variables
```env
# GUI Configuration
DISPLAY=:1
VNC_PASSWORD=secure_password
RESOLUTION=1920x1080
NOVNC_PORT=6080

# Authentication
AUTH_METHOD=browser
ANTHROPIC_API_KEY=sk-ant-... (optional fallback)
AUTO_LOGIN=true

# API Configuration  
API_PORT=8000
API_KEY=optional_api_protection
```

### TR5: Network Configuration
- Bridge network mode for Unraid
- Exposed ports:
  - 8000: API server
  - 6080: noVNC web interface
- Internal ports:
  - 5900: VNC server (not exposed)

## Implementation Hints

### Authentication Handler (`docker/auth_handler.py`)
```python
# Monitor for authentication needs
# Launch browser with Selenium/Playwright
# Handle OAuth callback
# Store tokens in persistent location
```

### Supervisor Configuration
```ini
[program:xvfb]
command=/usr/bin/Xvfb :1 -screen 0 %(ENV_RESOLUTION)s

[program:desktop]
command=/usr/bin/startxfce4

[program:novnc]
command=/usr/share/novnc/utils/launch.sh

[program:api-server]
command=poetry run python main.py
```

### Unraid Template Key Fields
- Repository: `your-docker-hub/claude-code-wrapper`
- WebUI: `http://[IP]:[PORT:6080]/`
- Volumes: `/mnt/user/appdata/claude-code-wrapper`
- Network: Bridge
- Privileged: No (use security opts if needed)

## Acceptance Criteria

### AC1: Container Functionality
- [ ] Container builds successfully with all dependencies
- [ ] noVNC accessible at http://localhost:6080
- [ ] API server accessible at http://localhost:8000
- [ ] All services start automatically

### AC2: Authentication Flow
- [ ] Browser opens automatically when auth needed
- [ ] Claude login completes successfully
- [ ] Tokens persist in mounted volume
- [ ] API key fallback works if browser auth fails

### AC3: Unraid Deployment
- [ ] Community App template installs with one click
- [ ] All paths and ports pre-configured
- [ ] Clear instructions in template description
- [ ] Container updates preserve authentication

### AC4: API Compatibility
- [ ] All existing API endpoints work unchanged
- [ ] OpenAI client libraries connect successfully
- [ ] Streaming responses function properly
- [ ] Session management works as expected

### AC5: Performance
- [ ] Container uses < 2GB RAM idle
- [ ] GUI responsive through noVNC
- [ ] API response times unchanged from native
- [ ] Startup time < 30 seconds

## Assumptions
1. Users have Unraid 6.9+ with Docker support
2. Users will access GUI only for initial authentication
3. Container will run on x86_64 architecture
4. Network connectivity available for Claude API
5. Users understand basic Docker/Unraid concepts

## Future Enhancements (Out of Scope)
- ARM64 support
- Multiple user authentication
- Kubernetes deployment
- Windows container variant
- Mobile-friendly noVNC interface