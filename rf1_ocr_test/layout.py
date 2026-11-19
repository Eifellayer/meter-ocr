"""Validate crop settings and locate meter digits in camera images and SLFork overlays."""

from itertools import pairwise
from math import atan, ceil, cos, degrees, floor, radians, sin
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


def rotated_width(width, height, rotation):
    angle = rotation % 360
    if angle in ROTATIONS:
        return height if angle in (90, 270) else width
    turn = radians(angle)
    span = width * abs(round(cos(turn), 15)) + height * abs(round(sin(turn), 15))
    return ceil((width + span) / 2) - floor((width - span) / 2)


def fine_rotation(value):
    """Validated fractional part of the image rotation (whole degrees stay in ``rotation``)."""
    if type(value) not in (int, float) or value != value or not -0.5 <= value <= 0.5:
        return 0.0
    return round(float(value), 1)


def split_rotation(text):
    """Parse a rotation such as "-1.5" or "-1,5" into whole degrees and a 0.1° remainder."""
    value = round(float(str(text).strip().replace(",", ".")), 1)
    if not -180 <= value <= 180:
        raise ValueError("Ungültige Bilddrehung")
    whole = int(round(value))
    return whole, round(value - whole, 1)


def crop_coordinates(text, whole_width, rotation=0):
    """Check settings in the original image's coordinates before opening the frame."""
    if not isinstance(text, str) or not CROP_COORDINATES.fullmatch(text):
        raise ValueError("Ungültige Bildkoordinaten")
    if type(rotation) is not int or not (-180 <= rotation <= 180 or rotation == 270):
        raise ValueError("Ungültige Bilddrehung")
    left, top, right, bottom = (int(part) for part in text.split(","))
    if not (left < right and top < bottom):
        raise ValueError("Der Ausschnitt muss eine positive Größe haben")
    width = rotated_width(right - left, bottom - top, rotation)
    if type(whole_width) is not int or not 1 <= whole_width <= width:
        raise ValueError("Die Vorkommabreite muss in den gedrehten Ausschnitt passen")
    return left, top, right, bottom


def turn_crop(image, rotation, *, expand=True):
    angle = rotation % 360
    if expand and angle in ROTATIONS:
        method = ROTATIONS[angle]
        return image.transpose(method) if method is not None else image
    if not angle:
        return image
    rgb = image.convert("RGB")
    background = tuple(int(value) for value in ImageStat.Stat(rgb.resize((24, 12))).median)
    return rgb.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=expand, fillcolor=background)


RAW_ROW_UNCLEAR = "Ziffernreihe nicht eindeutig gefunden. Stelle den Bildausschnitt im Test passend ein."
MANUAL_ROW_UNCLEAR = "Ziffern schwer lesbar. Prüfe Bilddrehung, Kamerawinkel, Fokus und Beleuchtung."
# Only a few digits unclear: the camera is usually fine, so do not send people to adjust it.
PARTLY_UNCLEAR = "Einzelne Ziffern waren nicht eindeutig lesbar. Die App versucht es automatisch weiter."


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


def find_raw_digit_rows(frame, whole_digits, fraction_digits, limit=4):
    """Rank separate rows by glyph size, spacing and contrast around the register."""
    count = whole_digits + fraction_digits
    if count < 3:
        return []
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
                if any(0.55 * pitch <= centers[0] - (box[0] + box[2]) / 2 <= 1.45 * pitch
                       and h * .65 <= box[3] - box[1] <= h * 1.45
                       and abs(box[3] - row[0][3]) <= h * .30 for box in boxes[:index]):
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
                size = median(box[3] - box[1] for box in row)
                regularity = 1 - sum(abs(gap - pitch) / pitch for gap in pitches) / len(pitches)
                score = size * regularity * (1 + min(contrast, 100) / 200)
                if bounds not in candidates or score > candidates[bounds][0]:
                    candidates[bounds] = (score, centers)
    xscale, yscale = frame.width / width, frame.height / height
    result = []
    for bounds, (score, centers) in sorted(candidates.items(), key=lambda item: (-item[1][0], item[0][1], item[0][0])):
        left, top, right, bottom = bounds
        crop = (round(left * xscale), round(top * yscale), round(right * xscale), round(bottom * yscale))
        if any(same_digit_region(crop, old[0][0]) for old in result):
            continue
        boundaries = [crop[0], *(round((a + b) * xscale / 2) for a, b in pairwise(centers)), crop[2]]
        digit_boxes = [(a - crop[0], 0, b - crop[0], crop[3] - crop[1])
                   for a, b in pairwise(boundaries)]
        result.append(((crop, boundaries[whole_digits] - crop[0], digit_boxes), score))
        if len(result) >= limit:
            break
    return result


