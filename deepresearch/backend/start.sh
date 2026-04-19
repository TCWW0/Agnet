#!/usr/bin/env zsh
set -euo pipefail

# start.sh - lightweight startup helper for deepresearch backend (development)
# Usage:
#   bash start.sh
# The script will try to activate a top-level .venv if present, then run uvicorn.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PATH="$ROOT_DIR/../.venv"
ENV_FILE="$ROOT_DIR/backend/.env"

if [ -f "$VENV_PATH/bin/activate" ]; then
  echo "Activating virtualenv at $VENV_PATH"
  # shellcheck disable=SC1090
  source "$VENV_PATH/bin/activate"
fi

# If a backend .env exists, load it via a small Python wrapper to avoid
# Bash 'source' issues with non-shell .env formatting. This ensures the
# Python process will see the same environment variables when uvicorn starts.
if [ -f "$ENV_FILE" ]; then
  echo "Loading environment from $ENV_FILE and starting uvicorn..."
  python - <<PY
import os
from dotenv import load_dotenv
load_dotenv("${ENV_FILE}")
os.execvp("python", ["python", "-m", "uvicorn", "src.main:app", "--app-dir", "deepresearch/backend", "--reload", "--port", "8000"])
PY
  # python execvp replaces the process; we should never reach here
  exit 0
fi

echo "Starting DeepResearch backend (mode=${DEEPRESEARCH_CHAT_MODE:-mock}) on port 8000..."
exec python -m uvicorn src.main:app --app-dir deepresearch/backend --reload --port 8000
