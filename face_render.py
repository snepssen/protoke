"""Draw a protogen-style visor face and animate it against the vocal.

The face is vector geometry emitted as an ASS subtitle track, so it composites
through the same libass the lyrics already need — no image sequence, no extra
dependency, and it sits between the artwork and the lyrics no matter which
visual treatment is running.

A protogen's face is a dark visor carrying two lit elements: the eyes and the
mouth. Nothing else — flexOS drives ``visorEyes`` and ``visorMouth`` as two
separate LED panels and has no third one, so there is no nose here and no iris.

Both elements are drawn from continuous parameters rather than picked from a
list of outlines. That is deliberate: a face assembled by swapping between
fixed shapes cannot be half way between two of them, and never being between
anything is what makes such a face read as separate pieces stuck to a
background. :mod:`face_shapes` holds the dials; this module turns them into
geometry.
"""

from __future__ import annotations

import math

import face_expression
import face_matrix
import face_shapes
import face_visemes
import video_formats


#: Face-local drawing space. The face is authored in a 1000-unit square and
#: scaled to the frame, so every proportion below is resolution independent.
UNIT = 1000.0

PLACEMENTS = {
    "upper": 0.34,
    "center": 0.46,
    "lower": 0.62,
}
DEFAULT_PLACEMENT = "upper"
DEFAULT_SCALE = 0.62
#: How finely the face re-poses. Fine enough that the interpolated mouth reads
#: as travelling rather than stepping, coarse enough to stay cheap.
DEFAULT_STEP_RATE = 24.0
#: The head keeps moving while a pose is held, so an event is cut at least
#: this often even when the face has not changed shape. Without it a long
#: silence would be one event and the head would slide in a straight line
#: across the whole of it.
MOTION_SEGMENT = 0.12
#: How long the handover to the resting face takes once the singing has
#: stopped for good.
IDLE_BLEND = 0.5

#: How the face is drawn. "solid" is smooth outlines; "matrix" samples the
#: same outlines onto a lit-cell grid, the way an LED visor shows them.
SOLID, MATRIX = "solid", "matrix"
STYLES = (SOLID, MATRIX)

#: The eyes sit well outboard, as they do on a real visor: flexOS's idle face
#: puts them at roughly a third of the panel width either side of centre.
EYE_CENTRE_X = 268.0
EYE_CENTRE_Y = -132.0
EYE_HALF_WIDTH = 152.0
EYE_THICKNESS = 62.0
EYE_CLOSED_THICKNESS = 17.0
#: How high the ``^`` peaks, and how tall and wide the ``o`` opens.
EYE_CARET_RISE = 112.0
EYE_ROUND_HALF_WIDTH = 104.0
EYE_ROUND_HALF_HEIGHT = 118.0
#: Every shape narrows to this fraction of its width as it shuts, so a blink
#: from any expression lands on exactly the same line.
EYE_SHUT_WIDTH = 0.86

#: The face sits on a helmet with a muzzle, and the mouth is on the muzzle:
#: lower than a flat panel would put it, narrower than the eyes are far apart,
#: and further forward — which is what MOUTH_PARALLAX below is about.
MOUTH_CENTRE_Y = 126.0
MOUTH_HALF_WIDTH = 262.0
#: How much more the mouth moves than the eyes when the head shifts. It is
#: further out on the muzzle, so it swings wider; without this the face reads
#: as a flat sticker being slid around rather than a head turning.
MOUTH_PARALLAX = 1.7
MOUTH_APERTURE = 210.0
MOUTH_THICKNESS = 34.0
MOUTH_CORNER_LIFT = 78.0
#: Depth of the ``w`` mouth's two curves.
MOUTH_W_DEPTH = 62.0


# ------------------------------------------------------------------ geometry

