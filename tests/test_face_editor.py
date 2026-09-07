"""The face editor: dial validation, saved presets, and the preview loop."""

import json
import os
import re
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL))

import face_expression  # noqa: E402
import face_presets  # noqa: E402
import face_preview  # noqa: E402
import face_render  # noqa: E402
import face_shapes  # noqa: E402


class DialTests(unittest.TestCase):
    """What arrives from the browser cannot be trusted to be drawable."""

    def test_every_dial_has_a_range(self):
        for spec in (face_presets.EYE_DIALS, face_presets.MOUTH_DIALS,
                     face_presets.FACE_DIALS):
            for name, (low, high) in spec.items():
                self.assertLess(low, high, name)

    def test_out_of_range_values_are_clamped(self):
        cleaned = face_presets.clean({
            "eye": {"openness": 99.0, "slant": -99.0},
            "mouth": {"aperture": 5.0},
            "sharpness": 3.0, "motion": -1.0})
        self.assertEqual(cleaned["eye"]["openness"],
                         face_presets.EYE_DIALS["openness"][1])
        self.assertEqual(cleaned["eye"]["slant"],
                         face_presets.EYE_DIALS["slant"][0])
        self.assertEqual(cleaned["mouth"]["aperture"],
                         face_presets.MOUTH_DIALS["aperture"][1])
        self.assertEqual(cleaned["sharpness"], 1.0)
        self.assertEqual(cleaned["motion"], 0.0)

    def test_junk_falls_back_rather_than_failing(self):
        # A preset that cannot be drawn is worse than one quietly brought
        # back into bounds.
        cleaned = face_presets.clean({"eye": {"hook": "nonsense"},
                                      "mouth": None, "sharpness": []})
        self.assertIsInstance(face_presets.to_face(cleaned), face_shapes.Face)

    def test_an_empty_dial_set_still_makes_a_face(self):
        self.assertIsInstance(face_presets.to_face({}), face_shapes.Face)

    def test_a_built_in_round_trips_through_the_editor(self):
        for name in face_expression.EXPRESSIONS:
            dials = face_presets.from_expression(name)
            face = face_presets.to_face(dials)
            original = face_expression.resting_face(name)
            self.assertAlmostEqual(face.eye.hook, original.eye.hook, msg=name)
            self.assertAlmostEqual(face.mouth.jag, original.mouth.jag,
                                   msg=name)
            self.assertAlmostEqual(face.sharpness, original.sharpness,
                                   msg=name)


class SavedPresetTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        patch = mock.patch.object(
            face_presets, "presets_path",
            lambda: os.path.join(self.folder.name, "face-presets.json"))
        patch.start()
        self.addCleanup(patch.stop)

    def test_saving_then_loading_returns_the_same_dials(self):
        dials = face_presets.from_expression("sharp")
        face_presets.save("Scowl", dials)
        loaded = face_presets.load()
        self.assertIn("Scowl", loaded)
        self.assertAlmostEqual(loaded["Scowl"]["sharpness"],
                               dials["sharpness"])

    def test_a_preset_cannot_shadow_a_built_in(self):
        with self.assertRaises(ValueError):
            face_presets.save("visor", face_presets.from_expression("visor"))

    def test_a_preset_needs_a_name(self):
        for name in ("", "   "):
            with self.assertRaises(ValueError):
                face_presets.save(name, {})

    def test_deleting_removes_only_that_preset(self):
        face_presets.save("One", {})
        face_presets.save("Two", {})
        face_presets.delete("One")
        self.assertEqual(list(face_presets.load()), ["Two"])

    def test_deleting_something_absent_is_not_an_error(self):
        face_presets.delete("never existed")

    def test_a_corrupt_file_does_not_take_the_app_down(self):
        Path(face_presets.presets_path()).write_text("{ not json")
        self.assertEqual(face_presets.load(), {})

    def test_the_catalogue_carries_built_ins_and_saved_alike(self):
        face_presets.save("Mine", {})
        names = [entry["name"] for entry in face_presets.catalogue()]
        self.assertIn("visor", names)
        self.assertIn("Mine", names)
        builtin = {entry["name"]: entry["builtin"]
                   for entry in face_presets.catalogue()}
        self.assertTrue(builtin["visor"])
        self.assertFalse(builtin["Mine"])

    def test_a_saved_preset_renders(self):
        # What the editor saves has to survive all the way to a render.
        face_presets.save("Mine", face_presets.from_expression("grin"))
        dials = face_presets.load()["Mine"]
        _, events, _ = face_render.build_face_ass(
            [{"text": "hi", "start": 0.2, "end": 0.6}], 3.0, dials=dials)
        self.assertGreater(events, 1)


