# Multi-stage build for Claude Code OpenAI Wrapper with GUI support

# Stage 1: Build Claude CLI
FROM node:20-alpine AS claude-cli
RUN npm install -g @anthropic-ai/claude-code

# Stage 2: Main container with Ubuntu GUI
FROM ubuntu:22.04

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Install base packages
RUN apt-get update && apt-get install -y \
    # X11 and desktop environment
    xvfb \
    x11vnc \
    xfce4 \
    xfce4-terminal \
    dbus-x11 \
    # Web browser for authentication
    firefox \
    # VNC and noVNC
    novnc \
    websockify \
    # Python and development tools
    python3.11 \
    python3.11-venv \
    python3-pip \
    python3-dev \
    build-essential \
    # Process management
    supervisor \
    # Utilities
    curl \
    wget \
    git \
    nano \
    htop \
    # Node.js (for Claude CLI)
    nodejs \
    npm \
    # Dependencies for browser automation
    libgtk-3-0 \
    libgbm-dev \
    libnss3 \
    libxss1 \
    libasound2 \
    # Clean up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy Claude CLI from stage 1
COPY --from=claude-cli /usr/local/lib/node_modules/@anthropic-ai/claude-code /usr/local/lib/node_modules/@anthropic-ai/claude-code
COPY --from=claude-cli /usr/local/bin/claude /usr/local/bin/claude

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Set up working directory
WORKDIR /app

# Copy application files
COPY pyproject.toml poetry.lock ./
COPY *.py ./
COPY examples ./examples/

# Install Python dependencies
ENV PATH="/root/.local/bin:$PATH"
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi

# Copy Docker-specific files
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker/entrypoint.sh /app/entrypoint.sh
COPY docker/auth_handler.py /app/auth_handler.py

# Make scripts executable
RUN chmod +x /app/entrypoint.sh

# Create necessary directories
RUN mkdir -p /config/claude /config/api /data /var/log/supervisor

# Configure noVNC
RUN ln -s /usr/share/novnc/vnc.html /usr/share/novnc/index.html

# Set up environment variables
ENV DISPLAY=:1
ENV RESOLUTION=1920x1080x24
ENV VNC_PASSWORD=changeme
ENV NOVNC_PORT=6080
ENV API_PORT=8000
ENV AUTH_METHOD=browser
ENV AUTO_LOGIN=true

# Expose ports
EXPOSE 8000 6080

# Set entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]