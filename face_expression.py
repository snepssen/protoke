"""What the face is doing between the words: eye shapes and head movement.

Expressiveness comes from the silhouette rather than from detail inside the
eye, so there is no iris to animate — an eye is a line that expands into a
filled shape, and which shape it expands into is the whole vocabulary.

The face is not a static fixture. It is treated as though it were mounted on a
head you cannot see: it bobs, nods and tilts, and it moves more freely between
sung phrases than during them, the way a singer does when they are listening
rather than delivering.
"""

from __future__ import annotations

import math

import face_shapes


#: Resting faces, as dial settings rather than named outlines. Anything can
#: sit between any two of these, which is the point.
def _face(eye, mouth, sharpness=0.0):
    return face_shapes.Face(face_shapes.Eye(*eye), face_shapes.Mouth(*mouth),
                            sharpness)


#                    eye:  open  bow  slant hook  round weight
#                  mouth:  width aper curve skew  jag   weight
EXPRESSIONS = {
    "visor":     {"face": "◤‿◥", "label": "Visor smug",
                  "shape": _face((1.0, 0.55, 0.34, 0.80, 0.06, 1.0),
                                 (0.84, 0.0, 0.62, 0.34, 0.0, 1.0))},
    "grin":      {"face": "◤w◥", "label": "Visor grin",
                  "shape": _face((1.0, 0.62, 0.30, 0.85, 0.05, 1.0),
                                 (1.00, 0.0, 0.66, 0.0, 0.90, 0.95))},
    "hooked":    {"face": "︿﹀", "label": "Hooked",
                  "shape": _face((1.0, 0.95, 0.05, 1.00, 0.0, 0.78),
                                 (1.00, 0.0, 0.72, 0.0, 0.75, 0.86))},
    # Anger is directness. Straight edges, hard corners, and a head that
    # holds still — a scowl that bobs along to the music is not a scowl.
    "sharp":     {"face": "▶_◀", "label": "Sharp", "motion": 0.22,
                  "shape": _face((1.0, 0.10, -0.85, 0.55, 0.0, 1.10),
                                 (0.92, 0.0, 0.22, 0.0, 0.85, 1.05),
                                 sharpness=1.0)},
    "smug":      {"face": "¬‿¬", "label": "Smug",
                  "shape": _face((0.62, 0.18, 0.10, 0.30, 0.10, 0.95),
                                 (0.82, 0.0, 0.58, 0.42, 0.0, 1.0))},
    "content":   {"face": "^_^", "label": "Content",
                  "shape": _face((1.0, 1.00, 0.0, 0.10, 0.0, 0.95),
                                 (0.88, 0.0, 0.14, 0.0, 0.0, 1.0))},
    "happy":     {"face": "^w^", "label": "Happy",
                  "shape": _face((1.0, 1.00, 0.0, 0.10, 0.0, 0.95),
                                 (1.00, 0.0, 0.62, 0.0, 0.95, 0.95))},
    "wide":      {"face": "o_o", "label": "Wide eyed",
                  "shape": _face((1.0, 0.40, 0.0, 0.0, 1.0, 1.0),
                                 (0.88, 0.0, 0.10, 0.0, 0.0, 1.0))},
    "sleepy":    {"face": "-_-", "label": "Half asleep",
                  "shape": _face((0.24, 0.05, 0.0, 0.0, 0.0, 1.0),
                                 (0.86, 0.0, 0.08, 0.0, 0.0, 1.0))},
    "delighted": {"face": "^o^", "label": "Delighted",
                  "shape": _face((1.0, 1.00, 0.0, 0.10, 0.0, 0.95),
                                 (0.56, 0.78, 0.10, 0.0, 0.0, 1.0))},
    "curious":   {"face": "owo", "label": "Curious",
                  "shape": _face((1.0, 0.40, 0.0, 0.0, 1.0, 1.0),
                                 (1.00, 0.0, 0.62, 0.0, 0.90, 0.95))},
}
#: The visor eyes with a smirk: the shape the helmet actually wears, and a
#: singer's resting face rather than a mascot's.
DEFAULT_EXPRESSION = "visor"


