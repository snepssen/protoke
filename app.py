#!/usr/bin/env python3
"""
Protoke — browser GUI + processing backend.

Pipeline per song:
  1. transcribe          -> word-timed transcript JSON  (or reuse existing .json)
  2. lyrics_engine       -> karaoke .ass subtitles (3 colours + black outline)
  2b. face_render        -> optional protogen-style face as a second .ass track
  3. ffmpeg              -> centre-cropped cover + audio + burned-in subtitles
                            at 1920x1080 or 1080x1920, 60fps .mp4

Runs on macOS, Windows and Linux. Which transcription engines are usable is
decided by ``transcribe.probe()`` rather than assumed anywhere here.

Run:  python3 app.py          (opens http://127.0.0.1:8765 in your browser)
Test: python3 app.py --render --audio a.wav --json t.json --cover c.jpg --out o.mp4
"""

import argparse
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import face_audio
import face_expression
import face_matrix
import face_presets
import face_preview
import face_render
import lyrics_engine
import lyrics_align
import platform_support
import separate
import track_assets
import transcribe
import video_effects
import video_formats

PORT = 8765
HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = {
    "accent": "#FFD400",    # word being voiced
    "active": "#FFFFFF",    # active line
    "inactive": "#8A99A8",  # next (inactive) line — steel grey
    "font": platform_support.default_font(),
    "sizeMode": "default",   # big | default | dense
    "smartSize": False,      # pick size mode per track automatically
    "spacing": "tight",      # tight | normal | wide
    "lineCount": 5,          # stable lyric lines visible together
    "lyricPosition": "lower",  # lower | center
    "lineGap": 1.2,
    "visualMode": "ambient",  # still | ambient | party
    "extremeMode": False,      # explicit photosensitive/strobe opt-in
    "waveform": "bottom",     # off | bottom | side
    "bpm": 0,                 # 0 estimates tempo for Party Hard
    "mwCmd": transcribe.macwhisper.DEFAULT_COMMAND,
    "engine": transcribe.AUTOMATIC,
    "face": False,              # protogen-style animated face overlay
    "faceColor": "",            # blank follows the sung-word colour
    "facePlacement": face_render.DEFAULT_PLACEMENT,
    "faceScale": face_render.DEFAULT_SCALE,
    "faceGlow": True,
    "faceMotion": 1.0,          # how freely the invisible head moves
    "faceBlink": face_expression.BLINK_EVERY,   # seconds between blinks
    "faceDials": None,          # a face dialled in through the editor
    "faceStyle": face_render.SOLID,   # solid outlines, or an LED cell grid
    "faceColumns": face_matrix.DEFAULT_COLUMNS,
    "faceVocals": True,         # animate singing the lyric sheet misses
    "separateVocals": False,    # opt-in: isolating the voice costs ~1 GB
    "separationQuality": separate.FAST,
    "keepVocalStem": False,     # leave the separated vocal beside the track
    "faceExpression": face_expression.DEFAULT_EXPRESSION,
    "preset": "medium",
    "format": "landscape",
}

#: Settings the browser sends and the renderer understands. Kept in one place
#: so a new control cannot be silently dropped between the two.
SETTING_KEYS = (
    "accent", "active", "inactive", "font", "sizeMode", "smartSize",
    "spacing", "lineCount", "lyricPosition", "lineGap", "visualMode",
    "extremeMode", "waveform", "bpm", "mwCmd", "engine", "face", "faceColor",
    "facePlacement", "faceScale", "faceGlow", "faceMotion", "faceVocals",
    "faceStyle", "faceColumns", "faceBlink", "faceDials",
    "separateVocals", "separationQuality", "keepVocalStem", "faceExpression",
    "reuseJson", "outputDir", "lyricsFile", "format",
)


def normalise_settings(settings):
    """Apply the rules the UI also enforces, so headless runs match it.

    The face and the equaliser are alternatives: the face carries the motion
    that the bars used to, and running both crowds the frame.
    """
    if settings.get("face"):
        settings["waveform"] = "off"
    return settings

JOBS = {}        # job_id -> state dict
JOBS_LOCK = threading.Lock()
SERVER_TOKEN = secrets.token_urlsafe(32)
MAX_REQUEST_BYTES = 1_000_000


# ---------------------------------------------------------------- ffmpeg pick

FFMPEG = platform_support.find_ffmpeg()
FFPROBE = platform_support.find_ffprobe(FFMPEG)


# ------------------------------------------------------------------ helpers

