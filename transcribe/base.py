"""Shared contract for every transcription backend.

An engine reports whether it can run *before* anything is downloaded or
loaded, so the UI can list real choices instead of failing mid-render. The
probe is the single source of truth: nothing else in the tool decides which
engines exist.
"""

from __future__ import annotations

import os


class EngineUnavailable(RuntimeError):
    """Raised when an engine is asked to work but its runtime is missing."""


class TranscriptionEngine:
    """Subclasses fill in the metadata and implement ``transcribe``.

    Constructors take engine-specific options as keyword arguments and must
    accept ``**_ignored``: the caller passes every engine's options to
    whichever engine it built, so one backend gaining a setting cannot break
    the others.
    """

    name = "base"
    label = "Base"
    detail = ""
    install_hint = ""
    #: lower sorts earlier when resolving the automatic choice
    priority = 100

    @classmethod
    def availability(cls):
        """Return ``(available, reason)``. ``reason`` explains a False."""
        raise NotImplementedError

    @classmethod
    def describe(cls):
        available, reason = cls.availability()
        return {
            "name": cls.name,
            "label": cls.label,
            "detail": cls.detail,
            "available": available,
            "reason": "" if available else reason,
            "installHint": cls.install_hint,
        }

    def transcribe(self, audio_path, progress=None):
        """Return ``[{'text': str, 'start': float, 'end': float}, ...]``."""
        raise NotImplementedError


def normalise_words(words, minimum_duration=0.04):
    """Sort, clamp and clean word records coming out of any engine."""
    cleaned = []
    for word in words:
        text = str(word.get("text", "")).strip()
        if not text:
            continue
        start = max(0.0, float(word.get("start", 0.0)))
        end = float(word.get("end", start))
        if end < start:
            start, end = end, start
        cleaned.append({"text": text,
                        "start": start,
                        "end": max(end, start + minimum_duration)})
    cleaned.sort(key=lambda item: item["start"])
    return cleaned


def merge_subword_tokens(tokens, timestamps, audio_end=None,
                         default_token_duration=0.08):
    """Fold sentencepiece sub-word tokens into whole words with timings.

    ``onnx-asr`` hands back one token and one emission time each. A leading
    space (or the raw U+2581 marker, depending on the vocabulary) marks the
    start of a new word; everything after it belongs to the word in progress.
    A token's end is the next token's emission time, because a transducer
    reports when a token *starts* being emitted.
    """
    words = []
    for index, raw in enumerate(tokens):
        token = str(raw)
        if not token.strip():
            continue
        starts_word = token.startswith(" ") or token.startswith("▁")
        text = token.replace("▁", " ").strip()
        if not text:
            continue
        start = float(timestamps[index])
        if index + 1 < len(timestamps):
            end = float(timestamps[index + 1])
        elif audio_end is not None:
            end = float(audio_end)
        else:
            end = start + default_token_duration
        if starts_word or not words:
            words.append({"text": text, "start": start, "end": end})
        else:
            words[-1]["text"] += text
            words[-1]["end"] = end
    return normalise_words(words)


def parse_clock(value):
    """'MM:SS.mmm' or 'HH:MM:SS.mmm' -> seconds."""
    parts = [part.replace(",", ".") for part in str(value).strip().split(":")]
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    return float(parts[0])


def words_from_payload(data):
    """Word records from any transcript JSON shape the tool accepts.

    Shapes:
      1. ``[{"timestamp": "MM:SS.mmm-MM:SS.mmm", "text": w}, ...]``
      2. ``{"segments": [{"words": [{"word": w, "start": s, "end": e}]}]}``
      3. ``[{"start": s, "end": e, "text": w}, ...]``
    """
    words = []
    if isinstance(data, dict) and "segments" in data:
        for segment in data["segments"]:
            contained = segment.get("words") or []
            if contained:
                for word in contained:
                    words.append({
                        "text": word.get("word", word.get("text", "")),
                        "start": word.get("start", 0),
                        "end": word.get("end", 0)})
            else:
                words.append({"text": segment.get("text", ""),
                              "start": segment.get("start", 0),
                              "end": segment.get("end", 0)})
    elif isinstance(data, list):
        for entry in data:
            if not isinstance(entry, dict):
                continue
            if "timestamp" in entry:
                stamp = str(entry["timestamp"])
                separator = "-->" if "-->" in stamp else "-"
                start, end = stamp.split(separator, 1)
                words.append({"text": entry.get("text", entry.get("word", "")),
                              "start": parse_clock(start),
                              "end": parse_clock(end)})
            else:
                words.append({"text": entry.get("text", entry.get("word", "")),
                              "start": entry.get("start", 0),
                              "end": entry.get("end", 0)})
    else:
        raise ValueError("Unrecognised transcript JSON structure")
    return normalise_words(words, minimum_duration=0.0)


def existing_transcript(audio_path):
    """A timed JSON already sitting beside the audio, if there is one."""
    base = os.path.splitext(audio_path)[0]
    for candidate in (base + ".words.json", base + ".json"):
        if os.path.isfile(candidate):
            return candidate
    return None
