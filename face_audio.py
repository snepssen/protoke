"""Hear the singing the lyric sheet does not describe.

A yodel, a held "ahh", a scat run — none of it appears in a transcript, so a
mouth driven only by words sits shut through all of it. This module supplies
the missing input.

The signal is not raw volume. A voice fluctuates at roughly syllable rate,
two to ten times a second, whether or not it is forming words, while
instruments sustain or land on the beat. Measuring how strongly the level
modulates in that band separates singing from backing well enough to move a
mouth, and it needs one pass over the full mix rather than a separated stem.
"""

from __future__ import annotations

import array
import math
import subprocess


FRAME_RATE = 50.0
#: A separated vocal only has to be audible to count. A full mix has to look
#: like a voice as well, so it needs a far higher bar before the mouth moves.
STEM_THRESHOLD = 0.12
MIX_THRESHOLD = 0.50
#: The band a voice lives in, give or take.
LOW_HZ, HIGH_HZ = 180, 3400
#: Syllables per second: the range that separates voice from accompaniment.
SLOWEST_SYLLABLE, FASTEST_SYLLABLE = 2.0, 10.0


def envelope(audio_path, ffmpeg, frame_rate=FRAME_RATE, timeout=900):
    """Vocal-band level per frame, normalised so a loud line reaches 1.0."""
    sample_rate = 4000
    command = [ffmpeg, "-v", "error", "-i", audio_path,
               "-af", f"highpass=f={LOW_HZ},lowpass=f={HIGH_HZ}",
               "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "pipe:1"]
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return [], frame_rate
    if result.returncode != 0 or len(result.stdout) < 4:
        return [], frame_rate

    samples = array.array("f")
    usable = len(result.stdout) - (len(result.stdout) % 4)
    samples.frombytes(result.stdout[:usable])

    window = max(1, int(sample_rate / frame_rate))
    levels = []
    for start in range(0, len(samples) - window + 1, window):
        total = 0.0
        for index in range(start, start + window):
            total += samples[index] * samples[index]
        levels.append(math.sqrt(total / window))
    if not levels:
        return [], frame_rate

    ordered = sorted(levels)
    reference = ordered[int(len(ordered) * 0.92)] or max(ordered) or 1.0
    return [min(1.0, value / reference) for value in levels], frame_rate


def _moving_average(values, window):
    if window <= 1 or not values:
        return list(values)
    averaged, half = [], window // 2
    for index in range(len(values)):
        low = max(0, index - half)
        high = min(len(values), index + half + 1)
        averaged.append(sum(values[low:high]) / (high - low))
    return averaged


def voiced_strength(levels, frame_rate=FRAME_RATE):
    """Per frame, how much this sounds like someone singing.

    The level is high-passed against its own slow average to leave only what
    fluctuates, then smoothed over about a syllable. A sustained pad has
    plenty of level and almost no modulation and so scores near zero; a voice
    scores high whether or not it is saying words.
    """
    if not levels:
        return []
    slow = _moving_average(levels, int(frame_rate / SLOWEST_SYLLABLE) | 1)
    fluctuation = [abs(value - baseline)
                   for value, baseline in zip(levels, slow)]
    # Smoothed over a syllable at the fastest rate we care about, so single
    # transients do not register as speech.
    modulation = _moving_average(
        fluctuation, max(1, int(frame_rate / FASTEST_SYLLABLE) * 3))
    peak = _percentile(modulation, 0.95) or max(modulation) or 1.0
    scaled = [min(1.0, value / peak) for value in modulation]
    # Both have to hold: something quiet cannot be a vocal, and something
    # loud but steady is an instrument.
    return [strength * min(1.0, level / 0.35)
            for strength, level in zip(scaled, levels)]


def _percentile(values, fraction):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


class VocalTrack:
    """Where the voice is, and how open the mouth should be, frame by frame."""

    def __init__(self, levels, strengths, frame_rate=FRAME_RATE,
                 threshold=MIX_THRESHOLD):
        self.levels = levels
        self.strengths = strengths
        self.frame_rate = frame_rate
        self.threshold = threshold

    @classmethod
    def measure(cls, audio_path, ffmpeg, isolated=False, **options):
        """Measure a track. ``isolated`` when the file is a vocal-only stem.

        On a full mix the level alone cannot say whether a voice is present,
        so how fast it fluctuates has to stand in. On an isolated vocal there
        is nothing else in the file: if it is loud, the singer is singing, and
        putting the mix's modulation test in front of that only throws away
        the held notes it was meant to catch.
        """
        levels, frame_rate = envelope(audio_path, ffmpeg)
        if isolated:
            strengths = _moving_average(levels,
                                        max(1, int(frame_rate * 0.12)))
        else:
            strengths = voiced_strength(levels, frame_rate)
        return cls(levels, strengths, frame_rate, **options)

    def __bool__(self):
        return bool(self.levels)

    def _index(self, time):
        return int(time * self.frame_rate)

    def strength_at(self, time):
        index = self._index(time)
        if index < 0 or index >= len(self.strengths):
            return 0.0
        return self.strengths[index]

    def level_at(self, time):
        index = self._index(time)
        if index < 0 or index >= len(self.levels):
            return 0.0
        return self.levels[index]

    def singing_at(self, time):
        return self.strength_at(time) >= self.threshold

    def segments(self, start, end, minimum_seconds=0.35):
        """Stretches of voice inside ``[start, end)``, merged across breaths."""
        if not self.strengths:
            return []
        found, run = [], None
        first, last = self._index(start), min(self._index(end),
                                              len(self.strengths))
        for index in range(max(0, first), max(0, last)):
            if self.strengths[index] >= self.threshold:
                if run is None:
                    run = index
            elif run is not None:
                found.append((run / self.frame_rate, index / self.frame_rate))
                run = None
        if run is not None:
            found.append((run / self.frame_rate, last / self.frame_rate))

        merged = []
        for segment in found:
            if merged and segment[0] - merged[-1][1] <= 0.25:
                merged[-1] = (merged[-1][0], segment[1])
            else:
                merged.append(segment)
        return [item for item in merged
                if item[1] - item[0] >= minimum_seconds]
