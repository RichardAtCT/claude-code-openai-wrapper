#!/usr/bin/env bash
set -e

VENV_DIR=".venv"

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

pip install --upgrade pip
pip install -e ".[dev]" 2>/dev/null || pip install -e .

echo "Done. To activate: source $VENV_DIR/bin/activate"
