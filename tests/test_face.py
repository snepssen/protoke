"""The animated face: viseme timing, blinks, and the ASS it produces."""

from pathlib import Path
import pathlib
import sys
import unittest


TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL))

import face_expression  # noqa: E402
import face_matrix  # noqa: E402
import face_shapes  # noqa: E402
import face_render  # noqa: E402
import face_visemes  # noqa: E402
import video_effects  # noqa: E402
import video_formats  # noqa: E402


class VisemeTests(unittest.TestCase):
    def test_vowels_and_visible_consonants_become_shapes(self):
        self.assertEqual(
            [viseme for viseme, _ in face_visemes.word_visemes("hello")],
            ["eh", "ll", "oh"])
        self.assertEqual(
            [viseme for viseme, _ in face_visemes.word_visemes("moon")],
            ["mm", "oo"])

    def test_every_viseme_has_mouth_parameters(self):
        for word in ("hello", "world", "fire", "you", "shh", "rhythm"):
            for viseme, _ in face_visemes.word_visemes(word):
                self.assertIn(viseme, face_visemes.VISEMES, word)

    def test_word_with_no_letters_still_rests(self):
        self.assertEqual(face_visemes.word_visemes("!!!"),
                         [(face_visemes.REST, 1.0)])

    def test_timeline_covers_each_word_without_overlapping(self):
        words = [{"text": "hello", "start": 0.0, "end": 0.6},
                 {"text": "world", "start": 0.7, "end": 1.2}]
        spans = face_visemes.viseme_timeline(words)
        self.assertAlmostEqual(spans[0][0], 0.0)
        self.assertAlmostEqual(spans[-1][1], 1.2, places=5)
        for earlier, later in zip(spans, spans[1:]):
            self.assertLessEqual(earlier[1], later[0] + 1e-9)

    def test_short_word_keeps_articulations_in_spelling_order(self):
        # Too brief to show every shape: the survivors must not be reordered.
        spans = face_visemes.viseme_timeline(
            [{"text": "firewall", "start": 0.0, "end": 0.18}])
        full = [viseme for viseme, _ in face_visemes.word_visemes("firewall")]
        kept = [viseme for _, _, viseme in spans]
        self.assertLess(len(kept), len(full))
        positions = [full.index(viseme) for viseme in kept]
        self.assertEqual(positions, sorted(positions))

    def test_the_mouth_does_not_go_home_between_words(self):
        # Returning to the resting face inside a verse looks like chewing;
        # between phrases the mouth waits closed but ready, still in the
        # singing system.
        keys = face_visemes.mouth_keyframes(
            [{"text": "hi", "start": 0.0, "end": 0.4},
             {"text": "there", "start": 2.0, "end": 2.4}])
        aperture = face_visemes.mouth_at(keys, 1.0)[0].aperture
        self.assertGreater(aperture, 0.0)
        self.assertLess(aperture, 0.25)

    def test_the_mouth_glides_straight_between_close_words(self):
        # Inside a phrase there should be no closing at all.
        keys = face_visemes.mouth_keyframes(
            [{"text": "hello", "start": 0.5, "end": 0.9},
             {"text": "world", "start": 1.0, "end": 1.4}])
        lowest = min(face_visemes.mouth_at(keys, 0.9 + step * 0.01)[0].aperture
                     for step in range(10))
        self.assertGreater(lowest, 0.3)

    def test_the_mouth_anticipates_the_next_word(self):
        # A real mouth is already forming a shape before the sound arrives.
        keys = face_visemes.mouth_keyframes(
            [{"text": "hi", "start": 0.0, "end": 0.3},
             {"text": "again", "start": 2.0, "end": 2.5}])
        self.assertGreater(face_visemes.mouth_at(keys, 1.95)[0].aperture,
                           face_visemes.mouth_at(keys, 1.2)[0].aperture)

    def test_only_a_long_gap_hands_over_to_the_resting_face(self):
        words = [{"text": "hi", "start": 0.0, "end": 0.4},
                 {"text": "soon", "start": 2.0, "end": 2.4},
                 {"text": "later", "start": 20.0, "end": 20.4}]
        spans = face_visemes.sung_spans(words)
        self.assertEqual(len(spans), 2, spans)
        self.assertAlmostEqual(spans[0][1], 2.4, places=1)
        self.assertAlmostEqual(spans[1][0], 20.0, places=1)

    def test_mouth_moves_smoothly_rather_than_snapping(self):
        words = [{"text": "hello", "start": 0.5, "end": 1.1},
                 {"text": "world", "start": 1.2, "end": 1.8}]
        keys = face_visemes.mouth_keyframes(words)
        samples = [face_visemes.mouth_at(keys, 0.45 + step * 0.02)[0].aperture
                   for step in range(70)]
        # No single step may jump most of the way across the aperture range.
        jumps = [abs(later - earlier)
                 for earlier, later in zip(samples, samples[1:])]
        self.assertLess(max(jumps), 0.12)
        self.assertGreater(max(samples), 0.5)

    def test_mouth_rests_closed_before_and_after_the_words(self):
        keys = face_visemes.mouth_keyframes(
            [{"text": "hi", "start": 2.0, "end": 2.4}])
        self.assertAlmostEqual(face_visemes.mouth_at(keys, 0.0)[0].aperture, 0.0)
        self.assertAlmostEqual(face_visemes.mouth_at(keys, 9.0)[0].aperture, 0.0)

    def test_mouth_needs_no_audio_at_all(self):
        # The mouth is driven by the words alone: no envelope is accepted.
        keys = face_visemes.mouth_keyframes(
            [{"text": "sing", "start": 0.0, "end": 0.8}])
        self.assertGreater(max(face_visemes.mouth_at(keys, t * 0.05)[0].aperture
                               for t in range(20)), 0.2)

