"""Render the face as a lit-cell grid instead of smooth outlines.

Most protogen visors are LED panels, and a panel does not draw curves — it
lights cells. Sampling the same outlines onto a grid gives that look without a
second set of artwork: one face definition, two ways of showing it.

Filling is done by scanline rather than by testing every cell. A face is a few
hundred edges and a grid is a few hundred cells; crossing each row once costs
the edges, testing every cell costs the product, and at twenty-four poses a
second the product is what makes a render take an hour.
"""

from __future__ import annotations


#: Cells across the face. Real visors run coarse — flexOS is 32 wide, the
#: bigger builds 64 — and coarse is what reads as a panel rather than as a
#: screenshot of one.
DEFAULT_COLUMNS = 36
#: How much of each cell the lit dot fills. Below 1.0 the grid stays visible,
#: which is the whole point.
DOT_FILL = 0.72


def _crossings(shape, y):
    """Where a horizontal line at ``y`` crosses this outline."""
    found = []
    count = len(shape)
    for index in range(count):
        x1, y1 = shape[index]
        x2, y2 = shape[(index + 1) % count]
        if (y1 <= y < y2) or (y2 <= y < y1):
            span = y2 - y1
            if span:
                found.append(x1 + (y - y1) * (x2 - x1) / span)
    found.sort()
    return found


def lit_cells(shapes, columns=DEFAULT_COLUMNS, bounds=None):
    """``{(column, row), ...}`` for the cells the face lights up.

    Even-odd across the sorted crossings, so a shape with a hole in it leaves
    the hole unlit without needing to be told about it.
    """
    if not shapes:
        return set(), (0.0, 0.0, 1.0, 1.0)
    if bounds is None:
        xs = [x for shape in shapes for x, _ in shape]
        ys = [y for shape in shapes for _, y in shape]
        bounds = (min(xs), min(ys), max(xs), max(ys))
    left, top, right, bottom = bounds
    width = (right - left) or 1.0
    height = (bottom - top) or 1.0
    cell = width / max(1, columns)
    rows = max(1, int(round(height / cell)))

    lit = set()
    for row in range(rows):
        y = top + (row + 0.5) * height / rows
        for shape in shapes:
            crossings = _crossings(shape, y)
            for start, end in zip(crossings[0::2], crossings[1::2]):
                first = int((start - left) / cell)
                last = int((end - left) / cell)
                for column in range(max(0, first), min(columns, last + 1)):
                    centre = left + (column + 0.5) * cell
                    if start <= centre <= end:
                        lit.add((column, row))
    return lit, bounds


def matrix_shapes(shapes, columns=DEFAULT_COLUMNS, fill=DOT_FILL,
                  bounds=None):
    """The face as one square per lit cell, in the same units as the input."""
    lit, bounds = lit_cells(shapes, columns=columns, bounds=bounds)
    if not lit:
        return []
    left, top, right, bottom = bounds
    width = (right - left) or 1.0
    height = (bottom - top) or 1.0
    cell = width / max(1, columns)
    rows = max(1, int(round(height / cell)))
    half = cell * fill / 2.0

    dots = []
    for column, row in sorted(lit):
        x = left + (column + 0.5) * cell
        y = top + (row + 0.5) * height / rows
        dots.append([(x - half, y - half), (x + half, y - half),
                     (x + half, y + half), (x - half, y + half)])
    return dots
