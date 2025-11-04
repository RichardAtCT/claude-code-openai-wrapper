FROM python:3.12-slim

# Install system deps for Node.js and general utils
RUN apt-get update && apt-get install -y \
    curl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry globally
RUN curl -sSL https://install.python-poetry.org | python3 -

# Add Poetry to PATH
ENV PATH="/root/.local/bin:${PATH}"

# Install Claude Code CLI globally (for SDK compatibility)
RUN npm install -g @anthropic-ai/claude-code

# Copy the app code
COPY . /app

# Set working directory
WORKDIR /app

# Install Python dependencies with Poetry
RUN poetry install --no-root

# Expose the port (default 8000)
EXPOSE 8000

# Run the app with Uvicorn (development mode with reload; switch to --no-reload for prod)
CMD ["poetry", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]