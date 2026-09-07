#!/bin/sh
# One-time setup: create ./.venv and install the portable Parakeet engine.
# Re-running it is safe and upgrades the engine in place.
cd "$(dirname "$0")" || exit 1

python=""
for candidate in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    python="$candidate"
    break
  fi
done
if [ -z "$python" ]; then
  echo "Python 3.10 or newer is required but was not found on PATH." >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Creating .venv with $python"
  "$python" -m venv .venv || exit 1
fi

echo "Installing the Parakeet (ONNX) transcription engine"
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install "onnx-asr[cpu,hub]" || exit 1

# A desktop window instead of a browser tab. Small enough not to be worth
# asking about: it uses the operating system's own webview.
.venv/bin/python -m pip install pywebview >/dev/null 2>&1 || \
  echo "Desktop window unavailable; the app will open in your browser."

# Apple silicon gets the faster MLX engine as well; the probe prefers it.
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
  echo "Apple silicon detected — also installing the MLX fast path"
  .venv/bin/python -m pip install parakeet-mlx || \
    echo "MLX engine install failed; the ONNX engine will be used instead."
fi

# Vocal separation is optional and heavy — it pulls PyTorch, around a
# gigabyte — so it is only installed when explicitly asked for.
if [ "$1" = "--with-separation" ]; then
  echo "Installing vocal separation (this downloads PyTorch, ~1 GB)"
  .venv/bin/python -m pip install "audio-separator[cpu]" audioread || \
    echo "Separation install failed; the voice will be estimated from the mix."
fi

echo
.venv/bin/python app.py --engines
echo
.venv/bin/python app.py --separators
echo
echo "Setup complete. Start the app with:  ./start.sh"
if [ "$1" != "--with-separation" ]; then
  echo
  echo "The face can follow singing that has no words in the lyric sheet."
  echo "For that it needs to isolate the voice, which is a ~1 GB install:"
  echo "  ./setup.sh --with-separation"
fi
