"""MacWhisper's ``mw`` CLI — kept working, no longer required.

This was the tool's only transcriber. It stays as a macOS-only engine so
existing setups and already-transcribed sessions keep working, but it is now
one option behind the probe rather than the pipeline itself.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading

from .base import (TranscriptionEngine, EngineUnavailable, normalise_words,
                   words_from_payload)


DEFAULT_COMMAND = 'mw transcribe --persist "{input}"'
DATABASE = os.path.expanduser(
    "~/Library/Application Support/MacWhisper/Database/main.sqlite")


class MacWhisperEngine(TranscriptionEngine):
    name = "macwhisper"
    label = "MacWhisper (mw)"
    detail = "macOS only · needs MacWhisper Pro"
    install_hint = "MacWhisper → Settings → Advanced → Command-Line Tool"
    priority = 30

    @classmethod
    def availability(cls):
        if sys.platform != "darwin":
            return False, "macOS only"
        if not shutil.which("mw"):
            return False, "The mw command-line tool is not installed"
        return True, ""

    def __init__(self, ffmpeg=None, command=DEFAULT_COMMAND, **_ignored):
        available, reason = self.availability()
        if not available:
            raise EngineUnavailable(reason)
        self.command = command or DEFAULT_COMMAND
        self.ffmpeg = ffmpeg

    def transcribe(self, audio_path, progress=None):
        command_string = self.command.replace("{input}", audio_path)
        if progress:
            progress(0.02, f"Transcribing with MacWhisper: {command_string}")
        try:
            process = subprocess.Popen(shlex.split(command_string),
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True)
        except FileNotFoundError as exc:
            raise EngineUnavailable(
                "'mw' was not found. Install the CLI from MacWhisper → "
                "Settings → Advanced → Command-Line Tool, or choose another "
                "transcription engine.") from exc

        def watch_stderr():
            for line in process.stderr:
                match = re.search(r"(\d{1,3})\s*%", line)
                if match and progress:
                    progress(int(match.group(1)) / 100.0, "Transcribing")
        watcher = threading.Thread(target=watch_stderr, daemon=True)
        watcher.start()
        stdout, stderr = process.communicate()
        watcher.join(timeout=2)
        if process.returncode != 0:
            tail = " / ".join((stderr or "").strip().splitlines()[-3:])
            raise RuntimeError(f"mw exited with code {process.returncode}"
                               + (f" — {tail}" if tail else ""))

        # A customised command may print word-timed JSON straight out.
        try:
            direct = json.loads(stdout.strip())
        except (json.JSONDecodeError, ValueError):
            direct = None
        if direct:
            words = words_from_payload(direct)
            if words:
                if progress:
                    progress(1.0, f"Transcribed {len(words)} words")
                return words

        if progress:
            progress(0.9, "Reading word timings from MacWhisper's database")
        words = words_from_database(audio_path)
        if not words:
            raise RuntimeError(
                "Transcription finished but no word timings were found in "
                "MacWhisper's database. Make sure the command template "
                "includes --persist, and that the selected model supports "
                "word timestamps.")
        if progress:
            progress(1.0, f"Transcribed {len(words)} words")
        return words


def words_from_database(audio_path, db_path=DATABASE):
    """Word timings for the newest MacWhisper session matching this file."""
    import sqlite3

    if not os.path.isfile(db_path):
        return []
    stem, extension = os.path.splitext(os.path.basename(audio_path))
    extension = extension.lstrip(".")

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True,
                                 timeout=10)
    try:
        row = connection.execute(
            "SELECT id FROM session WHERE originalFilename = ? "
            "AND (originalExtension = ? OR originalExtension IS NULL) "
            "AND dateDeleted IS NULL "
            "ORDER BY dateCreated DESC LIMIT 1", (stem, extension)).fetchone()
        if not row:
            row = connection.execute(
                "SELECT id FROM session WHERE originalFilename = ? "
                "AND dateDeleted IS NULL "
                "ORDER BY dateCreated DESC LIMIT 1", (stem,)).fetchone()
        if not row:
            return []
        lines = connection.execute(
            'SELECT start, "end", text, wordsJson FROM transcriptline '
            "WHERE sessionId = ? "
            "ORDER BY COALESCE(orderIndex, start), start", (row[0],)).fetchall()
    finally:
        connection.close()

    words = []
    for start_ms, end_ms, text, words_json in lines:
        parsed = None
        if words_json:
            try:
                parsed = json.loads(words_json)
            except (json.JSONDecodeError, ValueError):
                parsed = None
        if parsed:
            for word in parsed:
                words.append({"text": str(word.get("text", "")),
                              "start": word["startTime"] / 1000.0,
                              "end": word["endTime"] / 1000.0})
        elif text and text.strip():
            words.append({"text": text.strip(),
                          "start": (start_ms or 0) / 1000.0,
                          "end": (end_ms or 0) / 1000.0})
    return normalise_words(words)
