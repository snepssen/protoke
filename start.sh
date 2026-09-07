#!/bin/sh
# Linux/macOS launcher. Prefers ./.venv so an installed transcription engine
# is picked up, then falls back to whichever Python 3 is on PATH.
cd "$(dirname "$0")" || exit 1
if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python app.py "$@"
fi
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    exec "$candidate" app.py "$@"
  fi
done
echo "Python 3.10 or newer is required but was not found on PATH." >&2
exit 1
