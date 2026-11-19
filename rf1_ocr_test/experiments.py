"""Experimental functions in shadow mode (off by default).

With "Experimentelle Funktionen testen" switched on, each automatic check additionally reads the
same image with every ticked experiment, but only when the host has spare capacity. Only the
stable result counts; the debug log keeps both (field ``experiment``) so a later review can tell
whether an experiment is better and never wrong. An experiment becomes standard only after that.
"""

import os
import time

from PIL import Image

from layout import bright_glyphs, digit_components, glare_slots

EXPERIMENTS = {
    "perspective": "Perspektivkorrektur (Kippung)",
}
# A trapezoid below this difference in glyph height is treated as level.
MIN_KEYSTONE = 0.03
MAX_KEYSTONE = 0.35


def enabled_experiments(rules):
    if not rules.get("experiments_enabled"):
        return []
    chosen = rules.get("experiments") or {}
    return [name for name in EXPERIMENTS if chosen.get(name)]


def host_load():
    try:
        return round(os.getloadavg()[0] / (os.cpu_count() or 1), 2)
    except (AttributeError, OSError):
        return None


def glyph_heights(register, boxes):
    """Return (x centre, top, bottom) of the tallest bright glyph in each frame."""
    gray = register.convert("L")
    strokes = bright_glyphs(gray, max(3, round(gray.height * .25)))
    parts = []
    for threshold in (80, 110):
        parts += digit_components(strokes, threshold, True)
    found = []
    for left, top, right, bottom in boxes:
        inside = [part for part in parts
                  if left <= (part[0] + part[2]) / 2 <= right and top <= (part[1] + part[3]) / 2 <= bottom
                  and part[3] - part[1] >= (bottom - top) * .3]
        if inside:
            part = max(inside, key=lambda box: box[3] - box[1])
            found.append(((left + right) / 2, part[1], part[3]))
    return found


def measure_keystone(register, boxes):
    """Measure how much smaller the glyphs on one side are (perspective tilt of the camera).

    Returns a dict with glyph height left/right, edge angles and the height ratio right/left,
    or None when too few glyphs are visible.
    """
    glyphs = glyph_heights(register, boxes)
    if len(glyphs) < 4:
        return None
    count = len(glyphs)
    xs = [x for x, _, _ in glyphs]
    mean_x = sum(xs) / count
    spread = sum((x - mean_x) ** 2 for x in xs)
    if spread <= 0:
        return None

    def slope(values):
        mean = sum(values) / count
        return sum((x - mean_x) * (v - mean) for x, v in zip(xs, values)) / spread, mean

    top_slope, top_mean = slope([top for _, top, _ in glyphs])
    bottom_slope, bottom_mean = slope([bottom for _, _, bottom in glyphs])
    first, last = min(xs), max(xs)
    left_height = (bottom_mean + bottom_slope * (first - mean_x)) - (top_mean + top_slope * (first - mean_x))
    right_height = (bottom_mean + bottom_slope * (last - mean_x)) - (top_mean + top_slope * (last - mean_x))
    if left_height <= 0 or right_height <= 0:
        return None
    from math import atan, degrees
    return {"left_height": round(left_height, 1), "right_height": round(right_height, 1),
            "top_angle": round(degrees(atan(top_slope)), 2), "bottom_angle": round(degrees(atan(bottom_slope)), 2),
            "ratio": round(right_height / left_height, 3)}


def correct_keystone(register, ratio):
    """Stretch the smaller side so all glyphs get the same height (horizontal trapezoid)."""
    if ratio is None or abs(1 - ratio) < MIN_KEYSTONE or abs(1 - ratio) > MAX_KEYSTONE:
        return register
    width, height = register.size
    centre = height / 2
    if ratio < 1:   # right side smaller: take a shorter strip on the right
        left_half, right_half = centre, centre * ratio
    else:           # left side smaller
        left_half, right_half = centre / ratio, centre
    quad = (0, centre - left_half, 0, centre + left_half,
            width, centre + right_half, width, centre - right_half)
    return register.transform(register.size, Image.Transform.QUAD, quad, resample=Image.Resampling.BICUBIC)


def shadow_perspective(register, boxes, read_box):
    """Read the register again after the keystone correction; returns the debug record part."""
    started = time.monotonic()
    # The last roller turns continuously; its half digits would distort the height.
    glared = set(glare_slots(register, boxes))
    measured = measure_keystone(register, [box for index, box in enumerate(boxes[:-1]) if index not in glared])
    if measured is None:
        return {"measured": None, "reading": None, "seconds": round(time.monotonic() - started, 2)}
    corrected = correct_keystone(register, measured["ratio"])
    reading = "".join(read_box(corrected, box) for box in boxes)
    return {"measured": measured, "reading": reading, "seconds": round(time.monotonic() - started, 2)}
