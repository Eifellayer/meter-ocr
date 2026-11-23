"""Bounded search for a reproducible meter crop and rotation."""

from dataclasses import dataclass, field, replace
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from math import ceil, cos, floor, radians, sin
import subprocess
import os
from itertools import product
from pathlib import Path
from statistics import median

from PIL import Image, ImageChops, ImageFilter, ImageStat

from checks import OCR_PROFILES, compare_sample, crop_register, meter_prefix, read_with_retries
from consumption import accumulate_consumption
from layout import (crop_coordinates, digit_box_settings, find_digit_row, find_neighbour_digit_rows,
                    dark_register_cells, find_dark_register, find_dark_strip, find_glyph_register, find_raw_digit_rows, normalize_digit_boxes,
                    rotated_width, same_digit_region, scale_digit_boxes, turn_crop, glare_slots, digit_presence,
                    empty_digit_slots)

from meter_learning import propose_digit_boxes

DEFAULT_LIMIT = 100
MIN_IMAGES = 3
MIN_IMAGE_LIMIT = MIN_IMAGES + 1
MAX_IMAGES = 100
MAX_ATTEMPTS = 260
TIME_LIMIT = 20 * 60
IMAGE_WAIT_LIMIT = 360
INTENSIVE_VERIFICATION_SECONDS = 4 * 60
CAPTURE_INTERVAL = 5
PERFECT_CONFIRMATION_INTERVAL = 12
LAST_DIGIT_CAPTURE_INTERVAL = 2
# Fine grid up to ±20° (no jump from 12° to 18°). Right angles are no longer part of the
# regular rotation: quarter turns are only tried when nothing with the right digit count
# was found (quarter_turn_layouts).
ANGLES = (-3, 3, -1, 1, -2, 2, -4, 4, -6, 6, -9, 9, -12, 12, -14, 14, -16, 16, -18, 18, -20, 20)
SEARCH_ANGLE_LIMIT = 20
SMALL_ANGLES = (0, -1, 1, -2, 2, -3, 3)
MAX_LAYOUTS_PER_IMAGE = 5
COARSE_LIMIT = 50
SHORTLIST_LIMIT = 5
DEFAULT_INTENSIVE_AGREEMENT = 80
# 0.5.11, two percentages: the 80 % were a rough guess. When a glyph sits
# in (nearly) every digit field, the frame itself is right; a lower reading agreement is then
# enough to keep working with it. The reading is still confirmed image by image.
COARSE_AGREEMENT = 60
DIGIT_FOUND_COARSE = 85
MIN_VERIFICATION_QUALITY = .65
FRAME_ATTEMPT_LIMIT = 30
MAX_GROUPS = 12
MAX_REJECTED = 8
SMALL_LABEL_AREA = .35
PREFILTER_TURN = 6
# A first profile with fewer sure digits makes a candidate hopeless: skip the second read.
HOPELESS_DIGITS = 3
# 0.5.29: a setup frame checked against the last counted reading uses a realistic flow, not
# the meter's maximum. Live 22.11.2026: an hour after the last reading the maximum of 6 m³/h
# let an upside-down frame read 5.7 m³ too much and collect two confirmations.
SETUP_FLOW_SHARE = .5
# Two frames on the same digits whose turns differ by 180° ± this many degrees (0.5.29).
HALF_TURN_TOLERANCE = 30
# Sideways frames read turned by 180° on a picture where nothing read reliably (0.5.31).
SIDEWAYS_TWINS = 2
# 0.5.35: a direction counts as clearly better readable with this lead in fitting digits, read
# without the known reading's help (``orientation_agreement``).
ORIENTATION_MARGIN = 2
# A reading this far (plus its own step) below the newest reading seen lies behind it.
BEHIND_SLACK_LITRES = 100
SETUP_FLOW_FLOOR_LPH = 1500



def agreeing_prefixes(readings, precision, digits):
    """Precision at which two OCR readings agree: the requested one, or one decimal less (min. 1).

    Returns None if they do not agree. Used for setup hits only: the whole digits and at least
    one decimal must be sure and identical in both readings.
    """
    if len(readings) < 2:
        return None
    for decimals in (precision, precision - 1) if precision >= 2 else (precision,):
        first, second = (meter_prefix(value, decimals, digits) for value in readings[:2])
        if first is not None and first == second:
            return decimals
    return None


