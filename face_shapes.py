"""The face as a set of continuous parameters rather than a list of shapes.

Every eye and every mouth this tool can draw is one shape with its dials in a
different position. That is the whole point: a face built from a menu of fixed
outlines has to *swap* between them, and swapping is what makes a face look
like separate pieces stuck to a background. Parameters interpolate, so an
expression can be half way to another one, a viseme can be a third of the way
open, and the eyes and mouth travel on the same mechanism.

ProtoTracer reaches the same conclusion from the other direction: it holds a
mesh and a set of morph targets — anger, doubt, surprise, the visemes, blink —
each with an independent weight, and the face at any instant is the base plus
every weighted target. Nothing there picks an expression either.
"""

from __future__ import annotations


class Eye:
    """One eye's dials.

    ``hook`` is the shape that makes a visor eye read as a visor eye: the
    outer end curling down into a point rather than stopping. ``roundness``
    takes the same shape all the way to a filled oval, so ``o_o`` and a sharp
    wedge are the same object at different settings.
    """

    __slots__ = ("openness", "bow", "slant", "hook", "roundness", "weight")

    def __init__(self, openness=1.0, bow=0.55, slant=0.30, hook=0.70,
                 roundness=0.10, weight=1.0):
        self.openness = openness
        self.bow = bow
        self.slant = slant
        self.hook = hook
        self.roundness = roundness
        self.weight = weight

    def values(self):
        return (self.openness, self.bow, self.slant, self.hook,
                self.roundness, self.weight)

    @classmethod
    def of(cls, values):
        return cls(*values)

    def blended(self, other, amount):
        return Eye(*[a + (b - a) * amount
                     for a, b in zip(self.values(), other.values())])

    def with_openness(self, openness):
        eye = Eye(*self.values())
        eye.openness = openness
        return eye


class Mouth:
    """One mouth's dials.

    ``width`` and ``aperture`` are the visemes; ``curve`` is the smile;
    ``skew`` lifts one corner more than the other, which is what makes a
    smirk a smirk; ``jag`` bends the line into the zigzag grin that visor
    faces wear at rest.
    """

    __slots__ = ("width", "aperture", "curve", "skew", "jag", "weight")

    def __init__(self, width=0.86, aperture=0.0, curve=0.70, skew=0.0,
                 jag=0.0, weight=1.0):
        self.width = width
        self.aperture = aperture
        self.curve = curve
        self.skew = skew
        self.jag = jag
        self.weight = weight

    def values(self):
        return (self.width, self.aperture, self.curve, self.skew, self.jag,
                self.weight)

    @classmethod
    def of(cls, values):
        return cls(*values)

    def blended(self, other, amount):
        return Mouth(*[a + (b - a) * amount
                       for a, b in zip(self.values(), other.values())])


class Face:
    """An eye setting, a mouth setting and how hard the drawing is.

    ``sharpness`` straightens every curve towards its control polygon: at 1.0
    the arcs become straight runs meeting at hard corners. It belongs to the
    face rather than to either feature because it is a quality of the whole
    expression — anger is directness, and directness draws as straight edges
    and sharp angles, not as tighter curves.
    """

    __slots__ = ("eye", "mouth", "sharpness")

    def __init__(self, eye, mouth, sharpness=0.0):
        self.eye = eye
        self.mouth = mouth
        self.sharpness = sharpness

    def blended(self, other, amount):
        return Face(self.eye.blended(other.eye, amount),
                    self.mouth.blended(other.mouth, amount),
                    self.sharpness
                    + (other.sharpness - self.sharpness) * amount)


#: Mouth settings for each visible articulation. Same dials as every other
#: mouth in the tool, so a viseme can blend into a resting expression.
VISEMES = {
    "rest": Mouth(0.86, 0.00, 0.70, 0.0, 0.0),
    "mm":   Mouth(0.80, 0.00, 0.40, 0.0, 0.0),
    "ff":   Mouth(0.84, 0.14, 0.32, 0.0, 0.0),
    "ee":   Mouth(1.00, 0.30, 0.58, 0.0, 0.0),
    "eh":   Mouth(0.92, 0.52, 0.44, 0.0, 0.0),
    "ah":   Mouth(0.86, 1.00, 0.25, 0.0, 0.0),
    "oh":   Mouth(0.60, 0.86, 0.22, 0.0, 0.0),
    "oo":   Mouth(0.40, 0.52, 0.18, 0.0, 0.0),
    "th":   Mouth(0.88, 0.26, 0.40, 0.0, 0.0),
    "ll":   Mouth(0.78, 0.58, 0.36, 0.0, 0.0),
}
REST = "rest"
