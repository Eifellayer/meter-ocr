"""Orientation of the camera picture from the meter's labels and red decimal rollers (0.5.37).

Shadow mode only: after a setup is saved, this guesses how the picture would have to be turned
or mirrored and compares that with what the setup saved. Nothing is changed from it; the result
goes to the shadow log so the cues can be judged on real meters first.

- Labels: Tesseract's orientation detection (OSD) on the whole picture tells by how many degrees
  clockwise the printed text must be turned to stand upright. Mirrored text reads as another
  script with low confidence; the mirrored picture is tried as well.
- Red rollers: many gas meters show the decimals on red rollers. On an upright strip they sit on
  the right; a strip turned by 180° shows them on the left.
"""

import io
import re
import subprocess

from PIL import Image, ImageOps, ImageStat

OSD_TIMEOUT = 20
# OSD confidence below which its answer carries no evidence.
OSD_CONFIDENT = 1.5
# Mirrored labels count only when the mirrored picture reads clearly better.
MIRROR_LEAD = 1.0
# Mean redness (red minus the mean of green and blue, 0–255) a side needs ahead of the other.
RED_LEAD = 18.0
MAX_SIDE = 1600


def osd(image):
    """Tesseract orientation of the printed text: {"rotate", "confidence", "script"} or {"error"}."""
    picture = ImageOps.grayscale(image)
    scale = min(1.0, MAX_SIDE / max(picture.size))
    if scale < 1.0:
        picture = picture.resize((max(1, round(picture.width * scale)), max(1, round(picture.height * scale))))
    with io.BytesIO() as buffer:
        picture.save(buffer, "PNG")
        data = buffer.getvalue()
    try:
        result = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "0", "--dpi", "150"],
                                input=data, capture_output=True, timeout=OSD_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as error:
        return {"error": type(error).__name__}
    text = result.stdout.decode("utf-8", errors="ignore")
    rotate = re.search(r"Rotate:\s*(\d+)", text)
    confidence = re.search(r"Orientation confidence:\s*([0-9.]+)", text)
    script = re.search(r"Script:\s*(\S+)", text)
    if not rotate or not confidence:
        return {"error": "no_text"}
    return {"rotate": int(rotate.group(1)) % 360, "confidence": round(float(confidence.group(1)), 2),
            "script": script.group(1) if script else None}


def label_guess(image):
    """Clockwise turn and mirroring the labels suggest, with both OSD answers; None fields when unclear."""
    plain, mirrored = osd(image), osd(ImageOps.mirror(image))
    guess = {"osd": plain, "osd_mirrored": mirrored, "rotate": None, "mirror": None}
    plain_confidence = plain.get("confidence") or 0.0
    mirrored_confidence = mirrored.get("confidence") or 0.0
    plain_latin = plain_confidence >= OSD_CONFIDENT and plain.get("script") == "Latin"
    if (mirrored_confidence >= OSD_CONFIDENT and mirrored.get("script") == "Latin" and not plain_latin
            and mirrored_confidence >= plain_confidence + MIRROR_LEAD):
        guess.update(rotate=mirrored["rotate"], mirror=True)
    elif plain_confidence >= OSD_CONFIDENT and plain.get("script") in ("Latin", None):
        guess.update(rotate=plain["rotate"], mirror=False)
    return guess


def redness(register, box):
    left, top, right, bottom = (int(value) for value in box)
    if right - left < 3 or bottom - top < 3:
        return None
    red, green, blue = ImageStat.Stat(register.convert("RGB").crop((left, top, right, bottom))).mean
    return red - (green + blue) / 2


def red_side(register, whole_boxes, fraction_boxes):
    """Where the red rollers are on the strip as saved: "right" (upright), "left" or None.

    The first and the last cells are compared, as many as there are decimals: upright the
    decimals are the last ones, on a strip turned by 180° the first ones.
    """
    cells = [redness(register, box) for box in [*whole_boxes, *fraction_boxes]]
    count = len(fraction_boxes)
    if not count or len(cells) < 2 * count or any(value is None for value in cells):
        return {"side": None}
    first, last = sum(cells[:count]) / count, sum(cells[-count:]) / count
    side = "right" if last >= first + RED_LEAD else "left" if first >= last + RED_LEAD else None
    return {"side": side, "first": round(first, 1), "last": round(last, 1)}


def frame_turn(rotation):
    """The clockwise quarter turn nearest to the saved frame's rotation (frames turn clockwise)."""
    return round((rotation or 0) / 90) * 90 % 360


def compare(guess, red, frame_rotation):
    """Whether the cues agree with the saved setup: True, False, or None without usable evidence."""
    verdicts = []
    if guess.get("rotate") is not None:
        verdicts.append(guess["rotate"] == frame_turn(frame_rotation) and guess.get("mirror") is False)
    if red.get("side") is not None:
        verdicts.append(red["side"] == "right")
    if not verdicts:
        return None
    return all(verdicts)


def check(picture, register, whole_boxes, fraction_boxes, frame_rotation, rules):
    """Shadow entry fields for one saved setup: shadow, established, agree."""
    with Image.open(io.BytesIO(picture)) as image:
        image.load()
        guess = label_guess(image.convert("RGB"))
    red = red_side(register, whole_boxes, fraction_boxes)
    established = {"image_rotation": rules.get("image_rotation", 0), "image_mirrored": bool(rules.get("image_mirrored")),
                   "frame_rotation": frame_rotation, "frame_turn": frame_turn(frame_rotation)}
    return {"labels": guess, "red_rollers": red}, established, compare(guess, red, frame_rotation)
