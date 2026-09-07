#!/bin/bash
# macOS launcher. Uses ./.venv when it exists so an installed transcription
# engine is picked up; otherwise falls back to the system Python.
cd "$(dirname "$0")" || exit 1
if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python app.py "$@"
fi
exec python3 app.py "$@"
