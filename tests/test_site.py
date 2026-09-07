"""The project page.

The page ships the renderer's own geometry rather than redrawing the face in
JavaScript, so most of what is worth checking is that the exported frames are
real and that the page cannot quietly stop matching them.
"""

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SITE = DOCS / "index.html"


class SiteParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.fragments = []
        self.sources = []
        self.images_without_alt = []
        self.buttons_without_type = []
        self.inline_handlers = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.append(values["id"])
        if tag == "a" and values.get("href", "").startswith("#"):
            self.fragments.append(values["href"][1:])
        if tag in ("img", "source", "script", "video"):
            for key in ("src", "poster"):
                if values.get(key):
                    self.sources.append(values[key])
        if tag == "link" and values.get("href"):
            self.sources.append(values["href"])
        if tag == "img" and not values.get("alt"):
            self.images_without_alt.append(values.get("src", "unknown"))
        if tag == "button" and values.get("type") != "button":
            self.buttons_without_type.append(values.get("id", "unnamed"))
        self.inline_handlers.extend(name for name, _ in attrs if name.startswith("on"))


class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = SITE.read_text(encoding="utf-8")
        cls.parser = SiteParser()
        cls.parser.feed(cls.html)

    def test_ids_are_unique_and_fragments_resolve(self):
        self.assertEqual(len(self.parser.ids), len(set(self.parser.ids)))
        for fragment in self.parser.fragments:
            self.assertIn(fragment, self.parser.ids, f"#{fragment} goes nowhere")

    def test_images_and_buttons_are_labelled(self):
        self.assertEqual(self.parser.images_without_alt, [])
        self.assertEqual(self.parser.buttons_without_type, [])

    def test_no_inline_event_handlers(self):
        self.assertEqual(self.parser.inline_handlers, [])

    def test_every_local_asset_the_page_asks_for_exists(self):
        """A 404 on a page nobody rebuilds locally is silent for a long time."""
        for source in self.parser.sources:
            if source.startswith(("http://", "https://", "//", "data:")):
                continue
            self.assertTrue((DOCS / source).is_file(),
                            f"{source} is referenced but not published")

    def test_the_page_points_at_its_own_repository(self):
        self.assertIn("github.com/snepssen/protoke", self.html)


class FaceLoopTests(unittest.TestCase):
    """The exported frames are the only face the page has."""

    @classmethod
    def setUpClass(cls):
        cls.source = (DOCS / "face-loop.js").read_text(encoding="utf-8")
        payload = cls.source.split("window.FACE_LOOP =", 1)[1].rsplit(";", 1)[0]
        cls.loop = json.loads(payload.strip())

    def test_the_frames_ship_as_a_script_not_a_fetch(self):
        """A file:// or CSP-restricted page cannot fetch its own JSON."""
        self.assertIn("window.FACE_LOOP", self.source)
        self.assertNotIn("fetch(", (DOCS / "site.js").read_text(encoding="utf-8"))

    def test_the_frames_load_before_the_script_that_uses_them(self):
        html = SITE.read_text(encoding="utf-8")
        self.assertLess(html.index("face-loop.js"), html.index("site.js"))

    def test_the_loop_holds_real_geometry(self):
        self.assertGreaterEqual(len(self.loop["frames"]), 24)
        for frame in self.loop["frames"]:
            self.assertEqual(len(frame["s"]), 3, "two eyes and a mouth")
            for shape in frame["s"]:
                self.assertEqual(len(shape) % 2, 0, "flat x,y pairs")
                self.assertGreaterEqual(len(shape), 12)

    def test_the_eyes_actually_blink_across_the_loop(self):
        """Without this the loop could be one still frame repeated."""
        heights = []
        for frame in self.loop["frames"]:
            ys = frame["s"][0][1::2]
            heights.append(max(ys) - min(ys))
        self.assertGreater(max(heights) - min(heights), 1.0,
                           "the eye never changes height, so it never blinks")

    def test_the_head_moves(self):
        offsets = {tuple(frame["o"]) for frame in self.loop["frames"]}
        self.assertGreater(len(offsets), 1, "the face never breathes")


class PageStyleTests(unittest.TestCase):
    """Layout faults that only show up in a browser, caught in the source."""

    @classmethod
    def setUpClass(cls):
        cls.css = (DOCS / "style.css").read_text(encoding="utf-8")

    def test_the_face_canvas_scales_instead_of_overflowing(self):
        """The drawing buffer is 1040 wide; the column is not.

        Without width:100% the canvas lays out at its buffer size and pushes
        itself out of a centred container — which is exactly how it shipped
        off-centre the first time.
        """
        rule = re.search(r"#faceCanvas\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(rule, "no #faceCanvas rule")
        body = rule.group(1).replace(" ", "")
        self.assertIn("width:100%", body)
        self.assertIn("height:auto", body)
        self.assertIn("max-width:", body)

    def test_the_face_keeps_its_real_colour_in_every_theme(self):
        """The stage stands in for black video output, not for the page.

        Painting the canvas with --signal followed the visitor's OS theme and
        dropped the face to 3.15:1 against the near-black stage on a light
        desktop — dim, and a lie about what the renderer produces.
        """
        script = (DOCS / "site.js").read_text(encoding="utf-8")
        self.assertIn("--face", script)
        self.assertNotIn("getPropertyValue('--signal')", script)

        # --face must be defined once, outside any theme block, so no
        # prefers-color-scheme or [data-theme] rule can override it.
        outside = re.split(r"@media|:root\[data-theme", self.css)[0]
        self.assertIn("--face:", outside)
        self.assertEqual(self.css.count("--face:"), 1)

    def test_wide_content_scrolls_inside_its_own_box(self):
        for selector in (r"\.tablewrap\s*\{([^}]*)\}", r"pre\s*\{([^}]*)\}"):
            body = re.search(selector, self.css).group(1).replace(" ", "")
            self.assertIn("overflow-x:auto", body)


class PublishedMediaTests(unittest.TestCase):
    """The demo clip is allowed on purpose, and only just."""

    def test_the_clip_is_published_and_small(self):
        clip = DOCS / "protoke-demo.mp4"
        self.assertTrue(clip.is_file())
        self.assertLess(clip.stat().st_size, 5 * 1024 * 1024)

    def test_the_clip_is_not_quietly_gitignored(self):
        """Present locally but ignored by git means a 404 on the live site.

        .gitignore excludes *.mp4 wholesale; the allowance for this one has to
        come after that rule, because git takes the last matching pattern.
        """
        import shutil
        import subprocess

        if not shutil.which("git") or not (ROOT / ".git").exists():
            self.skipTest("not a git checkout")
        result = subprocess.run(
            ["git", "check-ignore", "-q", "docs/protoke-demo.mp4"],
            cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 1,
                         "the published clip is gitignored and will not deploy")

    def test_the_release_check_still_rejects_stray_media(self):
        """The exception must not have become a blanket permission."""
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        import check_release

        self.assertEqual(check_release.PUBLISHED_MEDIA_DIR, "docs")
        self.assertNotIn(".wav", check_release.PUBLISHED_MEDIA_SUFFIXES)
        self.assertNotIn(".onnx", check_release.PUBLISHED_MEDIA_SUFFIXES)
        self.assertFalse(check_release.published_media(ROOT / "stray.mp4"))
        self.assertTrue(check_release.published_media(DOCS / "protoke-demo.mp4"))


if __name__ == "__main__":
    unittest.main()