def _quadratic(start, control, end, steps=14, sharpness=0.0):
    """Sample a quadratic bezier into a polyline.

    ``sharpness`` pulls the result towards the control polygon — the straight
    run start->control->end — so at 1.0 the arc becomes two straight edges
    meeting at a hard corner. Blending towards the polygon rather than
    switching to it keeps every value in between drawable, which is what lets
    an angry face be half way to a calm one.
    """
    points = []
    for step in range(steps + 1):
        t = step / steps
        inverse = 1.0 - t
        curved = (
            inverse * inverse * start[0] + 2 * inverse * t * control[0]
            + t * t * end[0],
            inverse * inverse * start[1] + 2 * inverse * t * control[1]
            + t * t * end[1])
        if sharpness <= 0.0:
            points.append(curved)
            continue
        if t < 0.5:
            local = t * 2.0
            straight = (start[0] + (control[0] - start[0]) * local,
                        start[1] + (control[1] - start[1]) * local)
        else:
            local = (t - 0.5) * 2.0
            straight = (control[0] + (end[0] - control[0]) * local,
                        control[1] + (end[1] - control[1]) * local)
        points.append((curved[0] + (straight[0] - curved[0]) * sharpness,
                       curved[1] + (straight[1] - curved[1]) * sharpness))
    return points


def _normals(points, closed=False):
    """Unit normal per point, averaged across the joins."""
    count = len(points)
    normals = []
    for index in range(count):
        if closed:
            previous = points[(index - 1) % count]
            following = points[(index + 1) % count]
        else:
            previous = points[max(0, index - 1)]
            following = points[min(count - 1, index + 1)]
        dx = following[0] - previous[0]
        dy = following[1] - previous[1]
        length = math.hypot(dx, dy) or 1.0
        normals.append((-dy / length, dx / length))
    return normals


def _stroke(points, thickness, closed=False):
    """Turn a path into a fillable outline of the given thickness.

    ``closed`` strokes a loop; treating a ring as an open path leaves a notch
    where the two ends meet.
    """
    if len(points) < 2:
        return []
    if not isinstance(thickness, (list, tuple)):
        thickness = [thickness] * len(points)
    normals = _normals(points, closed=closed)
    outer, inner = [], []
    for index, (x, y) in enumerate(points):
        nx, ny = normals[index]
        half = max(0.35, thickness[index] / 2.0)
        outer.append((x + nx * half, y + ny * half))
        inner.append((x - nx * half, y - ny * half))
    return outer + inner[::-1]


def _taper(count, peak, tip=0.10, tail=0.90):
    """Thickness along an eye: a fine inner point swelling to a blunt tail."""
    profile = []
    for index in range(count):
        fraction = index / max(1, count - 1)
        swell = math.sin(math.pi * min(1.0, fraction * 0.78 + 0.06))
        blend = tip + (1.0 - tip) * swell
        profile.append(max(0.6, peak * max(blend, tail * fraction)))
    return profile


def _oval(half_width, half_height, steps=30, sharpness=0.0):
    """A closed filled oval, centred on the origin.

    ``sharpness`` pulls it towards the diamond inscribed in the same box, so a
    hard expression gets an angular eye rather than a rounder one.
    """
    points = []
    for step in range(steps):
        angle = 2.0 * math.pi * step / steps
        cos, sin = math.cos(angle), math.sin(angle)
        x, y = half_width * cos, half_height * sin
        if sharpness > 0.0:
            edge = abs(cos) + abs(sin) or 1.0
            x += (x / edge - x) * sharpness
            y += (y / edge - y) * sharpness
        points.append((x, y))
    return points


# ---------------------------------------------------------------------- eyes

