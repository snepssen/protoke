"""The vocal-separation seam.

Nothing here runs a model: separation is an optional, heavyweight dependency,
and the tool has to behave correctly on a machine where none is installed.
"""

import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock


TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL))

import separate  # noqa: E402
from separate import base  # noqa: E402


class ProbeTests(unittest.TestCase):
    def test_probe_describes_every_engine(self):
        described = separate.probe()
        self.assertEqual(len(described), len(separate.ENGINES))
        for entry in described:
            for key in ("name", "label", "detail", "available", "reason",
                        "installHint"):
                self.assertIn(key, entry)

    def test_probe_is_ordered_by_preference(self):
        names = [entry["name"] for entry in separate.probe()]
        priorities = [next(engine.priority for engine in separate.ENGINES
                           if engine.name == name) for name in names]
        self.assertEqual(priorities, sorted(priorities))

    def test_unavailable_engines_explain_themselves(self):
        for entry in separate.probe():
            if not entry["available"]:
                self.assertTrue(entry["reason"])
                self.assertTrue(entry["installHint"])

    def test_unknown_engine_is_rejected(self):
        with self.assertRaises(separate.SeparationUnavailable):
            separate.resolve("nonexistent-separator")

    def test_every_engine_accepts_the_shared_options(self):
        import inspect

        for engine in separate.ENGINES:
            parameters = inspect.signature(engine.__init__).parameters
            self.assertTrue(
                any(item.kind is item.VAR_KEYWORD
                    for item in parameters.values()),
                f"{engine.name} must accept **kwargs")

    def test_install_summary_names_a_package_and_the_fallback(self):
        summary = separate.install_summary()
        self.assertIn("audio-separator", summary)
        self.assertIn("full mix", summary)

    def test_fast_is_the_default_quality(self):
        # The face only needs to know where the voice is and how loud, so a
        # quick model with some backing left in it is the right trade.
        self.assertEqual(separate.FAST, separate.QUALITIES[0])
        self.assertIn(separate.SMOOTH, separate.QUALITIES)


class CacheKeyTests(unittest.TestCase):
    def test_the_key_is_stable_for_one_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "song.wav")
            Path(path).write_bytes(b"x" * 100)
            self.assertEqual(base.cache_key(path, "fast", "uvr"),
                             base.cache_key(path, "fast", "uvr"))

    def test_quality_and_engine_change_the_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "song.wav")
            Path(path).write_bytes(b"x" * 100)
            keys = {base.cache_key(path, "fast", "uvr"),
                    base.cache_key(path, "smooth", "uvr"),
                    base.cache_key(path, "fast", "demucs")}
            self.assertEqual(len(keys), 3)

    def test_an_edited_track_gets_a_new_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "song.wav")
            Path(path).write_bytes(b"x" * 100)
            before = base.cache_key(path, "fast", "uvr")
            Path(path).write_bytes(b"x" * 200)
            self.assertNotEqual(before, base.cache_key(path, "fast", "uvr"))

    def test_a_missing_file_still_produces_a_key(self):
        self.assertTrue(base.cache_key("/no/such/song.wav", "fast", "uvr"))

    def test_the_key_keeps_the_track_name_readable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "B06 VoidKitty.wav")
            Path(path).write_bytes(b"x")
            self.assertTrue(
                base.cache_key(path, "fast", "uvr").startswith("B06 VoidKitty"))


class WithoutASeparatorTests(unittest.TestCase):
    """The tool must work on a machine that has none of this installed."""

    def test_separation_is_optional_in_the_settings(self):
        import app

        self.assertIn("separateVocals", app.DEFAULTS)
        self.assertIn("separateVocals", app.SETTING_KEYS)
        self.assertIn(app.DEFAULTS["separationQuality"], separate.QUALITIES)

    def test_asking_for_a_vocal_without_an_engine_is_not_fatal(self):
        import app

        job = {"log": [], "id": "test"}
        if separate.available():
            self.skipTest("a separator is installed on this machine")
        self.assertIsNone(
            app.vocal_stem_for(job, "/no/such/song.wav",
                               {"separateVocals": True}))

    def test_separation_can_be_switched_off(self):
        import app

        job = {"log": [], "id": "test"}
        self.assertIsNone(
            app.vocal_stem_for(job, "/no/such/song.wav",
                               {"separateVocals": False}))


class MixFallbackHintTests(unittest.TestCase):
    """The reason the voice was guessed has to match the machine it ran on."""

    def test_no_separator_gives_install_instructions(self):
        with mock.patch.object(separate, "available", return_value=[]):
            hint = separate.mix_fallback_hint(requested=False)
        self.assertIn("pip install", hint)

    def test_an_installed_separator_is_never_told_to_install_itself(self):
        engine = types.SimpleNamespace(label="UVR models")
        with mock.patch.object(separate, "available", return_value=[engine]):
            offered = separate.mix_fallback_hint(requested=False)
            failed = separate.mix_fallback_hint(requested=True)
        for hint in (offered, failed):
            self.assertNotIn("pip install", hint)
            self.assertNotIn("No vocal separator is installed", hint)
            self.assertIn("UVR models", hint)
        # Not asking for it and asking and missing out are different faults.
        self.assertNotEqual(offered, failed)


if __name__ == "__main__":
    unittest.main()
