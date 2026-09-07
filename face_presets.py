"""Saved faces: the built-in expressions plus whatever the user has dialled in.

The built-ins are a starting point, not a fixed menu. Anyone using this knows
better than the defaults what their own character's face should look like, so
the dials are editable and what comes out can be saved, named and rendered
with.

User presets live under the config directory rather than the cache: a cache is
something you can delete to reclaim disk, and these are not.
"""

from __future__ import annotations

import json
import os

import face_expression
import face_shapes
import platform_support


FILENAME = "face-presets.json"

#: Every dial the editor exposes, with the range it is allowed to take. The
#: limits are here rather than in the UI because this is what validates what
#: arrives over HTTP.
EYE_DIALS = {
    "openness": (0.0, 1.0),
    "bow": (-0.4, 1.4),
    "slant": (-1.2, 1.2),
    "hook": (0.0, 1.4),
    "roundness": (0.0, 1.0),
    "weight": (0.3, 1.8),
}
MOUTH_DIALS = {
    "width": (0.10, 1.30),
    "aperture": (0.0, 1.2),
    "curve": (-0.6, 1.2),
    "skew": (-1.0, 1.0),
    "jag": (0.0, 1.2),
    "weight": (0.3, 1.8),
}
FACE_DIALS = {
    "sharpness": (0.0, 1.0),
    "motion": (0.0, 2.0),
}


def presets_path():
    return os.path.join(platform_support.config_dir(), FILENAME)


def _clamp(value, limits, fallback):
    low, high = limits
    try:
        return max(low, min(float(value), high))
    except (TypeError, ValueError):
        return fallback


def clean(dials):
    """Validate a dial set arriving from the browser.

    Anything missing falls back to the default face rather than failing, and
    anything out of range is clamped — a preset that cannot be drawn is worse
    than one that has been quietly brought back into bounds.
    """
    default = face_expression.resting_face(
        face_expression.DEFAULT_EXPRESSION)
    eye_in = dict(dials.get("eye") or {})
    mouth_in = dict(dials.get("mouth") or {})
    eye = {name: _clamp(eye_in.get(name), limits, getattr(default.eye, name))
           for name, limits in EYE_DIALS.items()}
    mouth = {name: _clamp(mouth_in.get(name), limits,
                          getattr(default.mouth, name))
             for name, limits in MOUTH_DIALS.items()}
    return {
        "eye": eye,
        "mouth": mouth,
        "sharpness": _clamp(dials.get("sharpness"), FACE_DIALS["sharpness"],
                            default.sharpness),
        "motion": _clamp(dials.get("motion"), FACE_DIALS["motion"], 1.0),
    }


def to_face(dials):
    """A :class:`face_shapes.Face` from a cleaned dial set."""
    clean_dials = clean(dials)
    return face_shapes.Face(face_shapes.Eye(**clean_dials["eye"]),
                            face_shapes.Mouth(**clean_dials["mouth"]),
                            clean_dials["sharpness"])


def from_expression(name):
    """The dial set behind a built-in expression, ready for the editor."""
    face = face_expression.resting_face(name)
    return {
        "eye": {dial: getattr(face.eye, dial) for dial in EYE_DIALS},
        "mouth": {dial: getattr(face.mouth, dial) for dial in MOUTH_DIALS},
        "sharpness": face.sharpness,
        "motion": face_expression.resting_motion(name),
    }


def load():
    """Every saved preset, or an empty dict if none have been saved."""
    try:
        with open(presets_path(), "r", encoding="utf-8") as handle:
            stored = json.load(handle)
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(stored, dict):
        return {}
    return {str(name): clean(dials) for name, dials in stored.items()
            if isinstance(dials, dict)}


def save(name, dials):
    """Store one preset under ``name``. Returns every saved preset."""
    name = str(name).strip()[:48]
    if not name:
        raise ValueError("A preset needs a name")
    if name in face_expression.EXPRESSIONS:
        raise ValueError(f"{name!r} is a built-in expression; "
                         f"choose another name")
    stored = load()
    stored[name] = clean(dials)
    _write(stored)
    return stored


def delete(name):
    """Remove one saved preset. Returns every saved preset that remains."""
    stored = load()
    stored.pop(str(name), None)
    _write(stored)
    return stored


def _write(stored):
    path = presets_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Written beside the target and moved into place, so an interrupted save
    # cannot leave a half-written file where the presets used to be.
    temporary = path + ".partial"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(stored, handle, indent=1, sort_keys=True)
    os.replace(temporary, path)


def catalogue():
    """Built-in expressions and saved presets, for the UI's picker."""
    entries = [{"name": name, "label": spec["label"], "face": spec["face"],
                "builtin": True, "dials": from_expression(name)}
               for name, spec in face_expression.EXPRESSIONS.items()]
    entries += [{"name": name, "label": name, "face": "★",
                 "builtin": False, "dials": dials}
                for name, dials in sorted(load().items())]
    return entries
