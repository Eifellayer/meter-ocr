"""Read seven-segment (digital) displays without text recognition (0.5.0, shadow mode first).

Tesseract does not read seven-segment digits at all (test 21.11.2026: 1 of 8 digits). A digital
display needs no text recognition: each digit is seven fields that are on or off. This module
looks at those fields directly. It is pure image arithmetic, fast enough for a Raspberry Pi.
"""

from PIL import Image, ImageOps

# Segments: a top, b upper right, c lower right, d bottom, e lower left, f upper left, g middle.
DIGITS = {
    "abcdef": "0", "bc": "1", "abdeg": "2", "abcdg": "3", "bcfg": "4", "acdfg": "5",
    "acdefg": "6", "abc": "7", "abcdefg": "8", "abcdfg": "9",
    # Common variants: 6 without the top bar, 9 without the bottom bar, 7 with the upper left bar.
    "cdefg": "6", "abcfg": "9", "abcf": "7",
}
# Field of each segment inside the bounding box of the digit: (left, top, right, bottom) as fractions.
FIELDS = {
    "a": (.28, .00, .72, .14), "g": (.28, .43, .72, .57), "d": (.28, .86, .72, 1.0),
    "f": (.00, .14, .20, .43), "b": (.80, .14, 1.0, .43),
    "e": (.00, .57, .20, .86), "c": (.80, .57, 1.0, .86),
}
ON = .5          # share of ink in a field that counts as a lit segment
NARROW = .42     # a digit narrower than this share of its height is a "1"


def _threshold(histogram):
    """Otsu's threshold of a 256-bin histogram."""
    total = sum(histogram)
    weighted = sum(index * count for index, count in enumerate(histogram))
    best, best_value, below, below_sum = 127, -1.0, 0, 0
    for index, count in enumerate(histogram):
        below += count
        if not below or below == total:
            continue
        below_sum += index * count
        mean_low, mean_high = below_sum / below, (weighted - below_sum) / (total - below)
        value = below * (total - below) * (mean_low - mean_high) ** 2
        if value > best_value:
            best, best_value = index, value
    return best


def ink_mask(picture, light_digits=None):
    """Black-and-white picture with the lit segments white; None when there is no contrast.

    ``light_digits``: True for glowing digits on a dark display (LED), False for dark digits on
    a light display (LCD), None to decide by which of the two takes up less of the picture.
    """
    gray = picture.convert("L")
    low, high = gray.getextrema()
    if high - low < 40:
        return None
    limit = _threshold(gray.histogram())
    bright = gray.point(lambda value: 255 if value > limit else 0)
    if light_digits is None:
        light_digits = bright.histogram()[255] / (gray.width * gray.height) < .5
    return bright if light_digits else ImageOps.invert(bright)


def _extent(profile, minimum):
    """First and one-past-last index where the profile reaches ``minimum``, or None."""
    hits = [index for index, value in enumerate(profile) if value >= minimum]
    return (hits[0], hits[-1] + 1) if hits else None


def read_cell(mask):
    """The digit in one cell of an ink mask, "?" when the lit fields match no digit."""
    width, height = mask.size
    if width < 4 or height < 8:
        return "?"
    pixels = mask.load()
    columns = [sum(pixels[x, y] > 0 for y in range(height)) for x in range(width)]
    rows = [sum(pixels[x, y] > 0 for x in range(width)) for y in range(height)]
    if sum(columns) < width * height * .03:
        return "?"
    # Single specks do not move the bounding box; a thin bar (the top of a 7) still counts.
    vertical = _extent(rows, max(2, width * .04))
    if vertical is None:
        return "?"
    top, bottom = vertical
    # The decimal point sits at the bottom beside the digit: the width of the digit is taken
    # from its upper three quarters, so the point does not widen the bounding box.
    upper = top + max(1, round((bottom - top) * .75))
    upper_columns = [sum(pixels[x, y] > 0 for y in range(top, upper)) for x in range(width)]
    horizontal = _extent(upper_columns, max(2, height * .04))
    if horizontal is None:
        return "?"
    left, right = horizontal
    tall, wide = bottom - top, right - left
    if tall < height * .4:
        return "?"
    if wide < tall * NARROW:
        # Only the two right bars: a one. Both halves must be lit, else it is a fragment.
        upper = sum(rows[top:top + tall // 2]) / max(1, wide * (tall // 2))
        lower = sum(rows[top + tall // 2:bottom]) / max(1, wide * (tall - tall // 2))
        return "1" if upper >= .35 and lower >= .35 else "?"
    lit = ""
    for name in "abcdefg":
        x0, y0, x1, y1 = FIELDS[name]
        box = (left + round(x0 * wide), top + round(y0 * tall),
               max(left + round(x0 * wide) + 1, left + round(x1 * wide)),
               max(top + round(y0 * tall) + 1, top + round(y1 * tall)))
        field = mask.crop(box)
        if field.histogram()[255] / (field.width * field.height) >= ON:
            lit += name
    return DIGITS.get(lit, "?")


def display_polarity(register, boxes):
    """True for glowing digits on a dark display, False for dark digits on a light one."""
    left, top = min(box[0] for box in boxes), min(box[1] for box in boxes)
    right, bottom = max(box[2] for box in boxes), max(box[3] for box in boxes)
    gray = register.convert("L").crop((left, top, right, bottom))
    limit = _threshold(gray.histogram())
    # The digits take up less of the display than its background.
    return sum(gray.histogram()[limit + 1:]) / max(1, gray.width * gray.height) < .5


def read_digits(register, boxes, light_digits=None):
    """One character per frame, read from the lit segments ("?" where unclear)."""
    boxes = [tuple(box) for box in boxes]
    usable = [box for box in boxes if box[2] > box[0] and box[3] > box[1]]
    if not usable:
        return "?" * len(boxes)
    if light_digits is None:
        light_digits = display_polarity(register, usable)
    result = ""
    for box in boxes:
        # Each frame gets its own threshold: light falls unevenly on a display.
        mask = ink_mask(register.crop(box), light_digits) if box in usable else None
        result += read_cell(mask) if mask is not None else "?"
    return result


def read_display(register, boxes, whole_digits, light_digits=None):
    """The reading as text with the decimal point after ``whole_digits`` digits."""
    digits = read_digits(register, boxes, light_digits)
    return digits[:whole_digits] + "." + digits[whole_digits:] if len(digits) > whole_digits else digits