BLINK_SECONDS = 0.16
#: Seconds between blinks, on average. Rested eyes go about ten seconds; an
#: awake, talking person is nearer four or five. The default sits with the
#: latter because a face on screen that rarely blinks reads as switched off.
BLINK_EVERY = 5.0
BLINK_FASTEST, BLINK_SLOWEST = 1.5, 30.0
#: How often a blink comes as a pair. People double-blink often enough that
#: never doing it is one of the things that reads as mechanical.
DOUBLE_BLINK_CHANCE = 0.18
DOUBLE_BLINK_GAP = 0.14


def resting(expression):
    """The dial settings for an expression, by name or by kaomoji."""
    if expression in EXPRESSIONS:
        return EXPRESSIONS[expression]
    for spec in EXPRESSIONS.values():
        if spec["face"] == expression:
            return spec
    return EXPRESSIONS[DEFAULT_EXPRESSION]


def resting_face(expression):
    """The :class:`face_shapes.Face` an expression rests at."""
    return resting(expression)["shape"]


def resting_motion(expression):
    """How freely the head moves in this expression, as a multiplier.

    An expression is not only a shape. Anger is direct, and directness is
    still: a scowl that bobs along to the music stops being a scowl.
    """
    return float(resting(expression).get("motion", 1.0))


# ------------------------------------------------------------------- blinking

def _random_sequence(seed):
    """A tiny deterministic generator; renders must repeat exactly."""
    state = seed & 0xFFFFFFFF
    while True:
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        yield state / 0x7FFFFFFF


def idle_blinks(duration, seed=20260906, every=BLINK_EVERY):
    """``[(start, end), ...]`` blinks, averaging one every ``every`` seconds.

    Intervals are drawn skewed rather than uniformly: real blinking clusters,
    with occasional long gaps, and evenly spaced blinks are conspicuously
    metronomic. Some arrive in pairs for the same reason.
    """
    every = max(BLINK_FASTEST, min(float(every), BLINK_SLOWEST))
    numbers = _random_sequence(seed)
    blinks = []
    # The first blink lands early and within a bounded window. Left to the
    # skewed draw it can be one of the long intervals, and a face that holds
    # its eyes open for the first ten seconds reads as switched off — which
    # matters most on a short clip, where that may be the only blink there is.
    time = every * (0.25 + 0.55 * next(numbers))
    while time < duration:
        # Right-skewed around the average: mostly a little under, sometimes
        # much longer. The exponent does the skewing, and the coefficient is
        # set so the mean interval lands on `every` — the mean of u**1.7 over
        # a uniform u is 1/2.7, so 0.42 + 1.567/2.7 == 1.0.
        time += every * (0.42 + 1.567 * next(numbers) ** 1.7)
        if time >= duration:
            break
        blinks.append((time, min(time + BLINK_SECONDS, duration)))
        if next(numbers) < DOUBLE_BLINK_CHANCE:
            second = time + BLINK_SECONDS + DOUBLE_BLINK_GAP
            if second + BLINK_SECONDS < duration:
                blinks.append((second, second + BLINK_SECONDS))
                time = second
    return blinks


def _blink_openness(blinks, time):
    """1.0 open, 0.0 shut, easing in and out of whichever blink contains t."""
    for start, end in blinks:
        if start <= time < end:
            half = (end - start) / 2.0 or 1.0
            closed = ((time - start) / half if time < start + half
                      else (end - time) / half)
            return max(0.0, 1.0 - min(1.0, closed))
    return 1.0


