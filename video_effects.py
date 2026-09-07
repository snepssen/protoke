"""FFmpeg visual-treatment filters and lightweight tempo estimation."""

from __future__ import annotations

import math
import struct
import subprocess


VISUAL_MODES = ("still", "ambient", "party")
WAVEFORM_MODES = ("off", "bottom", "side")


def _hex(value, fallback="FFD400"):
    text = str(value or "").strip().lstrip("#")
    if len(text) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in text):
        return text.upper()
    return fallback


def _edge_glow(accent, strength=1.0):
    """Approximate a short edge falloff with concentric translucent strokes."""
    colour = _hex(accent)
    layers = ((0, 10, .11), (10, 10, .085), (20, 10, .063),
              (30, 10, .044), (40, 10, .028), (50, 10, .014))
    return ",".join(
        "drawbox="
        f"x={inset}:y={inset}:w=iw-{inset * 2}:h=ih-{inset * 2}:"
        f"color=0x{colour}@{alpha * strength:.3f}:t={thickness}"
        for inset, thickness, alpha in layers
    )


def build_filter_graph(profile, subtitle_path, settings, bpm=None,
                       face_path=None):
    """Return ``(filter_complex, audio_map)`` for one complete render.

    ``subtitle_path`` and ``face_path`` must already be escaped for FFmpeg's
    subtitles filter. ``audio_map`` is either an output label or the original
    input stream.

    The face is burned in before the lyrics and after every visual treatment,
    so it always sits on the artwork and under the words no matter which
    motion mode is running.
    """
    width, height = int(profile["width"]), int(profile["height"])
    mode = settings.get("visualMode", "ambient")
    waveform = settings.get("waveform", "bottom")
    extreme = bool(settings.get("extremeMode")) and mode == "party"
    if mode not in VISUAL_MODES:
        mode = "ambient"
    if waveform not in WAVEFORM_MODES:
        waveform = "bottom"

    video = ["fps=60"]
    if mode == "ambient":
        video.extend([
            "zoompan="
            "z='1.035+0.006*sin(on/55)':"
            "x='iw/2-(iw/zoom/2)+sin(on/49)*5':"
            "y='ih/2-(ih/zoom/2)+cos(on/61)*5':"
            f"d=1:s={width}x{height}:fps=60",
            "eq=brightness='0.010*sin(2*PI*t/4.2)':saturation=1.05:eval=frame",
            _edge_glow(settings.get("accent"), .68),
        ])
    elif mode == "party":
        tempo = max(40.0, min(float(bpm or 120.0), 240.0))
        if extreme:
            beat_phase = f"2*PI*on*{tempo:.3f}/3600"
            video.extend([
                "zoompan="
                f"z='1.085+0.032*sin({beat_phase})':"
                f"x='iw/2-(iw/zoom/2)+sin({beat_phase}*1.5)*18':"
                f"y='ih/2-(ih/zoom/2)+cos({beat_phase}*1.25)*18':"
                f"d=1:s={width}x{height}:fps=60",
                f"hue=h='mod(floor(t*{tempo:.3f}/30)*83,360)':s=1.78",
                "rgbashift=rh=9:rv=-4:bh=-9:bv=4:edge=wrap",
                f"eq=brightness='if(lt(mod(t,30/{tempo:.3f}),0.055),"
                "0.20,-0.035)':contrast=1.16:saturation=1.45:eval=frame",
                _edge_glow(settings.get("accent"), 1.72),
            ])
        else:
            video.extend([
                "zoompan="
                "z='1.055+0.018*sin(on/16)':"
                "x='iw/2-(iw/zoom/2)+sin(on/13)*10':"
                "y='ih/2-(ih/zoom/2)+cos(on/17)*10':"
                f"d=1:s={width}x{height}:fps=60",
                f"hue=h='mod(floor(t*{tempo:.3f}/60)*57,360)':s=1.34",
                _edge_glow(settings.get("accent"), 1.28),
            ])

    graph = [f"[0:v]{','.join(video)}[base]"]
    visual_input = "base"
    audio_map = "1:a:0"
    if waveform != "off":
        colour = _hex(settings.get("accent"))
        if extreme:
            graph.append(
                "[1:a]asplit=3[audioout][wavesource][shadersource]")
        else:
            graph.append("[1:a]asplit=2[audioout][wavesource]")
        audio_map = "[audioout]"
        visual_base = "base"
        if extreme:
            graph.append(
                f"[shadersource]showspectrum=s=320x180:slide=scroll:"
                "mode=combined:color=rainbow:scale=cbrt:fscale=log:"
                "saturation=2:gain=3:fps=30,tmix=frames=8,"
                "gblur=sigma=5,"
                f"scale={width}:{height}:flags=fast_bilinear,"
                "format=yuv420p[shader]")
            graph.append(
                "[base][shader]blend=all_mode=screen:"
                "all_opacity=0.34[reactive]")
            visual_base = "reactive"
        if waveform == "bottom":
            wave_height = max(72, round(height * .085))
            margin = max(28, round(height * .035))
            graph.append(
                f"[wavesource]showfreqs=s={width}x{wave_height}:mode=bar:"
                f"r=30:colors=0x{colour}@0.62:ascale=sqrt:fscale=log:"
                "averaging=4"
                + (",hue=h='t*180':s=2.2,tmix=frames=3" if extreme else "")
                + ",format=rgba,"
                "colorkey=0x000000:0.12:0.08[wave]")
            graph.append(
                f"[{visual_base}][wave]overlay=0:H-h-{margin}:"
                "format=auto[decorated]")
        else:
            wave_width = max(78, round(width * .07))
            margin = max(24, round(width * .025))
            graph.append(
                f"[wavesource]showfreqs=s={height}x{wave_width}:mode=bar:"
                f"r=30:colors=0x{colour}@0.60:ascale=sqrt:fscale=log:"
                "averaging=4"
                + (",hue=h='t*180':s=2.2,tmix=frames=3" if extreme else "")
                + ",format=rgba,"
                "colorkey=0x000000:0.12:0.08,transpose=1[wave]")
            graph.append(
                f"[{visual_base}][wave]overlay=W-w-{margin}:0:"
                "format=auto[decorated]")
        visual_input = "decorated"

    if face_path:
        graph.append(f"[{visual_input}]subtitles='{face_path}'[faced]")
        visual_input = "faced"
    graph.append(f"[{visual_input}]subtitles='{subtitle_path}'[video]")
    return ";".join(graph), audio_map