def eye_outline(eye, mirrored=False, sharpness=0.0):
    """One eye from its dials, in face units.

    A single shape covers the whole vocabulary. ``hook`` curls the outer end
    down into a point — the thing that makes a visor eye read as one rather
    than as an eyebrow. ``roundness`` inflates the same outline towards a
    filled oval, so a sharp wedge and ``o_o`` are one object at two settings
    and the face can sit anywhere between them.
    """
    openness = max(0.0, min(1.0, eye.openness))
    shut = EYE_HALF_WIDTH * EYE_SHUT_WIDTH
    half_width = shut + (EYE_HALF_WIDTH - shut) * openness
    height = EYE_CARET_RISE * 1.15 * openness
    thickness = (EYE_CLOSED_THICKNESS
                 + (EYE_THICKNESS - EYE_CLOSED_THICKNESS) * openness
                 * eye.weight)

    if eye.roundness >= 0.985:
        outline = _oval(half_width * 0.68,
                        max(EYE_CLOSED_THICKNESS / 2.0, height * 0.92),
                        sharpness=sharpness)
    else:
        # The spine runs inner point -> over the bow -> outer end, then the
        # hook drags that outer end back down and inward.
        slant = eye.slant * height * 0.55
        bow = eye.bow * height
        hook = eye.hook * height * 0.75
        spine = _quadratic((-half_width, slant * 0.35),
                           (-half_width * 0.18, -bow * 0.95),
                           (half_width * 0.72, -bow * 0.55 - slant),
                           steps=12, sharpness=sharpness)
        if hook > 1.0:
            spine += _quadratic(
                (half_width * 0.72, -bow * 0.55 - slant),
                (half_width * 1.02, -bow * 0.30 - slant),
                (half_width * 0.86, hook - bow * 0.20 - slant),
                steps=8, sharpness=sharpness)[1:]
        profile = _taper(len(spine), thickness, tip=0.10, tail=0.90)
        outline = _stroke(spine, profile)
        if eye.roundness > 0.0:
            # Inflate towards the oval rather than switching to it.
            oval = _oval(half_width * 0.68,
                         max(EYE_CLOSED_THICKNESS / 2.0, height * 0.92),
                         sharpness=sharpness)
            outline = morph(outline, oval, eye.roundness, count=40)

    sign = -1.0 if mirrored else 1.0
    return [(EYE_CENTRE_X * sign + x * sign, EYE_CENTRE_Y + y)
            for x, y in outline]


# --------------------------------------------------------------------- mouth

def _lens(half_width, aperture, lift, steps=30, sharpness=0.0):
    """A closed mouth aperture: an ellipse bent along a smiling centre line.

    Built directly rather than by offsetting a curve. The tips of a mouth are
    sharp enough that an offset outline folds through itself there, which
    showed up as notches in the corners.
    """
    points = []
    for step in range(steps):
        angle = 2.0 * math.pi * step / steps
        x = half_width * math.cos(angle)
        ratio = x / half_width if half_width else 0.0
        centre = MOUTH_CENTRE_Y + lift * 0.75 - lift * 1.75 * ratio * ratio
        y = centre + (aperture / 2.0) * math.sin(angle)
        if sharpness > 0.0:
            # Towards the diamond in the same box: an angular open mouth.
            edge = abs(math.cos(angle)) + abs(math.sin(angle)) or 1.0
            x += (x / edge - x) * sharpness
            y = centre + (y - centre) / edge * sharpness \
                + (y - centre) * (1.0 - sharpness)
        points.append((x, y))
    return points


def mouth_outline(mouth, sharpness=0.0):
    """One mouth from its dials, in face units.

    Solid, never an outline: drawn as a ring it has to put a hole inside
    itself, and that ring thins to nothing as the mouth closes. ``skew`` lifts
    one corner further than the other, and ``jag`` bends the closed line into
    the zigzag grin a visor wears at rest.
    """
    half_width = MOUTH_HALF_WIDTH * max(0.05, mouth.width)
    aperture = MOUTH_APERTURE * max(0.0, mouth.aperture)
    lift = MOUTH_CORNER_LIFT * mouth.curve
    skew = MOUTH_CORNER_LIFT * mouth.skew

    if aperture < MOUTH_THICKNESS:
        left = (-half_width, MOUTH_CENTRE_Y - lift + skew)
        right = (half_width, MOUTH_CENTRE_Y - lift - skew)
        if mouth.jag > 0.001:
            spine = _jagged(left, right, lift, mouth.jag, sharpness=sharpness)
        else:
            spine = _quadratic(left, (0.0, MOUTH_CENTRE_Y + lift * 0.75),
                               right, steps=16, sharpness=sharpness)
        return [_stroke(spine, MOUTH_THICKNESS * mouth.weight)]
    return [_lens(half_width, aperture, lift, sharpness=sharpness)]


def _jagged(left, right, lift, amount, peaks=2, sharpness=0.0):
    """A zigzag between two corners: the resting grin of a visor face.

    Two broad points, not a row of small ones — more than that stops reading
    as a mouth and starts reading as a scribble. The ends also ride up towards
    the eyes, which is what ties the face together as one drawing.
    """
    points = []
    span = right[0] - left[0]
    for step in range(peaks * 2 + 1):
        fraction = step / (peaks * 2)
        x = left[0] + span * fraction
        base = left[1] + (right[1] - left[1]) * fraction
        swing = lift * 0.46 * amount * (1 if step % 2 else -1)
        # Lift the outer ends so the mouth reaches back towards the eyes.
        ends = lift * 0.55 * amount * (1.0 - abs(fraction - 0.5) * 2.0)
        points.append((x, base + lift * 0.45 + swing + ends))
    smoothed = []
    for index in range(len(points) - 1):
        smoothed += _quadratic(points[index],
                               ((points[index][0] + points[index + 1][0]) / 2,
                                points[index][1]),
                               points[index + 1], steps=4,
                               sharpness=sharpness)[:-1]
    smoothed.append(points[-1])
    return smoothed


def _signed_area(points):
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _resample(points, count):
    """Evenly spaced points around a closed outline, from a fixed start.

    Morphing two outlines needs them to have the same number of points and to
    start in the same place, or the shape turns inside out on the way across.
    """
    if len(points) < 3:
        return list(points)
    if _signed_area(points) < 0:
        points = points[::-1]
    start = min(range(len(points)), key=lambda i: (points[i][0], points[i][1]))
    ordered = points[start:] + points[:start]

    lengths, total = [], 0.0
    for current, following in zip(ordered, ordered[1:] + ordered[:1]):
        total += math.hypot(following[0] - current[0],
                            following[1] - current[1])
        lengths.append(total)
    if total <= 0:
        return [ordered[0]] * count

    sampled, index = [], 0
    for step in range(count):
        target = total * step / count
        while index < len(lengths) - 1 and lengths[index] < target:
            index += 1
        previous = lengths[index - 1] if index else 0.0
        span = lengths[index] - previous or 1.0
        blend = (target - previous) / span
        current = ordered[index]
        following = ordered[(index + 1) % len(ordered)]
        sampled.append((current[0] + (following[0] - current[0]) * blend,
                        current[1] + (following[1] - current[1]) * blend))
    return sampled


def morph(first, second, blend, count=48):
    """One outline part way to another."""
    a = _resample(first, count)
    b = _resample(second, count)
    return [(x1 + (x2 - x1) * blend, y1 + (y2 - y1) * blend)
            for (x1, y1), (x2, y2) in zip(a, b)]


def face_shapes_for(face, muzzle=(0.0, 0.0)):
    """Every filled outline making up one pose, in face units.

    Two eyes and a mouth — the whole face. ``muzzle`` shifts the mouth alone:
    it sits further forward on the snout, so when the head moves it swings
    wider than the eyes do, and without that the face reads as a flat sticker
    being slid around the frame.
    """
    offset_x, offset_y = muzzle
    sharpness = max(0.0, min(1.0, getattr(face, "sharpness", 0.0)))
    mouth = mouth_outline(face.mouth, sharpness=sharpness)
    if offset_x or offset_y:
        mouth = [[(x + offset_x, y + offset_y) for x, y in shape]
                 for shape in mouth]
    return [eye_outline(face.eye, sharpness=sharpness),
            eye_outline(face.eye, mirrored=True, sharpness=sharpness),
            *mouth]


# ----------------------------------------------------------------- ASS output

ASS_HEADER = """[Script Info]
Title: Lyric video face
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Face,Arial,20,{colour},{colour},&H000000&,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Text
"""


