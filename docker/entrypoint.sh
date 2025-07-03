#!/bin/bash
set -e

echo "Starting Claude Code OpenAI Wrapper Docker Container..."

# Create VNC password directory
mkdir -p /root/.vnc

# Set VNC password
if [ ! -f /root/.vnc/passwd ]; then
    echo "Setting VNC password..."
    x11vnc -storepasswd "${VNC_PASSWORD}" /root/.vnc/passwd
fi

# Create config directories if they don't exist
mkdir -p /config/claude /config/api /data

# Check if we need to restore Claude authentication
if [ -f "/config/claude/.claude_auth" ]; then
    echo "Restoring Claude authentication..."
    mkdir -p /root/.config/claude
    cp -r /config/claude/.claude_auth /root/.config/claude/
fi

# Set up environment for Claude CLI
export CLAUDE_HOME=/config/claude
export HOME=/root

# Configure API settings from environment
if [ -n "${API_KEY}" ]; then
    export API_KEY="${API_KEY}"
fi

# Set authentication method
if [ -n "${ANTHROPIC_API_KEY}" ]; then
    echo "Using direct API key authentication"
    export AUTH_METHOD="api_key"
elif [ -n "${CLAUDE_CODE_USE_BEDROCK}" ]; then
    echo "Using AWS Bedrock authentication"
    export AUTH_METHOD="bedrock"
elif [ -n "${CLAUDE_CODE_USE_VERTEX}" ]; then
    echo "Using Google Vertex AI authentication"
    export AUTH_METHOD="vertex"
else
    echo "Using browser-based Claude authentication"
    export AUTH_METHOD="browser"
fi

# Check if we need to test Claude authentication
if [ "${AUTH_METHOD}" = "browser" ] && [ ! -f "/config/claude/.auth_verified" ]; then
    echo "Browser authentication required on first run"
    touch /tmp/need_auth
fi

# Start supervisor to manage all services
echo "Starting services..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf