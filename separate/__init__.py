"""Vocal separation seam.

``probe()`` is the single source of truth for which separators exist on this
machine. Separation is always optional: without one the face estimates the
voice from the full mix, and with one it stops guessing.

Results are cached, because separating a track costs far more than rendering
one and the answer does not change between renders.
"""

from __future__ import annotations

import os

from .base import (FAST, QUALITIES, SMOOTH, SeparationEngine,
                   SeparationUnavailable, cache_key)
from .demucs_engine import DemucsEngine
from .uvr import UvrEngine


ENGINES = (UvrEngine, DemucsEngine)
AUTOMATIC = "auto"

__all__ = ["ENGINES", "AUTOMATIC", "FAST", "SMOOTH", "QUALITIES",
           "SeparationEngine", "SeparationUnavailable", "probe", "available",
           "resolve", "create", "separated_vocal", "install_summary",
           "mix_fallback_hint"]


def probe():
    """Describe every separator, best automatic choice first."""
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
        raise SeparationUnavailable(f"Unknown separation engine {name!r}")
    usable = available()
    if not usable:
        raise SeparationUnavailable(install_summary())
    return usable[0]


def create(name=AUTOMATIC, **options):
    """Instantiate a separator, or raise with a usable reason."""
    engine = resolve(name)
    ready, reason = engine.availability()
    if not ready:
        raise SeparationUnavailable(
            f"{engine.label} is not available: {reason}. "
            f"Install it with: {engine.install_hint}")
    return engine(**options)


def separated_vocal(audio_path, cache_dir, name=AUTOMATIC, quality=FAST,
                    progress=None, model_dir=None):
    """Path to a vocals-only rendering of ``audio_path``, separating if needed.

    A previous result for the same file is reused: separation is the slowest
    thing here by a wide margin, and re-rendering a track with different
    colours should not pay for it twice.
    """
    engine = create(name, model_dir=model_dir)
    os.makedirs(cache_dir, exist_ok=True)
    out_path = os.path.join(
        cache_dir, cache_key(audio_path, quality, engine.name))
    if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
        if progress:
            progress(1.0, "Reusing the separated vocal from an earlier run")
        return out_path, True
    engine.separate(audio_path, out_path, quality=quality, progress=progress)
    return out_path, False


def install_summary():
    """What to install when nothing is available."""
    return ("No vocal separator is installed. Install one with:  "
            "pip install 'audio-separator[cpu]' audioread  — the face will "
            "otherwise estimate the voice from the full mix.")


def mix_fallback_hint(requested=False):
    """Why the voice is being guessed from the mix, and what would fix it.

    Three different situations end up here and each needs different advice:
    separation was never asked for but is installed, it was never asked for
    and is not installed, or it was asked for and could not run. Telling
    someone to install what they already have is worse than saying nothing.
    """
    usable = available()
    if not usable:
        return install_summary()
    if not requested:
        return (f"{usable[0].label} is installed — turn vocal separation on "
                f"to measure the voice exactly instead of estimating it.")
    return (f"{usable[0].label} is installed but produced no stem for this "
            f"track, so the voice was estimated from the mix.")
