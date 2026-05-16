#!/bin/bash
# Export AI-friendly design blueprint JSON from Lanhu
set -e
cd "$(dirname "$0")"
if [ ! -d "venv" ]; then
  echo "Run easy-install.sh or create venv first."
  exit 1
fi
source venv/bin/activate
python export_design_blueprint.py "$@"
