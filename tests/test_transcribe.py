"""The transcription seam and the cross-platform support layer."""

from pathlib import Path
import sys
import tempfile
import unittest


TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL))

import platform_support  # noqa: E402
import transcribe  # noqa: E402
from transcribe import base  # noqa: E402


class ProbeTests(unittest.TestCase):
    def test_probe_describes_every_engine(self):
        described = transcribe.probe()
        self.assertEqual(len(described), len(transcribe.ENGINES))
        for entry in described:
            for key in ("name", "label", "detail", "available", "reason",
                        "installHint"):
                self.assertIn(key, entry)

    def test_probe_is_ordered_by_preference(self):
        names = [entry["name"] for entry in transcribe.probe()]
        priorities = [next(engine.priority for engine in transcribe.ENGINES
                           if engine.name == name) for name in names]
        self.assertEqual(priorities, sorted(priorities))

    def test_unavailable_engines_explain_themselves(self):
        for entry in transcribe.probe():
            if not entry["available"]:
                self.assertTrue(entry["reason"])
                self.assertTrue(entry["installHint"])

    def test_unknown_engine_is_rejected(self):
        with self.assertRaises(transcribe.EngineUnavailable):
            transcribe.resolve("nonexistent-engine")

    def test_every_engine_accepts_the_shared_options(self):
        # create() hands one option bag to whichever engine it builds, so an
        # engine that refuses an unknown keyword breaks every other one.
        import inspect

        for engine in transcribe.ENGINES:
            parameters = inspect.signature(engine.__init__).parameters
            self.assertTrue(
                any(item.kind is item.VAR_KEYWORD
                    for item in parameters.values()),
                f"{engine.name} must accept **kwargs")

    def test_install_summary_names_the_portable_engine(self):
        self.assertIn("onnx-asr", transcribe.install_summary())


