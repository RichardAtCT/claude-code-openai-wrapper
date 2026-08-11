#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

screen -dmS claude-wrapper bash -c "
  source '$PROJECT_DIR/.venv/bin/activate'
  cd '$PROJECT_DIR'
  python -m uvicorn src.main:app --host 0.0.0.0 --port 6969
"

echo "Server started in screen session 'claude-wrapper' on port 6969"
echo "Attach with: screen -r claude-wrapper"
