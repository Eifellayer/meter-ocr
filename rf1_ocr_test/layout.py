"""Validate crop settings and locate digit frames in the SLFork overlay."""

from itertools import pairwise
import re
from statistics import median

from PIL import Image, ImageOps, ImageStat

CROP_COORDINATES = re.compile(r"\d{1,4}\s*,\s*\d{1,4}\s*,\s*\d{1,4}\s*,\s*\d{1,4}")
ROTATIONS = {
    0: None,
    90: Image.Transpose.ROTATE_270,
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_90,
}


def crop_coordinates(text, whole_width, rotation=0):
    """Check settings in the original image's coordinates before opening the frame."""
    if not isinstance(text, str) or not CROP_COORDINATES.fullmatch(text):
        raise ValueError("Ungültige Bildkoordinaten")
    if type(rotation) is not int or rotation not in ROTATIONS:
        raise ValueError("Ungültige Bilddrehung")
    left, top, right, bottom = (int(part) for part in text.split(","))
    if not (left < right and top < bottom):
        raise ValueError("Der Ausschnitt muss eine positive Größe haben")
    width = bottom - top if rotation in (90, 270) else right - left
    if type(whole_width) is not int or not 1 <= whole_width <= width:
        raise ValueError("Die Vorkommabreite muss in den gedrehten Ausschnitt passen")
    return left, top, right, bottom


def turn_crop(image, rotation):
    method = ROTATIONS[rotation]
    return image.transpose(method) if method is not None else image


RAW_ROW_UNCLEAR = "Ziffernreihe nicht eindeutig gefunden. Bitte den Bildausschnitt im Test einstellen."
MANUAL_ROW_UNCLEAR = "Ziffern im Ausschnitt schwer lesbar. Bitte Kamerawinkel, Fokus und Beleuchtung prüfen."