def _height(shape):
    ys = [y for _, y in shape]
    return max(ys) - min(ys)


def _width(shape):
    xs = [x for x, _ in shape]
    return max(xs) - min(xs)


class ExpressionTests(unittest.TestCase):
    """Resting faces and the idle blink."""

    def test_every_expression_is_a_set_of_dials(self):
        for name, spec in face_expression.EXPRESSIONS.items():
            shape = spec["shape"]
            self.assertIsInstance(shape.eye, face_shapes.Eye, name)
            self.assertIsInstance(shape.mouth, face_shapes.Mouth, name)
            self.assertTrue(spec["label"])
            self.assertTrue(spec["face"])

    def test_any_two_expressions_can_sit_between_each_other(self):
        # A face built by swapping between fixed outlines cannot be part way
        # to anything, and that is what makes it read as stuck-on pieces.
        first = face_expression.resting_face("visor")
        second = face_expression.resting_face("wide")
        half = first.blended(second, 0.5)
        for index, value in enumerate(half.eye.values()):
            low = min(first.eye.values()[index], second.eye.values()[index])
            high = max(first.eye.values()[index], second.eye.values()[index])
            self.assertGreaterEqual(value, low - 1e-9)
            self.assertLessEqual(value, high + 1e-9)

    def test_expressions_are_typeable_on_a_command_line(self):
        # They are CLI arguments as well as menu entries, and "¬‿¬" is not
        # something anyone wants to type.
        for name in face_expression.EXPRESSIONS:
            self.assertTrue(name.isascii() and name.islower(), name)

    def test_an_expression_can_also_be_named_by_its_kaomoji(self):
        self.assertEqual(face_expression.resting("¬‿¬")["label"], "Smug")

    def test_the_default_face_is_hooked_and_smirking(self):
        # The hook is what makes a visor eye read as one; the smirk is a
        # singer's resting face rather than a mascot's.
        default = face_expression.resting_face(
            face_expression.DEFAULT_EXPRESSION)
        self.assertGreater(default.eye.hook, 0.5)
        self.assertGreater(default.mouth.skew, 0.1)

    def test_unknown_expression_falls_back_to_the_default(self):
        self.assertEqual(face_expression.resting("nonsense"),
                         face_expression.resting(
                             face_expression.DEFAULT_EXPRESSION))

    def test_eyes_only_close_to_blink(self):
        performance = face_expression.EyePerformance(120.0)
        shut = [time / 10 for time in range(1200)
                if performance.openness_at(time / 10) < 0.5]
        blinking = sum(end - start for start, end in performance.blinks)
        self.assertLess(len(shut) / 10, blinking + 0.5)

    def test_blinks_repeat_exactly(self):
        first = face_expression.EyePerformance(120.0).blinks
        self.assertEqual(first, face_expression.EyePerformance(120.0).blinks)
        self.assertTrue(first)

    def test_the_requested_blink_rate_is_the_delivered_rate(self):
        # Rested eyes go about ten seconds between blinks; an awake, talking
        # person is nearer four or five. Both have to be reachable.
        for every in (4.0, 5.0, 10.0):
            blinks = face_expression.idle_blinks(900.0, every=every)
            gaps = [later[0] - earlier[0]
                    for earlier, later in zip(blinks, blinks[1:])]
            # A double blink is one event to the eye, so its own tiny gap is
            # not an interval between blinks.
            intervals = [gap for gap in gaps if gap > 0.5]
            mean = sum(intervals) / len(intervals)
            self.assertAlmostEqual(mean, every, delta=every * 0.15)

    def test_blinks_are_not_metronomic(self):
        # Evenly spaced blinks are conspicuous; real ones cluster.
        blinks = face_expression.idle_blinks(900.0, every=5.0)
        intervals = [later[0] - earlier[0]
                     for earlier, later in zip(blinks, blinks[1:])
                     if later[0] - earlier[0] > 0.5]
        self.assertGreater(max(intervals) / min(intervals), 2.0)

    def test_some_blinks_come_in_pairs(self):
        blinks = face_expression.idle_blinks(900.0, every=5.0)
        doubles = sum(1 for earlier, later in zip(blinks, blinks[1:])
                      if later[0] - earlier[0] < 0.5)
        self.assertGreater(doubles, 0)

    def test_an_absurd_blink_rate_is_clamped(self):
        for every in (0.0, -5.0, 1e6):
            blinks = face_expression.idle_blinks(120.0, every=every)
            gaps = [later[0] - earlier[0]
                    for earlier, later in zip(blinks, blinks[1:])
                    if later[0] - earlier[0] > 0.5]
            for gap in gaps:
                self.assertGreater(gap, 0.5)

    def test_eyes_shut_at_the_middle_of_a_blink(self):
        performance = face_expression.EyePerformance(60.0)
        # Blinks arrive in pairs sometimes, so measure one that stands alone.
        blinks = performance.blinks
        alone = next(
            (start, end) for index, (start, end) in enumerate(blinks)
            if (index + 1 >= len(blinks) or blinks[index + 1][0] - end > 0.5)
            and (index == 0 or start - blinks[index - 1][1] > 0.5))
        start, end = alone
        self.assertEqual(performance.openness_at(start - 0.2), 1.0)
        self.assertLess(performance.openness_at((start + end) / 2), 0.05)
        self.assertEqual(performance.openness_at(end + 0.2), 1.0)


