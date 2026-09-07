"""Parakeet TDT through ONNX Runtime — the portable default.

This is the engine that makes the tool free and cross-platform: onnx-asr runs
NVIDIA's Parakeet TDT on Windows, Linux and macOS, on x86 and Arm, with or
without a GPU. Weights are fetched from Hugging Face once and cached.
"""

from __future__ import annotations

import importlib.util
import os

from . import audio as audio_io
from .base import TranscriptionEngine, EngineUnavailable, merge_subword_tokens


DEFAULT_MODEL = "nemo-parakeet-tdt-0.6b-v2"
MULTILINGUAL_MODEL = "nemo-parakeet-tdt-0.6b-v3"


class OnnxParakeetEngine(TranscriptionEngine):
    name = "onnx-parakeet"
    label = "Parakeet (ONNX)"
    detail = "Free, runs on Windows, Linux and macOS"
    install_hint = "pip install 'onnx-asr[cpu,hub]'"
    priority = 20

    @classmethod
    def availability(cls):
        for module, hint in (("onnx_asr", "onnx-asr"),
                             ("onnxruntime", "onnxruntime"),
                             ("numpy", "numpy")):
            if importlib.util.find_spec(module) is None:
                return False, f"{hint} is not installed"
        return True, ""

    def __init__(self, ffmpeg=None, model=DEFAULT_MODEL, quantization=None,
                 model_path=None, **_ignored):
        available, reason = self.availability()
        if not available:
            raise EngineUnavailable(reason)
        if not ffmpeg:
            raise EngineUnavailable("ffmpeg is required to decode audio")
        self.ffmpeg = ffmpeg
        self.model_name = model or DEFAULT_MODEL
        self.quantization = quantization
        self.model_path = model_path
        self._model = None

    def _load(self):
        if self._model is None:
            import onnx_asr

            model = onnx_asr.load_model(
                self.model_name,
                path=self.model_path,
                quantization=self.quantization)
            self._model = model.with_timestamps()
        return self._model

    def transcribe(self, audio_path, progress=None):
        def report(fraction, message):
            if progress:
                progress(max(0.0, min(1.0, fraction)), message)

        report(0.02, "Decoding audio")
        samples = audio_io.decode_mono(audio_path, self.ffmpeg)
        total_seconds = len(samples) / audio_io.SAMPLE_RATE or 1.0

        report(0.06, f"Loading {self.model_name}")
        model = self._load()
        pieces = list(audio_io.chunks(samples))

        words = []
        for index, (offset, chunk) in enumerate(pieces, start=1):
            report(0.10 + 0.88 * (offset / total_seconds),
                   f"Transcribing part {index} of {len(pieces)}")
            result = model.recognize(audio_io.to_numpy(chunk),
                                     sample_rate=audio_io.SAMPLE_RATE)
            words.extend(_words_from_result(result,
                                            offset,
                                            len(chunk) / audio_io.SAMPLE_RATE))
        report(1.0, f"Transcribed {len(words)} words")
        return words


def _words_from_result(result, offset, chunk_seconds):
    """Turn one TimestampedResult into offset-corrected word records."""
    tokens = getattr(result, "tokens", None)
    timestamps = getattr(result, "timestamps", None)
    if tokens and timestamps and len(tokens) == len(timestamps):
        merged = merge_subword_tokens(tokens, timestamps,
                                      audio_end=chunk_seconds)
    else:
        # No timestamps came back: spread the text evenly rather than losing
        # the chunk. Alignment against a lyric sheet still repairs the timing.
        text = str(getattr(result, "text", "") or "").split()
        if not text:
            return []
        step = chunk_seconds / len(text)
        merged = [{"text": word, "start": i * step, "end": (i + 1) * step}
                  for i, word in enumerate(text)]
    for word in merged:
        word["start"] += offset
        word["end"] += offset
    return merged


def model_is_cached(model_name=DEFAULT_MODEL):
    """Whether Hugging Face already holds the weights, so the UI can warn
    before a first run spends several hundred megabytes of download."""
    home = os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")
    folder = model_name.split("/")[-1]
    hub = os.path.join(home, "hub")
    if not os.path.isdir(hub):
        return False
    return any(folder in entry for entry in os.listdir(hub))
