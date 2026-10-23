#!/bin/sh
# Linux/macOS launcher. Offers to install anything missing first, then
# prefers ./.venv so the installed transcription engine is picked up.
#
# The check is separate from the offer on purpose: somebody who already has
# everything should see the window, not a question.
cd "$(dirname "$0")" || exit 1
for candidate in python3 python; do
  command -v "$candidate" >/dev/null 2>&1 || continue
  if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "${PYTHON:-}" ]; then
  echo "Python 3.10 or newer is required but was not found on PATH." >&2
  exit 1
fi
if ! "$PYTHON" bootstrap.py --check; then
  "$PYTHON" bootstrap.py || exit 1
fi
if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python app.py "$@"
fi
exec "$PYTHON" app.py "$@"