def same_digit_region(first, second):
    l, t, r, b = first
    x, y, u, v = second
    shared = max(0, min(r, u) - max(l, x)) * max(0, min(b, v) - max(t, y))
    return shared >= .65 * max((r - l) * (b - t), (u - x) * (v - y))


def find_raw_digit_row(frame, whole_digits, fraction_digits):
    rows = find_raw_digit_rows(frame, whole_digits, fraction_digits, limit=2)
    if not rows or len(rows) > 1 and rows[1][1] >= .85 * rows[0][1]:
        return None
    return rows[0][0]


def bright_glyphs(gray, stroke):
    """White top-hat: glyph strokes brighter than their local surroundings, independent of uneven light."""
    from PIL import ImageChops, ImageFilter

    size = max(3, stroke | 1)
    opened = gray.filter(ImageFilter.MinFilter(size)).filter(ImageFilter.MaxFilter(size))
    return ImageOps.autocontrast(ImageChops.subtract(gray, opened), cutoff=1)


def find_glyph_register(frame, count, with_tilt=False):
    """Locate a row of bright, evenly spaced roller digits by local contrast.

    Works on dim, uneven camera images (e.g. ESPHome cameras with a flash LED) where the
    window itself is not darker everywhere than its surroundings: a reflection, a red
    fraction field or a barcode below the window do not interrupt the glyph row.
    """
    if count < 3:
        return None
    gray = frame.convert("L")
    gray.thumbnail((400, 300), Image.Resampling.BILINEAR)
    width, height = gray.size
    found = []
    for stroke in (7, 11):
        glyphs = bright_glyphs(gray, stroke)
        for threshold in (80, 120):
            for box in digit_components(glyphs, threshold, True):
                tall = box[3] - box[1]
                if not height / 20 <= tall <= height / 3 or box[2] - box[0] > tall:
                    continue
                center = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
                twin = next((i for i, old in enumerate(found)
                             if abs((old[0] + old[2]) / 2 - center[0]) <= tall * .2
                             and abs((old[1] + old[3]) / 2 - center[1]) <= tall * .3), None)
                if twin is None:
                    found.append(box)
                elif tall > found[twin][3] - found[twin][1]:
                    found[twin] = box
    boxes = sorted(found, key=lambda box: (box[0] + box[2]) / 2)

    def darkness(cell):
        l, t, r, b = cell
        if l < 0 or r > width or t < 0 or b > height or r <= l or b <= t:
            return 256
        return ImageStat.Stat(gray.crop((l, t, r, b))).median[0]

    best = None
    for index, seed in enumerate(boxes):
        tall = seed[3] - seed[1]
        chain = [seed]
        slots = [0]
        pitch = None
        for box in boxes[index + 1:]:
            last = chain[-1]
            distance = (box[0] + box[2]) / 2 - (last[0] + last[2]) / 2
            size = box[3] - box[1]
            if not .55 * tall <= size <= 1.6 * tall:
                continue
            if abs((box[1] + box[3]) / 2 - (last[1] + last[3]) / 2) > .45 * tall:
                continue
            if pitch is None:
                if not .9 * tall <= distance <= 2.2 * tall:
                    continue
                step = 1
            else:
                step = round(distance / pitch)
                if step not in (1, 2, 3) or abs(distance - step * pitch) > .22 * pitch:
                    continue
            if slots[-1] + step >= count:
                break
            chain.append(box)
            slots.append(slots[-1] + step)
            centers = [(b[0] + b[2]) / 2 for b in chain]
            pitch = (centers[-1] - centers[0]) / slots[-1]
        if pitch is None or len(chain) < max(3, count - 2) or slots[-1] < count - 2:
            continue
        missing = count - 1 - slots[-1]
        first = (chain[0][0] + chain[0][2]) / 2
        last = (chain[-1][0] + chain[-1][2]) / 2
        # A slot missing at an end (glare, half-turned roller): extend towards the darker side.
        for _ in range(missing):
            left_cell = (round(first - 1.5 * pitch), chain[0][1], round(first - .5 * pitch), chain[0][3])
            right_cell = (round(last + .5 * pitch), chain[-1][1], round(last + 1.5 * pitch), chain[-1][3])
            if darkness(left_cell) < darkness(right_cell):
                first -= pitch
            else:
                last += pitch
        top = min(box[1] for box in chain)
        bottom = max(box[3] for box in chain)
        glyph = median(box[3] - box[1] for box in chain)
        margin = .35 * glyph
        bounds = (first - .5 * pitch, top - margin, last + .5 * pitch, bottom + margin)
        if bounds[0] < 0 or bounds[2] > width or bounds[1] < 0 or bounds[3] > height:
            continue
        # Bright digits sit in a dark window: reject bright gaps between dark print on a light label.
        contrasts = []
        for box in chain:
            x = (box[0] + box[2]) / 2
            y = (box[1] + box[3]) / 2
            cell = (round(x - .35 * pitch), round(y - .5 * glyph), round(x + .35 * pitch), round(y + .5 * glyph))
            above = (cell[0], round(y - 1.3 * glyph), cell[2], round(y - .9 * glyph))
            below = (cell[0], round(y + .9 * glyph), cell[2], round(y + 1.3 * glyph))
            contrasts.append(min(darkness(above), darkness(below)) - darkness(cell))
        if median(contrasts) < 10:
            continue
        score = sum(box[3] - box[1] for box in chain) * (1 - .15 * (count - len(chain)))
        if best is None or score > best[0]:
            points = [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for b in chain]
            slopes = [(y2 - y1) / (x2 - x1) for i, (x1, y1) in enumerate(points)
                      for x2, y2 in points[i + 1:] if x2 > x1]
            best = score, bounds, degrees(atan(median(slopes))) if slopes else 0.0
    if best is None:
        return None
    box = tuple(round(value * scale) for value, scale in zip(
        best[1], (frame.width / width, frame.height / height) * 2))
    return (box, round(best[2], 1)) if with_tilt else box


