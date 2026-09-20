from pathlib import Path
import sys
import tempfile
import unittest


TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL))

import track_assets  # noqa: E402


class TrackAssetTests(unittest.TestCase):
    def test_matches_companions_despite_separator_and_case_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            audio = folder / "B06 VoidKitty.wav"
            cover = folder / "B06 - Voidkitty.png"
            lyrics = folder / "B06 - Voidkitty.md"
            for path in (audio, cover, lyrics):
                path.write_text("", encoding="utf-8")
            matched = track_assets.resolve_track_assets(str(audio))
        self.assertEqual(matched["cover"], str(cover))
        self.assertEqual(matched["lyrics"], str(lyrics))

    def test_suno_markdown_becomes_clean_sung_lines(self):
        source = """Red Aura

[Intro — spoken low]
Hello... (there)! *Wake* up?
[Verse 1]
Don't look — just listen.

Suno style tags
This prompt must not appear

Negative tags
Nor this
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Red Aura.md"
            path.write_text(source, encoding="utf-8")
            track = track_assets.parse_track_lyrics(path)
        self.assertEqual(track["title"], "Red Aura")
        self.assertEqual(track["lines"],
                         ["Hello there Wake up", "Don't look just listen"])

    def test_arrangement_notes_and_metadata_are_not_lyrics(self):
        source = """Little Oddball

Lyrics
[Intro]
(light Nordic bounce, accordion flicks, soft stomp)
[Verse 1]
A real sung line
[Verse 4 — tempo up, punchy, wry] (unchanged through "the next verse")
[End]

Style tags
This prompt must not appear
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Little Oddball.md"
            path.write_text(source, encoding="utf-8")
            track = track_assets.parse_track_lyrics(path)
        self.assertEqual(track["lines"], ["A real sung line"])

    def test_parenthetical_backing_vocal_after_lyric_is_preserved(self):
        source = """Blank Tapestry

[Chorus]
Full of maybes and seas
(full of maybes and seas)
One spark, one line, one color

**Suno style tags**
This prompt must not appear
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Blank Tapestry.md"
            path.write_text(source, encoding="utf-8")
            track = track_assets.parse_track_lyrics(path)
        self.assertEqual(
            track["lines"],
            [
                "Full of maybes and seas",
                "full of maybes and seas",
                "One spark one line one color",
            ],
        )

    def test_folder_scan_is_recursive_and_sorted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "A").mkdir()
            (root / "B").mkdir()
            (root / "B" / "B01.wav").write_text("", encoding="utf-8")
            (root / "A" / "A01.wav").write_text("", encoding="utf-8")
            found = track_assets.scan_audio_tree(str(root))
        self.assertEqual([Path(path).name for path in found],
                         ["A01.wav", "B01.wav"])


if __name__ == "__main__":
    unittest.main()
