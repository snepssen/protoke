"""faster-whisper fallback.

A different model family to Parakeet, kept as a safety net: it installs
cleanly almost anywhere, has well-tested word timestamps, and covers the case
where a user cannot get the Parakeet weights.
"""

from __future__ import annotations

import importlib.util

from .base import TranscriptionEngine, EngineUnavailable, normalise_words


DEFAULT_MODEL = "medium"


class FasterWhisperEngine(TranscriptionEngine):
    name = "faster-whisper"
    label = "Whisper (faster-whisper)"
    detail = "Fallback · slower than Parakeet on CPU"
    install_hint = "pip install faster-whisper"
    priority = 40

    @classmethod
    def availability(cls):
        if importlib.util.find_spec("faster_whisper") is None:
            return False, "faster-whisper is not installed"
        return True, ""

    def __init__(self, ffmpeg=None, model=DEFAULT_MODEL, **_ignored):
        available, reason = self.availability()
        if not available:
            raise EngineUnavailable(reason)
        self.model_name = model or DEFAULT_MODEL
        self.ffmpeg = ffmpeg

    def transcribe(self, audio_path, progress=None):
        from faster_whisper import WhisperModel

        if progress:
            progress(0.06, f"Loading Whisper {self.model_name}")
        model = WhisperModel(self.model_name, device="auto",
                             compute_type="int8")
        segments, info = model.transcribe(audio_path, word_timestamps=True,
                                          vad_filter=True)
        duration = getattr(info, "duration", 0.0) or 0.0

        words = []
        for segment in segments:
            for word in getattr(segment, "words", None) or []:
                words.append({"text": word.word,
                              "start": word.start, "end": word.end})
            if progress and duration:
                progress(0.10 + 0.88 * (segment.end / duration),
                         f"Transcribing · {segment.end:.0f}s of {duration:.0f}s")
        if progress:
            progress(1.0, f"Transcribed {len(words)} words")
        return normalise_words(words)
