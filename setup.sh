#!/bin/sh
# Install everything Protoke needs without asking: ffmpeg with libass where
# the package manager needs no root (Homebrew), and ./.venv with the Parakeet
# transcription engine. Re-running it is safe and upgrades the engine.
#   ./setup.sh --with-separation   also vocal separation (PyTorch, ~1 GB)
cd "$(dirname "$0")" || exit 1
for candidate in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    python="$candidate"
    break
  fi
done
if [ -z "${python:-}" ]; then
  echo "Python 3.10 or newer is required but was not found on PATH." >&2
  exit 1
fi
# A root-needing ffmpeg is printed, not run, so carry on to what follows.
"$python" bootstrap.py --yes "$@"
[ -x .venv/bin/python ] || exit 1
echo
.venv/bin/python app.py --engines
echo
.venv/bin/python app.py --separators
echo
echo "Setup complete. Start the app with:  ./start.sh"
case " $* " in
  *" --with-separation "*) ;;
  *)
    echo
    echo "The face can follow singing that has no words in the lyric sheet."
    echo "For that it needs to isolate the voice, which is a ~1 GB install:"
    echo "  ./setup.sh --with-separation"
    ;;
esac