def find_dark_register(frame, count):
    """Find the meter window: first as a row of bright digits, then as a wide dark strip."""
    return find_glyph_register(frame, count) or find_dark_strip(frame, count)


def find_dark_strip(frame, count):
    """Find a wide, contrasting dark window even when individual glyphs are incomplete."""
    from PIL import ImageFilter

    if count < 3:
        return None
    image = frame.convert("L")
    image.thumbnail((320, 240))
    image = ImageOps.autocontrast(image, cutoff=2)
    width, height = image.size
    # Close bright strokes inside the dark strip, leaving the outside edges intact.
    dark = image.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))
    minimum = max(24, width // 4)
    best = None
    for threshold in (48, 75):
        previous = []
        for y in range(height + 1):
            row = dark.crop((0, y, width, y + 1)).tobytes() if y < height else b""
            runs = []
            start = None
            for x, value in enumerate((*row, 255)):
                if value < threshold:
                    if start is None:
                        start = x
                elif start is not None:
                    if x - start >= minimum:
                        runs.append((start, x))
                    start = None
            current = []
            for left, right in runs:
                parent = next((item for item in previous if abs(item[0] - left) <= 5
                               and abs(item[1] - right) <= 5), None)
                current.append((left, right, parent[2] if parent else y))
            for left, right, top in previous:
                if any(t == top and abs(l - left) <= 5 and abs(r - right) <= 5 for l, r, t in current):
                    continue
                span, tall = right - left, y - top
                if tall < 8 or not count * .55 <= span / tall <= count * 2:
                    continue
                if left < 2 or right > width - 2 or top < 2 or y + 3 >= height:
                    continue
                inside = ImageStat.Stat(image.crop((left, top, right, y))).median[0]
                outside = ImageStat.Stat(image.crop((left, y + 1, right, min(height, y + max(4, tall // 2))))).median[0]
                if outside - inside < 28:
                    continue
                score = span * tall * (outside - inside)
                if best is None or score > best[0]:
                    best = score, (left, top, right, y)
            previous = current
    if best is None:
        return None
    return tuple(round(value * scale) for value, scale in zip(
        best[1], (frame.width / width, frame.height / height) * 2))


def dark_register_cells(register, count):
    """Fit roller centers to visible strokes inside an already located dark window."""
    image = register.convert("RGB")
    image.thumbnail((720, 180), Image.Resampling.BILINEAR)
    w, h = image.size
    if count < 3 or w < count * 10 or h < 15:
        return ()
    estimate = w / count
    best = None
    for channel in ("G", "B", "L", "T"):
        if channel == "T":
            gray = bright_glyphs(image.convert("L"), round(h * .15))
        else:
            gray = ImageOps.autocontrast(image.convert("L") if channel == "L" else image.getchannel(channel), cutoff=2)
        for threshold in (105, 120, 140):
            glyphs = [box for box in digit_components(gray, threshold, True)
                      if w * .025 <= (box[0] + box[2]) / 2 <= w * .975
                      and h * .20 <= box[3] - box[1] <= h * .60
                      and box[2] - box[0] <= estimate * .66]
            if not max(3, count - 2) <= len(glyphs) <= 2 * count + 4:
                continue
            centers = [(l + r) / 2 for l, _, r, _ in glyphs]
            pitches = {round((right - left) / steps, 1)
                       for i, left in enumerate(centers) for right in centers[i + 1:]
                       for steps in (1, 2, 3)
                       if estimate * .72 <= (right - left) / steps <= estimate * 1.12}
            for pitch in sorted(pitches):
                for anchor in centers:
                    for slot in range(count):
                        first = anchor - slot * pitch
                        last = first + (count - 1) * pitch
                        if first < .27 * pitch or last > w - .27 * pitch:
                            continue
                        grid = [first + i * pitch for i in range(count)]
                        matches = [min(range(len(centers)), key=lambda i: abs(centers[i] - x)) for x in grid]
                        matched = [(slot, index) for slot, (x, index) in enumerate(zip(grid, matches))
                                   if abs(x - centers[index]) <= pitch * .28]
                        if len(matched) < max(3, count - 2) or matched[-1][0] - matched[0][0] < count - 3:
                            continue
                        vertical = [(glyphs[index][1] + glyphs[index][3]) / 2 for _, index in matched]
                        middle = median(vertical)
                        if any(abs(center - middle) > h * .22 for center in vertical):
                            continue
                        error = sum(abs(grid[slot] - centers[index]) / pitch for slot, index in matched)
                        error += sum(abs(center - middle) / h for center in vertical)
                        score = len(matched), -error
                        if best is not None and score <= best[0]:
                            continue
                        glyph_height = median(glyphs[index][3] - glyphs[index][1] for _, index in matched)
                        boxes = []
                        matched_centers = dict(matched)
                        for slot, x in enumerate(grid):
                            if slot in matched_centers:
                                x = centers[matched_centers[slot]]
                            top = max(0, round(middle - .73 * glyph_height))
                            bottom = min(h, round(middle + .73 * glyph_height))
                            boxes.append((max(0, round(x - pitch * .36)), top,
                                          min(w, round(x + pitch * .36)), bottom))
                        best = score, boxes
    if best is None:
        return ()
    return normalize_digit_boxes(recenter_on_glyphs(image, best[1]), image.size)


def recenter_on_glyphs(image, boxes):
    """Move each frame sideways onto the bright glyph it covers.

    Blurred glyphs merge with glare or the roller edge into one component whose centre is off;
    the column profile of the local-contrast image finds the stroke mass instead.
    """
    if len(boxes) < 2:
        return boxes
    w, h = image.size
    pitch = (boxes[-1][0] + boxes[-1][2] - boxes[0][0] - boxes[0][2]) / 2 / (len(boxes) - 1)
    if pitch <= 4:
        return boxes
    strokes = bright_glyphs(image.convert("L"), max(3, round(h * .15)))
    span = max(2, round(pitch * .5))
    moved = []
    for left, top, right, bottom in boxes:
        center = (left + right) / 2
        start = max(0, round(center - pitch * .55))
        stop = min(w, round(center + pitch * .55))
        if stop - start <= span or bottom - top < 4:
            moved.append((left, top, right, bottom))
            continue
        band = strokes.crop((start, top, stop, bottom))
        columns = [sum(band.crop((x, 0, x + 1, band.height)).tobytes()) for x in range(band.width)]
        sums = [sum(columns[x:x + span]) for x in range(len(columns) - span + 1)]
        best = max(range(len(sums)), key=sums.__getitem__)
        if sums[best] <= 0:
            moved.append((left, top, right, bottom))
            continue
        shift = start + best + span / 2 - center
        shift = round(max(-pitch * .3, min(pitch * .3, shift)))
        shift = max(-left, min(w - right, shift))
        moved.append((left + shift, top, right + shift, bottom))
    return moved


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


def digit_box_settings(boxes, count):
    """Validate optional thousandths of the rotated crop, ordered left to right."""
    if boxes in (None, []):
        return []
    if not isinstance(boxes, (tuple, list)) or len(boxes) != count:
        raise ValueError("Die Anzahl der Ziffernrahmen passt nicht zur Zähleranzeige.")
    result = []
    for box in boxes:
        if not isinstance(box, (list, tuple)) or len(box) != 4 or any(type(v) is not int for v in box):
            raise ValueError("Ungültiger Ziffernrahmen.")
        left, top, right, bottom = box
        if not (0 <= left < right <= 1000 and 0 <= top < bottom <= 1000
                and right - left >= 10 and bottom - top >= 25):
            raise ValueError("Ungültiger Ziffernrahmen.")
        if result and left + right <= result[-1][0] + result[-1][2]:
            raise ValueError("Ziffernrahmen müssen von links nach rechts angeordnet sein.")
        result.append([left, top, right, bottom])
    return result


def scale_digit_boxes(boxes, size):
    width, height = size
    return [(left * width // 1000, top * height // 1000,
             ceil(right * width / 1000), ceil(bottom * height / 1000)) for left, top, right, bottom in boxes]


def normalize_digit_boxes(boxes, size):
    width, height = size
    return tuple((round(left * 1000 / width), round(top * 1000 / height),
                  round(right * 1000 / width), round(bottom * 1000 / height))
                 for left, top, right, bottom in boxes)


def _meter_window(image, seed, count):
    """Estimate horizontal window edges beside the glyph, if the background has a boundary."""
    left, top, right, bottom = seed
    height = bottom - top
    margin = max(2, height // 9)
    if top < margin or bottom + margin >= image.height:
        return None
    width = image.width
    upper = image.crop((0, top - margin, width, top)).resize((width, 1), Image.Resampling.BOX).tobytes()
    lower = image.crop((0, bottom, width, bottom + margin)).resize((width, 1), Image.Resampling.BOX).tobytes()
    center = (left + right) // 2
    tones = [(a + b) // 2 for a, b in zip(upper, lower)]
    background = tones[center]
    start, end = center, center + 1
    while start > 0 and abs(tones[start - 1] - background) <= 30:
        start -= 1
    while end < width and abs(tones[end] - background) <= 30:
        end += 1
    if 0 < start < end < width and count * height * .45 <= end - start <= count * height * 1.75:
        return start, end
    return None


def find_neighbour_digit_rows(frame, whole_digits, fraction_digits, limit=2, min_support=1):
    """Propose bounded digit grids from visible glyphs, including gaps in their middle."""
    count = whole_digits + fraction_digits
    image = frame.convert("L")
    image.thumbnail((400, 300), Image.Resampling.BILINEAR)
    image = ImageOps.autocontrast(image, cutoff=2)
    width, height = image.size
    if count < 2:
        return []
    candidates = {}
    scans = [(light, digit_components(image, threshold, light))
             for threshold in (90, 150) for light in (True, False)]
    all_boxes = set(box for _, boxes in scans for box in boxes)
    for light_digits, boxes in scans:
        seeds = sorted(boxes, key=lambda box: box[3] - box[1], reverse=True)[:14]
        for seed in seeds:
            left, top, right, bottom = seed
            tall = bottom - top
            if any(other[3] - other[1] > tall * 1.55 and other[0] <= right and other[2] >= left
                   and abs(other[1] + other[3] - top - bottom) <= tall for other in all_boxes):
                continue
            center = (left + right) / 2
            nearby = [box for box in boxes if abs((box[0] + box[2]) / 2 - center) <= count * tall * 1.7
                      and abs((box[1] + box[3]) - (top + bottom)) <= tall * .65
                      and tall * .55 <= box[3] - box[1] <= tall * 1.48]
            # A denser run can be a serial number. Never sample it by skipping glyphs.
            if len(nearby) > count:
                continue
            centers = [(box[0] + box[2]) / 2 for box in nearby]
            window = _meter_window(image, seed, count)
            if len(nearby) < 2 and window is None:
                continue
            pitches = {round(tall * factor) for factor in (.68, .85, 1.05, 1.25)}
            for other in sorted(centers, key=lambda x: abs(x - center))[:8]:
                for skips in range(1, min(count, 4)):
                    pitch = abs(other - center) / skips
                    if .48 * tall <= pitch <= 1.7 * tall:
                        pitches.add(round(pitch))
            hypotheses = [(center - pitch * slot - (gap if slot >= whole_digits else 0), pitch, gap)
                          for pitch in sorted(pitches) if pitch >= 5
                          for gap in ((0, round(pitch * .35)) if fraction_digits else (0,))
                          for slot in range(count)]
            if window:
                start, end = window
                pitch = (end - start) / count
                hypotheses.append((start + pitch / 2, pitch, 0))
            for start, pitch, gap in hypotheses:
                grid = [start + i * pitch + (gap if i >= whole_digits else 0) for i in range(count)]
                a, b = round(grid[0] - pitch / 2), round(grid[-1] + pitch / 2)
                if not (0 <= a < b <= width):
                    continue
                matches = []
                residual = 0.0
                for x in grid:
                    closest = min(nearby, key=lambda box: abs((box[0] + box[2]) / 2 - x))
                    distance = abs((closest[0] + closest[2]) / 2 - x)
                    match = closest if distance <= pitch * .40 else None
                    matches.append(match)
                    if match:
                        residual += distance / pitch
                if any(.55 * pitch <= distance <= 1.4 * pitch for x in centers
                       for distance in (grid[0] - x, x - grid[-1])):
                    continue
                support = sum(match is not None for match in matches)
                if support < min_support or support < 2 and (not window or support != 1):
                    continue
                if support < 2 and abs(a - window[0]) + abs(b - window[1]) > pitch * .7:
                    continue
                matched = [box for box in matches if box is not None]
                y1, y2 = min(box[1] for box in matched), max(box[3] for box in matched)
                margin = max(2, round(tall * .15))
                bounds = (a, max(0, y1 - margin), b, min(height, y2 + margin))
                edge_error = ((abs(a - window[0]) + abs(b - window[1])) / pitch) if window else 0
                score = support * 2 - residual - min(2.0, edge_error * .5)
                key = (round(a / 3), round(b / 3), round(y1 / 3))
                if key not in candidates or candidates[key][0] < score:
                    candidates[key] = (score, bounds, grid, matches, pitch, light_digits, window)

    result = []
    sx, sy = frame.width / width, frame.height / height
    for _, bounds, grid, matches, pitch, light_digits, window in sorted(
            candidates.values(), key=lambda item: item[0], reverse=True)[:16]:
        left, top, right, bottom = bounds
        inside = ImageStat.Stat(image.crop(bounds)).median[0]
        span = max(5, (bottom - top) // 2)
        strips = [(left, max(0, top - span), right, top), (left, bottom, right, min(height, bottom + span))]
        if window:
            start, end = window
            strips += [(max(0, start - 5), top, start, bottom), (end, top, min(width, end + 5), bottom)]
        surrounding = [ImageStat.Stat(image.crop(strip)).median[0] for strip in strips
                       if strip[0] < strip[2] and strip[1] < strip[3]]
        contrast = max(((value - inside) * (1 if light_digits else -1) for value in surrounding), default=0)
        if contrast < 12:
            continue
        crop = tuple(round(value * scale) for value, scale in zip(bounds, (sx, sy, sx, sy)))
        if any(abs(crop[0] - old[0][0]) < pitch * sx * .35 and abs(crop[2] - old[0][2]) < pitch * sx * .35
               and abs(crop[1] - old[0][1]) < (crop[3] - crop[1]) * .25 for old in result):
            continue
        inferred = [(x + (match[0] + match[2]) / 2) / 2 if match else x
                    for x, match in zip(grid, matches)]
        boundaries = [left, *(round((a + b) / 2) for a, b in pairwise(inferred)), right]
        digit_boxes = []
        for index, (x, match) in enumerate(zip(inferred, matches)):
            # Allow the roller to move inside the cell while keeping neighbouring cells apart.
            left_edge, right_edge = floor(x - pitch * .5), ceil(x + pitch * .5)
            if match:
                stroke_margin = max(1, round(pitch * .08))
                left_edge = min(left_edge, match[0] - stroke_margin)
                right_edge = max(right_edge, match[2] + stroke_margin)
            l = max(boundaries[index], left_edge)
            r = min(boundaries[index + 1], right_edge)
            digit_boxes.append((round(l * sx) - crop[0], 0, round(r * sx) - crop[0], crop[3] - crop[1]))
        whole_width = round(boundaries[whole_digits] * sx) - crop[0]
        result.append((crop, whole_width, digit_boxes))
        if len(result) >= limit:
            break
    return result


def _column_activity(gray, left, right, top, bottom):
    """Vertical variation per column: digit strokes vary, gaps between rollers stay flat."""
    return [ImageStat.Stat(gray.crop((x, top, x + 1, bottom))).stddev[0] for x in range(left, right)]


def _busiest_window(profile, start, width):
    sums = [sum(profile[i:i + width]) for i in range(0, len(profile) - width + 1)]
    if not sums:
        return None
    best = max(range(len(sums)), key=sums.__getitem__)
    return start + best + width / 2, sums[best], sums


def roll_center(image, boxes):
    """Horizontal centre (pixels) of the roller after the second-to-last digit box, or None.

    The last roller sits a little farther from its neighbour than the other digits do, so an
    evenly spaced box often lands beside it. The roller window shows strokes and texture with
    vertical variation; the gaps between rollers do not. The method is first checked on the
    neighbour's known position and only trusted if it finds that one again.
    """
    if len(boxes) < 3:
        return None
    gray = image.convert("L")
    before, neighbour = boxes[-3], boxes[-2]
    width = neighbour[2] - neighbour[0]
    centre = (neighbour[0] + neighbour[2]) / 2
    pitch = centre - (before[0] + before[2]) / 2
    if width < 4 or pitch < width * .8:
        return None
    top = max(0, min(neighbour[1], boxes[-1][1]))
    bottom = min(gray.height, max(neighbour[3], boxes[-1][3]))
    if bottom - top < 4:
        return None
    # Self-check on the neighbour, whose centre is known.
    left, right = max(0, round(centre - pitch)), min(gray.width, round(centre + pitch))
    found = _busiest_window(_column_activity(gray, left, right, top, bottom), left, width)
    if found is None or abs(found[0] - centre) > width / 5:
        return None
    reference = found[1]
    left = max(0, round(centre + .75 * pitch - width / 2))
    right = min(gray.width, round(centre + 1.7 * pitch + width / 2))
    profile = _column_activity(gray, left, right, top, bottom)
    found = _busiest_window(profile, left, width)
    if found is None:
        return None
    x, score, sums = found
    # A roller must show roughly as much detail as its neighbour and clearly more than a gap.
    if score < .4 * reference or score < 1.2 * min(sums):
        return None
    return x


def digit_row_tilt(image, boxes, skip=()):
    """Remaining tilt of a digit row in degrees (app convention, as for ``rotation``), or None.

    Each box contributes the centre of its strongest contrast (the digit, light or dark), and a
    straight line is fitted through those centres. Single images are noisy (a turning roller
    shifts its centre), so callers average several measurements before acting on them.
    """
    gray = image.convert("L")
    points = []
    for index, (left, top, right, bottom) in enumerate(boxes):
        height = bottom - top
        if index in skip or right - left < 4 or height < 6:
            continue
        # Measure inside the frame only. Just outside it lie the bright edges of the counter
        # window, which are not parallel to the digits and gave readings like 16°.
        margin = max(1, round(height * .06))
        top, bottom = max(0, round(top + margin)), min(gray.height, round(bottom - margin))
        if bottom - top < 4:
            continue
        cell = gray.crop((max(0, left), top, min(gray.width, right), bottom))
        if cell.width < 2 or cell.height < 2:
            continue
        centre = median(cell.getdata())
        width = cell.width
        lit = [0] * cell.height
        for index, value in enumerate(cell.getdata()):
            lit[index // width] += abs(value - centre) > 30
        # Digit rows are partly lit; rows lit across most of the frame are a window edge.
        inked = [row for row, count in enumerate(lit) if width * .08 <= count <= width * .65]
        # The digit is one block of rows; fragments of a slanted window edge are separate.
        runs, run = [], []
        for row in inked:
            if run and row - run[-1] > 2:
                runs.append(run)
                run = []
            run.append(row)
        if run:
            runs.append(run)
        block = max(runs, key=lambda rows: rows[-1] - rows[0], default=[])
        if not block or block[-1] - block[0] < max(3, cell.height // 4):
            continue
        points.append(((left + right) / 2, top + (block[0] + block[-1]) / 2))
    if len(points) < 3:
        return None
    # Median of all pairwise slopes (Theil–Sen): one turning roller cannot tip the line.
    slopes = [(y2 - y1) / (x2 - x1) for index, (x1, y1) in enumerate(points)
              for x2, y2 in points[index + 1:] if x2 != x1]
    if not slopes:
        return None
    slope = median(slopes)
    # Positive ``rotation`` turns the picture clockwise; a row falling to the right needs the opposite.
    return -degrees(atan(slope))


def glyph_clipped(image, box):
    """Is a digit cut off at the left or right edge of its frame?

    A frame pushed sideways shows only part of the digit (half a 9 reads as 4). The strokes
    then run into the frame edge: the outermost columns carry as much detail as the busiest
    column inside. A centred digit leaves a quieter margin on both sides.
    """
    left, top, right, bottom = (round(value) for value in box)
    gray = image.convert("L")
    left, right = max(0, left), min(gray.width, right)
    top, bottom = max(0, top), min(gray.height, bottom)
    width = right - left
    if width < 8 or bottom - top < 6:
        return False
    profile = _column_activity(gray, left, right, top, bottom)
    busiest = max(profile)
    if busiest < 12:
        return False
    edge = max(1, width // 12)
    return max(profile[:edge]) > busiest * .75 or max(profile[-edge:]) > busiest * .75
