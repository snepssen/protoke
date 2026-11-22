"""Parakeet TDT through ONNX Runtime — the portable default.

This is the engine that makes the tool free and cross-platform: onnx-asr runs
NVIDIA's Parakeet TDT on Windows, Linux and macOS, on x86 and Arm, with or
without a GPU. Weights are fetched from Hugging Face once and cached.
"""

from __future__ import annotations

import importlib.util
import os
import sys

from . import audio as audio_io
from . import hub
from .base import TranscriptionEngine, EngineUnavailable, merge_subword_tokens


DEFAULT_MODEL = "nemo-parakeet-tdt-0.6b-v2"
MULTILINGUAL_MODEL = "nemo-parakeet-tdt-0.6b-v3"
MACOS_PROVIDERS = ("CPUExecutionProvider",)


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
                 model_path=None, providers=None, **_ignored):
        available, reason = self.availability()
        if not available:
            raise EngineUnavailable(reason)
        if not ffmpeg:
            raise EngineUnavailable("ffmpeg is required to decode audio")
        self.ffmpeg = ffmpeg
        self.model_name = model or DEFAULT_MODEL
        self.quantization = quantization
        self.model_path = model_path
        # CoreML currently expands this large, partly-supported graph while
        # compiling it. On memory-constrained Macs that can make macOS kill
        # the whole desktop app before transcription starts. Automatic uses
        # MLX on Apple silicon; an explicitly selected ONNX run takes this
        # stable CPU path instead. Keep the original full-precision weights:
        # quantization can move word boundaries, and those boundaries drive
        # both viseme transitions and between-line head motion.
        self.providers = (MACOS_PROVIDERS if providers is None and
                          sys.platform == "darwin" else providers)
        self._model = None

    def _load(self):
        if self._model is None:
            import onnx_asr

            options = {
                "path": self.model_path or self._pinned_path(),
                "quantization": self.quantization,
            }
            if self.providers is not None:
                options["providers"] = self.providers
            model = onnx_asr.load_model(self.model_name, **options)
            self._model = model.with_timestamps()
        return self._model

    def _pinned_path(self):
        """The pinned commit's files, in a folder onnx-asr loads as is. Only
        the precision in use is fetched, as onnx-asr itself would."""
        suffix = f".{self.quantization}" if self.quantization else ""
        return hub.pinned_snapshot(_repo(self.model_name), [
            "config.json", "vocab.txt",
            f"encoder-model{suffix}.onnx*", f"decoder_joint-model{suffix}.onnx*"])

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


def _repo(model_name):
    """onnx-asr names models by its own aliases ("nemo-parakeet-tdt-0.6b-v2"),
    which it downloads from a different repository
    ("istupakov/parakeet-tdt-0.6b-v2-onnx"). Without onnx-asr installed (the
    UI checks before it is), the Parakeet aliases its resolver knows are used."""
    try:
        from onnx_asr.resolver import model_repos
    except ImportError:
        model_repos = {
            f"nemo-parakeet-{name}": f"istupakov/parakeet-{name}-onnx"
            for name in ("ctc-0.6b", "rnnt-0.6b", "tdt-0.6b-v2", "tdt-0.6b-v3")
        }
    return model_repos.get(model_name, model_name)


def model_is_cached(model_name=DEFAULT_MODEL):
    """Whether Hugging Face already holds the weights (at the pinned commit),
    so the UI can warn before a first run spends several hundred megabytes of
    download."""
    folder = hub.snapshot_dir(_repo(model_name))
    if not os.path.isdir(folder):
        return False
    if os.path.basename(folder) != "snapshots":
        return any(os.scandir(folder))
    return any(os.listdir(os.path.join(folder, rev)) for rev in os.listdir(folder))
