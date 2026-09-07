"""Decode audio for a transcription engine and cut it at quiet points.

Long songs are split before they reach a model. Chunking keeps peak memory
flat regardless of track length, lets the UI show real progress, and — by
cutting only where the track is already quiet — avoids slicing through the
middle of a sung word.
"""

from __future__ import annotations

import array
import math
import struct
import subprocess


SAMPLE_RATE = 16000


def decode_mono(audio_path, ffmpeg, sample_rate=SAMPLE_RATE, timeout=1800):
    """Return the whole track as a float32 ``array`` at ``sample_rate``."""
    command = [ffmpeg, "-v", "error", "-i", audio_path,
               "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "pipe:1"]
    result = subprocess.run(command, capture_output=True, timeout=timeout)
    if result.returncode != 0 or len(result.stdout) < 4:
        tail = (result.stderr or b"").decode("utf-8", "replace")[-300:]
        raise RuntimeError(
            f"Could not decode {audio_path} for transcription. {tail}".strip())
    samples = array.array("f")
    usable = len(result.stdout) - (len(result.stdout) % 4)
    samples.frombytes(result.stdout[:usable])
    return samples


def _rms_envelope(samples, sample_rate, window_seconds=0.05):
    window = max(1, int(sample_rate * window_seconds))
    envelope = []
    for start in range(0, len(samples) - window + 1, window):
        total = 0.0
        for index in range(start, start + window):
            total += samples[index] * samples[index]
        envelope.append(math.sqrt(total / window))
    return envelope, window


def split_points(samples, sample_rate=SAMPLE_RATE, target_seconds=110.0,
                 maximum_seconds=150.0):
    """Sample offsets to cut at: the quietest moment inside each search band.

    Returns cut offsets only — the caller pairs them into ranges.
    """
    total = len(samples)
    if total <= int(maximum_seconds * sample_rate):
        return []
    envelope, window = _rms_envelope(samples, sample_rate)
    if not envelope:
        return []

    cuts = []
    cursor = 0
    target = int(target_seconds * sample_rate)
    maximum = int(maximum_seconds * sample_rate)
    while total - cursor > maximum:
        # Look for the quietest window in the second half of the band, so
        # chunks stay near the target length instead of collapsing short.
        low = (cursor + target // 2) // window
        high = min(len(envelope) - 1, (cursor + maximum) // window)
        if high <= low:
            cut = cursor + target
        else:
            quietest = min(range(low, high + 1), key=lambda i: envelope[i])
            cut = quietest * window
        cut = max(cursor + window, min(cut, total - window))
        cuts.append(cut)
        cursor = cut
    return cuts


def chunks(samples, sample_rate=SAMPLE_RATE, target_seconds=110.0,
           maximum_seconds=150.0):
    """Yield ``(offset_seconds, float32 array)`` covering the whole track."""
    cuts = split_points(samples, sample_rate, target_seconds, maximum_seconds)
    bounds = [0, *cuts, len(samples)]
    for start, end in zip(bounds, bounds[1:]):
        if end > start:
            yield start / sample_rate, samples[start:end]


def to_numpy(samples):
    """A float32 NumPy view of the decoded samples, without a copy."""
    import numpy

    return numpy.frombuffer(samples, dtype=numpy.float32)


def write_wav(samples, path, sample_rate=SAMPLE_RATE):
    """16-bit PCM WAV, for engines that only accept a file path."""
    import wave

    pcm = bytearray()
    for value in samples:
        clipped = max(-1.0, min(1.0, value))
        pcm += struct.pack("<h", int(clipped * 32767))
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(pcm))
    return path
