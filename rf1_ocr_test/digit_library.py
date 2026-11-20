"""Digit shapes learned from this meter's own confirmed readings (0.4.0, Experiment 2).

The first decimal digit "8" of Stefan's meter is sometimes read, sometimes not ("10492.?5?",
20.11.). Generic font templates do not match this blurred roller well, but the same "8" was read
surely on many confirmed checks. After every confirmed automatic check the app keeps a running
average of each digit cell that both OCR profiles read the same, and an unclear cell is filled
only when it matches one learned digit clearly better than all others. No extra pictures; the
value still has to pass the usual cross-check with a second picture and the flow plausibility.
"""

import json
import math
import threading

from PIL import Image

from glyph_match import contrast_image

SIZE = (20, 28)
CORE = (16, 24)
MIN_SAMPLES = 3
# Fill only once most digits are known: an unknown digit must not look like its nearest known one.
MIN_DIGITS = 8
MAX_WEIGHT = 30
ACCEPT_SCORE = .85
ACCEPT_MARGIN = .06


def _unit(values):
    mean = sum(values) / len(values)
    centred = [value - mean for value in values]
    norm = math.sqrt(sum(value * value for value in centred))
    return [value / norm for value in centred] if norm > 1e-6 else None


def feature(crop, bright):
    """Zero-mean, unit-length local-contrast image of a digit cell at a fixed size."""
    if crop.width < 6 or crop.height < 10:
        return None
    image = contrast_image(crop, bright).resize(SIZE, Image.Resampling.BILINEAR)
    return _unit([float(value) for value in image.tobytes()])


class DigitLibrary:
    def __init__(self, path=None):
        self.path = path
        self.lock = threading.Lock()
        self.digits = {}
        self.filled = 0
        if path is not None:
            self.load()

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.digits = {digit: {"n": int(entry["n"]), "v": [float(value) for value in entry["v"]]}
                           for digit, entry in data.get("digits", {}).items()
                           if digit in "0123456789" and len(entry["v"]) == SIZE[0] * SIZE[1]}
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            self.digits = {}

    def save(self):
        if self.path is None:
            return
        try:
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"digits": self.digits}), encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            pass

    def clear(self):
        with self.lock:
            self.digits = {}
            self.filled = 0
        if self.path is not None:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass

    def learn(self, cells, bright):
        """Add confirmed (crop, digit) pairs; returns how many were learned."""
        learned = 0
        with self.lock:
            for crop, digit in cells:
                if digit not in tuple("0123456789"):
                    continue
                vector = feature(crop, bright)
                if vector is None:
                    continue
                entry = self.digits.get(digit)
                if entry is None:
                    self.digits[digit] = {"n": 1, "v": vector}
                else:
                    weight = min(entry["n"], MAX_WEIGHT)
                    merged = _unit([(old * weight + new) / (weight + 1) for old, new in zip(entry["v"], vector)])
                    if merged is not None:
                        entry["v"] = merged
                        entry["n"] += 1
                learned += 1
        if learned:
            self.save()
        return learned

    def samples(self):
        with self.lock:
            return {digit: entry["n"] for digit, entry in sorted(self.digits.items())}

    def scores(self, crop, bright):
        """{digit: best correlation over small shifts} for digits with enough samples."""
        with self.lock:
            known = {digit: entry["v"] for digit, entry in self.digits.items() if entry["n"] >= MIN_SAMPLES}
        if len(known) < MIN_DIGITS:
            return {}
        if crop.width < 6 or crop.height < 10:
            return {}
        image = contrast_image(crop, bright).resize(SIZE, Image.Resampling.BILINEAR)
        pixels = [float(value) for value in image.tobytes()]
        width, height = SIZE
        core_w, core_h = CORE
        result = {}
        for digit, vector in known.items():
            best = -1.0
            core = _unit([vector[(y + 2) * width + x + 2] for y in range(core_h) for x in range(core_w)])
            if core is None:
                continue
            for dy in range(height - core_h + 1):
                for dx in range(width - core_w + 1):
                    window = _unit([pixels[(y + dy) * width + x + dx] for y in range(core_h) for x in range(core_w)])
                    if window is None:
                        continue
                    score = sum(a * b for a, b in zip(core, window))
                    best = max(best, score)
            result[digit] = best
        return result

    def fill(self, crop, bright, generic=None):
        """The learned digit for an unclear cell, or None when it is not clearly one digit.

        ``generic`` are the font-template scores of the same cell; a clear other digit there vetoes.
        """
        scores = self.scores(crop, bright)
        if len(scores) < 2:
            return None
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        (digit, best), (_, second) = ranked[0], ranked[1]
        if generic:
            other, other_score = max(generic.items(), key=lambda item: item[1])
            if other != digit and other_score >= .72 and other_score - generic.get(digit, 0.0) >= .08:
                return None
        if best >= ACCEPT_SCORE and best - second >= ACCEPT_MARGIN:
            with self.lock:
                self.filled += 1
            return digit
        return None

    def take_filled(self):
        with self.lock:
            count, self.filled = self.filled, 0
        return count


LIBRARY = DigitLibrary()
