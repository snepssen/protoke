"""Parakeet through MLX — the Apple silicon fast path.

Same model family as the ONNX engine, but running on the Mac's unified memory
and GPU. Only ever available on Apple silicon, so it is an accelerator for one
platform rather than the portable default.
"""

from __future__ import annotations

import importlib.util
import platform
import sys

from .base import TranscriptionEngine, EngineUnavailable, normalise_words


DEFAULT_MODEL = "mlx-community/parakeet-tdt-0.6b-v2"


class MlxParakeetEngine(TranscriptionEngine):
    name = "mlx-parakeet"
    label = "Parakeet (MLX)"
    detail = "Apple silicon only · fastest on this Mac"
    install_hint = "pip install parakeet-mlx"
    priority = 10

    @classmethod
    def availability(cls):
        if sys.platform != "darwin" or platform.machine() != "arm64":
            return False, "Requires Apple silicon"
        if importlib.util.find_spec("parakeet_mlx") is None:
            return False, "parakeet-mlx is not installed"
        return True, ""

    def __init__(self, ffmpeg=None, model=DEFAULT_MODEL, **_ignored):
        available, reason = self.availability()
        if not available:
            raise EngineUnavailable(reason)
        self.model_name = model or DEFAULT_MODEL
        self.ffmpeg = ffmpeg

    def transcribe(self, audio_path, progress=None):
        from parakeet_mlx import from_pretrained

        if progress:
            progress(0.06, f"Loading {self.model_name}")
        model = from_pretrained(self.model_name)
        if progress:
            progress(0.15, "Transcribing with MLX")
        result = model.transcribe(audio_path)

        words = []
        for sentence in getattr(result, "sentences", []) or []:
            for token in getattr(sentence, "tokens", []) or []:
                words.append({"text": getattr(token, "text", ""),
                              "start": getattr(token, "start", 0.0),
                              "end": getattr(token, "end", 0.0)})
        if not words:
            raise EngineUnavailable(
                "parakeet-mlx returned no word timings for this track")
        if progress:
            progress(1.0, f"Transcribed {len(words)} words")
        return normalise_words(_join_subwords(words))


def _join_subwords(words):
    """parakeet-mlx emits sub-word tokens with a leading space on word starts."""
    joined = []
    for word in words:
        raw = str(word.get("text", ""))
        text = raw.replace("▁", " ")
        if not text.strip():
            continue
        if joined and not (text.startswith(" ") or raw.startswith("▁")):
            joined[-1]["text"] += text.strip()
            joined[-1]["end"] = word["end"]
        else:
            joined.append({"text": text.strip(),
                           "start": word["start"], "end": word["end"]})
    return joined
