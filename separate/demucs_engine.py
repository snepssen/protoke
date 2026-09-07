"""Vocal separation through a plain Demucs install.

A fallback for a machine that already has Demucs but not audio-separator.
Demucs only ships its own models, so the quality setting has nothing to choose
between here — it always runs the fast one.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys

from .base import FAST, SeparationEngine, SeparationUnavailable


MODEL = "htdemucs"


class DemucsEngine(SeparationEngine):
    name = "demucs"
    label = "Demucs"
    detail = "Fast, some backing left in the vocal"
    install_hint = "pip install demucs"
    priority = 20

    @classmethod
    def availability(cls):
        if importlib.util.find_spec("demucs") is None:
            return False, "demucs is not installed"
        return True, ""

    def __init__(self, model_dir=None, **_ignored):
        available, reason = self.availability()
        if not available:
            raise SeparationUnavailable(reason)
        self.model_dir = model_dir

    def separate(self, audio_path, out_path, quality=FAST, progress=None):
        out_dir = os.path.dirname(out_path) or "."
        work = os.path.join(out_dir, ".demucs")
        os.makedirs(work, exist_ok=True)
        if progress:
            progress(0.05, f"Separating with Demucs ({MODEL})")

        command = [sys.executable, "-m", "demucs", "--two-stems", "vocals",
                   "-n", MODEL, "-o", work, audio_path]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            shutil.rmtree(work, ignore_errors=True)
            tail = (result.stderr or "").strip().splitlines()[-3:]
            raise SeparationUnavailable(
                "Demucs failed: " + " / ".join(tail))

        produced = None
        for root, _, names in os.walk(work):
            for name in names:
                if name.lower().startswith("vocals."):
                    produced = os.path.join(root, name)
        if not produced:
            shutil.rmtree(work, ignore_errors=True)
            raise SeparationUnavailable("Demucs wrote no vocals stem")
        os.replace(produced, out_path)
        shutil.rmtree(work, ignore_errors=True)
        if progress:
            progress(1.0, "Vocal separated")
        return out_path
