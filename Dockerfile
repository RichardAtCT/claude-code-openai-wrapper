FROM python:3.12-slim

# Install uv by copying its static binaries from the official image (pinned tag).
# Keep this version in sync with the `version:` pin in .github/workflows/ci.yml so
# lockfile resolution behaves identically in CI and Docker builds.
COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /bin/

# Copy files into the container as the root user by default.
ENV UV_LINK_MODE=copy

# Note: Claude Code CLI is bundled with claude-agent-sdk >= 0.1.8
# No separate Node.js/npm installation required

# Copy the app code
COPY . /app

# Set working directory
WORKDIR /app

# Install Python dependencies with uv into a project-local virtual environment.
# `--locked` fails the build if uv.lock is out of date with pyproject.toml (rather than
# silently using a stale lock); `--no-dev` skips dev-only tooling.
RUN uv sync --locked --no-dev

# Expose the port (default 8000)
EXPOSE 8000

# Run the app with Uvicorn (development mode with reload; switch to --no-reload for prod)
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
