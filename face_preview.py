"""Frames of a looping idle for the face editor.

The preview is generated here rather than redrawn in the browser so that what
the editor shows is what the renderer will produce. A second implementation of
the geometry in JavaScript would drift from this one the first time either was
touched, and an editor that lies about the result is worse than no editor.

One loop carries everything worth judging: the head moving, a blink, and the
mouth opening and closing through a few articulations.
"""

from __future__ import annotations

import face_expression
import face_matrix
import face_render
import face_shapes


LOOP_SECONDS = 3.2
FPS = 20
#: What the mouth does over one loop. Enough shapes to see it travel rather
#: than to see it sit at two extremes.
MOUTH_CYCLE = ("rest", "eh", "ah", "oh", "oo", "ee", "rest")
#: Where the blink falls in the loop.
BLINK_AT = 0.62


def _mouth_at(face, fraction):
    """The mouth part way around the cycle, blended between articulations."""
    span = 1.0 / (len(MOUTH_CYCLE) - 1)
    index = min(int(fraction / span), len(MOUTH_CYCLE) - 2)
    local = (fraction - index * span) / span
    first = face_shapes.VISEMES[MOUTH_CYCLE[index]]
    second = face_shapes.VISEMES[MOUTH_CYCLE[index + 1]]
    sung = first.blended(second, local * local * (3.0 - 2.0 * local))
    # Keep the preset's own corner shape while the aperture does the moving,
    # so the editor shows the mouth it will actually draw.
    return face_shapes.Mouth(sung.width, sung.aperture, face.mouth.curve,
                             face.mouth.skew, face.mouth.jag,
                             face.mouth.weight)


def _loop_centre(face, head, seconds, count, style, columns):
    """The vertical middle of everything the loop draws, in face units."""
    low = high = None
    for step in range(count):
        mouth = _mouth_at(face, step / max(1, count - 1))
        pose = face_shapes.Face(face.eye, mouth, face.sharpness)
        shapes = face_render.face_shapes_for(pose)
        if style == face_render.MATRIX:
            shapes = face_matrix.matrix_shapes(shapes, columns=columns)
        for shape in shapes:
            for _, y in shape:
                low = y if low is None else min(low, y)
                high = y if high is None else max(high, y)
    return 0.0 if low is None else (low + high) / 2.0


def frames(dials, style=face_render.SOLID, columns=face_matrix.DEFAULT_COLUMNS,
           tempo=100.0, seconds=LOOP_SECONDS, fps=FPS, motion=1.0,
           beat_confidence=2.5):
    """``[[shape, ...], ...]`` in face units, one entry per frame."""
    import face_presets

    face = face_presets.to_face(dials)
    head = face_expression.HeadMotion(tempo=tempo, beat_phase=0.0,
                                      amount=motion,
                                      beat_confidence=beat_confidence)
    blink = seconds * BLINK_AT
    produced = []
    count = max(1, int(seconds * fps))
    # The coordinate origin is not the middle of the face: the eyes reach
    # further up than the mouth reaches down. Centre on what is actually
    # drawn, measured once across the whole loop rather than per frame — per
    # frame the face would drift every time the mouth opened.
    centre_y = _loop_centre(face, head, seconds, count, style, columns)
    for step in range(count):
        time = step * seconds / count
        # A blink, eased the way the real one is.
        gap = abs(time - blink)
        half = face_expression.BLINK_SECONDS / 2.0
        openness = min(1.0, gap / half) if gap < half else 1.0

        mouth = _mouth_at(face, step / max(1, count - 1))
        pose = face_shapes.Face(face.eye.with_openness(
            face.eye.openness * openness), mouth, face.sharpness)

        dx, dy, tilt = head.at(time, singing=True)
        extra = face_render.MOUTH_PARALLAX - 1.0
        shapes = face_render.face_shapes_for(
            pose, muzzle=(dx * face_render.UNIT * extra,
                          dy * face_render.UNIT * extra * 0.5))
        if style == face_render.MATRIX:
            shapes = face_matrix.matrix_shapes(shapes, columns=columns)
        produced.append({
            # Whole face units: the space is a thousand wide, so this is a
            # tenth of a percent and it halves the payload.
            "shapes": [[[round(x), round(y - centre_y)] for x, y in shape]
                       for shape in shapes],
            "offset": [round(dx * face_render.UNIT, 1),
                       round(dy * face_render.UNIT, 1)],
            "tilt": round(tilt, 2),
        })
    return {"frames": produced, "fps": fps, "unit": face_render.UNIT}
