"""Turn word timings into a smoothly moving mouth.

There are no phonemes in a word-timed transcript, so mouth shapes are derived
from spelling: each word is split into the articulations you can actually see —
vowel groups plus consonants like ``m``, ``f`` and ``w`` — and the word's
duration is shared out between them.

The shapes are then interpolated rather than cut between. One parametric mouth
is reshaped by each viseme, so every shape lies on a continuum with every other
and the mouth can travel between them instead of snapping. Following the words
this way, with smoothing, is enough: it needs no loudness measurement and no
separated vocal stem.
"""

from __future__ import annotations

import face_shapes

#: The mouth settings for each visible articulation live with the other dials,
#: so a viseme and a resting expression are the same kind of thing and can be
#: blended into one another.
VISEMES = face_shapes.VISEMES
REST = face_shapes.REST

_VOWEL_GROUPS = {
    "oo": "oo", "ou": "oh", "ow": "oh", "oa": "oh", "oi": "oh", "oy": "oh",
    "ee": "ee", "ea": "ee", "ie": "ee", "ei": "ee", "ey": "ee",
    "ai": "eh", "ay": "eh", "au": "oh", "aw": "oh",
    "ue": "oo", "ui": "oo", "eu": "oo", "ew": "oo",
}
_VOWELS = {"a": "ah", "e": "eh", "i": "ee", "o": "oh", "u": "oo", "y": "ee"}
#: Consonants worth a mouth shape of their own; the rest are invisible and
#: simply ride on the neighbouring vowel.
_VISIBLE_CONSONANTS = {
    "m": "mm", "b": "mm", "p": "mm",
    "f": "ff", "v": "ff",
    "w": "oo", "r": "oo",
    "th": "th", "s": "th", "z": "th", "sh": "oo", "ch": "oo", "j": "oo",
    "l": "ll",
}
_VOWEL_WEIGHT = 2.2
_CONSONANT_WEIGHT = 1.0

#: How long the mouth takes to settle after a phrase, and how early it starts
#: moving towards the next one. Real speech anticipates: the mouth is already
#: forming a shape before the sound arrives.
RELEASE_SECONDS = 0.14
ANTICIPATE_SECONDS = 0.13
#: Gaps shorter than this are inside a phrase — the mouth glides straight from
#: one articulation to the next without closing at all.
GLIDE_GAP = 0.40
#: Only after this long with nothing to sing does the face give up and go back
#: to its resting expression. Below it the mouth stays in the singing system,
#: closed but ready, rather than snapping to a smirk mid-verse.
IDLE_AFTER = 3.0
#: How much the mouth closes between words inside a phrase.
BETWEEN_WORDS = face_shapes.Mouth(0.84, 0.10, 0.50, 0.0, 0.0)


def word_visemes(word):
    """Visible articulations for one word as ``[(viseme, weight), ...]``."""
    text = "".join(character for character in word.lower()
                   if character.isalpha())
    if not text:
        return [(REST, 1.0)]

    sequence = []
    index = 0
    while index < len(text):
        pair = text[index:index + 2]
        if pair in _VOWEL_GROUPS:
            sequence.append((_VOWEL_GROUPS[pair], _VOWEL_WEIGHT))
            index += 2
            continue
        if pair in _VISIBLE_CONSONANTS:
            sequence.append((_VISIBLE_CONSONANTS[pair], _CONSONANT_WEIGHT))
            index += 2
            continue
        character = text[index]
        if character in _VOWELS:
            sequence.append((_VOWELS[character], _VOWEL_WEIGHT))
        elif character in _VISIBLE_CONSONANTS:
            sequence.append((_VISIBLE_CONSONANTS[character],
                             _CONSONANT_WEIGHT))
        index += 1

    if not sequence:
        # An all-invisible word ("shh", "tsk") still opens the mouth a little.
        return [("ll", 1.0)]
    # Collapse repeats so "mommy" does not stutter on the same shape.
    collapsed = [sequence[0]]
    for viseme, weight in sequence[1:]:
        if viseme == collapsed[-1][0]:
            collapsed[-1] = (viseme, collapsed[-1][1] + weight * 0.4)
        else:
            collapsed.append((viseme, weight))
    return collapsed


def viseme_timeline(words, minimum_hold=0.055):
    """``[(start, end, viseme), ...]`` covering every word, in order."""
    spans = []
    for word in words:
        start = float(word["start"])
        end = max(float(word["end"]), start + minimum_hold)
        sequence = word_visemes(word.get("text", ""))
        total = sum(weight for _, weight in sequence) or 1.0
        available = end - start
        # Very short words cannot show every articulation; keep the strongest.
        affordable = max(1, int(available / minimum_hold))
        if len(sequence) > affordable:
            # Drop the weakest articulations but keep the survivors in
            # spelling order, so a clipped word still reads left to right.
            strongest = sorted(range(len(sequence)),
                               key=lambda i: -sequence[i][1])[:affordable]
            sequence = [sequence[i] for i in sorted(strongest)]
            total = sum(weight for _, weight in sequence) or 1.0
        cursor = start
        for viseme, weight in sequence:
            step = available * (weight / total)
            spans.append((cursor, cursor + step, viseme))
            cursor += step
    spans.sort(key=lambda span: span[0])
    return spans


