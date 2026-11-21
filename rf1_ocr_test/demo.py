"""Local OCR demonstration with a generated meter and no live inputs."""

import base64
from io import BytesIO
import time

from PIL import Image, ImageDraw, ImageFont

from checks import OCR_PROFILES, provisional_digit_estimate, read_register
from layout import turn_crop

DEMO_READING = "12344.942"
DEMO_ANGLE = 5
# The demo shares the processor with the automatic checks and a running setup.
DEMO_SECONDS = 40
_complete = {}


def run_demo(reflection=False):
    """Read the generated meter; only a complete result is kept for the next call.

    A result cut short by a busy machine used to be cached for good and the first
    request could run into the time limit ("Die Demo konnte nicht geladen werden").
    """
    reflection = bool(reflection)
    if reflection in _complete:
        return _complete[reflection]
    digits = DEMO_READING.replace(".", "")
    image = Image.new("RGB", (600, 128), "#263844")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((7, 12, 592, 116), radius=12, fill="#344d5b")
    font = ImageFont.truetype("DejaVuSansMono-Bold.ttf", 62)
    boxes = []
    for index, digit in enumerate(digits):
        left = 32 + 68 * index + (12 if index >= 5 else 0)
        box = (left, 24, left + 61, 104)
        boxes.append(box)
        draw.rectangle(box, fill="#742d2c" if index >= 5 else "#0e1821")
        draw.text((left + 30, 64), digit, font=font, fill="#f6f6ed", anchor="mm")
    if reflection:
        draw.rectangle(boxes[-1], fill="#fffaf0")
    slanted = turn_crop(image, DEMO_ANGLE)
    straight = turn_crop(slanted, -DEMO_ANGLE)
    dx, dy = (straight.width - image.width) // 2, (straight.height - image.height) // 2
    straight = straight.crop((dx, dy, dx + image.width, dy + image.height))
    reads = []
    deadline = time.monotonic() + DEMO_SECONDS
    for profile in OCR_PROFILES[:2]:
        row = "".join(read_register(straight.crop(box), True, 1, force_polarity=True, profile=profile, deadline=deadline) or "?"
                      for box in boxes)
        reads.append(row[:5] + "." + row[5:])
    result = "".join(a if a == b else "?" for a, b in zip(*reads))
    estimate = (provisional_digit_estimate(result, reads, 1001, {"time": 1000, "value": int(digits)},
                                          3, 5, 100) if reflection else None)

    def encode(picture):
        with BytesIO() as buffer:
            picture.save(buffer, "JPEG", quality=90)
            return base64.b64encode(buffer.getvalue()).decode()

    marked = straight.copy()
    overlay = ImageDraw.Draw(marked)
    for index, box in enumerate(boxes):
        overlay.rectangle(box, outline="#e9ac47" if result.replace(".", "")[index] == "?" else "#6ee7ae", width=2)

    answer = {"image": encode(slanted), "aligned": encode(marked), "reading": result,
              "angle": -DEMO_ANGLE, "attempts": reads, "expected": DEMO_READING,
              "estimate": estimate["reading"] if estimate else None}
    hidden = 1 if reflection else 0
    if result.count("?") <= hidden and time.monotonic() < deadline:
        _complete[reflection] = answer
    return answer