def ass_colour(value, fallback="#4FE3F5"):
    """'#RRGGBB' -> ASS '&HBBGGRR&'."""
    text = str(value or "").strip().lstrip("#")
    if len(text) != 6 or any(character not in "0123456789abcdefABCDEF"
                             for character in text):
        text = fallback.lstrip("#")
    red, green, blue = text[0:2], text[2:4], text[4:6]
    return f"&H{blue.upper()}{green.upper()}{red.upper()}&"


def _ass_time(seconds):
    seconds = max(0.0, seconds)
    centiseconds = int(round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{whole:02}.{centiseconds:02}"


def _draw(shapes, scale):
    """Face-unit outlines -> one ASS drawing command string.

    Coordinates stay in the face's own frame, centred on its origin, and the
    head's position is applied with ``\\move`` instead. libass anchors an
    ``\\an7\\pos`` drawing by its coordinate origin rather than its bounding
    box — measured, not assumed — so the same drawing can be carried around
    the frame without redrawing it, and a pose whose mouth is wide open sits
    exactly where one with a shut mouth would.
    """
    parts = []
    for shape in shapes:
        if len(shape) < 3:
            continue
        points = []
        for x, y in shape:
            # Whole pixels: the face is blurred anyway, and the decimals
            # were a sixth of the subtitle file on a full-length track.
            points.append(f"{round(x * scale)} {round(y * scale)}")
        parts.append("m " + points[0] + " l " + " ".join(points[1:]))
    return " ".join(parts)


def build_face_ass(words, duration, colour="#4FE3F5", video_format="landscape",
                   placement=DEFAULT_PLACEMENT, scale=DEFAULT_SCALE,
                   step_rate=DEFAULT_STEP_RATE, glow=True, motion=1.0,
                   style=SOLID, columns=face_matrix.DEFAULT_COLUMNS,
                   tempo=None, beat_phase=0.0, beat_confidence=1.0,
                   vocals=None,
                   expression=face_expression.DEFAULT_EXPRESSION,
                   blink_every=face_expression.BLINK_EVERY, dials=None,
                   blink_seed=20260906):
    """Return ``(ass_document, event_count, performance)`` for a whole track.

    An event is written when the pose changes, and in any case often enough
    that the head keeps moving through a held pose. Within each event the head
    glides between its start and end position, so the movement is continuous
    rather than stepped even though the shapes are not.
    """
    profile = video_formats.get_video_format(video_format)
    width, height = int(profile["width"]), int(profile["height"])
    placement_ratio = PLACEMENTS.get(placement, PLACEMENTS[DEFAULT_PLACEMENT])
    scale = max(0.15, min(float(scale), 1.2))
    face_width = min(width, height * 1.35) * scale
    unit_scale = face_width / UNIT
    centre_x = width / 2.0
    centre_y = height * placement_ratio

    keys = face_visemes.mouth_keyframes(words, vocals=vocals)
    performing = face_visemes.sung_spans(words, vocals=vocals)
    # A face dialled in through the editor overrides the named expression, so
    # a saved preset renders exactly as it previewed.
    if dials:
        import face_presets

        resting = face_presets.to_face(dials)
    else:
        resting = face_expression.resting_face(expression)
    performance = face_expression.EyePerformance(
        duration, expression=expression, seed=blink_seed,
        blink_every=blink_every)
    head = face_expression.HeadMotion(tempo=tempo, beat_phase=beat_phase,
                                      amount=motion, seed=blink_seed,
                                      beat_confidence=beat_confidence)
    step = 1.0 / max(4.0, float(step_rate))
    colour_code = ass_colour(colour)

    def idleness(time):
        """0 while the face is performing, 1 once it has settled to rest."""
        for start, end in performing:
            if start - IDLE_BLEND <= time <= end + IDLE_BLEND:
                if time < start:
                    return (start - time) / IDLE_BLEND
                if time > end:
                    return (time - end) / IDLE_BLEND
                return 0.0
        return 1.0

    def head_at(time, singing):
        dx, dy, tilt = head.at(time, singing=singing)
        return centre_x + dx * face_width, centre_y + dy * face_width, tilt

    def muzzle_at(time, singing):
        """How much further the mouth travels than the eyes, in face units."""
        dx, dy, _ = head.at(time, singing=singing)
        extra = MOUTH_PARALLAX - 1.0
        return dx * UNIT * extra, dy * UNIT * extra * 0.5

    # The grid is anchored to the face, not to each pose: measured from the
    # widest the face ever gets, so the cells stay put while the shapes
    # inside them change. Bounds taken per pose would make the whole panel
    # jump every time the mouth opened.
    matrix = style == MATRIX
    grid_bounds = None
    if matrix:
        widest = face_shapes_for(
            face_shapes.Face(resting.eye.with_openness(1.0),
                             face_shapes.VISEMES["ah"]))
        xs = [x for shape in widest for x, _ in shape]
        ys = [y for shape in widest for _, y in shape]
        pad = (max(xs) - min(xs)) * 0.04
        grid_bounds = (min(xs) - pad, min(ys) - pad,
                       max(xs) + pad, max(ys) + pad)

    # A panel is bolted to the head; its cells do not slide. So matrix mode
    # does not need an event every eighth of a second to keep the movement
    # smooth, and cutting fewer of them is most of the difference between a
    # four megabyte subtitle track and an eighteen megabyte one.
    segment = MOTION_SEGMENT * (4.0 if matrix else 1.0)

    events = []
    state = None          # (pose key, drawing, singing)
    pose_start = 0.0

    def flush(end, singing):
        if state is None or end - pose_start < 0.005:
            return
        start_x, start_y, start_tilt = head_at(pose_start, singing)
        end_x, end_y, end_tilt = head_at(end, singing)
        movement = (f"\\move({start_x:.1f},{start_y:.1f},"
                    f"{end_x:.1f},{end_y:.1f})")
        rotation = f"\\frz{start_tilt:.2f}"
        if abs(end_tilt - start_tilt) > 0.01:
            rotation += f"\\t(\\frz{end_tilt:.2f})"
        finish = (f"\\bord9\\3c{colour_code}\\3a&H70&\\blur11"
                  if glow else "\\bord0\\blur1.2")
        events.append(
            f"Dialogue: 0,{_ass_time(pose_start)},{_ass_time(end)},"
            f"Face,,0,0,0,{{\\an7{movement}{rotation}\\shad0"
            f"\\1c{colour_code}{finish}\\p1}}{state[1]}\n")

    mouth_hint = 0
    steps = int(math.ceil(max(0.0, duration) / step)) + 1
    for index in range(steps):
        time = index * step
        rest_blend = idleness(time)
        singing = rest_blend < 1.0
        openness = performance.openness_at(time)
        sung, mouth_hint = face_visemes.mouth_at(keys, time, mouth_hint)

        # One face, blended: the sung mouth towards the resting one as the
        # singing dies away, and the eyes closing over the top of whatever
        # that lands on. Nothing here swaps between shapes.
        singing_face = face_shapes.Face(resting.eye, sung)
        pose = singing_face.blended(resting, rest_blend)
        pose = face_shapes.Face(pose.eye.with_openness(
            pose.eye.openness * openness), pose.mouth)

        # A grid quantises anyway, so matrix poses are compared coarsely —
        # finer buckets would emit new events that light identical cells.
        buckets = 10 if matrix else 24
        key = (tuple(round(v * buckets) for v in pose.eye.values()),
               tuple(round(v * buckets) for v in pose.mouth.values()))
        if state is None or key != state[0] or \
                time - pose_start >= segment:
            flush(time, state[2] if state else singing)
            shapes = face_shapes_for(pose, muzzle_at(time, singing))
            if matrix:
                shapes = face_matrix.matrix_shapes(
                    shapes, columns=columns, bounds=grid_bounds)
            state = (key, _draw(shapes, unit_scale), singing)
            pose_start = time
    flush(max(duration, step), state[2] if state else False)

    document = ASS_HEADER.format(width=width, height=height,
                                 colour=colour_code) + "".join(events)
    return document, len(events), performance


def write_face_ass(path, words, duration, **options):
    """Write the face track. Returns ``(event_count, performance)``."""
    document, poses, performance = build_face_ass(words, duration, **options)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(document)
    return poses, performance