class EyePerformance:
    """The blink track for one song."""

    def __init__(self, duration, expression=DEFAULT_EXPRESSION,
                 seed=20260906, blink_every=BLINK_EVERY):
        self.duration = max(0.0, duration)
        self.blink_every = blink_every
        self.blinks = idle_blinks(self.duration, seed=seed,
                                  every=blink_every)

    def openness_at(self, time):
        """How far open the eyes are at ``time``, 1.0 unless blinking."""
        return _blink_openness(self.blinks, time)

    def summary(self):
        # A double blink is one event to the eye, so it is counted as one.
        events = 1 if self.blinks else 0
        for earlier, later in zip(self.blinks, self.blinks[1:]):
            if later[0] - earlier[0] > 0.5:
                events += 1
        rate = (self.duration / events) if events else 0.0
        return (f"{events} blink{'' if events == 1 else 's'}"
                + (f", one every {rate:.1f}s" if rate else ""))


# --------------------------------------------------------------- head motion

#: Displacements are fractions of the face's own width, so the movement scales
#: with the face rather than with the frame.
BOB_AMOUNT = 0.022
SWAY_AMOUNT = 0.011
TILT_DEGREES = 1.2
#: How much more freely the head moves when nothing is being sung.
BETWEEN_LINES = 1.6
#: Tempo used when none was measured or supplied.
FALLBACK_TEMPO = 100.0
#: Below this the track has no beat worth following — narration, free time,
#: an ambient bed. A head bobbing to a tempo nobody can hear is worse than a
#: still one, so the bob fades out and only breathing is left.
BEAT_FLOOR, BEAT_CEILING = 0.6, 2.0
#: How slowly the face breathes when there is no beat.
BREATH_SECONDS = 4.7


class HeadMotion:
    """Where the invisible head is pointing at a given moment.

    The bob follows the beat when there is one to follow. It needs the beat's
    *phase* as well as its rate, or it nods precisely between the beats rather
    than on them — and it needs to know whether the track has a beat at all,
    because narration and free-time music do not, and nodding to a tempo
    nobody can hear looks worse than keeping still. Where there is no beat the
    face breathes on a slow cycle instead. The sway and tilt run on their own
    unrelated periods so the movement never settles into an obvious loop.
    """

    def __init__(self, tempo=None, beat_phase=0.0, amount=1.0,
                 beat_confidence=1.0, seed=20260906):
        self.tempo = max(40.0, min(float(tempo or FALLBACK_TEMPO), 240.0))
        self.beat_phase = float(beat_phase or 0.0)
        self.amount = max(0.0, float(amount))
        span = BEAT_CEILING - BEAT_FLOOR
        self.beat = max(0.0, min(1.0,
                                 (float(beat_confidence) - BEAT_FLOOR) / span))
        self.phase = (seed % 1000) / 1000.0 * math.tau

    def at(self, time, singing=True):
        """``(dx, dy, tilt_degrees)`` as fractions of the face width."""
        if self.amount <= 0.0:
            return 0.0, 0.0, 0.0
        # Offset so beat zero lands where the music's beats actually land.
        beats = (time - self.beat_phase) * self.tempo / 60.0
        # Lowest exactly on the beat, rising back between them. A plain sine
        # puts the extreme halfway between beats, which reads as moving
        # against the music; squaring sharpens the drop into a nod.
        nod = ((math.cos(math.tau * beats) + 1.0) / 2.0) ** 2
        # Only bob as far as the track actually has a beat. With none, the
        # face breathes instead of nodding to something nobody can hear.
        breath = math.sin(math.tau * time / BREATH_SECONDS) * 0.34
        bob = (nod - 0.4) * self.beat + breath * (1.0 - self.beat)
        sway = math.sin(math.tau * beats / 8.0 + self.phase)
        tilt = math.sin(math.tau * beats / 6.0 + self.phase * 0.7)
        drift = math.sin(math.tau * time / 17.3 + self.phase)

        freedom = self.amount * (BETWEEN_LINES if not singing else 1.0)
        # Positive dy is downward: the head drops onto the beat.
        return (SWAY_AMOUNT * freedom * (sway * 0.7 + drift * 0.3),
                BOB_AMOUNT * freedom * bob,
                TILT_DEGREES * freedom * (tilt * 0.75 + drift * 0.25))
