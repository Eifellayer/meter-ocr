"""Validate crop settings and locate meter digits in camera images and SLFork overlays."""

from itertools import pairwise
from math import ceil, cos, floor, radians, sin
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


RAW_ROW_UNCLEAR = "Ziffernreihe nicht eindeutig gefunden. Bitte den Bildausschnitt im Test einstellen."
MANUAL_ROW_UNCLEAR = "Ziffern schwer lesbar. Prüfe Bilddrehung, Kamerawinkel, Fokus und Beleuchtung."


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


def find_neighbour_digit_rows(frame, whole_digits, fraction_digits, limit=2):
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
                if support < 2 and (not window or support != 1):
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