def digit_components(image, threshold, light_digits):
    """Return compact foreground components in a downscaled camera frame."""
    width, height = image.size
    mask = bytearray(image.point(lambda value: int((value >= threshold) == light_digits)).tobytes())
    boxes = []
    for start, present in enumerate(mask):
        if not present:
            continue
        left = right = start % width
        top = bottom = start // width
        pending = [start]
        mask[start] = 0
        count = 0
        while pending:
            index = pending.pop()
            y, x = divmod(index, width)
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
            count += 1
            for neighbor in (index - 1 if x else -1, index + 1 if x + 1 < width else -1,
                             index - width, index + width):
                if 0 <= neighbor < len(mask) and mask[neighbor]:
                    mask[neighbor] = 0
                    pending.append(neighbor)
        span, tall = right - left + 1, bottom - top + 1
        if (max(8, height // 72) <= tall <= height // 2 and 2 <= span <= tall
                and 0.14 * span * tall <= count <= 0.94 * span * tall):
            boxes.append((left, top, right + 1, bottom + 1))
    return sorted(boxes)


def find_raw_digit_row(frame, whole_digits, fraction_digits):
    """Find a regular row of glyphs in a contrasting meter window, without an ESP overlay."""
    count = whole_digits + fraction_digits
    if count < 3:
        return None
    image = frame.convert("L")
    image.thumbnail((400, 300), Image.Resampling.BILINEAR)
    image = ImageOps.autocontrast(image, cutoff=2)
    width, height = image.size
    candidates = {}
    for threshold in (90, 150):
        for light_digits in (True, False):
            boxes = digit_components(image, threshold, light_digits)
            for index, seed in enumerate(boxes):
                h = seed[3] - seed[1]
                row = [seed]
                for box in boxes[index + 1:]:
                    gap = box[0] - row[-1][2]
                    if gap > h:
                        break
                    if (gap >= 0 and h * 0.65 <= box[3] - box[1] <= h * 1.45
                            and abs(box[3] - row[-1][3]) <= h * 0.30):
                        row.append(box)
                if len(row) != count:
                    continue
                centers = [(box[0] + box[2]) / 2 for box in row]
                pitches = [b - a for a, b in pairwise(centers)]
                pitch = median(pitches)
                if not 0.42 * h <= pitch <= 1.65 * h or any(
                    not 0.66 * pitch <= gap <= 1.38 * pitch for gap in pitches
                ):
                    continue
                # Reject runs of ordinary label text with no visible meter window around them.
                left, right = row[0][0], row[-1][2]
                top, bottom = min(box[1] for box in row), max(box[3] for box in row)
                margin = max(1, round(h * 0.18))
                if top - margin < 2 or bottom + margin >= height - 2:
                    continue
                base = ImageStat.Stat(image.crop((left, top, right, bottom))).median[0]
                outside = [
                    ImageStat.Stat(image.crop(strip)).median[0]
                    for strip in ((left, max(0, top - h), right, top - margin),
                                  (left, bottom + margin, right, min(height, bottom + h)))
                ]
                direction = 1 if light_digits else -1
                contrast = min(direction * (value - base) for value in outside)
                if contrast < 18:
                    continue
                bounds = (max(0, left - margin), top - margin, min(width, right + margin), bottom + margin)
                candidates[bounds] = (contrast, row, centers)
    if not candidates:
        return None
    ordered = sorted(candidates, key=lambda bounds: candidates[bounds][0], reverse=True)
    left, top, right, bottom = ordered[0]
    contrast, _, centers = candidates[ordered[0]]
    for other in ordered[1:]:
        if candidates[other][0] < contrast * 0.85:
            break
        if abs(other[0] - left) > (right - left) / count or abs(other[1] - top) > (bottom - top) / 2:
            return None
    xscale, yscale = frame.width / width, frame.height / height
    crop = (round(left * xscale), round(top * yscale), round(right * xscale), round(bottom * yscale))
    boundaries = [crop[0], *(round((a + b) * xscale / 2) for a, b in pairwise(centers)), crop[2]]
    digit_boxes = [(a - crop[0], 0, b - crop[0], crop[3] - crop[1])
                   for a, b in pairwise(boundaries)]
    return crop, boundaries[whole_digits] - crop[0], digit_boxes


def find_digit_row(overlay, whole_digits=5, fraction_digits=None):
    width, height = overlay.size
    # SLFork draws digit frames in green. Alignment markers use a different color.
    mask = bytes(g > 95 and g - r > 42 and g - b > 36 for r, g, b in overlay.convert("RGB").getdata())
    columns = []
    for x in range(width):
        start = last = -4
        for y in range(height):
            if not mask[y * width + x]:
                continue
            if y - last > 3:
                if last - start >= max(14, height // 22):
                    columns.append((x, start, last))
                start = y
            last = y
        if last - start >= max(14, height // 22):
            columns.append((x, start, last))

    edges = []
    for edge in columns:
        x, top, bottom = edge
        if edges and x - edges[-1][0] <= 3 and all(
            abs(current - previous) <= 5 for current, previous in zip(edge[1:], edges[-1][1:])
        ):
            continue
        edges.append((x, top, bottom))

    def supported(left, right, y):
        strip = [mask[row * width + left:row * width + right]
                 for row in range(max(0, y - 3), min(height, y + 4))]
        return sum(any(column) for column in zip(*strip)) >= (right - left) * 0.60

    boxes = []
    for i, (left, top, bottom) in enumerate(edges):
        for right, right_top, right_bottom in edges[i + 1:]:
            span = right - left
            if span < max(12, width // 42):
                continue
            if span > width // 5:
                break
            if abs(top - right_top) > 6 or abs(bottom - right_bottom) > 6:
                continue
            if not (bottom - top) * 0.40 <= span <= (bottom - top) * 1.40:
                continue
            if supported(left, right, (top + right_top) // 2) and supported(
                left, right, (bottom + right_bottom) // 2
            ):
                boxes.append((left, min(top, right_top), right, max(bottom, right_bottom)))

    chains = []
    for i, box in enumerate(boxes):
        left, top, right, bottom = box
        span = right - left
        tolerance = max(5, (bottom - top) // 5)
        preceding = [
            chain for chain in chains[:i]
            if -span * 0.20 <= left - chain[-1][2] <= span * 0.44
            and abs(chain[-1][1] - top) <= tolerance
            and abs(chain[-1][3] - bottom) <= tolerance
            and 0.66 <= (chain[-1][2] - chain[-1][0]) / span <= 1.5
        ]
        chains.append(max(preceding, key=len, default=[]) + [box])

    row = max(chains, key=len, default=[])
    if fraction_digits is None:
        if len(row) not in (whole_digits + 2, whole_digits + 3):
            return None
        fraction_digits = len(row) - whole_digits
    if len(row) != whole_digits + fraction_digits:
        return None
    span = median(right - left for left, _, right, _ in row)
    if any(not 0.67 <= (second[0] - first[0]) / span <= 1.63
           for first, second in pairwise(row)):
        return None
    # Full register for visual inspection, with a separate boundary before the decimal rolls.
    left = max(0, row[0][0] - round(span * 0.06))
    right = min(width, max(box[2] for box in row) + round(span * (1.15 if fraction_digits == 2 else 0.08)))
    top = max(0, min(box[1] for box in row) - 2)
    bottom = min(height, max(box[3] for box in row) + 3)
    boundary = ((row[whole_digits - 1][2] + row[whole_digits][0]) // 2
                if fraction_digits else right - left)
    digit_boxes = [(a - left, b - top, c - left, d - top) for a, b, c, d in row]
    return (left, top, right, bottom), boundary - left, digit_boxes
