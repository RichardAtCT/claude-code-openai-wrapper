#!/bin/bash
# Test script to verify working directory configuration in Docker

echo "Testing Docker workspace configuration..."
echo "========================================="

# Test 1: Default (temp directory)
echo -e "\n1. Testing default configuration (isolated temp dir):"
docker run --rm \
  -v ~/.claude:/root/.claude \
  claude-wrapper:test \
  poetry run python -c "from claude_cli import ClaudeCodeCLI; cli = ClaudeCodeCLI(); print(f'Working directory: {cli.cwd}'); print(f'Is temp dir: {cli.temp_dir is not None}')"

# Test 2: With CLAUDE_CWD environment variable
echo -e "\n2. Testing with CLAUDE_CWD environment variable:"
docker run --rm \
  -v ~/.claude:/root/.claude \
  -e CLAUDE_CWD=/app \
  claude-wrapper:test \
  poetry run python -c "import os; from claude_cli import ClaudeCodeCLI; cli = ClaudeCodeCLI(cwd=os.getenv('CLAUDE_CWD')); print(f'Working directory: {cli.cwd}'); print(f'Is temp dir: {cli.temp_dir is not None}')"

# Test 3: With mounted workspace
echo -e "\n3. Testing with mounted workspace:"
mkdir -p /tmp/test_workspace
docker run --rm \
  -v ~/.claude:/root/.claude \
  -v /tmp/test_workspace:/workspace \
  -e CLAUDE_CWD=/workspace \
  claude-wrapper:test \
  poetry run python -c "import os; from claude_cli import ClaudeCodeCLI; cli = ClaudeCodeCLI(cwd=os.getenv('CLAUDE_CWD')); print(f'Working directory: {cli.cwd}'); print(f'Directory exists: {os.path.exists(cli.cwd)}')"

echo -e "\n========================================="
echo "Docker workspace tests complete!"