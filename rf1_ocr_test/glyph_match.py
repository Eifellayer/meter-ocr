"""Second opinion for blurred roller digits: compare a digit cell with blurred font templates.

Tesseract needs sharp strokes; on a blurred, dim camera image it often returns nothing for a
clearly visible 0 or 8. A template comparison (normalised cross-correlation on the local
contrast image) still separates most digits there. It never decides alone against Tesseract:
``combine`` accepts a template digit only where Tesseract stays silent and the template result
is clear, and turns a clear contradiction into an unclear digit.
"""
import hashlib
import math
import threading
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps

HEIGHT = 28
CELL = (72, 96)
FRACTIONS = (.56, .62, .68, .76)
SIGMAS = (.8, 1.6)
TOPHAT = 7
# Template digit is used when Tesseract read nothing (synthetic test: <1 % wrong at these limits).
ACCEPT_SCORE = .72
ACCEPT_MARGIN = .05
# A Tesseract digit is dropped when the templates clearly prefer another digit.
CONTRADICT_SCORE = .72
CONTRADICT_MARGIN = .08
# A real meter "1" carries a long flag and matches the "7" template almost as well (seen
# 20.11.: 7 = .86, 1 = .79 on a clear 1). Between these two the template needs twice the margin.
CONFUSABLE = ({"1", "7"},)
# Blurred 6 reads as 5 in several Tesseract profiles while the templates still rank the 6 first
# (20.11.: 6 = .80, 5 = .76). For this pair a small template lead is enough to leave it unclear.
BLUR_PAIRS = ({"5", "6"},)
BLUR_CONTRADICT_MARGIN = .02
# Anchored completion of hidden whole digits: summed template evidence ahead of the next candidate.
ANCHOR_MARGIN = .08
VISIBLE_SCORE = .6
MAX_CANDIDATES = 400

_templates = None
_lock = threading.Lock()
_cache = {}


def template_path():
    return Path(__file__).with_name("digit_templates.png")


def templates():
    """Blurred, zero-mean, unit-length templates as (digit, width, height, rows)."""
    global _templates
    with _lock:
        if _templates is not None:
            return _templates
        prepared = []
        try:
            with Image.open(template_path()) as sheet:
                sheet = sheet.convert("L")
                fonts = sheet.height // CELL[1]
                for font in range(fonts):
                    for digit in range(10):
                        cell = sheet.crop((digit * CELL[0], font * CELL[1],
                                           (digit + 1) * CELL[0], (font + 1) * CELL[1]))
                        box = cell.getbbox()
                        if box is None:
                            continue
                        shape = cell.crop(box)
                        for fraction in FRACTIONS:
                            height = max(6, round(HEIGHT * fraction))
                            width = max(2, round(shape.width * height / shape.height))
                            small = shape.resize((width, height), Image.Resampling.LANCZOS)
                            for sigma in SIGMAS:
                                canvas = Image.new("L", (width + 4, height + 4), 0)
                                canvas.paste(small, (2, 2))
                                canvas = canvas.filter(ImageFilter.GaussianBlur(sigma))
                                values = list(canvas.tobytes())
                                mean = sum(values) / len(values)
                                centred = [value - mean for value in values]
                                norm = math.sqrt(sum(value * value for value in centred)) or 1.0
                                unit = [value / norm for value in centred]
                                rows = [unit[y * canvas.width:(y + 1) * canvas.width] for y in range(canvas.height)]
                                prepared.append((str(digit), canvas.width, canvas.height, rows))
        except OSError:
            prepared = []
        _templates = prepared
        return _templates


def contrast_image(crop, bright):
    """Local-contrast image of a digit cell at working height; glyph strokes become bright."""
    image = crop.convert("RGB")
    if bright:
        red, green, blue = image.split()
        # The darkest channel turns both a black and a red roller background dark.
        channel = ImageChops.darker(ImageChops.darker(red, green), blue)
    else:
        channel = ImageOps.invert(image.convert("L"))
    width = max(4, round(image.width * HEIGHT / max(1, image.height)))
    channel = channel.resize((width, HEIGHT), Image.Resampling.BILINEAR)
    opened = channel.filter(ImageFilter.MinFilter(TOPHAT)).filter(ImageFilter.MaxFilter(TOPHAT))
    return ImageChops.subtract(channel, opened)


def correlation_scores(image):
    """Best normalised cross-correlation of every digit over all template positions."""
    width, height = image.size
    pixels = list(image.tobytes())
    rows = [pixels[y * width:(y + 1) * width] for y in range(height)]
    squares = [[value * value for value in row] for row in rows]
    best = {}
    for digit, t_width, t_height, t_rows in templates():
        if t_width > width or t_height > height:
            continue
        count = t_width * t_height
        top = best.get(digit, -1.0)
        for y in range(height - t_height + 1):
            band = rows[y:y + t_height]
            band_squares = squares[y:y + t_height]
            for x in range(width - t_width + 1):
                total = 0
                energy = 0
                dot = 0.0
                for row, row_squares, t_row in zip(band, band_squares, t_rows):
                    window = row[x:x + t_width]
                    total += sum(window)
                    energy += sum(row_squares[x:x + t_width])
                    dot += sum(map(float.__mul__, t_row, map(float, window)))
                variance = energy - total * total / count
                if variance <= 1e-6:
                    continue
                score = dot / math.sqrt(variance)
                if score > top:
                    top = score
        best[digit] = top
    return best