def log(job, msg):
    with JOBS_LOCK:
        job["log"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")


def set_state(job, **kw):
    with JOBS_LOCK:
        job.update(kw)


def audio_duration(path):
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except Exception:
        return None


def escape_for_subtitles_filter(path):
    """Escape a path for ffmpeg's subtitles= filter option value."""
    p = path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return p.replace("[", "\\[").replace("]", "\\]").replace(",", "\\,")


# ------------------------------------------------------------------ pipeline

def run_transcription(job, item, settings):
    """Transcribe one track with the chosen engine, saving <audio>.words.json."""
    audio = item["audio"]
    out_json = os.path.splitext(audio)[0] + ".words.json"
    engine_name = settings.get("engine") or transcribe.AUTOMATIC
    set_state(job, stage="transcribing")

    try:
        engine = transcribe.create(
            engine_name, ffmpeg=FFMPEG,
            command=settings.get("mwCmd", DEFAULTS["mwCmd"]))
    except transcribe.EngineUnavailable as exc:
        raise RuntimeError(str(exc)) from exc

    log(job, f"Transcribing with {engine.label}")

    def report(fraction, message):
        # Transcription owns the first 35% of the job's progress bar.
        set_state(job, progress=max(0.0, min(1.0, fraction)) * 0.35)
        if message:
            log(job, message)

    words = transcribe.normalise_words(
        engine.transcribe(audio, progress=report))
    if not words:
        raise RuntimeError(
            f"{engine.label} produced no word timings for "
            f"{os.path.basename(audio)}.")
    with open(out_json, "w", encoding="utf-8") as handle:
        json.dump(words, handle, ensure_ascii=False)
    log(job, f"Transcript saved: {os.path.basename(out_json)} "
             f"({len(words)} words)")
    return out_json


def prepare_cover(cover, out_dir, format_name):
    """Centre-crop cover art once, at the selected output dimensions."""
    profile = video_formats.get_video_format(format_name)
    width, height = profile["width"], profile["height"]
    scaled = os.path.join(
        out_dir, f"._cover_{width}x{height}_{uuid.uuid4().hex[:8]}.png")
    r = subprocess.run(
        [FFMPEG, "-y", "-i", cover,
         "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1",
         "-frames:v", "1", scaled],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("Cover art preparation failed: " + r.stderr[-400:])
    return scaled


def render_video(job, audio, cover, ass_path, out_path, preset="medium",
                 format_name="landscape", settings=None, face_path=None):
    if not FFMPEG:
        raise RuntimeError(
            "No ffmpeg with subtitle (libass) support was found. Install it "
            "with: " + platform_support.ffmpeg_install_hint())
    dur = audio_duration(audio)
    prepared_cover = prepare_cover(cover, os.path.dirname(out_path), format_name)
    sub = escape_for_subtitles_filter(ass_path)
    settings = settings or DEFAULTS
    bpm = None
    if settings.get("visualMode") == "party":
        if settings.get("extremeMode"):
            log(job, "WARNING: Extreme strobe enabled — output requires a "
                     "photosensitivity warning")
        try:
            manual_bpm = float(settings.get("bpm") or 0)
        except (TypeError, ValueError):
            manual_bpm = 0
        if manual_bpm > 0:
            bpm = max(40.0, min(manual_bpm, 240.0))
            log(job, f"Party Hard tempo: {bpm:g} BPM (manual)")
        else:
            estimated = video_effects.estimate_bpm(audio, FFMPEG)
            bpm = estimated or 120.0
            log(job, f"Party Hard tempo: {bpm:g} BPM "
                     f"({'estimated' if estimated else 'fallback'})")
    profile = video_formats.get_video_format(format_name)
    face = escape_for_subtitles_filter(face_path) if face_path else None
    filters, audio_map = video_effects.build_filter_graph(
        profile, sub, settings, bpm=bpm, face_path=face)
    cmd = [FFMPEG, "-y", "-loop", "1", "-framerate", "60", "-i", prepared_cover,
           "-i", audio,
           "-filter_complex", filters,
           "-map", "[video]", "-map", audio_map,
           "-c:v", "libx264", "-preset", preset, "-crf", "18",
           "-pix_fmt", "yuv420p", "-r", "60",
           "-c:a", "aac", "-b:a", "320k",
           "-shortest", "-movflags", "+faststart",
           "-progress", "pipe:1", "-nostats", "-loglevel", "error",
           out_path]
    log(job, "Rendering video with ffmpeg…")
    set_state(job, stage="rendering")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    err_lines = []

    def watch_err():
        for line in proc.stderr:
            err_lines.append(line)
    threading.Thread(target=watch_err, daemon=True).start()

    for line in proc.stdout:
        if line.startswith("out_time_ms=") and dur:
            try:
                done = int(line.split("=")[1]) / 1_000_000 / dur
                set_state(job, progress=0.40 + min(done, 1.0) * 0.60)
            except ValueError:
                pass
    proc.wait()
    try:
        os.remove(prepared_cover)
    except OSError:
        pass
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + "".join(err_lines)[-800:])


def process_item(job, item, settings):
    audio = item["audio"]
    companions = track_assets.resolve_track_assets(audio)
    cover = settings.get("cover") or companions["cover"]
    if not cover:
        raise RuntimeError(
            "No companion artwork found. Add a PNG/JPG with the same track "
            "name or choose fallback cover art.")
    name = os.path.splitext(os.path.basename(audio))[0]
    out_dir = settings.get("outputDir") or os.path.dirname(audio)
    format_name = settings.get("format", DEFAULTS["format"])
    profile = video_formats.get_video_format(format_name)
    out_path = os.path.join(out_dir, video_formats.output_name(audio, format_name))

    set_state(job, current=os.path.basename(audio), progress=0.0)

    # 1. transcript — reuse a .json next to the audio, then a previous
    # MacWhisper session on macOS, then transcribe fresh
    tjson = None
    if settings.get("reuseJson", True):
        existing = transcribe.existing_transcript(audio)
        if existing:
            log(job, f"Using existing transcript: {os.path.basename(existing)}")
            tjson = existing
        else:
            try:
                words = transcribe.macwhisper.words_from_database(audio)
            except Exception:
                words = []
            if words:
                tjson = os.path.splitext(audio)[0] + ".words.json"
                with open(tjson, "w", encoding="utf-8") as f:
                    json.dump(words, f, ensure_ascii=False)
                log(job, f"Reusing earlier MacWhisper transcription "
                         f"({len(words)} words from history)")
    if not tjson:
        tjson = run_transcription(job, item, settings)
    set_state(job, progress=0.35)

    # 1b. correct the words against the reference lyric sheet, if provided
    track = None
    auto_lyrics = False
    tracks = settings.get("_lyricTracks")
    if tracks:
        track = lyrics_align.match_track(tracks, audio)
    if not track and companions["lyrics"]:
        track = track_assets.parse_track_lyrics(companions["lyrics"])
        auto_lyrics = True

    if track:
        clean_lines = track_assets.clean_reference_lines(track["lines"])
        trans_words = lyrics_engine.load_words(tjson)
        data, st = lyrics_align.corrected_json(trans_words, clean_lines)
        tjson = os.path.splitext(audio)[0] + ".corrected.json"
        with open(tjson, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        source = (os.path.basename(companions["lyrics"])
                  if auto_lyrics else track["title"])
        log(job, f"Cleaned and aligned lyrics from '{source}': "
                 f"{st['matched']}/{st['ref_words']} words matched, "
                 f"{st['synthesized']} re-timed")
    elif tracks:
        log(job, "WARNING: no matching track title in the lyric sheet — "
                 "using raw transcription")
    else:
        log(job, "WARNING: no companion lyric file found — using raw "
                 "transcription")

    if not settings.get("cover"):
        log(job, f"Using companion artwork: {os.path.basename(cover)}")

    # 2. subtitles
    set_state(job, stage="styling")
    ass_path = os.path.join(out_dir, name + profile["suffix"] + ".ass")
    nwords, nlines, used_mode = lyrics_engine.transcript_to_ass(
        tjson, ass_path,
        colors={"accent": settings["accent"], "active": settings["active"],
                "inactive": settings["inactive"]},
        font=settings.get("font", DEFAULTS["font"]),
        size_mode=settings.get("sizeMode", DEFAULTS["sizeMode"]),
        spacing=settings.get("spacing", DEFAULTS["spacing"]),
        smart=bool(settings.get("smartSize", False)),
        gap_break=float(settings.get("lineGap", DEFAULTS["lineGap"])),
        line_count=int(settings.get("lineCount", DEFAULTS["lineCount"])),
        lyric_position=settings.get("lyricPosition", DEFAULTS["lyricPosition"]),
        video_format=format_name)
    smart_note = " (Smart)" if settings.get("smartSize") else ""
    log(job, f"Styled {nwords} words into {nlines} lyric lines "
             f"— {used_mode} size{smart_note} · "
             f"{settings.get('lineCount', DEFAULTS['lineCount'])} lines · "
             f"{settings.get('lyricPosition', DEFAULTS['lyricPosition'])} · "
             f"{profile['width']}x{profile['height']}")
    set_state(job, progress=0.40)

    # 2b. animated face, on its own subtitle track under the lyrics
    face_path = None
    if settings.get("face"):
        face_path = os.path.join(
            out_dir, name + profile["suffix"] + ".face.ass")
        # The head bobs to the beat, so the face wants a tempo whether or not
        # Party Hard asked for one.
        tempo, beat_phase, beat_confidence = face_tempo(job, audio, settings)
        vocals = face_vocals(job, audio, companions, settings)
        events, performance = build_face_track(
            job, audio, tjson, face_path, settings, format_name,
            tempo=tempo, beat_phase=beat_phase, vocals=vocals,
            beat_confidence=beat_confidence)
        log(job, f"Face: {events} events · "
                 f"{settings.get('faceStyle', DEFAULTS['faceStyle'])} · "
                 f"{settings.get('faceExpression', DEFAULTS['faceExpression'])}"
                 f" · {settings.get('facePlacement', DEFAULTS['facePlacement'])}"
                 f" · scale {float(settings.get('faceScale', DEFAULTS['faceScale'])):.2f}"
                 f" · {performance.summary()}")

    # 3. video
    render_video(job, audio, cover, ass_path, out_path,
                 preset=settings.get("preset", "medium"),
                 format_name=format_name, settings=settings,
                 face_path=face_path)
    log(job, f"Done: {out_path}")
    return out_path


def face_tempo(job, audio, settings):
    """``(bpm, beat_phase, confidence)`` for the head bob.

    A manual BPM has no phase to go with it, so the beats are assumed to start
    with the track.
    """
    try:
        manual = float(settings.get("bpm") or 0)
    except (TypeError, ValueError):
        manual = 0
    if manual > 0:
        return max(40.0, min(manual, 240.0)), 0.0, 1.0
    if not FFMPEG:
        return None, 0.0, 0.0
    tempo, phase, confidence = video_effects.estimate_tempo(audio, FFMPEG)
    if not tempo:
        log(job, "Head bob: no tempo could be measured; the face will breathe")
        return None, 0.0, 0.0
    if confidence < face_expression.BEAT_FLOOR:
        log(job, f"Head bob: no steady beat found (confidence "
                 f"{confidence:.2f}); the face will breathe rather than nod")
    else:
        log(job, f"Head bob: {tempo:g} BPM, beats at {phase:.2f}s, "
                 f"confidence {confidence:.2f}")
    return tempo, phase, confidence


def face_vocals(job, audio, companions, settings):
    """Listen for singing the lyric sheet does not describe.

    A separated vocal is exact and is used whenever one sits beside the track.
    Without one the voice has to be picked out of the full mix by how fast the
    level fluctuates, which is a guess — a good enough one to move a mouth
    through a yodel, but it will occasionally mistake a busy instrument for a
    singer.
    """
    if not settings.get("faceVocals", True) or not FFMPEG:
        return None
    stem = companions.get("vocals") or vocal_stem_for(job, audio, settings)
    source = stem or audio
    track = face_audio.VocalTrack.measure(
        source, FFMPEG, isolated=bool(stem),
        threshold=face_audio.STEM_THRESHOLD if stem
        else face_audio.MIX_THRESHOLD)
    if not track:
        log(job, "Face: no audio could be read for wordless singing")
        return None
    heard = sum(end - start for start, end in track.segments(0.0, 1e9))
    if stem:
        log(job, f"Wordless singing: from the isolated vocal "
                 f"({heard:.0f}s of voice)")
    else:
        hint = separate.mix_fallback_hint(
            bool(settings.get("separateVocals", False)))
        log(job, f"Wordless singing: estimated from the full mix "
                 f"({heard:.0f}s of voice) — {hint}")
    return track


def vocal_stem_for(job, audio, settings):
    """Separate the voice from the track, if a separator is installed.

    Cached: separating costs far more than rendering, and re-rendering the
    same track with different colours should not pay for it again.
    """
    if not settings.get("separateVocals", False):
        return None
    if not separate.available():
        return None
    quality = settings.get("separationQuality", separate.FAST)
    cache_root = platform_support.cache_dir()
    try:
        set_state(job, stage="separating")
        path, reused = separate.separated_vocal(
            audio, os.path.join(cache_root, "vocals"),
            quality=quality,
            model_dir=os.path.join(cache_root, "models"),
            progress=lambda fraction, message: log(job, message))
    except separate.SeparationUnavailable as exc:
        log(job, f"Vocal separation unavailable: {exc}")
        return None
    except Exception as exc:                       # noqa: BLE001 - report it
        log(job, f"Vocal separation failed ({exc}); "
                 f"estimating the voice from the full mix instead")
        return None
    log(job, f"Isolated vocal: {os.path.basename(path)}"
             f"{' (reused)' if reused else ''}")
    if settings.get("keepVocalStem"):
        beside = os.path.splitext(audio)[0] + "_(Vocals).wav"
        if not os.path.exists(beside):
            try:
                import shutil

                shutil.copy2(path, beside)
                log(job, f"Kept the vocal beside the track: "
                         f"{os.path.basename(beside)}")
            except OSError as exc:
                log(job, f"Could not keep the vocal beside the track: {exc}")
    return path


def build_face_track(job, audio, transcript_json, face_path, settings,
                     format_name, tempo=None, beat_phase=0.0,
                     vocals=None, beat_confidence=1.0):
    """Write the face's .ass track.

    Returns ``(event_count, performance)``.
    """
    set_state(job, stage="face")
    words, _ = lyrics_engine.load_transcript(transcript_json)
    duration = audio_duration(audio) or (
        max((word["end"] for word in words), default=0.0) + 2.0)

    colour = settings.get("faceColor") or settings.get("accent") \
        or DEFAULTS["accent"]
    return face_render.write_face_ass(
        face_path, words, duration,
        colour=colour,
        video_format=format_name,
        placement=settings.get("facePlacement", DEFAULTS["facePlacement"]),
        scale=float(settings.get("faceScale", DEFAULTS["faceScale"])),
        glow=bool(settings.get("faceGlow", True)),
        blink_every=float(settings.get("faceBlink", DEFAULTS["faceBlink"])),
        dials=settings.get("faceDials"),
        style=settings.get("faceStyle", DEFAULTS["faceStyle"]),
        columns=int(settings.get("faceColumns", DEFAULTS["faceColumns"])),
        motion=(float(settings.get("faceMotion", DEFAULTS["faceMotion"]))
                * face_expression.resting_motion(
                    settings.get("faceExpression",
                                 DEFAULTS["faceExpression"]))),
        tempo=tempo, beat_phase=beat_phase, vocals=vocals,
        beat_confidence=beat_confidence,
        expression=settings.get("faceExpression",
                                DEFAULTS["faceExpression"]))


def worker(job, settings):
    results, errors = [], []
    normalise_settings(settings)
    if settings.get("face"):
        log(job, "Face overlay on — the waveform equaliser is off for this run")
    lyr = settings.get("lyricsFile")
    if lyr:
        try:
            settings["_lyricTracks"] = lyrics_align.parse_lyric_sheet(lyr)
            log(job, f"Lyric sheet loaded: "
                     f"{len(settings['_lyricTracks'])} tracks")
        except Exception as e:
            log(job, f"WARNING: could not read lyric sheet: {e}")
    items = job["items"]
    for i, item in enumerate(items):
        set_state(job, itemIndex=i)
        try:
            results.append(process_item(job, item, settings))
        except Exception as e:
            log(job, f"ERROR ({os.path.basename(item['audio'])}): {e}")
            errors.append(str(e))
    set_state(job, stage="finished", progress=1.0,
              results=results, errors=errors,
              status="done" if not errors else
                     ("failed" if not results else "partial"))


# ------------------------------------------------------------------ file pickers

def scan_audio_folder(folder):
    """All supported audio files below a chosen folder."""
    return track_assets.scan_audio_tree(folder)


def pick(kind):
    """Native file chooser for the browser UI, on whichever platform."""
    return platform_support.pick(kind, scan_audio_tree=scan_audio_folder)


# ------------------------------------------------------------------ HTTP server

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):  # silence request logging
        pass

    def _authorised(self):
        supplied = self.headers.get("X-Protoke-Token", "")
        if not supplied:
            supplied = parse_qs(urlparse(self.path).query).get("token", [""])[0]
        return secrets.compare_digest(supplied, SERVER_TOKEN)

    def _require_auth(self):
        if self._authorised():
            return True
        self._send(403, {"error": "This request did not come from the active local app."})
        return False

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            if not self._require_auth():
                return
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif parsed.path.startswith("/api/"):
            if not self._require_auth():
                return
            if parsed.path.startswith("/api/status/"):
                jid = parsed.path.rsplit("/", 1)[1]
                with JOBS_LOCK:
                    job = JOBS.get(jid)
                    self._send(200, dict(job) if job else {"error": "unknown job"})
            elif parsed.path == "/api/defaults":
                self._send(200, {
                    **DEFAULTS,
                    "formats": video_formats.VIDEO_FORMATS,
                    "engines": transcribe.probe(),
                    "separators": separate.probe(),
                    "facePlacements": list(face_render.PLACEMENTS),
                    "faceStyles": list(face_render.STYLES),
                    "faceExpressions": face_presets.catalogue(),
                    "faceDials": {"eye": face_presets.EYE_DIALS,
                                  "mouth": face_presets.MOUTH_DIALS,
                                  "face": face_presets.FACE_DIALS},
                    "fonts": platform_support.font_choices(),
                    "ffmpeg": bool(FFMPEG),
                    "ffmpegHint": platform_support.ffmpeg_install_hint(),
                })
            else:
                self._send(404, {"error": "not found"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._require_auth():
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._send(400, {"error": "invalid Content-Length"})
            return
        if n < 0 or n > MAX_REQUEST_BYTES:
            self._send(413, {"error": "request body is too large"})
            return
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, {"error": "request body must be valid JSON"})
            return

        if self.path == "/api/pick":
            try:
                self._send(200, {"paths": pick(payload.get("kind", "audio"))})
            except platform_support.PickerUnavailable as e:
                self._send(200, {"paths": [], "error": str(e),
                                 "typePathInstead": True})
            except Exception as e:
                self._send(200, {"paths": [], "error": str(e)})

        elif self.path == "/api/assets":
            files = payload.get("files") or []
            self._send(200, {
                "items": [track_assets.resolve_track_assets(path)
                          for path in files]
            })

        elif self.path == "/api/start":
            files = payload.get("files") or []
            cover = payload.get("cover")
            if not files:
                self._send(400, {"error": "at least one audio file is required"})
                return
            format_name = payload.get("format", DEFAULTS["format"])
            try:
                video_formats.get_video_format(format_name)
            except ValueError as exc:
                self._send(400, {"error": str(exc)})
                return
            jid = uuid.uuid4().hex[:8]
            job = {"id": jid, "status": "running", "stage": "queued",
                   "progress": 0.0, "current": "", "itemIndex": 0,
                   "items": [{"audio": f} for f in files],
                   "log": [], "results": [], "errors": []}
            with JOBS_LOCK:
                JOBS[jid] = job
            settings = {key: payload.get(key, DEFAULTS.get(key))
                        for key in SETTING_KEYS}
            settings["cover"] = cover
            threading.Thread(target=worker, args=(job, settings),
                             daemon=True).start()
            self._send(200, {"jobId": jid})

        elif self.path == "/api/face/preview":
            try:
                self._send(200, face_preview.frames(
                    payload.get("dials") or {},
                    style=payload.get("style", face_render.SOLID),
                    columns=int(payload.get("columns",
                                            face_matrix.DEFAULT_COLUMNS)),
                    motion=float(payload.get("motion", 1.0))))
            except Exception as exc:                    # noqa: BLE001
                self._send(400, {"error": f"Could not draw that face: {exc}"})

        elif self.path == "/api/face/presets":
            self._send(200, {"presets": face_presets.catalogue()})

        elif self.path == "/api/face/save":
            try:
                face_presets.save(payload.get("name", ""),
                                  payload.get("dials") or {})
            except ValueError as exc:
                self._send(400, {"error": str(exc)})
                return
            except OSError as exc:
                self._send(500, {"error": f"Could not save: {exc}"})
                return
            self._send(200, {"presets": face_presets.catalogue()})

        elif self.path == "/api/face/delete":
            try:
                face_presets.delete(payload.get("name", ""))
            except OSError as exc:
                self._send(500, {"error": f"Could not delete: {exc}"})
                return
            self._send(200, {"presets": face_presets.catalogue()})

        elif self.path == "/api/expand":
            # Typed-path fallback for desktops with no file dialog: resolve a
            # pasted path the same way the picker would have.
            raw = os.path.expanduser(str(payload.get("path", "")).strip())
            kind = payload.get("kind", "audio")
            if not raw or not os.path.exists(raw):
                self._send(200, {"paths": [],
                                 "error": f"No such file or folder: {raw}"})
                return
            if kind == "audioFolder":
                if not os.path.isdir(raw):
                    self._send(200, {"paths": [],
                                     "error": "That path is not a folder."})
                    return
                found = scan_audio_folder(raw)
                self._send(200, {
                    "paths": found,
                    "error": "" if found
                             else "No supported audio files in that folder."})
            elif kind == "folder":
                self._send(200, {"paths": [raw]} if os.path.isdir(raw)
                           else {"paths": [],
                                 "error": "That path is not a folder."})
            else:
                self._send(200, {"paths": [raw]} if os.path.isfile(raw)
                           else {"paths": [],
                                 "error": "That path is not a file."})

        elif self.path == "/api/reveal":
            shown = platform_support.reveal(payload.get("path", ""))
            self._send(200, {"ok": shown})
        else:
            self._send(404, {"error": "not found"})


def open_window(url):
    """Show the UI in a native window if we can, else in the browser.

    The interface is already a local web page and the backend is already
    Python, so a desktop shell only has to supply a window — not a second
    runtime. pywebview uses the operating system's own webview, which is why
    it is a megabyte rather than the couple of hundred an embedded browser
    would cost, and why there is no second toolchain to build with.
    """
    try:
        import webview
    except ImportError:
        webbrowser.open(url)
        return False
    try:
        webview.create_window("Protoke", url,
                              width=1280, height=860, min_size=(940, 640))
        webview.start()
    except Exception:                                  # noqa: BLE001
        # Any desktop that cannot host a webview still has a browser.
        webbrowser.open(url)
        return False
    return True


def serve(window=True):
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/?token={SERVER_TOKEN}"
    print(f"Protoke running on http://127.0.0.1:{PORT}  (Ctrl+C to quit)")
    if not window:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nBye")
        return

    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if open_window(url):
        # The window owns the session: closing it ends the run.
        print("Bye")
        return
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nBye")


# ------------------------------------------------------------------ CLI render (testing / headless)

def resolve_output_path(rendered, requested):
    """Where ``--out`` actually wants the finished file.

    The render decides its own filename, so ask it where the file went rather
    than recomputing the path from ``--out`` — the two only agreed while both
    sat in the same folder. A folder for ``--out`` is an easy mistake and used
    to end in a traceback, so accept one and keep the rendered name.
    """
    if not requested:
        return rendered
    if os.path.isdir(requested):
        return os.path.join(requested, os.path.basename(rendered))
    return requested


def cli_render(args):
    job = {"id": "cli", "status": "running", "stage": "queued",
           "progress": 0.0, "current": "", "itemIndex": 0,
           "items": [{"audio": args.audio}], "log": [],
           "results": [], "errors": []}
    settings = dict(DEFAULTS)
    settings.update({"cover": args.cover, "reuseJson": True,
                     "outputDir": os.path.dirname(os.path.abspath(args.out)),
                     "format": args.format, "lineCount": args.lines,
                     "lyricPosition": args.lyric_position,
                     "visualMode": args.visual, "waveform": args.waveform,
                     "extremeMode": args.extreme, "bpm": args.bpm,
                     "engine": args.engine, "face": args.face,
                     "faceColor": args.face_color or "",
                     "facePlacement": args.face_placement,
                     "faceScale": args.face_scale,
                     "faceGlow": not args.no_face_glow,
                     "faceMotion": args.face_motion,
                     "faceStyle": args.face_style,
                     "faceBlink": args.blink_every,
                     "faceColumns": args.face_columns,
                     "faceVocals": not args.no_face_vocals,
                     "separateVocals": args.separate_vocals,
                     "separationQuality": args.separation_quality,
                     "keepVocalStem": args.keep_vocal_stem,
                     "faceExpression": args.face_expression})
    normalise_settings(settings)
    if args.accent:
        settings["accent"] = args.accent
    if args.preset:
        settings["preset"] = args.preset
    if args.json:
        base = os.path.splitext(args.audio)[0] + ".json"
        if os.path.abspath(args.json) != os.path.abspath(base):
            import shutil
            shutil.copy(args.json, base)
    rendered = process_item(job, job["items"][0], settings)
    destination = resolve_output_path(rendered, args.out)
    if os.path.abspath(rendered) != os.path.abspath(destination):
        import shutil
        shutil.move(rendered, destination)
    for l in job["log"]:
        print(l)
    print("Rendered:", destination)


def main(argv=None):
    """Entry point for both the console script and ``python3 app.py``."""
    ap = argparse.ArgumentParser(prog="protoke")
    ap.add_argument("--render", action="store_true", help="headless render")
    ap.add_argument("--browser", action="store_true",
                    help="open the interface in a browser rather than in a "
                         "desktop window")
    ap.add_argument("--audio")
    ap.add_argument("--json")
    ap.add_argument("--cover")
    ap.add_argument("--out")
    ap.add_argument("--accent")
    ap.add_argument("--preset")
    ap.add_argument("--format", choices=tuple(video_formats.VIDEO_FORMATS),
                    default=DEFAULTS["format"])
    ap.add_argument("--lines", type=int, choices=range(1, 6),
                    default=DEFAULTS["lineCount"])
    ap.add_argument("--lyric-position", choices=("lower", "center"),
                    default=DEFAULTS["lyricPosition"])
    ap.add_argument("--visual", choices=video_effects.VISUAL_MODES,
                    default=DEFAULTS["visualMode"])
    ap.add_argument("--waveform", choices=video_effects.WAVEFORM_MODES,
                    default=DEFAULTS["waveform"])
    ap.add_argument("--extreme", action="store_true",
                    help="enable rapid flashing and audio-reactive shaders")
    ap.add_argument("--bpm", type=float, default=DEFAULTS["bpm"],
                    help="Party Hard tempo; 0 estimates it from the audio")
    ap.add_argument("--engine",
                    choices=(transcribe.AUTOMATIC,
                             *(engine.name for engine in transcribe.ENGINES)),
                    default=DEFAULTS["engine"],
                    help="transcription engine; 'auto' picks the best "
                         "installed one")
    ap.add_argument("--engines", action="store_true",
                    help="list transcription engines and whether each can run")
    ap.add_argument("--face", action="store_true",
                    help="overlay the animated face (turns the equaliser off)")
    ap.add_argument("--face-color",
                    help="face colour as #RRGGBB; defaults to the sung-word "
                         "colour")
    ap.add_argument("--face-placement", choices=tuple(face_render.PLACEMENTS),
                    default=DEFAULTS["facePlacement"])
    ap.add_argument("--face-scale", type=float,
                    default=DEFAULTS["faceScale"],
                    help="face width as a fraction of the frame (0.15–1.2)")
    ap.add_argument("--no-face-glow", action="store_true",
                    help="draw the face without its neon bloom")
    ap.add_argument("--no-face-vocals", action="store_true",
                    help="ignore singing that has no words in the lyric sheet")
    ap.add_argument("--separate-vocals", action="store_true",
                    help="isolate the voice instead of estimating it from the "
                         "mix; needs a separator installed (~1 GB)")
    ap.add_argument("--separation-quality", choices=separate.QUALITIES,
                    default=separate.FAST,
                    help="'fast' is Demucs and is enough to find the voice; "
                         "'smooth' is MDX-Net and is slower but cleaner")
    ap.add_argument("--keep-vocal-stem", action="store_true",
                    help="also write the isolated vocal beside the track")
    ap.add_argument("--separators", action="store_true",
                    help="list vocal separators and whether each can run")
    ap.add_argument("--blink-every", type=float,
                    default=face_expression.BLINK_EVERY,
                    help="average seconds between blinks; rested eyes go "
                         "about 10, an awake talking person nearer 4 or 5")
    ap.add_argument("--face-style", choices=face_render.STYLES,
                    default=DEFAULTS["faceStyle"],
                    help="'solid' draws smooth outlines; 'matrix' samples "
                         "them onto a lit-cell grid like an LED visor")
    ap.add_argument("--face-columns", type=int,
                    default=face_matrix.DEFAULT_COLUMNS,
                    help="cells across the face in matrix style")
    ap.add_argument("--face-motion", type=float,
                    default=DEFAULTS["faceMotion"],
                    help="how freely the head bobs and tilts; 0 holds it still")
    ap.add_argument("--face-expression",
                    choices=tuple(face_expression.EXPRESSIONS),
                    default=DEFAULTS["faceExpression"],
                    help="the resting face; singing and blinks override it")
    a = ap.parse_args(argv)
    if a.separators:
        for engine in separate.probe():
            mark = "yes" if engine["available"] else "no "
            note = engine["reason"] or engine["detail"]
            print(f"  [{mark}] {engine['name']:<10} {engine['label']:<30} {note}")
            if not engine["available"] and engine["installHint"]:
                print(f"          install: {engine['installHint']}")
        raise SystemExit(0)
    if a.engines:
        for engine in transcribe.probe():
            mark = "yes" if engine["available"] else "no "
            note = engine["reason"] or engine["detail"]
            print(f"  [{mark}] {engine['name']:<16} {engine['label']:<26} {note}")
            if not engine["available"] and engine["installHint"]:
                print(f"          install: {engine['installHint']}")
        raise SystemExit(0)
    if a.render:
        missing = [name for name in ("audio", "out")
                   if not getattr(a, name)]
        if missing:
            ap.error("--render requires " + ", ".join("--" + name for name in missing))
        cli_render(a)
    else:
        serve(window=not a.browser)


if __name__ == "__main__":
    main()
