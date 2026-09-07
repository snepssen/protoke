"""Vocal separation through audio-separator, the UVR models as a library.

One install covers both of the model families worth having here: Demucs, which
is quick and leaves some backing in the vocal, and MDX-Net, which is slower and
cleaner. The face only needs to know where the voice is and how loud it is, so
the quick one is the default and the clean one is there for when the estimate
is being used for something fussier.
"""

from __future__ import annotations

import importlib.util
import os

from .base import FAST, SMOOTH, SeparationEngine, SeparationUnavailable


#: Demucs is the fast path — the owner's own measurement, and it matches what
#: the model is doing: one pass, no spectrogram round trip.
MODELS = {
    FAST: "htdemucs.yaml",
    SMOOTH: "UVR-MDX-NET-Inst_HQ_3.onnx",
}


class UvrEngine(SeparationEngine):
    name = "uvr"
    label = "UVR models (audio-separator)"
    detail = "Demucs and MDX-Net; downloads weights on first use"
    install_hint = "pip install 'audio-separator[cpu]' audioread"
    priority = 10

    #: audio-separator does not declare audioread, but importing it fails
    #: without it — so the probe has to check what the import actually needs
    #: rather than only the package that was asked for.
    REQUIRES = (("audio_separator", "audio-separator"),
                ("audioread", "audioread"),
                ("torch", "torch"))

    @classmethod
    def availability(cls):
        for module, package in cls.REQUIRES:
            if importlib.util.find_spec(module) is None:
                return False, f"{package} is not installed"
        return True, ""

    def __init__(self, model_dir=None, **_ignored):
        available, reason = self.availability()
        if not available:
            raise SeparationUnavailable(reason)
        self.model_dir = model_dir

    def separate(self, audio_path, out_path, quality=FAST, progress=None):
        import logging

        try:
            from audio_separator.separator import Separator
        except ImportError as exc:
            # A dependency can be missing even when the package is present.
            raise SeparationUnavailable(
                f"audio-separator could not be imported ({exc}). "
                f"Install it with: {self.install_hint}") from exc

        model = MODELS.get(quality, MODELS[FAST])
        if progress:
            progress(0.05, f"Loading separation model {model}")

        out_dir = os.path.dirname(out_path) or "."
        os.makedirs(out_dir, exist_ok=True)
        options = {
            "output_dir": out_dir,
            "output_format": "WAV",
            "output_single_stem": "Vocals",
            "log_level": logging.WARNING,
        }
        if self.model_dir:
            os.makedirs(self.model_dir, exist_ok=True)
            options["model_file_dir"] = self.model_dir

        separator = Separator(**options)
        separator.load_model(model_filename=model)
        if progress:
            progress(0.25, "Separating the vocal")
        produced = separator.separate(audio_path)
        if not produced:
            raise SeparationUnavailable(
                f"{self.label} produced no output for "
                f"{os.path.basename(audio_path)}")

        # It names outputs after the input and the model, so find the vocal it
        # just wrote and put it where the caller asked for it.
        written = [name if os.path.isabs(name) else os.path.join(out_dir, name)
                   for name in produced]
        vocals = next((path for path in written
                       if "vocal" in os.path.basename(path).lower()), written[0])
        if os.path.abspath(vocals) != os.path.abspath(out_path):
            os.replace(vocals, out_path)
        for leftover in written:
            if os.path.abspath(leftover) != os.path.abspath(out_path):
                try:
                    os.remove(leftover)
                except OSError:
                    pass
        if progress:
            progress(1.0, "Vocal separated")
        return out_path
