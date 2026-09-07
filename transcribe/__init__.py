"""Transcription engine seam.

``probe()`` is the single source of truth for which engines exist on this
machine. Nothing else in the tool hard-codes a transcriber, so adding or
removing a backend is a change in one place, and the UI can only ever offer
engines that will actually run.
"""

from __future__ import annotations

from .base import (EngineUnavailable, TranscriptionEngine, existing_transcript,
                   normalise_words, words_from_payload)
from .macwhisper import MacWhisperEngine
from .mlx_parakeet import MlxParakeetEngine
from .onnx_parakeet import OnnxParakeetEngine
from .whisper_engine import FasterWhisperEngine


ENGINES = (MlxParakeetEngine, OnnxParakeetEngine, MacWhisperEngine,
           FasterWhisperEngine)

AUTOMATIC = "auto"

__all__ = ["ENGINES", "AUTOMATIC", "EngineUnavailable", "TranscriptionEngine",
           "probe", "resolve", "create", "transcribe", "existing_transcript",
           "normalise_words", "words_from_payload", "install_summary"]


def probe():
    """Describe every engine, best automatic choice first."""
    ordered = sorted(ENGINES, key=lambda engine: engine.priority)
    return [engine.describe() for engine in ordered]


def available():
    """Just the engine classes that can run here, in preference order."""
    return [engine for engine in sorted(ENGINES,
                                        key=lambda item: item.priority)
            if engine.availability()[0]]


def resolve(name=AUTOMATIC):
    """Engine class for a name, or the best available one for 'auto'."""
    if name and name != AUTOMATIC:
        for engine in ENGINES:
            if engine.name == name:
                return engine
        raise EngineUnavailable(f"Unknown transcription engine {name!r}")
    usable = available()
    if not usable:
        raise EngineUnavailable(install_summary())
    return usable[0]


def create(name=AUTOMATIC, **options):
    """Instantiate an engine, raising EngineUnavailable with a usable reason."""
    engine = resolve(name)
    ready, reason = engine.availability()
    if not ready:
        raise EngineUnavailable(
            f"{engine.label} is not available: {reason}. "
            f"Install it with: {engine.install_hint}")
    return engine(**options)


def transcribe(audio_path, name=AUTOMATIC, progress=None, **options):
    """Word records for one audio file using the chosen or best engine."""
    engine = create(name, **options)
    return normalise_words(engine.transcribe(audio_path, progress=progress))


def install_summary():
    """What to install when nothing is available — the portable one first."""
    return ("No transcription engine is installed. Install the portable "
            "default with:  pip install 'onnx-asr[cpu,hub]'  — or supply a "
            "timed JSON file beside each audio track.")
