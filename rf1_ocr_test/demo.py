"""Local OCR demonstration with a generated meter and no live inputs."""

import base64
from pathlib import Path
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


def run_demo(reflection=False, draw=None):
    """Read the generated meter; only a complete result is kept for the next call.

    A result cut short by a busy machine used to be cached for good and the first
    request could run into the time limit ("Die Demo konnte nicht geladen werden").
    ``draw`` is the automatic check's own picture of the read digits (0.5.33); without it the
    digit frames are only outlined.
    """
    reflection = bool(reflection)
    if (reflection, draw is not None) in _complete:
        return _complete[reflection, draw is not None]
    digits = DEMO_READING.replace(".", "")
    image = Image.new("RGB", (600, 128), "#263844")
    canvas = ImageDraw.Draw(image)
    canvas.rounded_rectangle((7, 12, 592, 116), radius=12, fill="#344d5b")
    font = ImageFont.truetype("DejaVuSansMono-Bold.ttf", 62)
    boxes = []
    for index, digit in enumerate(digits):
        left = 32 + 68 * index + (12 if index >= 5 else 0)
        box = (left, 24, left + 61, 104)
        boxes.append(box)
        canvas.rectangle(box, fill="#742d2c" if index >= 5 else "#0e1821")
        canvas.text((left + 30, 64), digit, font=font, fill="#f6f6ed", anchor="mm")
    if reflection:
        canvas.rectangle(boxes[-1], fill="#fffaf0")
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

    if draw is not None:
        marked = draw(straight, boxes[5][0], boxes[:5], boxes[5:], result, 5, 3, readings=reads)
    else:
        marked = straight.copy()
        overlay = ImageDraw.Draw(marked)
        for index, box in enumerate(boxes):
            overlay.rectangle(box, outline="#e9ac47" if result.replace(".", "")[index] == "?" else "#6ee7ae", width=2)

    answer = {"image": encode(slanted), "aligned": encode(marked), "reading": result,
              "angle": -DEMO_ANGLE, "attempts": reads, "expected": DEMO_READING,
              "estimate": estimate["reading"] if estimate else None, "styled": draw is not None}
    hidden = 1 if reflection else 0
    if result.count("?") <= hidden and time.monotonic() < deadline:
        _complete[reflection, draw is not None] = answer
    return answer


# --- Real camera pictures (0.5.0) -------------------------------------------------------
# Four pictures of a real gas meter. Only the register window is left; serial number, bar
# code and the rest of the meter are painted over. The frames below are what the app's own
# setup found on these pictures.
REAL_IMAGES = Path(__file__).parent / "demo_images"
REAL_COUNT = 4
REAL_LAYOUT = {"box": (195, 190, 666, 369), "width": 286, "rotation": -11,
               "digit_boxes": [[50, 375, 127, 603], [155, 378, 231, 603], [268, 378, 348, 599],
                               [372, 378, 453, 599], [473, 386, 557, 599], [594, 386, 684, 596],
                               [718, 386, 805, 596], [853, 390, 944, 592]]}
REAL_SECONDS = 60  # a real picture needs 14 digit reads; a small or busy machine takes a while
REAL_DECIMALS = 2  # the last roller turns all the time; the routine check does not read it either
_real_complete = {}


def _jpeg(picture):
    with BytesIO() as buffer:
        picture.save(buffer, "JPEG", quality=90)
        return base64.b64encode(buffer.getvalue()).decode()


def run_real_demo(number, select, read, seconds=REAL_SECONDS, draw=None):
    """Read one of the real pictures the way the automatic check does.

    ``select`` and ``read`` are the app's own ``select_register`` and ``read_visible_digits``
    (handed in by the worker; this module must not import it). Digits that are not read
    within ``seconds`` stay open; such a result is shown but not kept.
    """
    if type(number) is not int or not 1 <= number <= REAL_COUNT:
        raise ValueError("unbekanntes Demobild")
    if (number, draw is not None) in _real_complete:
        return _real_complete[number, draw is not None]
    with Image.open(REAL_IMAGES / f"gas-{number}.png") as stored:
        strip = stored.convert("RGB")
    frame = Image.new("RGB", (800, 600), (188, 190, 196))
    frame.paste(strip, (150, 150))
    register, width, whole_boxes, fraction_boxes, _ = select(
        frame, None, REAL_LAYOUT["box"], REAL_LAYOUT["width"], REAL_LAYOUT["rotation"], 5, 3,
        digit_boxes=REAL_LAYOUT["digit_boxes"])
    deadline = time.monotonic() + seconds
    reads = [str(read(register, width, whole_boxes, fraction_boxes, False, "auto", profile=profile,
                      whole_digits=5, fraction_digits=REAL_DECIMALS, deadline=deadline, prefer_boxes=True))
             for profile in OCR_PROFILES[:2]]
    result = "".join(a if a == b else "?" for a, b in zip(*reads)) if len(set(map(len, reads))) == 1 else reads[0]
    digits = result.replace(".", "")
    if draw is not None:
        # 0.5.33: the same picture as the automatic check; the turning last roller is grey.
        marked = draw(register, width, whole_boxes, fraction_boxes, result, 5, 3, readings=reads,
                      quiet_slots=range(5 + REAL_DECIMALS, 8))
    else:
        marked = register.copy()
        overlay = ImageDraw.Draw(marked)
        for index, box in enumerate([*whole_boxes, *fraction_boxes]):
            skipped = index >= len(digits)
            overlay.rectangle(tuple(box), width=2, outline="#8a97a0" if skipped else
                              "#e9ac47" if digits[index] == "?" else "#6ee7ae")
    answer = {"image": _jpeg(strip), "aligned": _jpeg(marked), "reading": result, "attempts": reads,
              "angle": REAL_LAYOUT["rotation"], "expected": None, "estimate": None, "real": True,
              "complete": "?" not in result, "styled": draw is not None}
    if answer["complete"] and time.monotonic() < deadline:
        _real_complete[number, draw is not None] = answer
    return answer
