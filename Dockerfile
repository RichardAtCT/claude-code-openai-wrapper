# Using official Python slim image for a smaller footprint
FROM python:3.13.0-slim

# Set username from build argument
ARG BUILD_USER=appuser
ENV USER=$BUILD_USER \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Derive APP_HOME from USER
ENV APP_HOME=/home/$USER

RUN apt-get update && apt-get install --no-install-recommends -y \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash $USER

# Install Node.js and npm for Claude Code CLI
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /usr/bin/node /usr/local/bin/node \
    && ln -s /usr/bin/npm /usr/local/bin/npm

# Install Claude Code CLI globally with proper permissions
RUN npm install -g @anthropic-ai/claude-code \
    && chmod -R 755 /usr/lib/node_modules \
    && chmod -R 755 /usr/bin/claude* || true


# Download the latest installer
COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /uvx /bin/

# Set application directory and working directory
ENV APP_DIR=$APP_HOME
WORKDIR $APP_DIR

# Create a virtual environment in user space
ENV VIRTUAL_ENV=$APP_HOME/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV UV_PROJECT_ENVIRONMENT=$VIRTUAL_ENV

# Print debug information
RUN echo "Configuration: USER=$USER, APP_HOME=$APP_HOME, APP_DIR=$APP_DIR"

# Create virtual environment
RUN uv venv $VIRTUAL_ENV

RUN --mount=type=cache,target=/home/$USER/.cache/uv \
    --mount=type=bind,source=./uv.lock,target=uv.lock \
    --mount=type=bind,source=./pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project

# Copy only necessary files
COPY pyproject.toml $APP_DIR/
COPY uv.lock $APP_DIR/
COPY *.py $APP_DIR/
COPY README.md $APP_DIR/

RUN --mount=type=cache,target=/home/$USER/.cache/uv \
    uv sync --frozen

ENV PYTHONPATH=$APP_DIR

RUN chown -R "$USER":"$USER" $APP_DIR
USER $USER

# Final debug output
RUN echo "Final configuration - APP_HOME: $APP_HOME, USER: $USER, APP_DIR: $APP_DIR"

# Test Node.js and Claude CLI are available
RUN which node && node --version || echo "Node.js not found in PATH"
RUN which claude && claude --version || echo "Claude CLI not found in PATH"

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]