# Stage 1: Builder — install Poetry and dependencies
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# Copy dependency files first (cache-friendly)
COPY pyproject.toml poetry.lock ./

# Install dependencies into a virtualenv
RUN poetry config virtualenvs.in-project true && \
    poetry install --no-root --no-interaction

# Copy application code
COPY . .

# Install the project itself
RUN poetry install --no-interaction


# Stage 2: Runtime — minimal image with non-root user
FROM python:3.12-slim

# Install Node.js (required by Claude Agent SDK bundled CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --create-home appuser

WORKDIR /app

# Copy virtualenv and app code from builder (owned by appuser)
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/src /app/src
COPY --from=builder --chown=appuser:appuser /app/pyproject.toml /app/pyproject.toml

# Ensure virtualenv binaries are on PATH
ENV PATH="/app/.venv/bin:${PATH}"
ENV VIRTUAL_ENV="/app/.venv"

# Switch to non-root user
USER appuser

EXPOSE 8000

# Production CMD — no --reload
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