class PreviewTests(unittest.TestCase):
    """The preview is generated by the renderer's own geometry, on purpose."""

    def test_a_loop_covers_a_blink_and_the_mouth_opening(self):
        loop = face_preview.frames(face_presets.from_expression("visor"))
        self.assertGreater(len(loop["frames"]), 30)
        apertures = [max(y for shape in frame["shapes"] for _, y in shape)
                     - min(y for shape in frame["shapes"] for _, y in shape)
                     for frame in loop["frames"]]
        self.assertGreater(max(apertures) - min(apertures), 20)

    def test_every_frame_carries_a_head_position(self):
        loop = face_preview.frames(face_presets.from_expression("visor"))
        offsets = {tuple(frame["offset"]) for frame in loop["frames"]}
        self.assertGreater(len(offsets), 1)

    def test_the_preview_can_be_drawn_as_a_matrix(self):
        loop = face_preview.frames(face_presets.from_expression("grin"),
                                   style=face_render.MATRIX)
        self.assertGreater(len(loop["frames"][0]["shapes"]), 20)

    def test_the_preview_survives_a_junk_dial_set(self):
        loop = face_preview.frames({"eye": {"openness": "no"}})
        self.assertTrue(loop["frames"])

    def test_the_loop_is_centred_on_what_it_draws(self):
        # The coordinate origin is not the middle of the face — the eyes
        # reach further up than the mouth reaches down — so a viewer that
        # puts the origin in the middle of its canvas hangs the face low.
        for name in ("visor", "grin", "sharp", "wide", "sleepy"):
            loop = face_preview.frames(face_presets.from_expression(name),
                                       motion=0.0)
            xs = [x for frame in loop["frames"] for shape in frame["shapes"]
                  for x, _ in shape]
            ys = [y for frame in loop["frames"] for shape in frame["shapes"]
                  for _, y in shape]
            self.assertAlmostEqual((min(xs) + max(xs)) / 2, 0, delta=2, msg=name)
            self.assertAlmostEqual((min(ys) + max(ys)) / 2, 0, delta=2, msg=name)

    def test_opening_the_mouth_does_not_move_the_eyes(self):
        # Centring measured per frame would drift the whole face every time
        # the mouth opened, which is worse than being off centre. The eyes
        # move only when they blink, so outside a blink they must not move
        # however wide the mouth gets.
        loop = face_preview.frames(face_presets.from_expression("visor"),
                                   motion=0.0)
        rows = []
        for frame in loop["frames"]:
            eye, mouth = frame["shapes"][0], frame["shapes"][2]
            eye_ys = [y for _, y in eye]
            mouth_ys = [y for _, y in mouth]
            rows.append((max(eye_ys) - min(eye_ys), min(eye_ys),
                         max(mouth_ys) - min(mouth_ys)))
        open_eyes = max(row[0] for row in rows)
        unblinking = [row for row in rows if row[0] == open_eyes]
        tops = {row[1] for row in unblinking}
        mouths = [row[2] for row in unblinking]
        self.assertEqual(len(tops), 1, f"eye top moved: {sorted(tops)}")
        self.assertGreater(max(mouths) - min(mouths), 20,
                           "the mouth should have opened during those frames")

    def test_the_payload_stays_small_enough_to_send_on_every_slider_move(self):
        loop = face_preview.frames(face_presets.from_expression("visor"))
        self.assertLess(len(json.dumps(loop)), 250_000)