def _percentile(histogram, share):
    total, seen = sum(histogram), 0
    for level, count in enumerate(histogram):
        seen += count
        if seen >= total * share:
            return level
    return 255


def washed_out(register, boxes):
    """Indices of frames covered by a flash reflection, also for tightly drawn frames.

    In the darkest colour channel a reflected frame is bright almost everywhere: its median is
    at least twice the typical frame median and its brightest part saturates.
    """
    if len(boxes) < 3:
        return []
    image = register.convert("RGB")
    red, green, blue = image.split()
    darkest = ImageChops.darker(ImageChops.darker(red, green), blue)
    stats = []
    for left, top, right, bottom in boxes:
        left, top = max(0, left), max(0, top)
        right, bottom = min(darkest.width, right), min(darkest.height, bottom)
        if right - left < 2 or bottom - top < 2:
            stats.append(None)
            continue
        histogram = darkest.crop((left, top, right, bottom)).histogram()
        stats.append((_percentile(histogram, .5), _percentile(histogram, .95)))
    medians = sorted(item[0] for item in stats if item is not None)
    if len(medians) < 3:
        return []
    typical = medians[len(medians) // 2]
    found = [index for index, item in enumerate(stats)
             if item is not None and item[0] >= max(100, 2 * typical) and item[1] >= 230]
    return found if len(found) <= 2 else []


def digit_scores(crop, light_digits=None):
    """Return {digit: score} for one digit cell, or {} without templates or a usable cell.

    ``light_digits`` True means bright digits on a dark roller, False dark digits on a light
    background, None tries both and keeps the polarity with the clearer best match.
    """
    if crop.width < 6 or crop.height < 10 or not templates():
        return {}
    key = (crop.mode, crop.size, hashlib.sha256(crop.tobytes()).digest(), light_digits)
    with _lock:
        cached = _cache.get(key)
    if cached is not None:
        return cached
    polarities = (True, False) if light_digits is None else (bool(light_digits),)
    found = {}
    for bright in polarities:
        scores = correlation_scores(contrast_image(crop, bright))
        if scores and (not found or max(scores.values()) > max(found.values())):
            found = scores
    with _lock:
        if len(_cache) > 512:
            _cache.clear()
        _cache[key] = found
    return found


def ranked(scores, allowed=None):
    items = sorted(((score, digit) for digit, score in scores.items()
                    if allowed is None or digit in allowed), reverse=True)
    if not items:
        return None, 0.0, 0.0
    margin = items[0][0] - items[1][0] if len(items) > 1 else items[0][0]
    return items[0][1], items[0][0], margin


def combine(tesseract, scores):
    """Merge a Tesseract digit ("?" when unread) with template scores; never guess on a conflict."""
    digit, score, margin = ranked(scores)
    if digit is None:
        return tesseract
    if tesseract in tuple("0123456789"):
        # Measured against the digit Tesseract read, not the runner-up: a blurred 7 read as 4
        # (20.11.: 7 = .74, 2 = .72, 4 far behind) is a clear contradiction as well.
        gap = score - scores.get(tesseract, 0.0)
        needed = CONTRADICT_MARGIN * (2 if {digit, tesseract} in CONFUSABLE else 1)
        if digit != tesseract and score >= CONTRADICT_SCORE and gap >= needed:
            return "?"
        if {digit, tesseract} in BLUR_PAIRS and score >= CONTRADICT_SCORE and gap >= BLUR_CONTRADICT_MARGIN:
            return "?"
        return tesseract
    if score >= ACCEPT_SCORE and margin >= ACCEPT_MARGIN:
        runner_up = ranked({key: value for key, value in scores.items() if key != digit})[0]
        if {digit, runner_up} in CONFUSABLE and margin < 2 * ACCEPT_MARGIN:
            return tesseract
        return digit
    return tesseract


def anchored_whole(whole, scores, low, high):
    """Fill unclear whole digits from the only plausible meter readings between ``low`` and ``high``.

    ``whole`` is the read whole part with "?" for unclear digits, ``scores`` the template scores
    per position, ``low``/``high`` the range of whole cubic metres the meter can show now (last
    confirmed reading plus maximum flow). Visible digits must match. A single candidate is taken;
    with several, the template evidence at the unclear positions must clearly favour one.
    Returns the completed string or ``whole`` unchanged.
    """
    if "?" not in whole or low is None or high is None or high < low:
        return whole
    if high - low > 100000:
        return whole
    digits = len(whole)
    open_positions = [index for index, char in enumerate(whole) if char == "?"]
    candidates = []
    for value in range(max(0, low), high + 1):
        text = str(value).zfill(digits)
        if len(text) != digits:
            break
        if all(char == "?" or char == text[index] for index, char in enumerate(whole)):
            candidates.append(text)
            if len(candidates) > MAX_CANDIDATES:
                return whole
    if not candidates:
        return whole
    if len(candidates) == 1:
        return candidates[0]
    if len(scores) != digits:
        return whole
    # A cell without a visible glyph (reflection, half-turned roller) carries no evidence.
    visible = [index for index in open_positions
               if scores[index] and max(scores[index].values()) >= VISIBLE_SCORE]
    if not visible:
        return whole
    rated = sorted(((sum(scores[index].get(text[index], -1.0) for index in visible), text)
                    for text in candidates), reverse=True)
    if rated[0][0] - rated[1][0] < ANCHOR_MARGIN:
        return whole
    return rated[0][1]