class WordlessVocalTests(unittest.TestCase):
    """Singing the lyric sheet does not describe — a yodel, a held note."""

    def setUp(self):
        import face_audio

        self.face_audio = face_audio

    def track(self, levels, threshold=0.3):
        rate = 50.0
        return self.face_audio.VocalTrack(
            levels, self.face_audio.voiced_strength(levels, rate), rate,
            threshold=threshold)

    def fluttering(self, seconds, rate=50.0, syllables=5.0):
        """A level that rises and falls at syllable rate, like a voice."""
        import math

        return [0.55 + 0.45 * math.sin(math.tau * syllables * i / rate)
                for i in range(int(seconds * rate))]

    def steady(self, seconds, rate=50.0, level=0.9):
        """A loud level that does not fluctuate, like a held instrument."""
        return [level] * int(seconds * rate)

    def test_a_fluctuating_voice_scores_higher_than_a_steady_instrument(self):
        voice = self.face_audio.voiced_strength(self.fluttering(6.0))
        pad = self.face_audio.voiced_strength(self.steady(6.0))
        middle = slice(len(voice) // 4, 3 * len(voice) // 4)
        self.assertGreater(sum(voice[middle]) / len(voice[middle]),
                           sum(pad[middle]) / len(pad[middle]))

    def test_silence_is_never_voice(self):
        quiet = self.track([0.0] * 300)
        self.assertEqual(quiet.segments(0.0, 6.0), [])

    def test_no_audio_at_all_is_handled(self):
        empty = self.track([])
        self.assertFalse(empty)
        self.assertEqual(empty.segments(0.0, 10.0), [])
        self.assertEqual(empty.strength_at(1.0), 0.0)

    def test_wordless_singing_fills_a_gap_the_sheet_leaves(self):
        # A yodel between two verses has no words, so without this the mouth
        # would sit shut through all of it.
        rate = 50.0
        levels = ([0.0] * int(4 * rate) + self.fluttering(6.0)
                  + [0.0] * int(4 * rate))
        track = self.track(levels, threshold=0.25)
        words = [{"text": "before", "start": 0.5, "end": 1.0},
                 {"text": "after", "start": 13.0, "end": 13.5}]
        plain = face_visemes.mouth_keyframes(words)
        with_vocals = face_visemes.mouth_keyframes(words, vocals=track)
        self.assertGreater(len(with_vocals), len(plain) + 20)
        opened = max(face_visemes.mouth_at(with_vocals, 6.0 + i * 0.05)[0].aperture
                     for i in range(40))
        self.assertGreater(opened, 0.4)

    def test_a_vocal_stem_gets_a_lower_bar_than_a_full_mix(self):
        # A separated vocal only has to be audible; a full mix has to look
        # like a voice as well.
        self.assertLess(self.face_audio.STEM_THRESHOLD,
                        self.face_audio.MIX_THRESHOLD)

    def test_a_vocal_stem_is_found_beside_the_track(self):
        import tempfile

        import track_assets

        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            for name in ("B06 VoidKitty.wav", "1_B06 VoidKitty_(Vocals).wav",
                         "B06 VoidKitty_(Instrumental).wav",
                         "Another Song_(Vocals).wav"):
                (root / name).write_bytes(b"")
            found = track_assets.find_vocal_stem(str(root / "B06 VoidKitty.wav"))
            self.assertTrue(found.endswith("1_B06 VoidKitty_(Vocals).wav"),
                            found)

    def test_no_stem_means_no_false_match(self):
        import tempfile

        import track_assets

        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            (root / "song.wav").write_bytes(b"")
            (root / "other song_(Vocals).wav").write_bytes(b"")
            self.assertIsNone(
                track_assets.find_vocal_stem(str(root / "song.wav")))


class MouthHandoverTests(unittest.TestCase):
    """Going back to the resting face blends dials, it does not cut."""

    def test_the_face_blends_all_the_way_across(self):
        sung = face_shapes.Face(face_shapes.Eye(), face_shapes.VISEMES["ah"])
        resting = face_expression.resting_face("visor")
        for amount in (0.0, 0.5, 1.0):
            blended = sung.blended(resting, amount)
            self.assertIsInstance(blended.mouth, face_shapes.Mouth)
        self.assertEqual(sung.blended(resting, 0.0).mouth.values(),
                         sung.mouth.values())
        self.assertEqual(sung.blended(resting, 1.0).mouth.values(),
                         resting.mouth.values())

    def test_the_blend_moves_steadily_between_the_two(self):
        sung = face_shapes.Face(face_shapes.Eye(), face_shapes.VISEMES["ah"])
        resting = face_expression.resting_face("visor")
        heights = []
        for step in range(9):
            blended = sung.blended(resting, step / 8)
            heights.append(_height(
                face_render.mouth_outline(blended.mouth)[0]))
        self.assertGreater(heights[0], heights[-1])
        for earlier, later in zip(heights, heights[1:]):
            self.assertLess(abs(later - earlier), 40.0)


class HeadMotionTests(unittest.TestCase):
    """The face is mounted on a head you cannot see."""

    def test_the_head_actually_moves(self):
        head = face_expression.HeadMotion(tempo=120)
        samples = [head.at(step / 40.0) for step in range(200)]
        for axis, name in ((0, "sway"), (1, "bob"), (2, "tilt")):
            spread = (max(value[axis] for value in samples)
                      - min(value[axis] for value in samples))
            self.assertGreater(spread, 0.0, name)

    def test_the_bob_is_lowest_on_the_beat(self):
        # At the right rate but the wrong phase the head nods precisely
        # between the beats, which looks worse than not moving at all.
        tempo, beat = 120.0, 0.5
        head = face_expression.HeadMotion(tempo=tempo, beat_phase=0.0)
        on_beat = [head.at(index * beat)[1] for index in range(1, 9)]
        off_beat = [head.at((index + 0.5) * beat)[1] for index in range(1, 9)]
        self.assertGreater(sum(on_beat) / len(on_beat),
                           sum(off_beat) / len(off_beat))

    def test_the_beat_phase_shifts_the_bob(self):
        tempo = 120.0
        aligned = face_expression.HeadMotion(tempo=tempo, beat_phase=0.25)
        self.assertGreater(aligned.at(0.25)[1], aligned.at(0.5)[1])

    def test_the_head_moves_more_between_lines(self):
        head = face_expression.HeadMotion(tempo=120)
        singing = max(abs(head.at(step / 40.0, singing=True)[1])
                      for step in range(200))
        between = max(abs(head.at(step / 40.0, singing=False)[1])
                      for step in range(200))
        self.assertGreater(between, singing)

    def test_motion_can_be_switched_off(self):
        head = face_expression.HeadMotion(tempo=120, amount=0.0)
        for step in range(50):
            self.assertEqual(head.at(step / 10.0), (0.0, 0.0, 0.0))

    def test_movement_stays_subtle(self):
        # Displacements are fractions of the face width; a head that swings
        # far enough to leave its own footprint reads as a bouncing sticker.
        head = face_expression.HeadMotion(tempo=120)
        for step in range(400):
            dx, dy, tilt = head.at(step / 40.0, singing=False)
            self.assertLess(abs(dx), 0.06)
            self.assertLess(abs(dy), 0.06)
            self.assertLess(abs(tilt), 4.0)


class CorrectedTranscriptTests(unittest.TestCase):
    """A track with a lyric sheet hands the face a corrected transcript."""

    def setUp(self):
        import lyrics_engine

        self.lyrics_engine = lyrics_engine

    def corrected(self):
        return {"lines": [
            {"words": [{"text": "black", "start": 0.0, "end": 0.4},
                       {"text": "cat", "start": 0.5, "end": 0.9}]},
            {"words": [{"text": "outline", "start": 1.2, "end": 1.8}]},
        ]}

    def test_corrected_transcript_loads(self):
        # It carries its own line structure, which is not a plain word list.
        # Reading one with the raw loader raises, so everything that reads a
        # transcript has to come through load_transcript.
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            path = str(pathlib.Path(folder) / "song.corrected.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(self.corrected(), handle)
            words, lines = self.lyrics_engine.load_transcript(path)
            self.assertEqual([word["text"] for word in words],
                             ["black", "cat", "outline"])
            self.assertEqual(len(lines), 2)
            with self.assertRaises(ValueError):
                self.lyrics_engine.load_words(path)

    def test_raw_transcript_still_loads(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            path = str(pathlib.Path(folder) / "song.words.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump([{"text": "hi", "start": 0.0, "end": 0.3}], handle)
            words, lines = self.lyrics_engine.load_transcript(path)
            self.assertEqual(len(words), 1)
            self.assertIsNone(lines)

    def test_the_face_animates_from_corrected_words(self):
        words = [word for line in self.corrected()["lines"]
                 for word in line["words"]]
        _, poses, _ = face_render.build_face_ass(words, 4.0)
        self.assertGreater(poses, 1)


class FaceGeometryTests(unittest.TestCase):
    def eye(self, **dials):
        return face_render.eye_outline(face_shapes.Eye(**dials))

    def test_an_eye_shuts_to_a_line_whatever_its_settings(self):
        for dials in ({"hook": 1.0}, {"roundness": 1.0}, {"bow": 1.0},
                      {"slant": -0.6}):
            shape = self.eye(openness=0.0, **dials)
            self.assertLess(_height(shape), face_render.EYE_THICKNESS, dials)

    def test_an_open_eye_is_taller_than_a_shut_one(self):
        self.assertGreater(_height(self.eye(openness=1.0)),
                           _height(self.eye(openness=0.0)) * 3)

    def test_the_hook_curls_the_outer_end_down(self):
        # The shape that makes a visor eye read as a visor eye rather than as
        # an eyebrow.
        straight = self.eye(hook=0.0)
        hooked = self.eye(hook=1.0)
        self.assertGreater(max(y for _, y in hooked),
                           max(y for _, y in straight))

    def test_roundness_carries_the_eye_to_an_oval(self):
        sharp = self.eye(roundness=0.0)
        round_ = self.eye(roundness=1.0)
        self.assertGreater(_height(round_), _height(sharp))

    def test_eyes_are_mirror_images(self):
        eye = face_shapes.Eye()
        right = face_render.eye_outline(eye)
        left = face_render.eye_outline(eye, mirrored=True)
        self.assertEqual([(-x, y) for x, y in right], left)

    def test_eyes_sit_outboard_like_a_visor(self):
        shape = face_render.eye_outline(face_shapes.Eye())
        centre = sum(x for x, _ in shape) / len(shape)
        self.assertGreater(abs(centre) / face_render.UNIT, 0.20)

    def test_the_mouth_is_always_solid(self):
        # Drawn as an outline it has to put a hole inside itself, and that
        # ring thins to nothing as the mouth closes.
        for aperture in (0.0, 0.15, 0.4, 0.7, 1.0):
            mouth = face_shapes.Mouth(0.86, aperture, 0.5)
            self.assertEqual(len(face_render.mouth_outline(mouth)), 1,
                             f"aperture {aperture}")

    def test_the_mouth_never_gets_thinner_than_a_stroke(self):
        for aperture in (0.0, 0.05, 0.1, 0.2, 0.3):
            shape = face_render.mouth_outline(
                face_shapes.Mouth(0.86, aperture, 0.5))[0]
            self.assertGreaterEqual(_height(shape),
                                    face_render.MOUTH_THICKNESS * 0.9,
                                    f"aperture {aperture}")

    def test_a_wider_aperture_opens_the_mouth_further(self):
        self.assertGreater(
            _height(face_render.mouth_outline(
                face_shapes.Mouth(0.86, 1.0, 0.3))[0]),
            _height(face_render.mouth_outline(
                face_shapes.Mouth(0.86, 0.3, 0.3))[0]))

    def test_skew_makes_the_mouth_asymmetric(self):
        # A symmetrical smile is what makes a resting face look like a mascot.
        shape = face_render.mouth_outline(
            face_shapes.Mouth(0.82, 0.0, 0.62, 0.34))[0]
        left = [y for x, y in shape if x < -50]
        right = [y for x, y in shape if x > 50]
        self.assertGreater(sum(left) / len(left) - sum(right) / len(right),
                           20.0)

    def test_jag_bends_the_closed_mouth_into_a_zigzag(self):
        plain = face_render.mouth_outline(
            face_shapes.Mouth(0.98, 0.0, 0.72, 0.0, 0.0))[0]
        zigzag = face_render.mouth_outline(
            face_shapes.Mouth(0.98, 0.0, 0.72, 0.0, 1.0))[0]
        self.assertGreater(_height(zigzag), _height(plain))

    def test_a_face_is_two_eyes_and_a_mouth_and_nothing_else(self):
        for name in face_expression.EXPRESSIONS:
            shapes = face_render.face_shapes_for(
                face_expression.resting_face(name))
            self.assertEqual(len(shapes), 3, name)
            for shape in shapes:
                self.assertGreaterEqual(len(shape), 3, name)

    def test_the_mouth_sits_on_the_muzzle(self):
        eye_span = 2 * (face_render.EYE_CENTRE_X + face_render.EYE_HALF_WIDTH)
        self.assertLess(2 * face_render.MOUTH_HALF_WIDTH, eye_span)
        self.assertGreater(face_render.MOUTH_CENTRE_Y,
                           face_render.EYE_CENTRE_Y)

    def test_the_mouth_moves_further_than_the_eyes(self):
        face = face_expression.resting_face("visor")
        still = face_render.face_shapes_for(face)
        shifted = face_render.face_shapes_for(face, muzzle=(40.0, 8.0))
        self.assertEqual(still[0], shifted[0])
        self.assertEqual(still[1], shifted[1])
        self.assertNotEqual(still[2], shifted[2])
        self.assertGreater(face_render.MOUTH_PARALLAX, 1.0)


class SharpnessTests(unittest.TestCase):
    """Anger is directness: straight edges, hard corners, and stillness."""

    def face(self, sharpness):
        return face_shapes.Face(face_shapes.Eye(), face_shapes.VISEMES["ah"],
                                sharpness)

    def test_sharpness_straightens_a_curve_onto_its_corner(self):
        control = (0.0, -80.0)
        curved = face_render._quadratic((-100.0, 0.0), control, (100.0, 0.0),
                                        steps=8, sharpness=0.0)
        hard = face_render._quadratic((-100.0, 0.0), control, (100.0, 0.0),
                                      steps=8, sharpness=1.0)
        self.assertAlmostEqual(hard[len(hard) // 2][1], control[1], places=6)
        self.assertGreater(curved[len(curved) // 2][1], control[1])

    def test_sharpness_changes_both_eye_and_mouth(self):
        soft = face_render.face_shapes_for(self.face(0.0))
        hard = face_render.face_shapes_for(self.face(1.0))
        self.assertNotEqual(soft[0], hard[0])
        self.assertNotEqual(soft[2], hard[2])

    def test_sharpness_blends_like_everything_else(self):
        soft = self.face(0.0)
        hard = self.face(1.0)
        self.assertAlmostEqual(soft.blended(hard, 0.5).sharpness, 0.5)

    def test_the_sharp_expression_is_angular_and_still(self):
        # A scowl that bobs along to the music is not a scowl.
        self.assertGreater(
            face_expression.resting_face("sharp").sharpness, 0.9)
        self.assertLess(face_expression.resting_motion("sharp"), 0.5)

    def test_other_expressions_keep_their_curves_and_their_movement(self):
        for name in ("visor", "happy", "wide"):
            self.assertEqual(face_expression.resting_face(name).sharpness, 0.0,
                             name)
            self.assertEqual(face_expression.resting_motion(name), 1.0, name)

    def test_an_unknown_expression_still_reports_a_motion(self):
        self.assertEqual(face_expression.resting_motion("nonsense"),
                         face_expression.resting_motion(
                             face_expression.DEFAULT_EXPRESSION))


class MatrixStyleTests(unittest.TestCase):
    """The same outlines shown as an LED panel lights them."""

    def shapes(self):
        return face_render.face_shapes_for(
            face_expression.resting_face("grin"))

    def test_a_face_lights_cells(self):
        dots = face_matrix.matrix_shapes(self.shapes(), columns=36)
        self.assertGreater(len(dots), 40)
        for dot in dots:
            self.assertEqual(len(dot), 4)

    def test_more_columns_light_more_cells(self):
        coarse = face_matrix.matrix_shapes(self.shapes(), columns=24)
        fine = face_matrix.matrix_shapes(self.shapes(), columns=48)
        self.assertGreater(len(fine), len(coarse))

    def test_the_grid_can_be_anchored_so_cells_do_not_shift(self):
        # Bounds taken per pose would make the whole panel jump every time
        # the mouth opened.
        bounds = (-500.0, -300.0, 500.0, 300.0)
        shut = face_render.face_shapes_for(face_shapes.Face(
            face_shapes.Eye(), face_shapes.VISEMES["rest"]))
        open_ = face_render.face_shapes_for(face_shapes.Face(
            face_shapes.Eye(), face_shapes.VISEMES["ah"]))
        first = face_matrix.matrix_shapes(shut, bounds=bounds)
        second = face_matrix.matrix_shapes(open_, bounds=bounds)
        grid = {(round(dot[0][0], 3), round(dot[0][1], 3))
                for dot in first} & {(round(dot[0][0], 3), round(dot[0][1], 3))
                                     for dot in second}
        self.assertTrue(grid, "the two poses should share grid positions")

    def test_nothing_lights_for_an_empty_face(self):
        self.assertEqual(face_matrix.matrix_shapes([]), [])

    def test_dots_leave_a_gap_so_the_grid_reads(self):
        self.assertLess(face_matrix.DOT_FILL, 1.0)


class FaceDocumentTests(unittest.TestCase):
    WORDS = [{"text": "hello", "start": 0.5, "end": 1.4},
             {"text": "world", "start": 1.6, "end": 2.6}]

    def build(self, **options):
        document, poses, _ = face_render.build_face_ass(
            self.WORDS, 8.0, **options)
        return document, poses

    def test_header_matches_the_chosen_format(self):
        document, _ = self.build(video_format="portrait")
        self.assertIn("PlayResX: 1080", document)
        self.assertIn("PlayResY: 1920", document)

    def test_every_event_carries_the_head_around(self):
        # libass anchors an \an7 drawing by its coordinate origin, not its
        # bounding box (measured, not assumed), so the drawing stays in the
        # face's own frame and \move carries it — no redraw per position.
        document, _ = self.build()
        events = [line for line in document.splitlines()
                  if line.startswith("Dialogue:")]
        self.assertTrue(events)
        for event in events:
            self.assertIn("\\an7\\move(", event)
            self.assertIn("\\frz", event)

    def test_a_held_pose_is_still_cut_for_movement(self):
        # A long silence as one event would slide the head in a straight line
        # across the whole of it.
        document, events = face_render.build_face_ass(
            [{"text": "hi", "start": 0.5, "end": 0.9}], 12.0)[0:2]
        self.assertGreater(events, 12.0 / face_render.MOTION_SEGMENT * 0.8)

    def test_holding_the_head_still_is_possible(self):
        document, _ = self.build(motion=0.0)
        moves = {line.split("\\move(")[1].split(")")[0]
                 for line in document.splitlines()
                 if "\\move(" in line}
        self.assertEqual(len(moves), 1, "the head should not move at all")

    def test_one_event_per_pose_whether_or_not_it_glows(self):
        # The bloom is a blurred border on the same event, not a second copy
        # of the drawing.
        with_glow, poses = self.build(glow=True)
        without, plain_poses = self.build(glow=False)
        self.assertEqual(poses, plain_poses)
        self.assertEqual(with_glow.count("Dialogue:"), poses)
        self.assertEqual(without.count("Dialogue:"), poses)
        self.assertIn("\\bord9", with_glow)
        self.assertIn("\\bord0", without)

    def test_pose_count_stays_modest_over_a_full_length_track(self):
        words = [{"text": "singing", "start": index * 0.5,
                  "end": index * 0.5 + 0.4} for index in range(480)]
        _, poses, _ = face_render.build_face_ass(words, 240.0)
        self.assertLess(poses, 6000)

    def test_face_colour_is_written_into_the_style(self):
        document, _ = self.build(colour="#FF0000")
        self.assertIn("&H0000FF&", document)

    def test_expression_changes_the_resting_face(self):
        content, _ = self.build(expression="^_^")
        sleepy, _ = self.build(expression="-_-")
        self.assertNotEqual(content, sleepy)


class SettingsTests(unittest.TestCase):
    """The face and the equaliser are alternatives, in the UI and headless."""

    def setUp(self):
        import app

        self.app = app

    def test_face_turns_the_equaliser_off(self):
        settings = self.app.normalise_settings(
            {"face": True, "waveform": "bottom"})
        self.assertEqual(settings["waveform"], "off")

    def test_equaliser_is_untouched_without_a_face(self):
        settings = self.app.normalise_settings(
            {"face": False, "waveform": "side"})
        self.assertEqual(settings["waveform"], "side")

    def test_every_setting_the_ui_sends_is_carried_through(self):
        for key in ("face", "faceColor", "facePlacement", "faceScale",
                    "faceGlow", "faceExpression", "engine"):
            self.assertIn(key, self.app.SETTING_KEYS)
            self.assertIn(key, self.app.DEFAULTS)

    def test_default_placement_scale_and_expression_are_renderable(self):
        self.assertIn(self.app.DEFAULTS["facePlacement"],
                      face_render.PLACEMENTS)
        self.assertGreater(self.app.DEFAULTS["faceScale"], 0.15)
        self.assertIn(self.app.DEFAULTS["faceExpression"],
                      face_expression.EXPRESSIONS)


class FilterGraphTests(unittest.TestCase):
    def graph(self, **settings):
        base = {"visualMode": "still", "waveform": "off"}
        base.update(settings)
        return video_effects.build_filter_graph(
            video_formats.VIDEO_FORMATS["landscape"], "lyrics.ass", base,
            face_path=settings.pop("face_path", None))

    def test_face_is_burned_in_under_the_lyrics(self):
        graph, _ = video_effects.build_filter_graph(
            video_formats.VIDEO_FORMATS["landscape"], "lyrics.ass",
            {"visualMode": "still", "waveform": "off"}, face_path="face.ass")
        self.assertLess(graph.index("face.ass"), graph.index("lyrics.ass"))

    def test_face_sits_after_the_visual_treatment(self):
        graph, _ = video_effects.build_filter_graph(
            video_formats.VIDEO_FORMATS["landscape"], "lyrics.ass",
            {"visualMode": "party", "waveform": "off"}, bpm=120,
            face_path="face.ass")
        self.assertLess(graph.index("hue="), graph.index("face.ass"))

    def test_graph_is_unchanged_without_a_face(self):
        graph, _ = video_effects.build_filter_graph(
            video_formats.VIDEO_FORMATS["landscape"], "lyrics.ass",
            {"visualMode": "still", "waveform": "off"})
        self.assertNotIn("faced", graph)


if __name__ == "__main__":
    unittest.main()
