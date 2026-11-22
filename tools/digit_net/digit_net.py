"""Small built-in digit recognizer for blurred roller digits (complements Tesseract).

A compact convolutional network, trained offline on synthetic, heavily blurred roller digits
(various fonts, glare, neighbouring rollers, JPEG noise). It runs in pure Python without extra
packages. Class 10 means "no single digit" (roller between two digits, glare, empty).
The weights live in ``digit_net.json``; see tools/digit_net/ in the repository for training.
"""

from array import array
import base64
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps

FW, FH = 16, 24
CONFIDENT = 0.9
WEIGHTS = Path(__file__).with_name("digit_net.json")


def glyph_channel(picture, light=True):
    """Greyscale with the glyph bright: minimum of the colour channels for light digits.

    Red decimal fields and coloured light turn dark in the minimum, white digits stay bright.
    """
    if picture.mode != "L":
        r, g, b = picture.convert("RGB").split()
        if light:
            return ImageChops.darker(ImageChops.darker(r, g), b)
        return ImageOps.invert(ImageChops.lighter(ImageChops.lighter(r, g), b))
    return picture if light else ImageOps.invert(picture)


def glyph_image(picture, light=True):
    gray = glyph_channel(picture, light)
    if gray.height != 48:
        gray = gray.resize((max(8, round(gray.width * 48 / gray.height)), 48), Image.Resampling.BILINEAR)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    opened = gray.filter(ImageFilter.MinFilter(15)).filter(ImageFilter.MaxFilter(15))
    return ImageOps.autocontrast(ImageChops.subtract(gray, opened), cutoff=1)


def features(picture, light=True):
    small = glyph_image(picture, light).resize((FW, FH), Image.Resampling.BOX)
    values = list(small.tobytes())
    count = len(values)
    mean = sum(values) / count
    std = (sum((value - mean) ** 2 for value in values) / count) ** .5 or 1.0
    return [(value - mean) / std for value in values]


@lru_cache(maxsize=1)
def _weights():
    try:
        data = json.loads(WEIGHTS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    tensors = {}
    for name, item in data["tensors"].items():
        raw = array("b", base64.b64decode(item["data"]))
        scale = item["scale"]
        tensors[name] = ([value * scale for value in raw], item["shape"])
    return data["layout"], tensors


def _forward(x, model):
    (c1, c2, hidden, classes), t = model
    k1, b1 = t["k1"][0], t["b1"][0]
    k2, b2 = t["k2"][0], t["b2"][0]
    w3, b3 = t["w3"][0], t["b3"][0]
    w4, b4 = t["w4"][0], t["b4"][0]
    H, W = FH, FW
    # conv 5x5 (1 -> c1), padding 2, ReLU, 2x2 max pool
    padded = [[0.0] * (W + 4) for _ in range(H + 4)]
    for y in range(H):
        padded[y + 2][2:W + 2] = x[y * W:(y + 1) * W]
    act1 = [[[0.0] * c1 for _ in range(W)] for _ in range(H)]
    for y in range(H):
        for xx in range(W):
            patch = [padded[y + i][xx + j] for i in range(5) for j in range(5)]
            row = act1[y][xx]
            for c in range(c1):
                total = b1[c]
                for index, value in enumerate(patch):
                    if value:
                        total += value * k1[index * c1 + c]
                row[c] = total if total > 0 else 0.0
    H2, W2 = H // 2, W // 2
    pool1 = [[[max(act1[2 * y][2 * xx][c], act1[2 * y][2 * xx + 1][c], act1[2 * y + 1][2 * xx][c],
                   act1[2 * y + 1][2 * xx + 1][c]) for c in range(c1)] for xx in range(W2)] for y in range(H2)]
    zero = [0.0] * c1
    act2 = [[[0.0] * c2 for _ in range(W2)] for _ in range(H2)]
    for y in range(H2):
        for xx in range(W2):
            patch = []
            # im2col order: channel-major, then 3x3 kernel position
            cells = [pool1[y + i][xx + j] if 0 <= y + i < H2 and 0 <= xx + j < W2 else zero
                     for i in (-1, 0, 1) for j in (-1, 0, 1)]
            for c in range(c1):
                for cell in cells:
                    patch.append(cell[c])
            row = act2[y][xx]
            for c in range(c2):
                total = b2[c]
                for index, value in enumerate(patch):
                    if value:
                        total += value * k2[index * c2 + c]
                row[c] = total if total > 0 else 0.0
    H3, W3 = H2 // 2, W2 // 2
    flat = []
    for y in range(H3):
        for xx in range(W3):
            for c in range(c2):
                flat.append(max(act2[2 * y][2 * xx][c], act2[2 * y][2 * xx + 1][c],
                                act2[2 * y + 1][2 * xx][c], act2[2 * y + 1][2 * xx + 1][c]))
    hid = []
    for h in range(hidden):
        total = b3[h]
        for index, value in enumerate(flat):
            if value:
                total += value * w3[index * hidden + h]
        hid.append(total if total > 0 else 0.0)
    logits = []
    for k in range(classes):
        total = b4[k]
        for index, value in enumerate(hid):
            if value:
                total += value * w4[index * classes + k]
        logits.append(total)
    top = max(logits)
    from math import exp
    exps = [exp(value - top) for value in logits]
    total = sum(exps)
    return [value / total for value in exps]


_cache = {}


def probabilities(picture, light=True):
    model = _weights()
    if model is None or picture.width < 4 or picture.height < 6:
        return None
    key = (hashlib.sha256(picture.tobytes()).digest(), picture.mode, picture.size, light)
    cached = _cache.get(key)
    if cached is None:
        cached = _forward(features(picture, light), model)
        if len(_cache) > 512:
            _cache.clear()
        _cache[key] = cached
    return cached


def classify(picture, light=True, *, either_polarity=False):
    """Return (digit or None, probability). None when unsure or not a single digit."""
    options = (light, not light) if either_polarity else (light,)
    best = (None, 0.0)
    confident = []
    for polarity in options:
        probs = probabilities(picture, polarity)
        if probs is None:
            continue
        index = max(range(len(probs)), key=probs.__getitem__)
        if probs[index] >= CONFIDENT and index < 10:
            confident.append((str(index), probs[index]))
        if probs[index] > best[1]:
            best = (str(index) if index < 10 else None, probs[index])
    if len({digit for digit, _ in confident}) > 1:
        return None, 0.0
    if confident:
        return confident[0]
    return None, best[1]
