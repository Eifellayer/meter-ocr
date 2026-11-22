"""Standstill by picture comparison, shadow mode only (Stefan 22.11., 11:48).

"Wenn das eine Bild eine hundertprozentige Übereinstimmung mit dem nächsten hat, von der Stellung
der Rollen her, kann man sich die nächste Prüfung schenken." This module only measures: it
compares every roller of the register strip with the same roller of the previous check and
reports the grey-value difference per roller. Nothing is decided from it yet; the result goes to
the debug log (field ``stationary``) so the threshold can be chosen from real pictures first.
A value is never invented from "picture unchanged".
"""

from PIL import ImageChops, ImageOps, ImageStat

# Mean absolute grey difference (0–255) below which a roller counts as unchanged. A first guess
# from flash and sensor noise; to be checked against the debug log before it is used for anything.
SAME_THRESHOLD = 12.0
# Small camera or crop jitter: compare with shifts of up to this many pixels and keep the best.
MAX_SHIFT = 3
SIZE = (24, 40)


def _roller(register, box):
    left, top, right, bottom = (int(value) for value in box)
    if right - left < 4 or bottom - top < 4:
        return None
    return ImageOps.grayscale(register.crop((left, top, right, bottom)))


def _difference(before, after):
    """Smallest mean difference over small shifts of the later picture, both scaled to one size."""
    best = None
    width, height = after.size
    for dx in range(-MAX_SHIFT, MAX_SHIFT + 1, MAX_SHIFT):
        for dy in range(-MAX_SHIFT, MAX_SHIFT + 1, MAX_SHIFT):
            box = (max(0, dx), max(0, dy), min(width, width + dx), min(height, height + dy))
            moved = after.crop(box).resize(SIZE)
            shown = before.crop((max(0, -dx), max(0, -dy), min(width, width - dx),
                                 min(height, height - dy))).resize(SIZE)
            value = ImageStat.Stat(ImageChops.difference(shown, moved)).mean[0]
            best = value if best is None else min(best, value)
    return best


def compare(previous, current, *, threshold=SAME_THRESHOLD):
    """Compare two checks ``{"register": image, "boxes": [...], "image": time}``; None if not comparable.

    Returns ``{"against": time, "diff": [per roller], "moving": [1-based positions], "stationary": bool}``.
    Only frames of the same layout (same number of boxes, same box sizes) are compared.
    """
    if not previous or not current:
        return None
    old_boxes, new_boxes = previous.get("boxes") or [], current.get("boxes") or []
    if not old_boxes or len(old_boxes) != len(new_boxes):
        return None
    if previous.get("register") is None or current.get("register") is None:
        return None
    if previous["register"].size != current["register"].size:
        return None
    diffs = []
    for old_box, new_box in zip(old_boxes, new_boxes):
        if tuple(old_box) != tuple(new_box):
            return None
        before, after = _roller(previous["register"], old_box), _roller(current["register"], new_box)
        if before is None or after is None:
            return None
        diffs.append(round(_difference(before, after), 1))
    moving = [index + 1 for index, value in enumerate(diffs) if value >= threshold]
    return {"against": previous.get("image"), "diff": diffs, "moving": moving, "stationary": not moving,
            "threshold": threshold}
