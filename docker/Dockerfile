# Dockerfile for Claude Code OpenAI Wrapper with GUI support
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
    # Snap support for Firefox
    snapd \
    squashfs-tools \
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
    software-properties-common \
    # Dependencies for browser automation
    libgtk-3-0 \
    libgbm-dev \
    libnss3 \
    libxss1 \
    libasound2 \
    # Browser alternatives
    chromium-browser \
    # Clean up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Firefox via Mozilla PPA as a fallback
RUN add-apt-repository -y ppa:mozillateam/ppa && \
    echo 'Package: *\nPin: release o=LP-PPA-mozillateam\nPin-Priority: 1001' | tee /etc/apt/preferences.d/mozilla-firefox && \
    apt-get update && \
    apt-get install -y firefox && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Node.js 20 from NodeSource
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Claude CLI directly in this stage
RUN npm install -g @anthropic-ai/claude-code

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Set up working directory
WORKDIR /app

# Copy application files
COPY pyproject.toml ./
# Copy poetry.lock if it exists (make it optional for now)
COPY poetry.loc[k] ./
COPY *.py ./
COPY examples ./examples/

# Copy README.md if it exists (needed by poetry)
COPY README.m[d] ./

# Copy API documentation files
COPY openapi.yaml ./
COPY swagger-ui.html ./

# Install Python dependencies
ENV PATH="/root/.local/bin:$PATH"
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --no-root

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