class InterfaceLayoutTests(unittest.TestCase):
    """The page is about the video; the face and the tools have their own."""

    def setUp(self):
        self.markup = (TOOL / "index.html").read_text(encoding="utf-8")

    def test_the_face_has_its_own_configurator(self):
        self.assertIn('id="faceModal"', self.markup)
        self.assertIn('id="faceConfigure"', self.markup)
        for page in ("facePageLook", "facePageMotion", "facePageShape"):
            self.assertIn(f'id="{page}"', self.markup)

    def test_the_hidden_attribute_actually_hides(self):
        """Fields toggled with .hidden must disappear, not merely claim to.

        The browser's own ``[hidden]{display:none}`` is a single class of
        specificity, so any rule here that sets display — ``.field`` sets
        grid — beats it on source order and the field stays on screen. The
        MacWhisper command box showed for every engine because of this.
        """
        rules = re.findall(r"\[hidden\]\s*\{([^}]*)\}", self.markup)
        self.assertTrue(rules, "no [hidden] rule in the page's own CSS")
        winning = [body for body in rules if "!important" in body]
        self.assertTrue(
            winning,
            "[hidden] must win against rules like .field{display:grid}")

    def test_the_tools_have_their_own_settings(self):
        self.assertIn('id="settingsModal"', self.markup)
        self.assertIn('id="openSettings"', self.markup)
        # Neither of these is a per-render decision, so neither belongs on the
        # main page.
        for control in ('id="engine"', 'id="separationQuality"'):
            head = self.markup[:self.markup.index('id="settingsModal"')]
            self.assertNotIn(control, head, control)

    def test_every_dial_lives_in_the_configurator(self):
        for host in ('id="eyeDials"', 'id="mouthDials"', 'id="faceDials"'):
            self.assertIn(host, self.markup)
            self.assertGreater(self.markup.index(host),
                               self.markup.index('id="faceModal"'))

    def test_every_element_the_script_reaches_for_exists(self):
        import re

        ids = set(re.findall(r'id="([A-Za-z0-9_]+)"', self.markup))
        used = set(re.findall(r"\$\('([A-Za-z0-9_]+)'\)", self.markup))
        self.assertEqual(used - ids, set())

    def test_no_element_id_is_used_twice(self):
        import re

        ids = re.findall(r'id="([A-Za-z0-9_]+)"', self.markup)
        self.assertEqual(len(ids), len(set(ids)),
                         [name for name in set(ids) if ids.count(name) > 1])


class DesktopWindowTests(unittest.TestCase):
    """A missing webview must fall back to the browser, not fail."""

    def test_without_pywebview_the_browser_opens(self):
        import app

        with mock.patch.dict(sys.modules, {"webview": None}), \
                mock.patch.object(app.webbrowser, "open") as opened:
            self.assertFalse(app.open_window("http://127.0.0.1:8765/"))
            opened.assert_called_once()

    def test_a_webview_that_refuses_to_start_falls_back_too(self):
        import app

        broken = mock.MagicMock()
        broken.start.side_effect = RuntimeError("no display")
        with mock.patch.dict(sys.modules, {"webview": broken}), \
                mock.patch.object(app.webbrowser, "open") as opened:
            self.assertFalse(app.open_window("http://127.0.0.1:8765/"))
            opened.assert_called_once()


class OutputPathTests(unittest.TestCase):
    """--out names a file, but a folder is the mistake everyone makes."""

    def test_a_folder_keeps_the_rendered_name(self):
        import app

        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(
                app.resolve_output_path("/render/dir/song.mp4", folder),
                os.path.join(folder, "song.mp4"))

    def test_a_file_path_is_used_as_given(self):
        import app

        self.assertEqual(
            app.resolve_output_path("/render/dir/song.mp4", "/out/named.mp4"),
            "/out/named.mp4")

    def test_no_destination_leaves_the_render_where_it_landed(self):
        import app

        self.assertEqual(
            app.resolve_output_path("/render/dir/song.mp4", None),
            "/render/dir/song.mp4")


if __name__ == "__main__":
    unittest.main()