class WordHandlingTests(unittest.TestCase):
    def test_subword_tokens_merge_into_words(self):
        words = base.merge_subword_tokens(
            [" hel", "lo", " world"], [0.0, 0.2, 0.5], audio_end=0.9)
        self.assertEqual([word["text"] for word in words], ["hello", "world"])
        self.assertAlmostEqual(words[0]["start"], 0.0)
        self.assertAlmostEqual(words[0]["end"], 0.5)
        self.assertAlmostEqual(words[1]["end"], 0.9)

    def test_raw_sentencepiece_marker_is_also_a_word_start(self):
        words = base.merge_subword_tokens(["▁one", "▁two"], [1.0, 1.4])
        self.assertEqual([word["text"] for word in words], ["one", "two"])

    def test_normalise_drops_blanks_sorts_and_orders_bounds(self):
        words = base.normalise_words([
            {"text": "second", "start": 2.0, "end": 2.5},
            {"text": "   ", "start": 0.0, "end": 1.0},
            {"text": "first", "start": 1.0, "end": 0.5},
        ])
        self.assertEqual([word["text"] for word in words],
                         ["first", "second"])
        self.assertLess(words[0]["start"], words[0]["end"])

    def test_payload_parser_accepts_each_documented_shape(self):
        stamped = base.words_from_payload(
            [{"timestamp": "00:01.500-00:02.000", "text": "hi"}])
        segmented = base.words_from_payload(
            {"segments": [{"words": [{"word": "hi", "start": 1.5,
                                      "end": 2.0}]}]})
        plain = base.words_from_payload(
            [{"text": "hi", "start": 1.5, "end": 2.0}])
        self.assertEqual(stamped, segmented)
        self.assertEqual(stamped, plain)

    def test_payload_parser_rejects_an_unknown_shape(self):
        with self.assertRaises(ValueError):
            base.words_from_payload("not a transcript")

    def test_hour_length_timestamps_parse(self):
        self.assertAlmostEqual(base.parse_clock("01:02:03.500"), 3723.5)

    def test_existing_transcript_prefers_the_words_file(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "song.wav"
            audio.write_bytes(b"")
            self.assertIsNone(base.existing_transcript(str(audio)))
            (Path(folder) / "song.json").write_text("[]")
            self.assertTrue(
                base.existing_transcript(str(audio)).endswith("song.json"))
            (Path(folder) / "song.words.json").write_text("[]")
            self.assertTrue(base.existing_transcript(str(audio))
                            .endswith("song.words.json"))


class AudioChunkTests(unittest.TestCase):
    def samples(self, seconds, sample_rate=16000, quiet_at=None):
        import array
        import math

        data = array.array("f", [0.0] * (seconds * sample_rate))
        for index in range(len(data)):
            second = index / sample_rate
            quiet = quiet_at and quiet_at[0] < second < quiet_at[1]
            data[index] = 0.0 if quiet else 0.5 * math.sin(index * 0.01)
        return data

    def test_short_audio_is_left_whole(self):
        from transcribe import audio

        self.assertEqual(audio.split_points(self.samples(60)), [])

    def test_long_audio_is_cut_where_it_is_quiet(self):
        from transcribe import audio

        data = self.samples(300, quiet_at=(119, 121))
        cuts = audio.split_points(data)
        self.assertTrue(cuts)
        self.assertAlmostEqual(cuts[0] / 16000, 120, delta=1.5)

    def test_chunks_cover_the_track_without_gaps(self):
        from transcribe import audio

        data = self.samples(300, quiet_at=(119, 121))
        pieces = list(audio.chunks(data))
        self.assertGreater(len(pieces), 1)
        total = sum(len(chunk) for _, chunk in pieces)
        self.assertEqual(total, len(data))
        expected = 0.0
        for offset, chunk in pieces:
            self.assertAlmostEqual(offset, expected, places=5)
            expected += len(chunk) / 16000


class PlatformSupportTests(unittest.TestCase):
    def test_a_default_font_is_offered_and_listed(self):
        self.assertIn(platform_support.default_font(),
                      platform_support.font_choices())

    def test_ffmpeg_hint_is_actionable(self):
        self.assertTrue(platform_support.ffmpeg_install_hint().strip())

    def test_cache_directory_is_under_the_home_directory(self):
        self.assertTrue(platform_support.cache_dir().endswith(
            "protoke"))

    def test_revealing_a_missing_path_is_a_no_op(self):
        self.assertFalse(platform_support.reveal(""))
        self.assertFalse(platform_support.reveal("/no/such/file/here.mp4"))


class PackagingTests(unittest.TestCase):
    """An installed copy must carry every module the app imports."""

    def test_pyproject_lists_every_module(self):
        import tomllib

        manifest = tomllib.loads((TOOL / "pyproject.toml").read_text())
        listed = set(manifest["tool"]["setuptools"]["py-modules"])
        present = {path.stem for path in TOOL.glob("*.py")}
        self.assertEqual(present - listed, set(),
                         "module present but not packaged")
        self.assertEqual(listed - present, set(),
                         "packaged module does not exist")

    def test_pyproject_lists_every_package(self):
        """py-modules only covers loose files; sub-packages need finding too.

        ``separate`` shipped missing once because only ``transcribe*`` was
        listed, and nothing failed until an installed copy was run.
        """
        import fnmatch

        manifest = tomllib_load(TOOL / "pyproject.toml")
        patterns = manifest["tool"]["setuptools"]["packages"]["find"]["include"]
        packages = {path.parent.name for path in TOOL.glob("*/__init__.py")}
        for package in sorted(packages):
            self.assertTrue(
                any(fnmatch.fnmatch(package, rule) for rule in patterns),
                f"{package}/ is a package but no include pattern matches it")

    def test_entry_point_target_exists(self):
        import app

        manifest = tomllib_load(TOOL / "pyproject.toml")
        script = manifest["project"]["scripts"]["protoke"]
        module, _, function = script.partition(":")
        self.assertEqual(module, "app")
        self.assertTrue(callable(getattr(app, function)))


def tomllib_load(path):
    import tomllib

    return tomllib.loads(path.read_text())


if __name__ == "__main__":
    unittest.main()