def _vocal_keyframes(track, start, end):
    """Mouth keys for singing the lyric sheet does not describe.

    A yodel or a held note has no words to derive a shape from, so the shape
    comes from the sound itself: how far the mouth opens follows the level,
    and it narrows as the level climbs, which is what the voice is doing when
    it jumps register.
    """
    if track is None or not track:
        return []
    keys = []
    for segment_start, segment_end in track.segments(start, end):
        step = 1.0 / 14.0          # fast enough for a yodel's alternation
        keys.append((max(start, segment_start - ANTICIPATE_SECONDS),
                     VISEMES[REST]))
        time = segment_start
        previous = track.level_at(time)
        while time < segment_end:
            level = track.level_at(time)
            rising = level - previous
            previous = level
            # Wide and open when the voice is full, narrower as it snaps up
            # into another register.
            width = 0.86 - 0.34 * max(0.0, min(1.0, rising * 6.0))
            aperture = 0.16 + 0.84 * level
            keys.append((time, face_shapes.Mouth(width, aperture, 0.28)))
            time += step
        keys.append((min(end, segment_end + RELEASE_SECONDS), VISEMES[REST]))
    return keys


def mouth_keyframes(words, vocals=None, idle_after=IDLE_AFTER):
    """``[(time, (width, aperture, smile)), ...]`` for the whole track.

    A key sits at the centre of each articulation. What happens between them
    depends on how long the gap is:

    * inside a phrase the mouth glides straight on to the next shape, because
      a mouth that returns to rest between every word looks like it is
      chewing;
    * across a longer gap it closes to a ready position and anticipates the
      next entry, but stays in the singing system;
    * only after ``idle_after`` seconds does it hand over to the resting
      expression, which is what the caller draws instead.

    ``vocals`` fills the gaps where the sheet is silent but the singer is not.
    """
    spans = viseme_timeline(words)
    if not spans and vocals is None:
        return []
    rest = VISEMES[REST]
    keys = []
    if spans:
        keys.append((max(0.0, spans[0][0] - ANTICIPATE_SECONDS), rest))

    for index, (start, end, viseme) in enumerate(spans):
        keys.append(((start + end) / 2.0, VISEMES[viseme]))
        following = spans[index + 1] if index + 1 < len(spans) else None
        if following is None:
            keys.append((end + RELEASE_SECONDS, rest))
            continue
        gap = following[0] - end
        if gap <= GLIDE_GAP:
            # Inside a phrase: no key at all, so the mouth travels straight
            # from this articulation to the next one.
            continue
        if gap < idle_after:
            # Between phrases: close towards a ready position, then lead back
            # in early rather than waiting for the next word to arrive.
            keys.append((end + RELEASE_SECONDS, BETWEEN_WORDS))
            keys.append((following[0] - ANTICIPATE_SECONDS, BETWEEN_WORDS))
        else:
            keys.append((end + RELEASE_SECONDS, rest))
            keys.append((following[0] - ANTICIPATE_SECONDS, rest))

    if vocals is not None and vocals:
        # Wordless singing lives in the gaps the sheet leaves behind.
        bounds = [0.0] + [point for span in spans
                          for point in (span[0], span[1])]
        edges = sorted(set(bounds))
        gaps = [(spans[i][1], spans[i + 1][0]) for i in range(len(spans) - 1)
                if spans[i + 1][0] - spans[i][1] > GLIDE_GAP]
        if spans:
            gaps.insert(0, (0.0, spans[0][0]))
            gaps.append((spans[-1][1], spans[-1][1] + 3600.0))
        else:
            gaps = [(0.0, 3600.0)]
        for gap_start, gap_end in gaps:
            keys.extend(_vocal_keyframes(vocals, gap_start, gap_end))

    keys.sort(key=lambda key: key[0])
    return keys


def sung_spans(words, vocals=None, idle_after=IDLE_AFTER):
    """``[(start, end), ...]`` stretches the mouth is performing, not resting.

    Everything outside these is long enough with nothing to sing that the face
    settles back into its resting expression.
    """
    spans = viseme_timeline(words)
    performing = [(start, end) for start, end, _ in spans]
    if vocals is not None and vocals:
        performing += vocals.segments(0.0, 1e9)
    if not performing:
        return []
    performing.sort()
    merged = [list(performing[0])]
    for start, end in performing[1:]:
        if start - merged[-1][1] < idle_after:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def _smoothstep(t):
    return t * t * (3.0 - 2.0 * t)


def mouth_at(keys, time, index_hint=0):
    """The interpolated mouth, plus a reusable search index."""
    rest = VISEMES[REST]
    if not keys:
        return rest, 0
    index = index_hint
    while index + 1 < len(keys) and keys[index + 1][0] <= time:
        index += 1
    while index > 0 and keys[index][0] > time:
        index -= 1
    if time <= keys[0][0]:
        return keys[0][1], 0
    if time >= keys[-1][0]:
        return keys[-1][1], len(keys) - 1

    start_time, start_value = keys[index]
    end_time, end_value = keys[min(index + 1, len(keys) - 1)]
    span = end_time - start_time
    if span <= 0:
        return end_value, index
    blend = _smoothstep(max(0.0, min(1.0, (time - start_time) / span)))
    return start_value.blended(end_value, blend), index