def last_digit_candidates(layout, roll_center=None):
    """Frames for the last roller: settle its horizontal centre first, then move only vertically.

    Wide horizontal jumps put half of a neighbouring digit into the frame and produce partial
    readings. The roller does not move sideways, so once its centre is known (``roll_center``,
    in the layout's 0–1000 crop coordinates) the search only shifts the frame up and down.
    Without a trusted centre a few small horizontal steps are tried, including the position
    predicted from the last roller's slightly larger spacing.
    """
    left, top, right, bottom = layout.digit_boxes[-1]
    width, height = right - left, bottom - top
    centre = (left + right) / 2
    columns = []
    step = max(1, width // 10)
    if roll_center is not None and abs(roll_center - centre) <= width:
        # Quantised, so the same roller gives the same frame on consecutive images.
        columns.append(round((roll_center - centre) / step) * step)
    else:
        columns.append(0)
        if len(layout.digit_boxes) >= 3:
            before, neighbour = layout.digit_boxes[-3:-1]
            pitch = (neighbour[0] + neighbour[2] - before[0] - before[2]) / 2
            # The last roller usually sits slightly farther away than the even spacing suggests.
            for factor in (1.0, 1.1, 1.2):
                shift = round((neighbour[0] + neighbour[2]) / 2 + factor * pitch - centre)
                if abs(shift) <= width // 2:
                    columns.append(shift)
        columns += [step, -step]
    rows = [0] + [sign * max(1, round(height * part)) for part in (1 / 8, 1 / 4, 3 / 8) for sign in (1, -1)]
    candidates, seen = [], set()
    if roll_center is None:
        candidates.append(layout)
        seen.add(layout.digit_boxes[-1])
    for x in dict.fromkeys(columns):
        for y in rows:
            dx = max(-left, min(x, 1000 - right))
            dy = max(-top, min(y, 1000 - bottom))
            box = (left + dx, top + dy, right + dx, bottom + dy)
            if box in seen:
                continue
            seen.add(box)
            boxes = (*layout.digit_boxes[:-1], box)
            try:
                digit_box_settings(boxes, len(boxes))
            except ValueError:
                continue
            candidates.append(layout if box == layout.digit_boxes[-1] else replace(layout, digit_boxes=boxes, method="refined"))
    if layout.digit_boxes[-1] not in seen:
        candidates.append(layout)
    return candidates

@dataclass(frozen=True)
class Layout:
    box: tuple[int, int, int, int]
    rotation: int
    width: int
    digit_boxes: tuple = ()
    method: str = field(default="", compare=False)

    def settings(self):
        return {"crop_mode": "manual", "crop": ",".join(map(str, self.box)),
                "rotation": self.rotation, "width": self.width, "digit_boxes": list(self.digit_boxes)}


DETECTED_METHODS = ("neighbours", "register_window")


def similar_layout(layout, other):
    """Same digits found again, give or take a few pixels or one degree.

    Each setup image is searched afresh, so the frames of the same digit row differ slightly
    from image to image. Counting those as different geometries kept resetting the
    confirmations (1/3, 2/3, 1/3 …) although the app had found the right digits every time.
    """
    if layout is None or other is None:
        return False
    if layout == other:
        return True
    # Only fresh detections jitter. Deliberately refined frames (fine search, verified boxes)
    # must count as new, so their hits are not credited to a different box.
    if layout.method not in DETECTED_METHODS or other.method not in DETECTED_METHODS:
        return False
    if abs(layout.rotation - other.rotation) > 1 or len(layout.digit_boxes) != len(other.digit_boxes):
        return False
    width = max(1, layout.box[2] - layout.box[0])
    height = max(1, layout.box[3] - layout.box[1])
    if any(abs(a - b) > max(4, width * .04) for a, b in zip(layout.box[0::2], other.box[0::2])):
        return False
    if any(abs(a - b) > max(4, height * .15) for a, b in zip(layout.box[1::2], other.box[1::2])):
        return False
    if abs(layout.width - other.width) > max(4, width * .04):
        return False
    for first, second in zip(layout.digit_boxes, other.digit_boxes):
        # Digit boxes are stored in 0–1000 crop coordinates.
        if any(abs(a - b) > 30 for a, b in zip(first[0::2], second[0::2])):
            return False
        if any(abs(a - b) > 120 for a, b in zip(first[1::2], second[1::2])):
            return False
    return True


def same_register(layout, other, overlap=.8, max_turn=2):
    """The same meter register, even if one frame was fine-tuned (refined boxes, ±1–2°).

    Used only to count setup confirmations. ``similar_layout`` treats every refined frame as
    new, which reset the confirmations 1 → 2 → 1 on every image although each image read the
    right register (16 images, 0 confirmations). A shifted frame is still
    caught afterwards, because the readings must form a plausible counter series.
    """
    if layout is None or other is None:
        return False
    if layout == other or similar_layout(layout, other):
        return True
    if abs(layout.rotation - other.rotation) > max_turn or len(layout.digit_boxes) != len(other.digit_boxes):
        return False
    left, top = max(layout.box[0], other.box[0]), max(layout.box[1], other.box[1])
    right, bottom = min(layout.box[2], other.box[2]), min(layout.box[3], other.box[3])
    if right <= left or bottom <= top:
        return False
    area = lambda box: max(1, (box[2] - box[0]) * (box[3] - box[1]))
    shared = (right - left) * (bottom - top)
    return shared / (area(layout.box) + area(other.box) - shared) >= overlap


SKEW_CONFIDENCE = 1.25


def estimate_skew(frame, limit=SEARCH_ANGLE_LIMIT):
    """Measured tilt of the dominant horizontal structure (register window, digit row), or None.

    Cheap deskew without OCR (about 0.2 s): turn an edge image of a small copy in 1° steps and
    keep the angle whose row profile is the sharpest. The result is the angle ``turn_crop``
    needs to level the picture. The setup tries it (and ±1°, ±2°) first instead of waiting until
    the coarse angle grid reaches e.g. −14° after many images.
    """
    try:
        gray = frame.convert("L")
        scale = 360 / max(gray.size)
        small = gray.resize((max(16, round(gray.width * scale)), max(16, round(gray.height * scale))),
                            Image.Resampling.BILINEAR)
        down = small.filter(ImageFilter.Kernel((3, 3), (-1, -2, -1, 0, 0, 0, 1, 2, 1), 1))
        up = small.filter(ImageFilter.Kernel((3, 3), (1, 2, 1, 0, 0, 0, -1, -2, -1), 1))
        edges = ImageChops.add(down, up)
    except (OSError, ValueError, ZeroDivisionError):
        return None
    width, height = edges.size
    box = (width // 5, height // 5, width - width // 5, height - height // 5)
    scores = {}
    for angle in range(-limit, limit + 1):
        turned = turn_crop(edges, angle, expand=False).convert("L").crop(box)
        rows = list(turned.resize((1, turned.height), Image.Resampling.BOX).tobytes())
        mean = sum(rows) / len(rows)
        scores[angle] = sum((value - mean) ** 2 for value in rows) / len(rows)
    best = max(scores, key=lambda angle: (scores[angle], -abs(angle)))
    typical = median(scores.values())
    if not scores[best] or scores[best] < SKEW_CONFIDENCE * typical:
        return None
    return best


def skew_angles(skew, limit=SEARCH_ANGLE_LIMIT):
    """The measured tilt and its neighbours in 1° steps, most likely first."""
    if skew is None:
        return ()
    return tuple(skew + step for step in (0, -1, 1, -2, 2) if abs(skew + step) <= limit)


def unrotate_box(box, size, angle):
    """Convert a box in a center-rotated image to bounds in the original."""
    if angle == 0:
        return box
    w, h = size
    left, top, right, bottom = box
    c, s = cos(radians(angle)), sin(radians(angle))
    points = [(c * (x - w / 2) + s * (y - h / 2) + w / 2,
               -s * (x - w / 2) + c * (y - h / 2) + h / 2)
              for x in (left, right) for y in (top, bottom)]
    xs, ys = zip(*points)
    return max(0, floor(min(xs))), max(0, floor(min(ys))), min(w, ceil(max(xs))), min(h, ceil(max(ys)))


def neighbour_layout(frame, angle, detected, whole_digits, fraction_digits):
    """Translate a grid from the rotated camera view into the saved rotated crop."""
    bounds, _, boxes = detected
    outer = unrotate_box(bounds, frame.size, angle)
    left, top, right, bottom = outer
    if not (right - left >= 8 and bottom - top >= 8):
        return None
    register = turn_crop(crop_register(frame, outer), angle)
    w, h = register.size
    x = (left + right - frame.width) / 2
    y = (top + bottom - frame.height) / 2
    c, s = cos(radians(angle)), sin(radians(angle))
    dx = round(bounds[0] - (frame.width / 2 + c * x - s * y - w / 2))
    dy = round(bounds[1] - (frame.height / 2 + s * x + c * y - h / 2))
    shifted = [(max(0, l + dx), max(0, t + dy), min(w, r + dx), min(h, b + dy)) for l, t, r, b in boxes]
    try:
        normalized = digit_box_settings(normalize_digit_boxes(shifted, register.size), whole_digits + fraction_digits)
    except ValueError:
        return None
    whole_width = round((shifted[whole_digits - 1][2] + shifted[whole_digits][0]) / 2) if fraction_digits else w
    if not 0 < whole_width <= w:
        return None
    return Layout(outer, angle, whole_width, tuple(map(tuple, normalized)), method="neighbours")


def glyph_register_layout(frame, whole_digits, fraction_digits):
    """Propose the meter window from a row of bright digits, levelled by the measured tilt."""
    count = whole_digits + fraction_digits
    found = find_glyph_register(frame, count, with_tilt=True)
    if found is None:
        return None
    angle = max(-SEARCH_ANGLE_LIMIT, min(SEARCH_ANGLE_LIMIT, round(-found[1])))
    if angle:
        found = find_glyph_register(turn_crop(frame, angle, expand=False), count, with_tilt=True)
        if found is None:
            return None
    window = found[0]
    l, t, r, b = window
    turned = turn_crop(frame, angle, expand=False) if angle else frame
    strip = turned.crop(window)
    fitted = dark_register_cells(strip, count)
    if fitted:
        cells = scale_digit_boxes(fitted, strip.size)
        split = (cells[whole_digits - 1][2] + cells[whole_digits][0]) // 2 if fraction_digits else r - l
    else:
        edges = [round((r - l) * i / count) for i in range(count + 1)]
        cells = [(a, 0, z, b - t) for a, z in zip(edges, edges[1:])]
        split = edges[whole_digits]
    proposal = neighbour_layout(frame, angle, (window, split, cells), whole_digits, fraction_digits)
    if proposal is None:
        return None
    return replace(proposal, method="register_window")


def layouts(frame, overlay, rules, offset, current=None, prefer_configured=False, on_regions=None, *, upright=False,
            skew=None):
    """Try a few geometry candidates per image, rotating the search across images."""
    emitted = set()

    def candidate(box, angle, padding=0):
        left, top, right, bottom = box
        box = (max(0, left - padding), max(0, top - padding),
               min(frame.width, right + padding), min(frame.height, bottom + padding))
        span = rotated_width(box[2] - box[0], box[3] - box[1], angle)
        width = max(1, round(span * rules["integer_digits"] /
                             (rules["integer_digits"] + rules["fraction_digits"])))
        return Layout(box, angle, width)

    def unique(layout):
        if layout in emitted or layout.box[2] - layout.box[0] < 8 or layout.box[3] - layout.box[1] < 8:
            return False
        emitted.add(layout)
        return True

    if (current is not None and current.box[2] <= frame.width and current.box[3] <= frame.height
            and unique(current)):
        yield current
    first = offset % len(ANGLES)
    configured = None
    if "crop" in rules:
        box = crop_coordinates(rules["crop"], rules["width"], rules["rotation"])
        if box[2] <= frame.width and box[3] <= frame.height:
            configured = Layout(box, rules["rotation"], rules["width"],
                                tuple(map(tuple, rules.get("digit_boxes", []))))
    if prefer_configured and configured and unique(configured):
        yield configured
    # Reserve space for neighbour inference and, where possible, the regular crop.
    neighbour_limit = MAX_LAYOUTS_PER_IMAGE - int(configured is not None and not prefer_configured)
    raw_limit = neighbour_limit - 1
    # 0.5.21: an upright search (a picture already turned by a right angle) still tries the
    # tilt measured in it, so a meter hanging a few degrees askew keeps its decimals in the frame.
    level_angles = tuple(dict.fromkeys((skew, 0))) if upright and skew else (0,)
    angles = level_angles if upright else (
        SMALL_ANGLES if offset == 0 else (0, ANGLES[first], ANGLES[(first + 1) % len(ANGLES)]))
    if not upright and skew is not None:
        # The measured tilt first: a −14° meter is found on the first image (0.4.0).
        measured = skew_angles(skew)
        angles = measured + tuple(angle for angle in angles if angle not in measured)
    if not upright and current is not None and abs(current.rotation) <= SEARCH_ANGLE_LIMIT:
        # Search around the angle that already read best, in 1° steps (e.g. −12° → −13°, −14°).
        center = round(current.rotation)
        nearby = [center + step for step in (0, -1, 1, -2, 2)
                  if abs(center + step) <= SEARCH_ANGLE_LIMIT and center + step not in angles]
        angles = tuple(angles) + tuple(nearby)
    if len(emitted) < raw_limit:
        ranked = []
        for angle in angles:
            adjusted = turn_crop(frame, angle, expand=False)
            for detected, score in find_raw_digit_rows(adjusted, rules["integer_digits"], rules["fraction_digits"]):
                box = unrotate_box(detected[0], frame.size, angle)
                ranked.append((score, angle, detected, box))
        level = skew or 0
        ranked.sort(key=lambda item: (-item[0], abs(item[1] - level), item[3][1], item[3][0]))
        whole, fraction = rules["integer_digits"], rules["fraction_digits"]
        glyph_window = glyph_register_layout(frame, whole, fraction)
        if glyph_window is not None and unique(glyph_window):
            yield glyph_window
        windows = []
        for angle in angles:
            if abs(angle) > SEARCH_ANGLE_LIMIT:
                continue
            window = find_dark_strip(turn_crop(frame, angle, expand=False), whole + fraction)
            if window and (not ranked or window[2] - window[0] > 1.25 * (ranked[0][3][2] - ranked[0][3][0])):
                l, t, r, b = window
                edges = [round((r - l) * i / (whole + fraction)) for i in range(whole + fraction + 1)]
                cells = [(a, 0, z, b - t) for a, z in zip(edges, edges[1:])]
                proposal = neighbour_layout(frame, angle, (window, edges[whole], cells), whole, fraction)
                if proposal is not None:
                    windows.append(((r - l) * (b - t), proposal))
        if windows:
            proposal = max(windows, key=lambda row: row[0])[1]
            proposal = replace(proposal, rotation=0, width=min(proposal.width, proposal.box[2] - proposal.box[0]),
                               digit_boxes=())
            register = crop_register(frame, proposal.box)
            boxes = dark_register_cells(register, whole + fraction)
            if boxes:
                scaled = scale_digit_boxes(boxes, register.size)
                split = (scaled[whole - 1][2] + scaled[whole][0]) // 2 if fraction else register.width
                proposal = replace(proposal, width=split, digit_boxes=boxes)
            if unique(proposal):
                yield replace(proposal, method="register_window")
        if ranked:
            _, _, (small, _, _), _ = ranked[0]
            sw, sh = small[2] - small[0], small[3] - small[1]
            # A small complete row can be a label alongside a larger display
            # whose moving or partly obscured digits did not pass the strict scan.
            for detected in find_neighbour_digit_rows(frame, whole, fraction, min_support=min(3, whole + fraction)):
                box = detected[0]
                if box[2] - box[0] < sw * 1.35 or box[3] - box[1] < sh * 1.45:
                    continue
                larger = neighbour_layout(frame, 0, detected, whole, fraction)
                if larger is not None and unique(larger):
                    yield larger
                    break
        regions = []
        for score, _, _, box in ranked:
            if not regions or score >= regions[0][0] * .75:
                if not any(same_digit_region(box, old) for _, old in regions):
                    regions.append((score, box))
        if on_regions is not None and len(regions) > 1:
            on_regions([box for _, box in regions[:4]])
        variants = []
        for _, angle, detected, box in ranked:
            if any(same_digit_region(box, item[0].box) for item in variants):
                continue
            left, top, right, bottom = box
            frames = normalize_digit_boxes(detected[2], (right - left, bottom - top)) if angle == 0 else ()
            alternate = candidate(box, angle, padding=2)
            turned = turn_crop(crop_register(frame, alternate.box), angle)
            optimized = propose_digit_boxes(turned, [], alternate.width, rules["integer_digits"], rules["fraction_digits"])
            variants.append((Layout(box, angle, detected[1], frames),
                             Layout(alternate.box, angle, alternate.width, tuple(map(tuple, optimized)))))
            if len(variants) >= raw_limit:
                break
        for group in zip(*variants):
            for layout in group:
                if len(emitted) >= raw_limit:
                    break
                if unique(layout):
                    yield layout
    whole, fraction = rules["integer_digits"], rules["fraction_digits"]
    for angle in level_angles if upright else tuple(dict.fromkeys((*skew_angles(skew)[:1], 0, ANGLES[first]))):
        if len(emitted) >= neighbour_limit:
            break
        adjusted = turn_crop(frame, angle, expand=False)
        for detected in find_neighbour_digit_rows(adjusted, whole, fraction):
            layout = neighbour_layout(frame, angle, detected, whole, fraction)
            if layout and unique(layout):
                yield layout
            if len(emitted) >= neighbour_limit:
                break
    if len(emitted) < neighbour_limit and overlay is not None and overlay.size == frame.size:
        found = find_digit_row(overlay, whole, fraction)
        if found:
            left, top, right, bottom = found[0]
            layout = Layout(found[0], 0, found[1],
                            normalize_digit_boxes(found[2], (right - left, bottom - top)))
            if unique(layout):
                yield layout
    if configured:
        for trial in (configured, candidate(configured.box, ANGLES[first], padding=2)):
            if len(emitted) >= MAX_LAYOUTS_PER_IMAGE:
                return
            if unique(trial):
                yield trial


def quarter_turn_layouts(frame, rules, region):
    area = tuple(round(value * size / 1000) for value, size in zip(region, frame.size * 2)) if region else (
        0, 0, frame.width, frame.height)
    image = frame.crop(area)
    width, height = image.size
    if min(width, height) < 8:
        return
    local_rules = {key: value for key, value in rules.items() if key != "crop"}
    for angle in (180, 90, -90):
        turned = turn_crop(image, angle)
        # 0.5.21: a meter turned by a right angle may also hang a few degrees askew. Its tilt is
        # measured in the turned picture and kept in the rotation; before, the turned picture was
        # only searched upright and a found tilt was dropped, so the frame cut off the decimals.
        skew = estimate_skew(turned)
        candidates = skip_small_labels(list(layouts(turned, None, local_rules, 0, upright=True, skew=skew)))
        for layout in candidates:
            left, top, right, bottom = layout.box
            if not (0 <= left < right <= turned.width and 0 <= top < bottom <= turned.height):
                continue
            if angle == 90:
                bounds = (top, height - right, bottom, height - left)
            elif angle == -90:
                bounds = (width - bottom, left, width - top, right)
            else:
                bounds = (width - right, height - bottom, width - left, height - top)
            box = tuple(value + origin for value, origin in zip(bounds, area[:2] * 2))
            yield replace(layout, box=box, rotation=quarter_rotation(angle, layout.rotation))


def quarter_rotation(quarter, tilt):
    """A right-angle turn plus the tilt found in the turned picture, kept within ±180° (0.5.21)."""
    if not tilt:
        return quarter
    total = quarter + tilt
    return total - 360 if total > 180 else total + 360 if total < -180 else total


def search_region(value):
    if not value:
        return None
    parts = tuple(map(int, value.split(",")))
    left, top, right, bottom = parts
    if not (0 <= left < right <= 1000 and 0 <= top < bottom <= 1000
            and right - left >= 20 and bottom - top >= 20):
        raise ValueError("Invalid calibration search region")
    return parts


def guided_layouts(frame, overlay, rules, offset, current, region):
    left, top, right, bottom = (round(value * size / 1000) for value, size in
                                zip(region, (frame.width, frame.height) * 2))
    if right - left < 8 or bottom - top < 8:
        return
    area = left, top, right, bottom
    local_rules = {key: value for key, value in rules.items() if key != "crop"}
    seed = None
    if current:
        a, b, c, d = current.box
        if left <= a < c <= right and top <= b < d <= bottom:
            seed = replace(current, box=(a - left, b - top, c - left, d - top))
    cropped_overlay = overlay.crop(area) if overlay is not None and overlay.size == frame.size else None
    for layout in layouts(frame.crop(area), cropped_overlay, local_rules, offset, seed):
        a, b, c, d = layout.box
        yield replace(layout, box=(a + left, b + top, c + left, d + top))


def two_decimal_reading(value):
    """Mask trailing digits so the comparison cannot round using an open slot."""
    whole, separator, fraction = str(value).replace(",", ".").partition(".")
    return f"{whole}.{fraction[:2]}?" if separator and len(fraction) >= 2 else value


def valid_intensive_agreement(value):
    return type(value) is int and 1 <= value <= 100


def crop_quality(frame, layout):
    """Measure local contrast at a consistent scale for the same crop."""
    image = crop_register(frame, layout.box).convert("L")
    width, height = image.size
    image = image.crop((width // 20, height // 10, width - width // 20, height - height // 10))
    image = image.resize((160, 48), Image.Resampling.LANCZOS)
    across = ImageChops.difference(image.crop((0, 0, 158, 48)), image.crop((2, 0, 160, 48)))
    down = ImageChops.difference(image.crop((0, 0, 160, 46)), image.crop((0, 2, 160, 48)))
    return (ImageStat.Stat(across).mean[0] + ImageStat.Stat(down).mean[0]) / 2


def register_light_hints(register):
    """The light part of ``image_quality_hints`` for a register that is already cut out.

    Used by the routine check (0.5.0) so the hints of the setup are also available later:
    "dark", "bright" or "low_contrast". Sharpness needs the whole frame and is left out.
    """
    gray = register.convert("L").resize((160, 48), Image.Resampling.BILINEAR)
    levels = sorted(gray.tobytes())
    low, high = levels[len(levels) // 10], levels[len(levels) * 9 // 10]
    hints = ["dark"] if high < 45 else ["bright"] if low > 215 else []
    if high - low < 32:
        hints.append("low_contrast")
    return hints


def image_quality_hints(frame, layout):
    """Give a rough first-frame assessment of the digit area."""
    gray = crop_register(frame, layout.box).convert("L").resize((160, 48), Image.Resampling.BILINEAR)
    levels = sorted(gray.tobytes())
    low, high = levels[len(levels) // 10], levels[len(levels) * 9 // 10]
    hints = []
    if high < 45:
        hints.append("dark")
    elif low > 215:
        hints.append("bright")
    contrast = high - low
    if contrast < 32:
        hints.append("low_contrast")
    elif crop_quality(frame, layout) < 0.065 * contrast:
        hints.append("soft")
    return hints


def agreement_percent(readings, sample, precision, digits):
    """Measure position agreement across profiles at the required precision."""
    rows = []
    for value in readings:
        whole, _, fraction = str(value).replace(",", ".").partition(".")
        rows.append((whole + fraction[:precision].ljust(precision, "?"))
                    if len(whole) == digits else "?" * (digits + precision))
    expected = meter_prefix(sample.get("actual_value"), precision, digits)
    if expected is not None and sample.get("reference_required") is not False and not reference_rejection(
            sample, compare_sample(sample, sample["actual_value"], precision, integer_digits=digits)[0]):
        target = str(expected).zfill(digits + precision)
        return round(100 * sum(a == b for row in rows for a, b in zip(row, target))
                     / (len(rows) * len(target)))
    return round(100 * sum(len(set(slot)) == 1 and slot[0].isdigit() for slot in zip(*rows))
                 / (digits + precision))


def reference_rejection(sample, status):
    if sample.get("reference_is_fallback") or not sample.get("reference_time"):
        return "reference_unavailable"
    if status != "match":
        return "reference_mismatch" if status == "difference" else "reference_unavailable"
    return None


def position_error(value, sample, precision, whole):
    """Identify a likely one-slot shift against a reliable reference."""
    reference = sample.get("actual_value")
    measured = str(value).replace(",", ".").partition(".")
    if len(measured[0]) != whole:
        return True
    expected = meter_prefix(reference, precision, whole)
    if expected is None:
        return False
    target = str(expected).zfill(whole + precision)
    reading = measured[0] + measured[2][:precision]
    aligned = sum(a == b for a, b in zip(reading, target))
    return any(sum(a == b for a, b in zip(left, right)) >= max(3, aligned + 2)
               for left, right in ((reading[1:], target), (reading, target[1:])))


def contradicts_reference(readings, sample, digits):
    """Reject a partial row only when both profiles consistently read several wrong positions."""
    expected = meter_prefix(sample.get("actual_value"), 0, digits)
    if expected is None or not sample.get("reference_time") or sample.get("reference_is_fallback"):
        return False
    rows = [str(value).replace(",", ".").partition(".")[0] for value in readings]
    if any(len(row) != digits for row in rows):
        return False
    agreed = [(a, digit) for a, b, digit in zip(*rows, str(expected).zfill(digits))
              if a == b and a in "0123456789"]
    return sum(a != digit for a, digit in agreed) >= 3 and all(a != digit for a, digit in agreed)


def uncertain_slots(readings, count):
    rows = [str(value).replace(".", "").replace(",", "") for value in readings]
    if any(len(row) != count for row in rows):
        return list(range(count))
    return [index for index, slot in enumerate(zip(*rows)) if len(set(slot)) != 1 or not slot[0].isdigit()]


def penultimate_issue(readings, sample, whole):
    """Identify a weak second decimal digit while the rest of the row agrees."""
    count, slot = whole + 3, whole + 1
    rows = [str(value).replace(".", "").replace(",", "") for value in readings]
    if any(len(row) != count for row in rows):
        return None
    unaffected = rows[0][:slot] + rows[0][slot + 1:]
    if not unaffected.isdigit() or any(row[:slot] + row[slot + 1:] != unaffected for row in rows[1:]):
        return None
    if uncertain_slots(readings, count) == [slot]:
        return slot, unaffected
    if sample.get("reference_required") is not False:
        reference = sample.get("actual_value")
        status, _ = compare_sample(sample, reference, 3, integer_digits=whole)
        expected = meter_prefix(reference, 3, whole)
        if expected is not None and reference_rejection(sample, status) is None:
            target = str(expected).zfill(count)
            if unaffected == target[:slot] + target[slot + 1:] and rows[0][slot] != target[slot]:
                return slot, unaffected
    return None


def meter_like(readings, minimum=5):
    """Did an upright candidate already read most of a register (e.g. "10493.3??")?

    Then the picture is not turned by a right angle and quarter turns are not searched.
    """
    return any(sum(char.isdigit() for char in str(value)) >= minimum for value in readings)


def whole_like(readings, digits):
    """Were most whole digits read (e.g. "1049?.???"), not just scattered digits like "?11?5.11?"? (0.5.23)"""
    needed = max(3, digits - 1)
    return any(sum(char.isdigit() for char in str(value).split(".")[0]) >= needed for value in readings)


def upright_layout(layout):
    """A frame turned less than 45°: only its reading shows that the picture is upright (0.5.22).

    A frame saved earlier at a right angle that reads the whole digits says nothing about
    whether a better frame at a right angle (with the measured tilt) exists.
    """
    return abs(getattr(layout, "rotation", 0) or 0) < 45


def setup_flow_limit(rules):
    """Flow a new setup frame may claim since the last counted reading (litres per hour).

    The learned limit when the app knows one, otherwise half the configured maximum (at least
    1.5 m³/h), never above the maximum.
    """
    maximum = rules.get("max_flow_lph")
    if type(maximum) not in (int, float) or maximum <= 0:
        return maximum
    learned = rules.get("learned_flow_lph")
    if type(learned) in (int, float) and learned > 0:
        return min(maximum, learned)
    return min(maximum, max(SETUP_FLOW_FLOOR_LPH, maximum * SETUP_FLOW_SHARE))


def baseline_litres(baseline):
    """The last known reading of a setup baseline in litres and the lowest value allowed, or None."""
    if not isinstance(baseline, dict):
        return None
    reading = next((baseline.get(key) for key in ("anchor_litres", "reading_litres")
                    if type(baseline.get(key)) is int), None)
    if reading is None:
        return None
    lowest = baseline.get("floor_litres")
    return reading, lowest if type(lowest) is int else reading


def digit_count(readings):
    """How many digits the best of the readings shows (0.5.31)."""
    return max((sum(char.isdigit() for char in str(value)) for value in readings), default=0)


def near_turn(rotation, turn):
    """Two rotations within HALF_TURN_TOLERANCE of each other, across ±180° (0.5.31)."""
    return abs((rotation - turn + 180) % 360 - 180) <= HALF_TURN_TOLERANCE


def half_turned(layout, other):
    """Two frames on the same digits, turned by about 180° against each other (0.5.29)."""
    if layout is None or other is None:
        return False
    if abs((layout.rotation - other.rotation) % 360 - 180) > HALF_TURN_TOLERANCE:
        return False
    left, top, right, bottom = layout.box
    x, y, u, v = other.box
    shared = max(0, min(right, u) - max(left, x)) * max(0, min(bottom, v) - max(top, y))
    return shared >= .5 * min(max(1, (right - left) * (bottom - top)), max(1, (u - x) * (v - y)))


def half_turn_layout(layout, slots):
    """The same frame read turned by another 180° (0.5.29).

    Digit boxes (0–1000 crop coordinates) are mirrored and reversed when there is one per
    slot, otherwise the frame is read with even rollers.
    """
    rotation = layout.rotation + 180 if layout.rotation <= 0 else layout.rotation - 180
    boxes = ()
    if len(layout.digit_boxes) == slots:
        boxes = tuple((1000 - box[2], 1000 - box[3], 1000 - box[0], 1000 - box[1])
                      for box in reversed(layout.digit_boxes))
    return replace(layout, rotation=rotation, digit_boxes=boxes)


def closer_half_turn(layout, reading, tried, baseline, precision, digits):
    """The frame turned by 180° on the same digits whose reading fits the last reading better.

    A meter hanging sideways can also read as a plausible number upside down: the right frame
    read the last reading plus a few litres, the frame turned by 180° a value several m³
    higher, and the higher one was confirmed. Of two such frames the one closer to the last
    known reading is the meter. ``tried`` holds (score, layout, readings) of this picture.
    0.5.32: when the turned frame's decimals stay unclear ("10517.?7?"), its whole cubic metres
    are compared; before, it counted as no evidence and the wrong frame was confirmed.
    0.5.35: a turned frame reading clearly below the newest reading seen is never the closer one:
    upside down, a frame read 10517.12 with 10516.24 booked and 10517.80 seen, the right one
    10517.83, and the lower wrong reading won.
    """
    known = baseline_litres(baseline)
    if known is None:
        return None
    last, lowest = known
    newest = newest_seen(baseline)
    for compared in dict.fromkeys((precision, 0)):
        prefix = meter_prefix(reading, compared, digits)
        if prefix is None:
            continue
        step = 10 ** (3 - compared)
        distance = abs(prefix * step - last)
        for _, other, values in tried:
            if other == layout or not values or not half_turned(layout, other):
                continue
            value = meter_prefix(values[0], compared, digits)
            if (value is not None and value * step + step > lowest // step * step
                    and value * step + step + BEHIND_SLACK_LITRES > newest
                    and abs(value * step - last) + (step if compared < precision else 0) < distance):
                return other
    return None


def presort_ranks(seen, chosen):
    """Rank of the chosen frame as tested and if frames with more filled digit fields came first (0.5.41).

    ``seen`` holds (layout, filled fields or None) in the order the setup tested them. Returns
    (tested rank, presorted rank) counted from 1, or None when the frame was not tested.
    """
    layouts = [layout for layout, _ in seen]
    if chosen not in layouts:
        return None
    order = sorted(range(len(seen)), key=lambda index: -(seen[index][1] if seen[index][1] is not None else -1))
    position = layouts.index(chosen)
    return position + 1, order.index(position) + 1


def orientation_agreement(value, whole_range=None, digits=5):
    """How well a reading made without the known reading's help fits the meter (0.5.35).

    Upside down, a frame shows the digits in reverse order and turned, and only few of them
    still fit the whole cubic metres the meter can show now (``whole_range``: lowest and highest
    value). Each read digit that fits counts +1, each that does not -1, with the row shifted by
    up to one slot (a frame may sit one roller off); a position any digit fits counts nothing.
    Without a usable range the number of read digits counts.
    """
    text = str(value or "")
    whole, _, fraction = text.partition(".")
    slots = whole + fraction
    count = sum(char.isdigit() for char in slots)
    if (not isinstance(whole_range, (tuple, list)) or len(whole_range) != 2
            or not all(type(bound) is int for bound in whole_range) or len(whole) != digits):
        return count
    low, high = max(0, whole_range[0]), whole_range[1]
    if not 0 <= high - low <= 1000 or len(str(high)) > digits:
        return count
    allowed = [set() for _ in range(digits)]
    for number in range(low, high + 1):
        for index, char in enumerate(str(number).zfill(digits)):
            allowed[index].add(char)
    best = None
    for offset in (-1, 0, 1):
        score = 0
        for index, char in enumerate(slots):
            position = index - offset
            if char.isdigit() and 0 <= position < digits and len(allowed[position]) < 10:
                score += 1 if char in allowed[position] else -1
        best = score if best is None else max(best, score)
    return best


def newest_seen(baseline):
    """The newest reading a setup baseline knows, in litres, or None (0.5.35).

    Besides the last booked reading this is the reading the camera saw last, which is not yet
    proven but read the meter as it is now.
    """
    known = baseline_litres(baseline)
    values = [known[0]] if known is not None else []
    if isinstance(baseline, dict):
        values += [baseline[key] for key in ("reading_litres", "pending_litres") if type(baseline.get(key)) is int]
    return max(values, default=None)


def behind_newest(reading, baseline, precision, digits):
    """True when a reading lies clearly below the newest reading seen before (0.5.35)."""
    newest = newest_seen(baseline)
    if newest is None:
        return False
    for compared in range(precision, -1, -1):
        prefix = meter_prefix(reading, compared, digits)
        if prefix is not None:
            step = 10 ** (3 - compared)
            return prefix * step + step + BEHIND_SLACK_LITRES <= newest
    return False


def skip_small_labels(candidates):
    """Skip small rows separated vertically from a detected register window."""
    windows = [layout.box for layout in candidates if layout.method == "register_window"]
    if not windows:
        return candidates
    left, top, right, bottom = max(windows, key=lambda box: (box[2] - box[0]) * (box[3] - box[1]))
    width, height = right - left, bottom - top
    return [layout for layout in candidates
            if layout.method == "register_window"
            or not ((layout.box[1] >= bottom or layout.box[3] <= top)
                    and layout.box[2] - layout.box[0] <= width * .60
                    and layout.box[3] - layout.box[1] <= height * .80)]


INTENSIVE_GAP = 40


def worth_intensive(items, shortlist, best, threshold):
    """Drop candidates without a chance once one candidate already reads the meter well.

    With a candidate at or above the agreement threshold, crops that read nothing (0 %) or
    lag far behind it, e.g. tiny print turned by 90°, are not re-read with extra profiles.
    """
    if best < threshold:
        return items
    # Below the confirmation threshold a frame is only a search aid once another frame reaches
    # it (70–75 % frames cost images and time without ever being saved).
    floor_percent = max(best - INTENSIVE_GAP, threshold)
    kept = [item for item in items
            if shortlist.get(item[1], (0,))[0] > 0 and shortlist.get(item[1], (0,))[0] >= floor_percent]
    return kept or items


def refinement_workers():
    cores = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count() or 1
    try:
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if quota != "max":
            cores = min(cores, max(1, int(quota) // int(period)))
    except (OSError, ValueError):
        pass
    try:
        spare_cpu = max(1, int(cores - os.getloadavg()[0]) - 1)
        spare_memory = os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        try:
            limit = Path("/sys/fs/cgroup/memory.max").read_text().strip()
            if limit != "max":
                used = int(Path("/sys/fs/cgroup/memory.current").read_text())
                spare_memory = min(spare_memory, int(limit) - used)
        except (OSError, ValueError):
            pass
        return max(1, min(4, spare_cpu, spare_memory // (256 * 1024 ** 2)))
    except (OSError, ValueError, AttributeError):
        return 1


def refinement_layouts(layout, rules, readings):
    """Vary missing or disputed slots first, keeping neighbouring centers as guides."""
    whole, fraction = rules["integer_digits"], rules["fraction_digits"]
    count = whole + fraction
    left, top, right, bottom = layout.box
    if not layout.digit_boxes:
        span = rotated_width(right - left, bottom - top, layout.rotation)
        split = min(1000, round(1000 * layout.width / span))
        edges = [round(i * split / whole) for i in range(whole + 1)]
        edges += [split + round(i * (1000 - split) / fraction) for i in range(1, fraction + 1)]
        boxes = tuple((a, 0, b, 1000) for a, b in zip(edges, edges[1:]))
    else:
        boxes = layout.digit_boxes
    weak = uncertain_slots(readings, count)
    pitch = median(r - l for l, _, r, _ in boxes)
    shifts = (0, -1, 1, -2, 2)
    slot_sets = [{i} for i in weak]
    offsets = sorted(product(shifts[:3], repeat=5), key=lambda values: sum(map(abs, values)))
    for dx, dy, dw, dh, spacing in offsets:
        for slots in slot_sets:
            if not any((dx, dy, dw, dh, spacing)) and layout.digit_boxes:
                continue
            trial = []
            for i, (l, t, r, b) in enumerate(boxes):
                if i in slots:
                    x = round(pitch * (dx + spacing * (i - (count - 1) / 2)) / 12)
                    margin = round(pitch * dw / 10)
                    l, r = max(0, l + x - margin), min(1000, r + x + margin)
                    t, b = max(0, t + 35 * dy - 45 * dh), min(1000, b + 35 * dy + 45 * dh)
                trial.append((l, t, r, b))
            try:
                valid = digit_box_settings(trial, count)
            except ValueError:
                continue
            yield replace(layout, digit_boxes=tuple(map(tuple, valid)),
                          method="refined")


def visible_fits_reading(visible, integer_digits, known, flow_lph, stamp):
    """True when the whole digits of ``visible`` ("?" = unknown) can show the known reading.

    ``known`` is {"value": litres, "time": epoch seconds}. The reachable range runs from one
    cubic metre below the reading (a picture taken just before the entry) up to the reading plus
    maximum flow × elapsed time plus one cubic metre. Missing data always passes.
    """
    whole = str(visible or "")[:integer_digits]
    if (not isinstance(known, dict) or type(known.get("value")) is not int or known["value"] < 0
            or type(known.get("time")) not in (int, float) or len(whole) != integer_digits
            or not any(char.isdigit() for char in whole)):
        return True
    elapsed = max(0.0, (stamp if type(stamp) in (int, float) else known["time"]) - known["time"])
    flow = flow_lph if type(flow_lph) in (int, float) and flow_lph > 0 else 0
    low = max(0, known["value"] // 1000 - 1)
    high = (known["value"] + int(flow * elapsed / 3600)) // 1000 + 1
    if high - low > 2000:
        return True
    for cubic_metres in range(low, high + 1):
        shown = str(cubic_metres).zfill(integer_digits)
        if len(shown) == integer_digits and all(char == "?" or char == digit for char, digit in zip(whole, shown)):
            return True
    return False


@dataclass
class Calibration:
    limit: int
    started: float
    state: str = "waiting"
    stage: str = "queued"
    rotation: int | None = None
    variant: int | None = None
    seen: set = field(default_factory=set)
    last_stamp: float = 0
    candidate: Layout | None = None
    counter: dict = field(default_factory=dict)
    confirmations: int = 0
    attempts: int = 0
    best: Layout | None = None
    best_confirmations: int = 0
    anchored: bool = False
    advanced: bool = False
    reference_reading: str | None = None
    reference_image_id: str | None = None
    verification_pending: bool = False
    verification_deadline: float | None = None
    automatic: bool = False
    simplified: bool = False
    intensive: bool = False
    setup_last_digit: bool = False
    stream_unavailable: bool = False
    followup: bool = False
    background: bool = False  # Fine check does not suspend confirmed seven-digit readings.
    purpose: str = ""  # "relocate": search again for a last-digit frame that sits beside its roller
    unclear_frames: int = 0
    followup_baseline: dict | None = None
    rank_candidates: bool = False
    coarse_attempts: int = 0
    optimizing: bool = False
    shortlist: dict = field(default_factory=dict)
    candidate_readings: dict = field(default_factory=dict)
    row_found: int = 0
    digit_found: dict = field(default_factory=dict)
    agreement_threshold: int = DEFAULT_INTENSIVE_AGREEMENT
    confirmed_quality: list = field(default_factory=list)
    fine_evidence: tuple | None = None
    # Image fetch statistics for the debug log, reset after each logged image.
    image_stats: dict = field(default_factory=dict)
    image_hints: list | None = None
    # 0.5.11: one line per evaluated picture for the checklist of the setup (newest last).
    rounds: list = field(default_factory=list)
    full_hits: int = 0
    stress_weak_slots: list = field(default_factory=list)
    duration: int = TIME_LIMIT
    attempt_limit: int = MAX_ATTEMPTS
    previous_layout: Layout | None = None
    known_good_layout: Layout | None = None
    reflected_layout: Layout | None = None
    reflected_positions: tuple = ()
    # Reflection found by the app itself (no marked positions): layout, positions, visible digits, images.
    auto_glare: dict | None = None
    # 0.5.19: a reading entered by hand ({"value": litres, "time": epoch}) and the flow limit;
    # a frame with a hidden digit must show whole cubic metres that fit it.
    known_reading: dict | None = None
    known_flow: float = 0.0
    glare_mismatch: bool = False
    auto_reflection: bool = False
    # Slots the user marked as hidden by a reflection (0-based); trusted without glare detection.
    marked_positions: tuple = ()
    reflected_confirmations: int = 0
    region: tuple | None = None
    focused: bool = False
    best_score: tuple = ()
    spent: float = 0
    searching_since: float | None = None
    last_image_at: float | None = None
    refinement_seen: set = field(default_factory=set)
    angle_compared: set = field(default_factory=set)
    rejected_regions: list = field(default_factory=list)
    # Background searches only use pictures of automatic checks: last one already evaluated.
    automatic_seq: int = 0
    # 0.4.0: frames of the same register (±2°, ≥ 80 % overlap) are one group: hits are counted
    # per image for the group, the list shows one entry per group, the best frame is saved.
    groups: list = field(default_factory=list)
    score_stamps: dict = field(default_factory=dict)
    # 0.5.0: images on which every required digit but the last one agreed (roller turning or
    # standing between two digits). They count towards a provisional seven-digit setup.
    partial_hits: int = 0
    partial_prefix: int | None = None
    partial_stamp: float = 0
    rejected: list = field(default_factory=list)
    skews: list = field(default_factory=list)
    current_stamp: float = 0
    # 0.5.31: turns the user marked as upside down ("Steht auf dem Kopf?"); frames near them are
    # tested turned by another 180°.
    wrong_turns: list = field(default_factory=list)
    # 0.5.41, shadow mode only: frames tested on the current picture with their filled digit fields.
    presort_shadow: bool = False
    presort_seen: list = field(default_factory=list)

    def measured_skew(self, frame):
        """Median of the tilt measured on the last images (None until one was measured)."""
        skew = estimate_skew(frame)
        if skew is not None:
            self.skews = [*self.skews[-4:], skew]
        return round(median(self.skews)) if self.skews else None

    def group_of(self, layout):
        for group in self.groups:
            if layout in group["layouts"] or same_register(layout, group["rep"]):
                return group
        return None

    def note_group(self, layout, readings, hit, digits):
        """Collect a frame in its register group; one hit per image and group."""
        if layout is None:
            return None
        group = self.group_of(layout)
        if group is None:
            group = {"rep": layout, "layouts": set(), "hits": set(), "quality": {}}
            self.groups.append(group)
            if len(self.groups) > MAX_GROUPS:
                # Forget the oldest group without hits (never the one being confirmed).
                for old in self.groups:
                    if not old["hits"] and old is not group and self.candidate not in old["layouts"]:
                        self.groups.remove(old)
                        break
                else:
                    self.groups.pop(0)
        group["layouts"].add(layout)
        if readings:
            # Remembered per group so a register with hits can be listed after its frames left the shortlist.
            group["reading"] = str(readings[0]).replace(",", ".")
        sure = digits - len(uncertain_slots(readings, digits)) if readings else 0
        images = group["quality"].setdefault(layout, {})
        images[self.current_stamp] = max(images.get(self.current_stamp, 0), sure)
        if hit:
            group["hits"].add(self.current_stamp)
        return group

    def best_of_group(self, layout):
        """The frame of this register that read most digits surely over several images.

        The setup saved the first confirmed −12° frame although −13°/−14°
        read better. Only frames with at least two images count; ties keep the confirmed frame.
        """
        group = self.group_of(layout)
        if group is None:
            return layout
        def quality(item):
            values = list(group["quality"].get(item, {}).values())
            return sum(values) / len(values) if len(values) >= 2 else None
        own = quality(layout)
        best = layout
        for item in group["layouts"]:
            score = quality(item)
            if (score is not None and item.digit_boxes and len(item.digit_boxes) == len(layout.digit_boxes)
                    and (own is None or score > own + .25) and (best is layout or score > quality(best))):
                best = item
        return best

    def distinct_shortlist(self):
        """One frame per register group, the best scoring first (no near-duplicate re-reads)."""
        seen = []
        for layout in self.shortlist:
            group = self.group_of(layout)
            if group is not None and any(group is other for other in seen):
                continue
            if group is not None:
                seen.append(group)
            yield layout

    def turned_wrong(self, layout):
        """The frame lies in a direction the user marked as upside down (0.5.31)."""
        return layout is not None and any(near_turn(layout.rotation, turn) for turn in self.wrong_turns)

    def oriented(self, layout, slots):
        """The frame turned the way the user wants it (0.5.31)."""
        return half_turn_layout(layout, slots) if self.turned_wrong(layout) else layout

    def flip_orientation(self, slots):
        """The user saw the tested frame upside down: test it turned by 180° from now on (0.5.31).

        A second flip turns it back. Everything counted in the old direction starts anew, frames
        found so far keep their place in the list, turned.
        """
        reference = self.candidate or self.best or next(iter(self.shortlist), None)
        turn = reference.rotation if reference is not None else self.rotation
        if turn is None:
            return False
        back = [wrong for wrong in self.wrong_turns if near_turn(turn, wrong + 180)]
        self.wrong_turns = ([wrong for wrong in self.wrong_turns if wrong not in back] if back
                            else [*self.wrong_turns, turn])

        def flip(layout):
            return half_turn_layout(layout, slots) if layout is not None and near_turn(layout.rotation, turn) else layout

        self.candidate = flip(self.candidate)
        self.shortlist = {flip(layout): score for layout, score in self.shortlist.items()}
        self.candidate_readings = {}
        self.score_stamps = {}
        self.groups = []
        self.rotation = flip(reference).rotation if reference is not None else None
        self.counter = {}
        self.best, self.best_confirmations = None, 0
        self.confirmations = self.full_hits = self.partial_hits = self.unclear_frames = 0
        self.partial_prefix = None
        self.anchored = self.advanced = False
        # 0.5.32: the next picture tests the turned frame first instead of searching all frames
        # again; if it does not read, the search widens as before.
        self.focused = self.candidate is not None
        self.verification_pending, self.verification_deadline = False, None
        self.reference_reading = None
        self.fine_evidence = None
        self.stress_weak_slots, self.confirmed_quality = [], []
        self.angle_compared, self.refinement_seen = set(), set()
        self.rejected_regions = []
        return True

    def orientation_evidence(self, layout, twin, orientation_score, stop):
        """Scores of a frame and its 180° twin read without the known reading's help (0.5.35).

        The normal reading completes the whole cubic metres from the known reading, so a frame
        upside down read "10517" as well and only its decimals were garbage; the comparison
        with the last reading then preferred the wrong frame. Returns (frame, twin) or None.
        """
        scores = []
        for trial in (layout, twin):
            if stop():
                return None
            try:
                scores.append(orientation_score(trial, OCR_PROFILES[0]))
            except (OSError, ValueError, subprocess.SubprocessError):
                return None
        self.attempts += 1
        return tuple(scores)

    def half_turn_closer(self, frame, layout, reading, tried, tested, baseline, precision, digits, slots, read,
                         stop, score_layout, orientation_score=None):
        """Why this frame must give way to the same digits turned by 180°, or None.

        A meter hanging sideways also reads as a plausible number upside down. 0.5.35: first
        the direction whose free reading fits the meter clearly better wins ("half_turn"). Only
        when that stays open, a frame reading clearly below the newest reading seen is not taken
        ("behind"), and the reading closer to the last reading decides as before (0.5.29). When
        this picture did not test the turned frame yet, it is read and added to ``tried``, so the
        loop that accepts frames checks it next.
        """
        if layout == self.candidate or self.intensive or self.followup:
            return None
        twin = half_turn_layout(layout, slots)
        if self.wrong_turns and self.turned_wrong(twin):
            # The user turned the frame this way (0.5.31): their direction wins.
            return None
        left, top, right, bottom = twin.box
        inside = 0 <= left < right <= frame.width and 0 <= top < bottom <= frame.height
        evidence = (self.orientation_evidence(layout, twin, orientation_score, stop)
                    if orientation_score is not None and inside else None)
        if evidence is not None and evidence[0] >= evidence[1] + ORIENTATION_MARGIN:
            return None
        reason = ("half_turn" if evidence is not None and evidence[1] >= evidence[0] + ORIENTATION_MARGIN
                  else None)
        if reason is None:
            # A frame confirmed before keeps its direction unless the twin reads clearly better.
            if layout == self.known_good_layout or not baseline:
                return None
            if behind_newest(reading, baseline, precision, digits):
                reason = "behind"
            elif closer_half_turn(layout, reading, tried, baseline, precision, digits) is not None:
                return "half_turn"
        # 0.5.32: other frames on the same digits turned by 180° may have read garbage (a box of
        # another size); only the exact twin of this frame decides.
        if any(other == twin for _, other, _ in tried) or stop() or twin in tested or not inside:
            return reason
        tested.add(twin)
        self.attempts += 1
        try:
            values = [read(twin, OCR_PROFILES[0])]
            if reason is None and meter_prefix(values[0], 0, digits) is None or stop():
                return reason
            values.append(read(twin, OCR_PROFILES[1]))
        except (OSError, ValueError, subprocess.SubprocessError):
            return reason
        values = self.mask_empty_fields(frame, twin, values)
        if reason is None:
            if closer_half_turn(layout, reading, [(None, twin, values)], baseline, precision, digits) is None:
                return None
            reason = "half_turn"
        tried.append((score_layout(twin, values), twin, values))
        return reason

    def gives_way(self, frame, layout, reading, coarse, tested, baseline, precision, digits, rules, read, stop,
                  score_layout, orientation_score, sample, sample_precision):
        """True when this frame is not taken because its 180° twin is the meter (0.5.35).

        Notes the reason for the list of rejected frames and keeps the twin read for the
        comparison of candidates; the twin itself is checked next in the loop that accepts frames.
        """
        if not baseline and orientation_score is None:
            return False
        known = len(coarse)
        reason = self.half_turn_closer(frame, layout, reading, coarse, tested, baseline, precision, digits,
                                       digits + rules["fraction_digits"], read, stop, score_layout,
                                       orientation_score)
        if reason is None:
            return False
        if self.rank_candidates and len(coarse) > known:
            _, twin, values = coarse[-1]
            self.record_intermediate(twin, values, sample, sample_precision, digits, rules["fraction_digits"], frame)
        self.note_rejection(layout, reason, reading)
        return True

    def note_rejection(self, layout, reason, reading=None):
        if any(same_digit_region(layout.box, entry["box"]) and entry["reason"] == reason
               and entry.get("rotation") == layout.rotation for entry in self.rejected):
            return
        entry = {"reason": reason, "box": list(layout.box), "rotation": layout.rotation}
        if reading:
            # 0.5.29: a frame that read well but did not fit the last reading is listed with
            # what it read, so a good-looking frame does not vanish without a trace.
            entry["reading"] = str(reading)[:16]
        self.rejected = [*self.rejected[-(MAX_REJECTED - 1):], entry]

    def size_reference(self):
        if self.known_good_layout is not None:
            return self.known_good_layout
        if self.candidate is not None and self.confirmations:
            return self.candidate
        for group in self.groups:
            if len(group["hits"]) >= 2:
                return group["rep"]
        return None

    def prefilter(self, candidates):
        """Common pre-filter for all candidate sources before any OCR (0.4.0).

        With a known register size (bewährter Rahmen, confirmed candidate or a frame with two
        hits), much smaller rows (serial number, small print ≈ half the digit height) and frames
        turned far away from it are dropped with a reason for the candidate list.
        """
        reference = self.size_reference()
        for layout in candidates:
            if reference is not None and layout != reference:
                area = lambda box: max(1, (box[2] - box[0]) * (box[3] - box[1]))
                if area(layout.box) < SMALL_LABEL_AREA * area(reference.box):
                    self.note_rejection(layout, "small_label")
                    continue
                if abs(layout.rotation - reference.rotation) > PREFILTER_TURN:
                    self.note_rejection(layout, "quarter_turn" if abs(layout.rotation) >= 45 else "rotation")
                    continue
            yield layout

    def expired(self, now):
        return self.remaining(now) <= 0

    def stationary_crop_ready(self):
        if not self.simplified or self.automatic or self.candidate is None:
            return False
        if self.confirmations >= MIN_IMAGES and not (self.anchored or self.advanced):
            return True
        # The last required roller stayed between two digits on every image (no gas flowing):
        # the frames are proven by all other digits, the setup is saved provisionally.
        return self.partial_hits > 0 and self.confirmations + self.partial_hits >= MIN_IMAGES + 1

    def partial_hit(self, layout, rows, stamp, flow, baseline=None, baseline_flow=None):
        """Count an image whose required digits all agree except the last one (0.5.0).

        ``rows`` are both readings without the decimal point, cut to the required slots. The
        partial reading must fit the candidate and may neither fall nor jump implausibly.
        0.5.29: the first partial hit must also fit the last known reading (``baseline``) at
        the setup flow; before, any frame could collect it, also one turned by 180°.
        """
        if self.candidate is not None and not same_register(layout, self.candidate):
            return False
        try:
            prefix = int(rows[0][:-1])
        except ValueError:
            return False
        litres = prefix * 100  # one decimal less than the two compared decimals: 0.1 m³
        earlier = None
        if self.partial_prefix is not None:
            earlier = self.partial_prefix * 100, self.partial_stamp
        if "reading_litres" in self.counter:
            known = self.counter["reading_litres"] // 100 * 100, self.counter.get("timestamp", stamp)
            earlier = known if earlier is None or known[0] > earlier[0] else earlier
        if earlier is not None:
            hours = max(0.0, stamp - earlier[1]) / 3600
            if litres < earlier[0] or litres - earlier[0] > flow * hours + 200:
                return False
        elif baseline_litres(baseline) is not None and any(
                type(baseline.get(key)) in (int, float) for key in ("anchor_time", "timestamp")):
            last, lowest = baseline_litres(baseline)
            limit = baseline_flow if type(baseline_flow) in (int, float) else flow
            since = next(baseline[key] for key in ("anchor_time", "timestamp")
                         if type(baseline.get(key)) in (int, float))
            hours = max(0.0, stamp - since) / 3600
            if litres + 100 <= lowest // 100 * 100 or litres - last // 100 * 100 > limit * hours + 200:
                return False
        if self.candidate is None:
            self.candidate = layout
        self.partial_hits += 1
        self.partial_prefix, self.partial_stamp = prefix, stamp
        self.unclear_frames = 0
        return True

    def note_auto_glare(self, frame, coarse, required_rows, required_slots, digits, reference_digits, on_selected):
        """Recognise a digit hidden by a reflection of the light without the user marking it.

        Only the washed-out frames may stay unclear; all other required digits must agree in both
        readings, and the same frames must be washed out with the same visible whole digits on
        MIN_IMAGES different images. Then the layout is handled like a marked reflection.
        """
        for _, layout, readings in coarse:
            rows = required_rows(readings)
            weak = uncertain_slots(rows, required_slots)
            if not 1 <= len(weak) <= 2 or required_slots - len(weak) < 4:
                continue
            try:
                left, top, right, bottom = layout.box
                register = turn_crop(frame.crop((left, top, right, bottom)), layout.rotation)
                boxes = scale_digit_boxes(layout.digit_boxes, register.size) if layout.digit_boxes else ()
            except (ValueError, TypeError):
                continue
            if len(boxes) < required_slots:
                continue
            glared = set(glare_slots(register, boxes)) | set(self.marked_positions)
            if not glared or not set(weak) <= glared:
                continue
            visible = "".join("?" if index in weak else rows[0][index] for index in range(digits))
            if reference_digits is not None and any(
                    char != reference_digits[index] for index, char in enumerate(visible) if char != "?"):
                continue
            if not self.visible_fits_known_reading(visible, digits):
                continue
            previous = self.auto_glare
            if (previous is not None and similar_layout(layout, previous["layout"])
                    and previous["positions"] == tuple(weak) and previous["visible"][:-1] == visible[:-1]):
                count = previous["count"] + 1
            else:
                count = 1
            self.auto_glare = {"layout": layout, "positions": tuple(weak), "visible": visible, "count": count}
            self.glare_mismatch = False
            if on_selected is not None:
                on_selected(layout, readings)
            if count >= MIN_IMAGES:
                self.reflected_layout = layout
                self.reflected_positions = tuple(weak)
                self.reflected_confirmations = count
                self.auto_reflection = True
            return True
        return False

    def visible_fits_known_reading(self, visible, integer_digits, stamp=None):
        """Do the visible whole digits fit the reading entered by hand (0.5.19)?

        Without a comparison sensor the reflection confirmation compared the visible digits
        against nothing, so a misread whole digit (e.g. 5 instead of 2) could be taken. The whole
        cubic metres must lie between the entered reading and what the meter can reach since then
        (maximum flow × time, at least one cubic metre either side). Without a known reading
        nothing can be checked and the frame passes.
        """
        return visible_fits_reading(visible, integer_digits, self.known_reading, self.known_flow,
                                    self.current_stamp if stamp is None else stamp)

    def reflection_crop_ready(self):
        return self.reflected_layout is not None and self.reflected_confirmations >= MIN_IMAGES

    def begin_verification(self, now):
        self.verification_pending = True
        if self.intensive and self.verification_deadline is None:
            self.verification_deadline = now + INTENSIVE_VERIFICATION_SECONDS

    def skippable_verification_id(self):
        if (self.intensive and not self.automatic and self.verification_pending
                and self.verification_deadline is not None and self.candidate is not None
                and self.confirmations >= MIN_IMAGES
                and self.state in ("waiting", "testing", "failed", "timeout", "image_timeout")):
            return str(self.verification_deadline)
        return None

    def remaining(self, now):
        if self.verification_deadline is not None:
            remaining = self.verification_deadline - now
            return min(remaining, self.duration - (now - self.started)) if self.setup_last_digit else remaining
        if (not self.intensive or self.setup_last_digit) and not self.automatic:
            return self.duration - (now - self.started)
        return self.duration - self.spent - (now - self.searching_since if self.searching_since is not None else 0)

    def image_wait_expired(self, now):
        return now - (self.last_image_at if self.last_image_at is not None else self.started) >= IMAGE_WAIT_LIMIT

    def precision(self, rules, has_reference):
        return 2 if self.simplified or rules["decimals"] == 2 else rules["decimals"] if has_reference else rules["fraction_digits"]

    def sweep_angles(self, layout, readings, sample, rules, read, stop, report, tested, frame_ceiling,
                     *, accept_first=False, offsets=None, stress_reads=None):
        whole, fraction = rules["integer_digits"], rules["fraction_digits"]
        referenced = sample.get("reference_required") is not False
        precision = self.precision(rules, referenced)

        def score(values):
            prefixes = [meter_prefix(value, precision, whole) for value in values]
            agreement = prefixes[0] is not None and prefixes[0] == prefixes[1]
            match = referenced and agreement and all(reference_rejection(
                sample, compare_sample(sample, value, precision, integer_digits=whole)[0]) is None for value in values)
            percentage = agreement_percent(values, sample, precision, whole)
            return match, agreement, percentage, -len(uncertain_slots(values, whole + fraction))

        expected = meter_prefix(readings[0], fraction, whole)
        expected_precision = fraction if expected is not None else precision
        expected = meter_prefix(readings[0], expected_precision, whole)

        def stress_score(candidate, values):
            if any(meter_prefix(value, expected_precision, whole) != expected for value in values):
                return -1
            if candidate not in stress_reads:
                stress_reads[candidate] = []
            extras = stress_reads[candidate]
            if len(extras) < 3:
                for profile in OCR_PROFILES[2 + len(extras):5]:
                    if stop():
                        return -1
                    try:
                        extras.append(read(candidate, profile))
                    except (OSError, ValueError, subprocess.SubprocessError):
                        continue
            return sum(meter_prefix(value, expected_precision, whole) == expected for value in stress_reads[candidate])

        best = score(readings), layout, readings
        center = 0 if offsets is None and abs(layout.rotation) <= 3 else layout.rotation
        l, t, r, b = layout.box
        for offset in SMALL_ANGLES if offsets is None else offsets:
            if stop() or self.attempts >= min(frame_ceiling, self.attempt_limit - MIN_IMAGES):
                break
            angle = center + offset
            if angle == layout.rotation or not -180 <= angle <= 180:
                continue
            trial = replace(layout, rotation=angle, width=min(layout.width, rotated_width(r - l, b - t, angle)))
            if trial in tested:
                continue
            tested.add(trial)
            self.attempts += 1
            if report is not None:
                report(self.attempts, angle)
            try:
                values = [read(trial, OCR_PROFILES[0])]
                if stop():
                    break
                values.append(read(trial, OCR_PROFILES[1]))
            except (OSError, ValueError, subprocess.SubprocessError):
                continue
            rank = score(values)
            if rank == best[0] and stress_reads is not None:
                best_support = stress_score(best[1], best[2])
                trial_support = stress_score(trial, values) if best_support < 3 else -1
                if trial_support > best_support and not stop():
                    best = rank, trial, values
            elif rank > best[0] or (rank == best[0] and not layout.digit_boxes
                                    and abs(trial.rotation) < abs(best[1].rotation)):
                # Digit frames belong to the angle they were fitted at: three degrees off, the
                # outer frames sit half a digit too high or too low. Only frames without own
                # digit boxes still prefer the smaller turn among equal readings (0.4.3).
                best = rank, trial, values
            if accept_first and (rank[0] if referenced else rank[1]):
                break
        return best[1], best[2]

    def compare_setup_angles(self, layout, readings, sample, rules, read, stop, report,
                             tested, ceiling, stress_reads):
        offsets = (-1, 1, -2, 2)
        trial, values = self.sweep_angles(
            layout, readings, sample, rules, read, stop, report, tested, ceiling,
            offsets=offsets, stress_reads=stress_reads,
        )
        width, height = layout.box[2] - layout.box[0], layout.box[3] - layout.box[1]
        complete = not stop() and all(replace(
            layout, rotation=angle, width=min(layout.width, rotated_width(width, height, angle)),
        ) in tested for angle in offsets)
        if complete:
            self.angle_compared.update((layout, trial))
        return trial, values, complete

    def status(self, now):
        selected_score = self.shortlist.get(self.candidate, ())
        return {"state": self.state, "stage": self.stage, "rotation": self.rotation, "variant": self.variant,
                "tested": len(self.seen), "limit": self.limit,
                "duration": INTENSIVE_VERIFICATION_SECONDS if self.verification_deadline is not None else self.duration,
                "attempts": self.attempts, "max_attempts": self.attempt_limit, "automatic": self.automatic,
                "confirmations": self.confirmations, "required": MIN_IMAGES,
                "reflected_confirmations": self.glare_hits(),
                "glare_prompt": self.glare_prompt(),
                "glare_mismatch": self.glare_mismatch,
                "row_found": self.row_found, "agreement_threshold": self.agreement_threshold,
                "coarse_threshold": COARSE_AGREEMENT, "digit_found_threshold": DIGIT_FOUND_COARSE,
                "full_hits": self.full_hits, "partial_hits": self.partial_hits,
                "image_hints": self.image_hints,
                "marked_positions": [slot + 1 for slot in self.marked_positions],
                "rounds": list(self.rounds),
                "known_good_available": self.known_good_layout is not None and self.region is None,
                "stress_weak_slots": self.stress_weak_slots,
                "coarse_complete": self.full_hits >= MIN_IMAGES,
                "awaiting_start_value": self.confirmations >= MIN_IMAGES and not (self.anchored or self.advanced),
                "simplified": self.simplified, "intensive": self.intensive, "setup_last_digit": self.setup_last_digit, "followup": self.followup,
                "background": self.background, "purpose": self.purpose,
                "coarse_attempts": self.coarse_attempts, "coarse_limit": COARSE_LIMIT,
                "shortlist": [score[0] for score in self.shortlist.values() if len(score) == 3],
                "candidates": self.candidate_rows(),
                "rejected": list(self.rejected),
                "turned_by_user": bool(self.wrong_turns),
                "candidate_agreement": selected_score[0] if len(selected_score) == 3 else None,
                "seconds": max(0, ceil(self.remaining(now)))}

    def glare_prompt(self):
        """A reflection found but not yet accepted: ask the user to confirm it (0.5.17)."""
        glare = self.auto_glare
        if (self.reflected_layout is not None or not glare or self.automatic or self.intensive
                or self.state not in ("waiting", "testing")):
            return None
        positions = [slot + 1 for slot in glare["positions"]]
        return {"id": ",".join(map(str, positions)), "positions": positions, "visible": glare.get("visible", "")}

    def drop_glare(self):
        """Forget a reflection candidate that contradicts the entered reading (0.5.19)."""
        self.auto_glare = None

    def confirm_glare(self):
        """The user confirmed the reflection: take the frame without waiting for three pictures."""
        glare = self.auto_glare
        if not glare:
            return False
        self.reflected_layout = glare["layout"]
        self.reflected_positions = tuple(glare["positions"])
        self.reflected_confirmations = MIN_IMAGES
        self.auto_reflection = True
        return True

    def glare_hits(self):
        """Pictures that confirmed the frame with a hidden digit so far."""
        return max(self.reflected_confirmations, (self.auto_glare or {}).get("count", 0))

    def threshold_for(self, layout):
        """Reading agreement a frame needs: lower once a glyph was found in its digit fields."""
        found = self.digit_found.get(layout)
        if found is not None and found >= DIGIT_FOUND_COARSE:
            return min(self.agreement_threshold, COARSE_AGREEMENT)
        return self.agreement_threshold

    def passes(self, layout):
        return self.shortlist.get(layout, (0,))[0] >= self.threshold_for(layout)

    def filled_fields(self, frame, layout):
        """How many digit fields of a frame show a glyph, before any OCR; None without fields (0.5.41)."""
        if not layout.digit_boxes:
            return None
        try:
            left, top, right, bottom = layout.box
            register = turn_crop(frame.crop((left, top, right, bottom)), layout.rotation)
            boxes = scale_digit_boxes(layout.digit_boxes, register.size)
            return len(boxes) - len(set(empty_digit_slots(register, boxes)))
        except (ValueError, TypeError, AttributeError):
            return None

    def mask_empty_fields(self, frame, layout, readings):
        """Digits read in a frame without any glyph become "?" (0.5.16)."""
        if not layout.digit_boxes or not readings:
            return readings
        try:
            left, top, right, bottom = layout.box
            register = turn_crop(frame.crop((left, top, right, bottom)), layout.rotation)
            boxes = scale_digit_boxes(layout.digit_boxes, register.size)
            empty = set(empty_digit_slots(register, boxes, skip=set(glare_slots(register, boxes))
                                          | set(self.marked_positions)))
        except (ValueError, TypeError, AttributeError):
            return readings
        if not empty:
            return readings
        masked = []
        for value in readings:
            slot, chars = 0, []
            for char in str(value):
                if char.isdigit() or char == "?":
                    chars.append("?" if slot in empty else char)
                    slot += 1
                else:
                    chars.append(char)
            masked.append("".join(chars))
        return masked

    def note_digit_found(self, frame, layout):
        if not layout.digit_boxes:
            return
        try:
            left, top, right, bottom = layout.box
            register = turn_crop(frame.crop((left, top, right, bottom)), layout.rotation)
            boxes = scale_digit_boxes(layout.digit_boxes, register.size)
            found = digit_presence(register, boxes, skip=glare_slots(register, boxes))
        except (ValueError, TypeError, AttributeError):
            return
        if found is not None:
            self.digit_found[layout] = max(found, self.digit_found.get(layout, 0))

    def candidate_rows(self):
        """One row per register group: best frame, hits over all images, merged near-duplicates."""
        rows, seen = [], []
        for layout, score in self.shortlist.items():
            if len(score) != 3:
                continue
            group = self.group_of(layout)
            if group is not None and any(group is other for other in seen):
                continue
            if group is not None:
                seen.append(group)
            members = group["layouts"] if group is not None else {layout}
            rows.append({"number": len(rows) + 1, "percent": score[0],
                         "reading": self.candidate_readings.get(layout, ""),
                         "rotation": layout.rotation, "box": list(layout.box),
                         "selected": self.candidate in members if self.candidate is not None else False,
                         "hits": len(group["hits"]) if group is not None else 0,
                         "merged": max(0, len(members) - 1), "found": self.digit_found.get(layout),
                         "role": "confirm" if score[0] >= self.threshold_for(layout) else "hint"})
        candidate = self.candidate
        if candidate is not None and not any(row["selected"] for row in rows):
            # The frame being confirmed is always listed, also when its score fell out of the list.
            group = self.group_of(candidate)
            rows.append({"number": len(rows) + 1, "percent": None,
                         "reading": self.candidate_readings.get(candidate, ""),
                         "rotation": candidate.rotation, "box": list(candidate.box), "selected": True,
                         "hits": len(group["hits"]) if group is not None else self.confirmations,
                         "merged": max(0, len(group["layouts"]) - 1) if group is not None else 0,
                         "found": self.digit_found.get(candidate), "role": "confirm"})
        # Registers with hits are always listed, also when their frames were
        # pushed out of the five-place shortlist by frames with a higher percentage but no hits.
        listed = [self.group_of(row_layout) for row_layout in self.shortlist] + [self.group_of(candidate)
                                                                                  if candidate is not None else None]
        for group in self.groups:
            if not group["hits"] or any(group is other for other in seen + listed if other is not None):
                continue
            layout = self.best_of_group(group["rep"])
            percent = group.get("percent") or None
            rows.append({"number": 0, "percent": percent,
                         "reading": self.candidate_readings.get(layout, group.get("reading", "")),
                         "rotation": layout.rotation, "box": list(layout.box),
                         "selected": self.candidate in group["layouts"] if self.candidate is not None else False,
                         "hits": len(group["hits"]), "merged": max(0, len(group["layouts"]) - 1),
                         "found": self.digit_found.get(layout),
                         "role": "hint" if percent is not None and percent < self.threshold_for(layout) else "confirm"})
        # 0.5.17: the frame confirmed with a hidden digit (reflection) was
        # missing from the list – it has no reading score, so it never entered the shortlist.
        glare = self.reflected_layout or (self.auto_glare or {}).get("layout")
        if glare is not None and not any(row["selected"] for row in rows):
            positions = self.reflected_positions or (self.auto_glare or {}).get("positions") or ()
            rows.append({"number": 0, "percent": None,
                         "reading": (self.auto_glare or {}).get("visible") or self.candidate_readings.get(glare, ""),
                         "rotation": glare.rotation, "box": list(glare.box), "selected": True,
                         "hits": self.glare_hits(), "merged": 0, "found": self.digit_found.get(glare),
                         "role": "confirm", "reflected": [slot + 1 for slot in positions]})
        # Registers with hits first, then by percentage; numbers follow the shown order.
        rows.sort(key=lambda row: (-(row["hits"] or 0), -(row["percent"] or 0)))
        for number, row in enumerate(rows, 1):
            row["number"] = number
        return rows

    def refine(self, layout, readings, sample, rules, read, stop, on_attempt, tested, frame_ceiling):
        on_attempt = on_attempt or (lambda *_: None)
        whole, fraction = rules["integer_digits"], rules["fraction_digits"]
        has_reference = sample.get("reference_required") is not False
        precision = self.precision(rules, has_reference)

        def score(values):
            rows = [str(value).replace(".", "").replace(",", "") for value in values]
            agreed = sum(a == b and a in "0123456789" for a, b in zip(*rows)
                         ) if all(len(row) == whole + fraction for row in rows) else 0
            prefixes = [meter_prefix(value, precision, whole) for value in values]
            complete = (agreed >= whole and all(len(str(value).replace(",", ".").partition(".")[0]) == whole
                                               for value in values)
                        and prefixes[0] is not None and prefixes[0] == prefixes[1])
            match = complete and has_reference and reference_rejection(
                sample, compare_sample(sample, values[0], precision, integer_digits=whole)[0]) is None
            expected = meter_prefix(sample.get("actual_value"), precision, whole) if has_reference else None
            aligned = (sum(a == b == c and a in "0123456789"
                           for a, b, c in zip(*rows, str(expected).zfill(whole + precision)))
                       if expected is not None and not sample.get("reference_is_fallback") else 0)
            percentage = agreement_percent(values, sample, precision, whole) if self.intensive else 0
            return bool(match), bool(complete), percentage, aligned, agreed

        def evaluate(trial):
            values = []
            try:
                for profile in OCR_PROFILES[:2]:
                    if stop():
                        return None
                    values.append(read(trial, profile))
                return score(values), trial, values
            except (OSError, ValueError, subprocess.SubprocessError):
                return None

        best = (score(readings), layout, readings)
        search_readings = readings
        if self.intensive:
            prefix = meter_prefix(sample.get("actual_value"), 2, whole) if has_reference else meter_prefix(
                readings[0], 2, whole)
            if prefix is not None and all(meter_prefix(value, 2, whole) == prefix for value in readings):
                search_readings = [two_decimal_reading(value) for value in readings]
        weak = [index + 1 for index in uncertain_slots(search_readings, whole + fraction)]
        if not 1 <= len(weak) <= 3 or best[0][-1] < min(2, whole):
            return layout, readings
        # Bound the work per image, leaving budget for independent confirmations.
        budget = min(6, max(0, min(frame_ceiling, self.attempt_limit - MIN_IMAGES) - self.attempts))
        variants = iter(refinement_layouts(layout, rules, search_readings))
        with ThreadPoolExecutor(max_workers=refinement_workers()) as pool:
            while budget and not stop():
                batch = []
                batch_size = min(budget, refinement_workers())
                for trial in variants:
                    if trial in tested or trial in self.refinement_seen:
                        continue
                    tested.add(trial)
                    self.refinement_seen.add(trial)
                    batch.append(trial)
                    if len(batch) >= batch_size:
                        break
                if not batch:
                    break
                budget -= len(batch)
                self.attempts += len(batch)
                on_attempt(self.attempts, best[1].rotation, weak)
                for result in pool.map(evaluate, batch):
                    if result and result[0] > best[0]:
                        best = result
                if best[0][0] or not has_reference and best[0][1]:
                    break
        if best[0] > self.best_score and not self.best_confirmations:
            self.best_score, self.best = best[0], best[1]
        return best[1], best[2]

    def retry_penultimate(self, layout, issue, rules, read, stop, on_attempt, accepts):
        """Try extra OCR and small changes to the second decimal digit only."""
        slot, unaffected = issue

        def retry(trial, profiles):
            values = []
            try:
                for profile in profiles:
                    if stop():
                        return None
                    values.append(read(trial, profile))
            except (OSError, ValueError, subprocess.SubprocessError):
                return None
            rows = [str(value).replace(".", "").replace(",", "") for value in values]
            if accepts(values) and all(row[:slot] + row[slot + 1:] == unaffected for row in rows):
                return trial, values
            return None

        if on_attempt is not None:
            on_attempt(self.attempts, layout.rotation, [slot + 1])
        reading = retry(layout, OCR_PROFILES[2:4])
        if reading:
            return reading

        def variants():
            known = self.known_good_layout or (self.previous_layout if self.followup else None)
            if (known and known.box == layout.box and known.rotation == layout.rotation
                    and known.width == layout.width and known.digit_boxes and layout.digit_boxes):
                boxes = list(layout.digit_boxes)
                boxes[slot] = known.digit_boxes[slot]
                try:
                    count = rules["integer_digits"] + rules["fraction_digits"]
                    valid = digit_box_settings(boxes, count)
                    yield replace(layout, digit_boxes=tuple(map(tuple, valid)), method="refined")
                except ValueError:
                    pass
            masked = unaffected[:slot] + "?" + unaffected[slot:]
            yield from refinement_layouts(layout, rules, [masked, masked])

        attempts = 0
        for trial in variants():
            if stop() or attempts >= 4:
                break
            if trial == layout or trial in self.refinement_seen:
                continue
            self.refinement_seen.add(trial)
            attempts += 1
            reading = retry(trial, OCR_PROFILES[:2])
            if reading:
                return reading
        return None

    def retry_digit_slots(self, layout, readings, rules, weak, read_slot, stop,
                          on_attempt, frame_ceiling, expected=None, *, fine_first=False, keep_frames=()):
        """Retry only the designated cells and preserve all other readings.

        A digit read from a nudged frame counts for this image; the frame itself is only adopted
        for slots outside ``keep_frames``. A roller that is turning shows the next digit in a
        moved frame: adopting that frame saved a displaced last frame with the setup (0.5.0).
        """
        whole = rules["integer_digits"]
        rows = [list(str(value).replace(".", "").replace(",", "")) for value in readings]

        def read_pair(trial, index, profiles):
            values = []
            try:
                for profile in profiles:
                    if stop():
                        return None
                    values.append(read_slot(trial, index, profile))
            except (OSError, ValueError, subprocess.SubprocessError):
                return None
            digit = values[0]
            if digit and len(digit) == 1 and digit in "0123456789" and digit == values[1]:
                if expected is None or digit == expected[index]:
                    return digit
            return None

        if on_attempt is not None:
            on_attempt(self.attempts, layout.rotation, [index + 1 for index in weak])
        adjusted = layout
        for index in weak:
            digit = read_pair(adjusted, index, OCR_PROFILES[2:4])
            if digit is None and adjusted.digit_boxes:
                left, top, right, bottom = adjusted.digit_boxes[index]
                tried = {adjusted.digit_boxes[index]}
                x_step = max(1, (right - left) // 8)
                y_step = max(1, (bottom - top) // 12)
                shifts = [(-x_step, 0), (x_step, 0), (0, -y_step), (0, y_step)]
                if fine_first:
                    x_fine, y_fine = max(1, x_step // 3), max(1, y_step // 2)
                    shifts[:0] = [(-x_fine, 0), (x_fine, 0), (0, -y_fine), (0, y_fine)]
                for dx, dy in shifts:
                    if stop() or self.attempts >= min(frame_ceiling, self.attempt_limit - 1):
                        break
                    dx = max(-left, min(dx, 1000 - right))
                    dy = max(-top, min(dy, 1000 - bottom))
                    moved = (left + dx, top + dy, right + dx, bottom + dy)
                    if moved in tried:
                        continue
                    tried.add(moved)
                    boxes = list(adjusted.digit_boxes)
                    boxes[index] = moved
                    try:
                        digit_box_settings(boxes, len(boxes))
                    except ValueError:
                        continue
                    trial = replace(adjusted, digit_boxes=tuple(boxes), method="refined")
                    self.attempts += 1
                    digit = read_pair(trial, index, OCR_PROFILES[:2])
                    if digit is not None:
                        if index not in keep_frames:
                            adjusted = trial
                        break
            if digit is None:
                return None
            for row in rows:
                row[index] = digit
        return adjusted, ["".join(row[:whole]) + ("." + "".join(row[whole:]) if len(row) > whole else "")
                          for row in rows]

    def probe_optional_last_slot(self, layout, rules, read_slot, stop, on_attempt=None):
        """Try a preview-only reading after the two-decimal verification succeeds."""
        if not self.simplified or rules["fraction_digits"] != 3:
            return None
        whole = rules["integer_digits"]
        reading = self.reference_reading
        if (meter_prefix(reading, 2, whole) is None or not isinstance(reading, str)
                or not reading.endswith("?")):
            return None
        return self.retry_digit_slots(
            layout, [reading, reading], rules, [whole + 2], read_slot, stop,
            on_attempt, self.attempts + 4, fine_first=True,
        )

    def probe_open_digit(self, layout, sample, rules, read, stop, on_attempt):
        """Try the last slot on this image without adding an independent hit."""
        digits = rules["integer_digits"]
        has_reference = sample.get("reference_required") is not False

        def matches(values):
            prefixes = [meter_prefix(value, 3, digits) for value in values]
            return prefixes[0] is not None and prefixes[0] == prefixes[1] and (
                not has_reference or all(reference_rejection(
                    sample, compare_sample(sample, value, 3, integer_digits=digits)[0]) is None
                    for value in values))

        readings = []
        try:
            for profile in OCR_PROFILES[:2]:
                if stop():
                    return None
                readings.append(read(layout, profile))
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
        prefix = meter_prefix(readings[0], 2, digits)
        if prefix is None or prefix != meter_prefix(readings[1], 2, digits):
            return None
        if has_reference and prefix != meter_prefix(sample.get("actual_value"), 2, digits):
            return None
        if matches(readings):
            return layout
        trial, readings = self.refine(layout, readings, sample, rules, read, stop, on_attempt,
                                      {layout}, self.attempt_limit)
        return trial if matches(readings) else None

    def remember_image(self, frame, stamp):
        digest = sha256(frame.convert("RGB").tobytes()).digest()
        if stamp <= self.last_stamp or digest in self.seen:
            return False
        self.seen.add(digest)
        self.last_stamp = stamp
        return True

    def retain_fine_evidence(self, score, accepted, preview, images):
        """Keep the highest scoring usable preview, preferring accepted hits on ties."""
        rank = (score, accepted)
        if score and (self.fine_evidence is None or rank > self.fine_evidence[0]):
            self.fine_evidence = rank, {**preview, "best_fine_score": score}, images

    def search_exhausted(self):
        confirming = self.intensive and (self.confirmations or self.verification_pending)
        return self.attempts >= self.attempt_limit and not confirming

    def begin_setup_last_digit(self, layout):
        self.setup_last_digit = self.intensive = True
        self.simplified = self.rank_candidates = False
        self.candidate = self.previous_layout = layout
        self.confirmations = self.best_confirmations = self.full_hits = 0
        self.best = None
        self.counter = {}
        self.reference_reading = None
        self.reference_image_id = None
        self.confirmed_quality = []
        self.verification_pending = False
        self.verification_deadline = None
        self.limit = min(MAX_IMAGES, max(self.limit, len(self.seen) + MIN_IMAGES + 1))
        self.stage = "last_digit"

    def check_last_digit(self, frame, sample, stamp, layout, digits, read, stop, on_image, on_decision,
                         roll_center=None):
        if self.search_exhausted() or not self.remember_image(frame, stamp):
            return None
        on_image()
        expected = None
        if sample.get("reference_required") is not False:
            value = sample.get("actual_value")
            status, _ = compare_sample(sample, value, 3, integer_digits=digits)
            target = meter_prefix(value, 3, digits)
            if target is None or reference_rejection(sample, status):
                on_decision("reference_unavailable")
                return None
            expected = str(target % 10)
        candidates = last_digit_candidates(layout, roll_center) if not self.verification_pending else [layout]
        for trial in candidates:
            if stop() or self.search_exhausted():
                return None
            if not self.confirmations:
                self.attempts += 1
            first = read(trial, OCR_PROFILES[0])
            if stop() or first not in tuple("0123456789") or (expected is not None and first != expected):
                continue
            if read(trial, OCR_PROFILES[1]) != first:
                continue
            if self.verification_pending:
                on_decision("verified")
                return trial
            self.confirmations = self.confirmations + 1 if trial == self.candidate else 1
            self.candidate = trial
            if self.confirmations > self.best_confirmations:
                self.best, self.best_confirmations = trial, self.confirmations
            on_decision("accepted")
            return trial if self.confirmations >= MIN_IMAGES else None
        on_decision("unclear")
        return None

    def verify(self, frame, sample, stamp, rules, read, stop, on_image=None, on_decision=lambda reason: None):
        """Confirm the exact saved geometry with the regular OCR retry routine."""
        if self.search_exhausted() or not self.remember_image(frame, stamp):
            return None
        if on_image is not None:
            on_image()
        if self.confirmed_quality and crop_quality(frame, self.candidate) < (
                MIN_VERIFICATION_QUALITY * median(self.confirmed_quality)):
            on_decision("soft_image")
            return None
        if not self.intensive:
            self.attempts += 1
        has_reference = sample.get("reference_required") is not False
        precision = self.precision(rules, has_reference)
        digits = rules["integer_digits"]
        rejection = "unreadable"
        try:
            value, confirmed, _ = read_with_retries(
                lambda profile: read(self.candidate, profile), sample, precision,
                max_attempts=max(2, rules["attempts"]), standalone=not has_reference,
                integer_digits=digits, stop_before_attempt=stop,
            )
            status, _ = compare_sample(sample, value, precision, ocr_confirmed=confirmed, integer_digits=digits)
            rejection = (reference_rejection(sample, status) if has_reference and status != "ocr_unclear"
                         else None if status == "ocr_only" else "unclear")
            if rejection:
                raise ValueError("Unconfirmed crop")
            rejection = "implausible"
            self.counter = accumulate_consumption(
                self.counter, "calibration", stamp, value, precision, rules["max_flow_lph"], digits)
            self.reference_reading = value
        except (OSError, ValueError, subprocess.SubprocessError):
            on_decision(rejection)
            return None
        on_decision("verified")
        return self.candidate

    def record_intermediate(self, layout, readings, sample, precision, digits, fraction, frame):
        required_agreement = agreement_percent(readings, sample, precision, digits)
        readable_agreement = agreement_percent(readings, {"reference_required": False}, fraction, digits)
        percentage = min(required_agreement, readable_agreement)
        self.note_digit_found(frame, layout)
        prefixes = agreeing_prefixes(readings[:2], precision, digits)
        group = self.note_group(layout, readings, prefixes is not None, digits + fraction)
        if group is not None:
            group["percent"] = max(group.get("percent", 0), percentage)
        if required_agreement:
            score = (percentage, round(crop_quality(frame, layout), 2), required_agreement)
            # A frame that read better on an earlier image must keep that score;
            # a later, worse image of the same frame no longer pushes it down (e.g. to 75 %).
            previous = self.shortlist.get(layout)
            if previous is not None and self.score_stamps.get(layout) != self.current_stamp:
                score = max(score, previous)
            self.score_stamps[layout] = self.current_stamp
            self.shortlist[layout] = score
            ranked = sorted(self.shortlist.items(), key=lambda pair: pair[1], reverse=True)
            # Keep every register group with hits in the list (a −13° frame with
            # seven hits was pushed out by near-duplicates); near-duplicates only fill free places.
            first, rest, seen = [], [], []
            for item in ranked:
                group = self.group_of(item[0])
                if group is not None and not any(group is other for other in seen):
                    seen.append(group)
                    first.append(item)
                else:
                    rest.append(item)
            first.sort(key=lambda item: (bool((self.group_of(item[0]) or {}).get("hits")), item[1]), reverse=True)
            kept = (first + rest)[:SHORTLIST_LIMIT]
            self.shortlist = dict(sorted(kept, key=lambda pair: pair[1], reverse=True))
            rows = [str(value).replace(",", ".") for value in readings]
            exemplar = max(rows, key=lambda value: sum(digit.isdigit() for digit in value))
            self.candidate_readings[layout] = exemplar if all(row == exemplar for row in rows) else "".join(
                digit if all(len(row) > index and row[index] == digit for row in rows) else "?"
                for index, digit in enumerate(exemplar)
            )
            self.candidate_readings = {item: self.candidate_readings[item] for item in self.shortlist
                                       if item in self.candidate_readings}


    def region_rejected(self, layout):
        return (self.confirmations < 2 and not self.followup
                and any(same_digit_region(layout.box, old) for old in self.rejected_regions))

    def reject_region(self, layout):
        if self.confirmations < 2 and not self.followup:
            self.rejected_regions = [*self.rejected_regions[-15:], layout.box]

    def examine(self, frame, overlay, sample, stamp, rules, read, stop, baseline=None, on_attempt=None,
                on_image=None, on_decision=lambda reason: None, refine_read=None, on_refine=None, on_regions=None,
                on_selected=None, angle_read=None, on_angle=None, on_shortlist=None,
                read_slot=None, orientation_score=None):
        """Return a verified layout, checking two OCR profiles per distinct image."""
        if not self.remember_image(frame, stamp):
            return None
        if on_image is not None:
            on_image()
        self.current_stamp = stamp
        has_reference = sample.get("reference_required") is not False
        # Without an outside reference, read every displayed digit to check movement.
        precision = self.precision(rules, has_reference)
        digits = rules["integer_digits"]
        flow = rules["max_flow_lph"]
        reference_pending = (self.simplified and not self.automatic and has_reference
                             and (reference_rejection(sample, "match") is not None
                                  or meter_prefix(sample.get("actual_value"), precision, digits) is None
                                  or meter_prefix(sample.get("raw_value"), precision, digits) is None))
        if reference_pending:
            has_reference = False
        required_slots = digits + precision
        slots = digits + rules["fraction_digits"]
        reference = meter_prefix(sample.get("actual_value"), precision, digits) if has_reference else None
        reference_digits = str(reference).zfill(required_slots) if reference is not None else None

        def required_rows(values):
            return [str(value).replace(".", "").replace(",", "")[:required_slots] for value in values]

        def local_adjustment_slots(values):
            if read_slot is None:
                return []
            rows = required_rows(values)
            weak = uncertain_slots(rows, required_slots)
            if not 1 <= len(weak) <= 2 or required_slots - len(weak) < 3:
                return []
            if reference_digits is not None and any(
                row[index] != digit for row in rows for index, digit in enumerate(reference_digits)
                if index not in weak
            ):
                return []
            return weak

        confirming_followup = self.followup and self.confirmations > 0
        committed = self.confirmations >= 2 or confirming_followup
        partial_only = self.simplified and not self.confirmations and self.partial_hits > 0
        preferred = ((self.confirmations == 1 or partial_only) and self.candidate is not None
                     and self.rank_candidates and (self.full_hits > 0 or self.simplified))
        collecting = self.rank_candidates and not (committed or preferred or self.optimizing
                                                    or self.full_hits >= MIN_IMAGES)
        if committed or preferred or self.focused:
            candidates = (self.candidate,)
        elif self.followup:
            candidates = (self.candidate or self.previous_layout,)
        elif self.rank_candidates and self.optimizing and self.shortlist:
            candidates = tuple(self.distinct_shortlist())
        else:
            seed = self.candidate or (next(iter(self.shortlist), None) if collecting else self.previous_layout)
            skew = None if self.region else self.measured_skew(frame)

            def detect(offset, current, report_regions=None):
                return (guided_layouts(frame, overlay, rules, offset, current, self.region)
                        if self.region else layouts(
                            frame, overlay, rules, offset, current,
                            prefer_configured=self.automatic or self.intensive, on_regions=report_regions,
                            skew=skew))

            def search_candidates():
                known = self.known_good_layout
                if known is not None and not self.confirmations:
                    # A confirmed frame is always tried first, even outside a chosen search region:
                    # a mistaken tap on a region proposal must never replace a working setup.
                    a, b, c, d = known.box
                    if 0 <= a < c <= frame.width and 0 <= b < d <= frame.height:
                        yield self.oriented(known, slots)
                found = [self.oriented(layout, slots) for layout in detect(len(self.seen) - 1, seed, on_regions)]
                kept = skip_small_labels(found)
                for layout in found:
                    if layout not in kept:
                        self.note_rejection(layout, "small_label")
                yield from self.prefilter(kept)
                # 0.5.22: a meter already set up sideways or upside down may also be searched at right
                # angles by the automatic repair; it is the only way to widen a frame that cuts off the
                # decimals of a counter hanging a few degrees askew.
                sideways_setup = "crop" in rules and abs(rules.get("rotation") or 0) >= 45
                # 0.5.23: labels and the serial number read as scattered digits ("?11?5.11?"), so only
                # mostly read whole digits of an upright frame show that the picture is upright. For a
                # meter already set up turned, an upright read never does; only a reliable one counts.
                upright_seen = not sideways_setup and any(
                    meter_like(readings, max(4, digits + rules["fraction_digits"] - 3))
                    and whole_like(readings, digits)
                    for _, tried, readings in coarse if upright_layout(tried))
                if (len(self.seen) == 1 and not self.intensive and (not self.automatic or sideways_setup)
                        and self.size_reference() is None
                        and not stop() and not any(reliable(score) for score, _, _ in coarse)
                        and (has_reference or not upright_seen)):
                    # Search the complete photo at right angles before asking for another image.
                    yield from (self.oriented(layout, slots)
                                for layout in quarter_turn_layouts(frame, rules, self.region))

            candidates = search_candidates()
        examined = False
        tested = set()
        self.presort_seen = []
        frame_ceiling = self.attempts + FRAME_ATTEMPT_LIMIT
        coarse = []
        perfect = None
        def score_layout(layout, readings):
            prefixes = [meter_prefix(value, precision, digits) for value in readings]
            agreement = prefixes[0] is not None and prefixes[0] == prefixes[1]
            reference_match = has_reference and agreement and all(reference_rejection(
                sample, compare_sample(sample, value, precision, integer_digits=digits)[0]) is None
                for value in readings)
            l, t, r, b = layout.box
            return (reference_match, self.confirmations > 0 and (same_register if self.simplified else similar_layout)(
                        layout, self.candidate),
                    (r - l) * (b - t), layout.method == "register_window", agreement)

        def reliable(score):
            return score[0] if has_reference else score[4]

        def fits_baseline(value):
            """A fresh frame's reading fits the last known reading at the setup flow (0.5.29)."""
            if not baseline or self.confirmations:
                return True
            try:
                accumulate_consumption(baseline, "calibration", stamp, value, precision, setup_flow_limit(rules),
                                       digits)
            except ValueError:
                return False
            return True

        for index, layout in enumerate(candidates, start=1):
            if stop():
                return None
            if not confirming_followup and self.attempts >= min(self.attempt_limit, frame_ceiling):
                break
            left, top, right, bottom = layout.box
            if self.region_rejected(layout) or not (
                    0 <= left < right <= frame.width and 0 <= top < bottom <= frame.height):
                continue
            if collecting and self.coarse_attempts >= COARSE_LIMIT:
                break
            if layout in tested:
                continue
            tested.add(layout)
            examined = True
            if self.presort_shadow:
                self.presort_seen.append((layout, self.filled_fields(frame, layout)))
            if not confirming_followup:
                self.attempts += 1
            if collecting:
                self.coarse_attempts += 1
            if on_attempt is not None:
                on_attempt(index, layout.rotation)
            try:
                readings = [read(layout, OCR_PROFILES[0])]
                if stop():
                    return None
                if (sum(char.isdigit() for char in str(readings[0])) < min(HOPELESS_DIGITS, digits)
                        and layout not in (self.known_good_layout, self.candidate, self.previous_layout)):
                    # Serial number, small print or empty area: a second profile cannot make it a
                    # meter reading and costs several seconds on a slow machine (0.4.0).
                    readings.append("".join("?" if char.isdigit() else char for char in str(readings[0])))
                else:
                    readings.append(read(layout, OCR_PROFILES[1]))
            except (OSError, ValueError, subprocess.SubprocessError):
                on_decision("unreadable")
                continue
            readings = self.mask_empty_fields(frame, layout, readings)
            score = score_layout(layout, readings)
            coarse.append((score, layout, readings))
            # A plain setup reads two decimals: there the row is complete without the third one.
            # Before 0.5.0 the missing third decimal kept every image from this shortcut, and
            # each image paid for all other candidates and a full angle comparison.
            # Only for the meter window found by its row of bright digits: a small label that
            # happens to read completely must not win against the larger display.
            short = precision == 2 and layout.method == "register_window"
            shown = precision if short else rules["fraction_digits"]
            if (self.rank_candidates and reliable(score)
                    and agreement_percent(readings, sample, shown, digits) == 100
                    and not uncertain_slots(required_rows(readings) if short else readings,
                                            digits + shown)
                    and fits_baseline(readings[0])):
                # 0.5.29: only a frame that also fits the last reading ends the search; a frame
                # turned by 180° read a clean but wrong value and the right frame was never read.
                perfect = layout
                break
            if reliable(score) and layout in (self.known_good_layout, self.candidate):
                break

        if (not self.confirmations and not (committed or preferred or self.followup or self.intensive)
                and not any(reliable(score) for score, _, _ in coarse) and not stop()):
            # 0.5.31: a meter hanging sideways was found upside down on the first picture and only
            # that direction stayed in the list; it never read clearly, and its turned twin was
            # never read again. While nothing reads reliably, the best sideways frames are also
            # read turned by 180° on this picture, so the right direction can enter the list.
            sideways = sorted((item for item in coarse if abs(item[1].rotation) >= 45),
                              key=lambda item: digit_count(item[2]), reverse=True)[:SIDEWAYS_TWINS]
            for _, layout, _ in sideways:
                twin = half_turn_layout(layout, slots)
                left, top, right, bottom = twin.box
                if (twin in tested or self.turned_wrong(twin) or self.region_rejected(twin)
                        or not (0 <= left < right <= frame.width and 0 <= top < bottom <= frame.height)
                        or self.attempts >= min(self.attempt_limit, frame_ceiling) or stop()):
                    continue
                tested.add(twin)
                self.attempts += 1
                if on_attempt is not None:
                    on_attempt(len(tested), twin.rotation)
                try:
                    values = [read(twin, OCR_PROFILES[0]), read(twin, OCR_PROFILES[1])]
                except (OSError, ValueError, subprocess.SubprocessError):
                    continue
                values = self.mask_empty_fields(frame, twin, values)
                coarse.append((score_layout(twin, values), twin, values))

        if self.reflected_layout is not None and not any(reliable(score) for score, _, _ in coarse):
            for _, layout, readings in coarse:
                if layout != self.reflected_layout:
                    continue
                rows = required_rows(readings)
                weak = uncertain_slots(rows, required_slots)
                visible = set(range(required_slots)) - set(weak)
                if (weak and set(weak) <= set(self.reflected_positions) and len(visible) >= 3
                        and (reference_digits is None or all(
                            rows[0][index] == reference_digits[index] for index in visible))):
                    self.reflected_confirmations += 1
                    if on_selected is not None:
                        on_selected(layout, readings)
                    on_decision("reflected_geometry")
                    return None
            self.reflected_confirmations = 0

        if (self.reflected_layout is None and self.simplified and not self.automatic and not self.intensive
                and not any(reliable(score) for score, _, _ in coarse)):
            if self.note_auto_glare(frame, coarse, required_rows, required_slots, digits, reference_digits,
                                    on_selected):
                on_decision("reflected_geometry")
                return None

        def ranked_crop(item):
            score, layout, readings = item
            return (reliable(score), score[1], score[3], score[2],
                    agreement_percent(readings, sample, precision, digits))

        if self.rank_candidates and perfect is None and not any(reliable(score) for score, _, _ in coarse):
            close_crops = [item for item in coarse if local_adjustment_slots(item[2])]
            if close_crops:
                coarse = [max(close_crops, key=ranked_crop)]
        targeted = len(coarse) == 1 and bool(local_adjustment_slots(coarse[0][2]))

        stress_reads = {}
        best_index = max(range(len(coarse)), key=lambda position: ranked_crop(coarse[position])) if coarse else None
        zero_readable = (best_index is not None and coarse[best_index][1].rotation == 0
                         and reliable(coarse[best_index][0])
                         and coarse[best_index][1] not in self.angle_compared)
        if (coarse and self.rank_candidates and angle_read is not None
                and meter_like(coarse[best_index][2], min(HOPELESS_DIGITS, digits))
                and (zero_readable or (
                    not targeted and perfect is None and not self.confirmations
                    and not any(layout == self.known_good_layout and reliable(score)
                                for score, layout, _ in coarse)))):
            # A seven-digit setup hit still needs the same angle comparison as a complete row.
            index = best_index
            score, layout, readings = coarse[index]
            ceiling = frame_ceiling
            if collecting:
                ceiling = min(ceiling, self.attempts + COARSE_LIMIT - self.coarse_attempts)
            previous_attempts = self.attempts
            if zero_readable:
                trial, values, complete = self.compare_setup_angles(
                    layout, readings, sample, rules, angle_read, stop, on_angle, tested, ceiling, stress_reads,
                )
                if not complete:
                    return None
            else:
                trial, values = self.sweep_angles(
                    layout, readings, sample, rules, angle_read, stop, on_angle, tested, ceiling,
                    accept_first=not reliable(score),
                )
            if layout == perfect:
                perfect = trial
            if collecting:
                self.coarse_attempts += self.attempts - previous_attempts
            values = self.mask_empty_fields(frame, trial, values)
            coarse[index] = score_layout(trial, values), trial, values
            if self.attempts > previous_attempts and on_selected is not None and not stop():
                on_selected(trial, values)

        additional_readings = {}
        if self.rank_candidates and not (committed or preferred):
            for _, layout, readings in coarse:
                self.record_intermediate(layout, readings, sample, precision, digits, rules["fraction_digits"], frame)
            coarse.sort(key=lambda item: self.shortlist.get(item[1], (0, 0)), reverse=True)
            self.agreement_threshold = rules.get("intensive_agreement", DEFAULT_INTENSIVE_AGREEMENT)
            found_percent = max((self.shortlist.get(layout, (0,))[0] for _, layout, _ in coarse), default=0)
            passing = [layout for _, layout, _ in coarse if self.passes(layout)]
            if passing:
                self.row_found = max(self.row_found, max(self.shortlist[layout][0] for layout in passing))
            run_threshold = min((self.threshold_for(layout) for layout in passing), default=self.agreement_threshold)
            stable = [item for item in coarse if item[0][4]]
            if collecting:
                found = any(reliable(score) for score, _, _ in coarse)
                threshold = rules.get("intensive_agreement", DEFAULT_INTENSIVE_AGREEMENT)
                almost_complete = round(100 * (required_slots - 1) / required_slots)

                def promising_candidate(layout, values):
                    score = self.shortlist.get(layout, (0, 0, 0))
                    if score[0] >= min(threshold, self.threshold_for(layout)):
                        return True
                    if required_slots < 2 or score[-1] < almost_complete:
                        return False
                    return len(uncertain_slots(required_rows(values), required_slots)) == 1

                promising = targeted or any(promising_candidate(layout, values) for _, layout, values in coarse)
                self.optimizing = self.coarse_attempts >= COARSE_LIMIT or found or promising
                if self.coarse_attempts >= COARSE_LIMIT and not (found or self.simplified and promising):
                    # Re-read the full ranked list against the next image and its reference.
                    return None
            # Read stable crops immediately, including when this image has no usable reference.
            intensive = ([item for item in coarse if item[1] == perfect] if perfect is not None
                         else coarse if self.optimizing else stable)
            intensive = worth_intensive(intensive, self.shortlist, found_percent, run_threshold)
            for index, (score, layout, readings) in enumerate(intensive[:SHORTLIST_LIMIT], start=1):
                if stop() or self.attempts >= min(self.attempt_limit, frame_ceiling):
                    return None
                self.attempts += 1
                if on_shortlist is not None:
                    on_shortlist(index, layout.rotation)
                extras = stress_reads.get(layout, [])
                profile_end = 5 if layout == perfect or (score[4] and not reliable(score)) else 3
                profiles = () if layout in stress_reads else OCR_PROFILES[2:profile_end]
                for profile in profiles:
                    if stop():
                        break
                    try:
                        extras.append(read(layout, profile))
                    except (OSError, ValueError, subprocess.SubprocessError):
                        continue
                if extras:
                    all_readings = [*readings, *extras]
                    if self.simplified and not score[4]:
                        readable = [value for value in all_readings
                                    if meter_prefix(value, precision, digits) is not None]
                        prefixes = {meter_prefix(value, precision, digits) for value in readable}
                        if len(readable) >= 2 and len(prefixes) == 1:
                            additional_readings[layout] = readable[:2]
                    self.record_intermediate(layout, all_readings, sample, precision, digits,
                                             rules["fraction_digits"], frame)
                    if layout == perfect:
                        self.stress_weak_slots = [index + 1 for index in uncertain_slots(
                            all_readings, digits + rules["fraction_digits"])]
            if additional_readings:
                self.optimizing = True
            if not self.optimizing:
                reason = "collecting"
                if stable and has_reference:
                    status, _ = compare_sample(sample, stable[0][2][0], precision, integer_digits=digits)
                    reason = reference_rejection(sample, status) or reason
                on_decision(reason)
                return None
            coarse.sort(key=lambda item: (item[1] == perfect, ranked_crop(item),
                                         self.shortlist.get(item[1], (0, 0))), reverse=True)
        else:
            coarse.sort(key=lambda item: item[0], reverse=True)
        refined = False
        threshold = self.agreement_threshold
        confirmable = self.rank_candidates and not (committed or preferred) and any(
            self.passes(item[1]) for item in coarse)
        for score, layout, readings in coarse:
            readings = additional_readings.get(layout, readings)
            if stop():
                return None
            if self.region_rejected(layout):
                continue
            if (confirmable and layout != self.candidate and not reliable(score)
                    and not self.passes(layout)):
                # Only a search aid: its angle and place already steer the fine search.
                continue
            if (not self.rank_candidates and not score[0] and not self.confirmations
                    and coarse[0][0][2] > 2.5 * score[2]):
                continue
            if on_selected is not None:
                on_selected(layout, readings)
            rejection = "unreadable"
            same = continuing = False
            try:
                if has_reference and contradicts_reference(readings, sample, digits):
                    self.reject_region(layout)
                    on_decision("position_error" if position_error(readings[0], sample, precision, digits)
                                else "reference_mismatch")
                    continue
                if has_reference and readings[0] == readings[1]:
                    status = compare_sample(sample, readings[0], precision, integer_digits=digits)[0]
                    expected = meter_prefix(sample.get("actual_value"), precision, digits)
                    prefix = meter_prefix(readings[0], precision, digits)
                    if (reference_rejection(sample, status) == "reference_mismatch"
                            and expected is not None and prefix is not None
                            and sum(a == b for a, b in zip(str(expected).zfill(digits + precision),
                                                         str(prefix).zfill(digits + precision))) < digits / 2):
                        self.reject_region(layout)
                        on_decision("position_error" if position_error(readings[0], sample, precision, digits)
                                    else "reference_mismatch")
                        continue
                first_prefix, second_prefix = (meter_prefix(value, precision, digits) for value in readings)
                agreement = first_prefix is not None and first_prefix == second_prefix
                matches = agreement and (not has_reference or all(reference_rejection(
                    sample, compare_sample(sample, value, precision, integer_digits=digits)[0]) is None
                    for value in readings))
                recovered_slot = False
                if not matches:
                    weak = local_adjustment_slots(readings)
                    if weak:
                        recovery = self.retry_digit_slots(
                            layout, readings, rules, weak, read_slot, stop, on_refine,
                            frame_ceiling, reference_digits, fine_first=True,
                            keep_frames=(required_slots - 1,) if self.simplified else (),
                        )
                        if recovery is None and angle_read is not None and not stop():
                            angle_sample = sample if has_reference else {**sample, "reference_required": False}
                            trial, values = self.sweep_angles(
                                layout, readings, angle_sample, rules, angle_read, stop, on_angle,
                                tested, frame_ceiling, accept_first=True, offsets=(-1, 1),
                            )
                            if trial != layout and reliable(score_layout(trial, values)):
                                recovery = trial, values
                        if recovery is None:
                            partial = (self.simplified and not (self.automatic or self.intensive or self.followup)
                                       and precision == 2 and weak == [required_slots - 1])
                            if (partial and self.candidate is None and self.gives_way(
                                    frame, layout, readings[0], coarse, tested, baseline, precision, digits,
                                    rules, read, stop, score_layout, orientation_score, sample, precision)):
                                # 0.5.35: the first partial hit made a frame the candidate without
                                # checking its direction; a frame upside down could collect it.
                                on_decision("implausible")
                                continue
                            if partial and self.partial_hit(layout, required_rows(readings), stamp, flow,
                                                            baseline, setup_flow_limit(rules)):
                                self.note_group(layout, readings, True, digits + rules["fraction_digits"])
                                if on_selected is not None:
                                    on_selected(layout, readings)
                                on_decision("accepted_partial")
                                return None
                            on_decision("unclear")
                            continue
                        layout, readings = recovery
                        recovered_slot = matches = True
                        if on_selected is not None:
                            on_selected(layout, readings)
                if (refine_read is not None and self.intensive and precision == 3
                        and self.confirmations >= 2 and not matches):
                    issue = penultimate_issue(readings, sample, digits)
                    if issue is not None:
                        recovery = self.retry_penultimate(
                            layout, issue, rules, refine_read, stop, on_refine,
                            lambda values: reliable(score_layout(layout, values)),
                        )
                        if not recovery:
                            on_decision("penultimate_unclear")
                            continue
                        layout, readings = recovery
                        recovered_slot = True
                        if on_selected is not None:
                            on_selected(layout, readings)
                if (refine_read is not None and (not refined or self.rank_candidates) and not matches
                        and not self.confirmations and not self.focused):
                    refined = True
                    original = layout
                    if angle_read is not None and not (self.followup or self.rank_candidates):
                        layout, readings = self.sweep_angles(layout, readings, sample, rules, angle_read, stop,
                                                             on_angle, tested, frame_ceiling)
                    resolved = [meter_prefix(value, precision, digits) for value in readings]
                    if (resolved[0] is None or resolved[0] != resolved[1] or
                            has_reference and any(reference_rejection(sample, compare_sample(
                                sample, value, precision, integer_digits=digits)[0]) for value in readings)):
                        layout, readings = self.refine(layout, readings, sample, rules, refine_read, stop, on_refine,
                                                       tested, frame_ceiling)
                    if (layout != original or angle_read is not None) and not stop() and on_selected is not None:
                        on_selected(layout, readings)
                if stop():
                    return None
                prefixes = [meter_prefix(value, precision, digits) for value in readings]
                image_precision = precision
                if None in prefixes:
                    on_decision("unclear")
                    continue
                if prefixes[0] != prefixes[1]:
                    on_decision("disagree")
                    continue
                if has_reference:
                    status, _ = compare_sample(sample, readings[0], image_precision, integer_digits=digits)
                    reason = reference_rejection(sample, status)
                    if reason == "reference_mismatch" and position_error(readings[0], sample, image_precision,
                                                                         digits):
                        self.reject_region(layout)
                        on_decision("position_error")
                        continue
                    if reason and not (self.focused or self.intensive or committed or self.rank_candidates):
                        # Keep a candidate with two agreeing OCR profiles as
                        # the preferred geometry. The reference may be stale
                        # or the meter may simply not have advanced yet.
                        self.candidate = layout
                        self.focused = True
                        on_decision(reason)
                        return None
                    if reason:
                        if reason == "reference_mismatch":
                            self.reject_region(layout)
                        on_decision(reason)
                        continue
                if (self.rank_candidates and angle_read is not None and layout.rotation == 0
                        and layout not in self.angle_compared):
                    original = layout
                    layout, readings, complete = self.compare_setup_angles(
                        layout, readings, sample, rules, angle_read, stop, on_angle,
                        tested, frame_ceiling, stress_reads,
                    )
                    if not complete:
                        return None
                    if original == perfect:
                        perfect = layout
                    if on_selected is not None:
                        on_selected(layout, readings)
                rejection = "implausible"
                # Plain setup: a fine-tuned frame of the same register keeps its hits. The
                # last-digit and follow-up checks keep the strict rule for their verified boxes.
                same = (same_register(layout, self.candidate)
                        if self.simplified and not (self.intensive or self.followup)
                        else similar_layout(layout, self.candidate))
                if same and layout != self.candidate and similar_layout(layout, self.candidate):
                    # Keep the first frame of this digit row; the small differences are noise.
                    # A fine-tuned frame of the same register is kept as it is: it produced
                    # the readings of this image.
                    layout = self.candidate
                # 0.5.29: a fine-tuned frame continues the counted series only when it is the same
                # register (plain setup) or the last-digit and follow-up checks refine their
                # verified box. Any other fine-tuned frame is checked against the last reading:
                # before, one was checked against nothing (no series yet) or against the series of
                # another frame, so the right frame turned by 180° counted as "lower reading".
                plain = self.simplified and not (self.intensive or self.followup)
                continuing = same or (recovered_slot and bool(self.counter) and not plain)
                if not continuing and self.gives_way(
                        frame, layout, readings[0], coarse, tested, baseline, image_precision, digits, rules,
                        read, stop, score_layout, orientation_score, sample, precision):
                    on_decision("implausible")
                    continue
                if stop():
                    return None
                anchor = self.counter if continuing else baseline or {}
                counter = accumulate_consumption(anchor, "calibration", stamp, readings[0], image_precision,
                                                flow if continuing else setup_flow_limit(rules), digits)
            except (OSError, ValueError, subprocess.SubprocessError):
                if rejection == "implausible" and baseline and not continuing:
                    self.note_rejection(layout, "implausible", readings[0])
                on_decision(rejection)
                continue
            if self.rank_candidates and (committed or preferred
                                         or all(layout != tested_layout for _, tested_layout, _ in coarse)):
                self.record_intermediate(layout, readings, sample, precision, digits, rules["fraction_digits"], frame)
            if not same:
                self.full_hits = 0
                self.partial_hits, self.partial_prefix = 0, None
                if layout != perfect:
                    self.stress_weak_slots = []
            digits_read = digits + rules["fraction_digits"]
            if (self.rank_candidates
                    and agreement_percent(readings, sample, rules["fraction_digits"], digits) == 100
                    and not uncertain_slots(readings, digits_read)):
                self.full_hits += 1
                if self.full_hits == MIN_IMAGES:
                    self.optimizing = True
                if self.full_hits == MIN_IMAGES and self.attempts + 1 < self.attempt_limit and not stop():
                    if on_shortlist is not None:
                        on_shortlist(1, layout.rotation)
                    self.attempts += 1
                    extra = []
                    for profile in OCR_PROFILES[2:5]:
                        if stop():
                            break
                        try:
                            extra.append(read(layout, profile))
                        except (OSError, ValueError, subprocess.SubprocessError):
                            continue
                    if extra:
                        all_readings = [*readings, *extra]
                        self.stress_weak_slots = [index + 1 for index in uncertain_slots(all_readings, digits_read)]
                        self.record_intermediate(layout, all_readings, sample, precision, digits,
                                                 rules["fraction_digits"], frame)
            self.confirmed_quality = (self.confirmed_quality if same else [])[-2:] + [crop_quality(frame, layout)]
            # A reading below the one counted before proves that earlier image a misread (the meter
            # never runs backwards): its confirmation does not count for this one (21.11., 10501.84
            # then twice 10501.82 gave three confirmations).
            previous_reading = self.counter.get("reading_litres") if same and isinstance(self.counter, dict) else None
            contradicted = (type(previous_reading) is int and
                            counter["reading_litres"] + max(counter["step_litres"], self.counter.get("step_litres", 0))
                            <= previous_reading)
            if contradicted:
                self.partial_hits, self.partial_prefix = 0, None
            self.confirmations = self.confirmations + 1 if same and not contradicted else 1
            self.anchored = (not reference_pending and
                             (((same or recovered_slot) and self.anchored) or has_reference or bool(baseline)))
            self.advanced = not reference_pending and same and (self.advanced or (
                "reading_litres" in anchor and
                counter["reading_litres"] > anchor["reading_litres"]))
            self.candidate, self.counter = layout, counter
            self.note_group(layout, readings, True, digits + rules["fraction_digits"])
            self.unclear_frames = 0
            self.reference_reading = readings[0]
            self.focused = False
            if self.confirmations > self.best_confirmations:
                self.best, self.best_confirmations = layout, self.confirmations
            if reference_pending:
                on_decision("accepted_geometry")
            elif self.confirmations >= MIN_IMAGES and not (self.anchored or self.advanced):
                on_decision("await_movement")
            elif self.simplified and rules["fraction_digits"] == 3 and uncertain_slots(readings, digits + 3):
                on_decision("accepted_partial")
            else:
                on_decision("accepted")
            if self.confirmations >= MIN_IMAGES and (self.anchored or self.advanced):
                return self.best_of_group(layout) if self.rank_candidates else layout
            # Preserve a reproducible candidate and test it on the next photograph.
            return None
        if not committed and not stop():
            if self.simplified and self.candidate is not None and (self.confirmations or self.partial_hits):
                # The seventh roller may be unreadable during a transition.
                # Hold a once-confirmed crop for up to three fresh images.
                # An unreadable frame never increases the confirmation count.
                self.unclear_frames += 1
                if self.unclear_frames <= 3:
                    on_decision("await_clear_roller")
                    return None
            if not examined:
                on_decision("no_region")
            self.unclear_frames = 0
            self.candidate, self.counter = None, {}
            self.focused = False
            self.confirmations, self.anchored, self.advanced = 0, False, False
            self.full_hits = 0
            self.partial_hits, self.partial_prefix = 0, None
            if self.rank_candidates and self.optimizing and self.coarse_attempts < COARSE_LIMIT:
                self.optimizing = False
        return None