def _novelty(samples, sample_rate):
    """``(onset novelty, frame_rate)`` — where energy rises in the track."""
    if not samples or sample_rate <= 0:
        return [], 0.0
    hop = max(1, round(sample_rate / 40.0))
    envelope = []
    for start in range(0, len(samples) - hop + 1, hop):
        frame = samples[start:start + hop]
        envelope.append(math.sqrt(sum(value * value for value in frame) / hop))
    if len(envelope) < 80:
        return [], 0.0

    novelty = []
    for index, value in enumerate(envelope):
        history = envelope[max(0, index - 8):index]
        baseline = sum(history) / len(history) if history else value
        novelty.append(max(0.0, value - baseline))
    peak = max(novelty, default=0.0)
    if peak <= 1e-8:
        return [], 0.0
    return [value / peak for value in novelty], sample_rate / hop


def estimate_bpm_from_samples(samples, sample_rate=400.0, minimum=60, maximum=180):
    """Estimate tempo from mono PCM samples using energy-onset autocorrelation."""
    novelty, frame_rate = _novelty(samples, sample_rate)
    if not novelty:
        return None

    candidates = []
    seen_lags = set()
    for bpm in range(int(minimum), int(maximum) + 1):
        lag = max(1, round(frame_rate * 60.0 / bpm))
        if lag in seen_lags:
            continue
        seen_lags.add(lag)
        score = sum(novelty[i] * novelty[i - lag]
                    for i in range(lag, len(novelty)))
        score /= max(1, len(novelty) - lag)
        candidates.append((score, lag))
    score, lag = max(candidates)
    if score <= 1e-5:
        return None
    return round(frame_rate * 60.0 / lag, 1)


def estimate_tempo_and_phase(samples, sample_rate=400.0, minimum=60,
                             maximum=180):
    """``(bpm, phase_seconds, confidence)`` — the beat, and whether there is one.

    Tempo alone is not enough to move a head to the music: at the right rate
    but the wrong phase it nods precisely between the beats, which looks worse
    than not moving. The phase is the offset whose pulse train collects the
    most onset energy.

    ``confidence`` is how far the winning tempo stands above the rest of the
    field. Narration, free-time music and ambient beds have no beat to find,
    and every candidate scores about the same — a head bobbing to a tempo
    nobody can hear is worse than a still one, so the caller uses this to
    decide whether to bob at all.
    """
    novelty, frame_rate = _novelty(samples, sample_rate)
    if not novelty:
        return None, 0.0, 0.0

    candidates = []
    seen_lags = set()
    for bpm in range(int(minimum), int(maximum) + 1):
        lag = max(1, round(frame_rate * 60.0 / bpm))
        if lag in seen_lags:
            continue
        seen_lags.add(lag)
        score = sum(novelty[i] * novelty[i - lag]
                    for i in range(lag, len(novelty)))
        score /= max(1, len(novelty) - lag)
        candidates.append((score, lag))
    if not candidates:
        return None, 0.0, 0.0
    score, lag = max(candidates)
    if score <= 1e-5:
        return None, 0.0, 0.0
    average = sum(item[0] for item in candidates) / len(candidates)
    confidence = (score / average - 1.0) if average > 0 else 0.0

    best_offset, best_energy = 0, -1.0
    for offset in range(lag):
        energy = sum(novelty[index]
                     for index in range(offset, len(novelty), lag))
        if energy > best_energy:
            best_energy, best_offset = energy, offset
    return (round(frame_rate * 60.0 / lag, 1), best_offset / frame_rate,
            max(0.0, confidence))


def decode_for_tempo(audio_path, ffmpeg, seconds=90):
    """A short low-rate mono decode, enough to find onsets."""
    cmd = [ffmpeg, "-v", "error", "-t", str(seconds), "-i", audio_path,
           "-ac", "1", "-ar", "400", "-f", "f32le", "pipe:1"]
    result = subprocess.run(cmd, capture_output=True, timeout=seconds + 30)
    if result.returncode or len(result.stdout) < 4:
        return []
    count = len(result.stdout) // 4
    return [value[0] for value in struct.iter_unpack(
        "<f", result.stdout[:count * 4])]


def estimate_bpm(audio_path, ffmpeg, seconds=90):
    """Approximate BPM for a track, or None."""
    return estimate_bpm_from_samples(
        decode_for_tempo(audio_path, ffmpeg, seconds), 400.0)


def estimate_tempo(audio_path, ffmpeg, seconds=90):
    """``(bpm, phase_seconds, confidence)`` for a track."""
    return estimate_tempo_and_phase(
        decode_for_tempo(audio_path, ffmpeg, seconds), 400.0)
