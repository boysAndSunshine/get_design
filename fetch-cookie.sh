#!/bin/bash
# Auto-capture Lanhu Cookie via Playwright browser login
set -e
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "Virtual environment not found. Run easy-install.sh or create venv first."
  exit 1
fi

VENV_PY="$(pwd)/venv/bin/python"
if ! "$VENV_PY" -c "import httpx" 2>/dev/null; then
  echo "Installing cookie capture dependencies into venv..."
  "$VENV_PY" -m pip install -q httpx playwright python-dotenv
  "$VENV_PY" -m playwright install chromium
fi
exec "$VENV_PY" lanhu_cookie_auth.py "$@"
