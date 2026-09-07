"""Shared contract for vocal-separation backends.

Separation is the heaviest thing this tool can be asked to do, so nothing here
is required: the probe reports what is installed, and the face falls back to
estimating the voice from the full mix when nothing is.

Weights are never bundled. They are downloaded on first use and cached, the
same arrangement the transcription engines use.
"""

from __future__ import annotations

import hashlib
import os


class SeparationUnavailable(RuntimeError):
    """Raised when an engine is asked to work but its runtime is missing."""


#: What the separation is for. The face only needs to know where the voice is
#: and how loud, so a fast model with some backing leaking through is worth
#: more than a slow one that is clean.
FAST = "fast"
SMOOTH = "smooth"
QUALITIES = (FAST, SMOOTH)


class SeparationEngine:
    """Subclasses fill in the metadata and implement ``separate``.

    Constructors take engine-specific options as keyword arguments and must
    accept ``**_ignored``: the caller passes every engine's options to
    whichever engine it built.
    """

    name = "base"
    label = "Base"
    detail = ""
    install_hint = ""
    #: lower sorts earlier when resolving the automatic choice
    priority = 100

    @classmethod
    def availability(cls):
        """Return ``(available, reason)``. ``reason`` explains a False."""
        raise NotImplementedError

    @classmethod
    def describe(cls):
        available, reason = cls.availability()
        return {
            "name": cls.name,
            "label": cls.label,
            "detail": cls.detail,
            "available": available,
            "reason": "" if available else reason,
            "installHint": cls.install_hint,
        }

    def separate(self, audio_path, out_path, quality=FAST, progress=None):
        """Write a vocals-only rendering of ``audio_path`` to ``out_path``."""
        raise NotImplementedError


def cache_key(audio_path, quality, engine):
    """A name for this track's separated vocal, stable across runs.

    Keyed on the file's identity rather than its contents: hashing a hundred
    megabytes to decide whether to skip a job that takes a minute is a poor
    trade, and a track that is edited changes size or modification time.
    """
    try:
        stat = os.stat(audio_path)
        identity = f"{os.path.abspath(audio_path)}:{stat.st_size}:{int(stat.st_mtime)}"
    except OSError:
        identity = os.path.abspath(audio_path)
    digest = hashlib.sha256(
        f"{identity}:{quality}:{engine}".encode()).hexdigest()[:16]
    stem = os.path.splitext(os.path.basename(audio_path))[0][:60]
    return f"{stem}-{digest}.wav"
