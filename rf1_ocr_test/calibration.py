"""Bounded search for a reproducible meter crop and rotation."""

from dataclasses import dataclass, field
from hashlib import sha256
from math import ceil, cos, floor, radians, sin
import subprocess

from checks import OCR_PROFILES, compare_sample, meter_prefix, read_with_retries
from consumption import accumulate_consumption
from checks import crop_register
from layout import crop_coordinates, find_digit_row, find_raw_digit_row, normalize_digit_boxes, rotated_width, turn_crop

from meter_learning import propose_digit_boxes

DEFAULT_LIMIT = 100
MIN_IMAGES = 3
MIN_IMAGE_LIMIT = MIN_IMAGES + 1
MAX_IMAGES = 100
MAX_ATTEMPTS = 100
TIME_LIMIT = 15 * 60
CAPTURE_INTERVAL = 5
ANGLES = (-3, 3, -6, 6, -12, 12, -18, 18, 90, -90, 180)
MAX_LAYOUTS_PER_IMAGE = 4


@dataclass(frozen=True)
class Layout:
    box: tuple[int, int, int, int]
    rotation: int
    width: int
    digit_boxes: tuple = ()

    def settings(self):
        return {"crop_mode": "manual", "crop": ",".join(map(str, self.box)),
                "rotation": self.rotation, "width": self.width, "digit_boxes": list(self.digit_boxes)}


def unrotate_box(box, size, angle):
    """Convert a box in a center-rotated image to bounds in the original."""
    if angle == 0:
        return box
    w, h = size
    left, top, right, bottom = box
    c, s = cos(radians(angle)), sin(radians(angle))
    points = [(c * (x - w / 2) + s * (y - h / 2) + w / 2,
               -s * (x - w / 2) + c * (y - h / 2) + h / 2)
              for x in (left, right) for y in (top, bottom)]
    xs, ys = zip(*points)
    return max(0, floor(min(xs))), max(0, floor(min(ys))), min(w, ceil(max(xs))), min(h, ceil(max(ys)))


def layouts(frame, overlay, rules, offset, current=None):
    """Try a few geometry candidates per image, rotating the search across images."""
    emitted = set()

    def candidate(box, angle, padding=0):
        left, top, right, bottom = box
        box = (max(0, left - padding), max(0, top - padding),
               min(frame.width, right + padding), min(frame.height, bottom + padding))
        span = rotated_width(box[2] - box[0], box[3] - box[1], angle)
        width = max(1, round(span * rules["integer_digits"] /
                             (rules["integer_digits"] + rules["fraction_digits"])))
        return Layout(box, angle, width)

    def unique(layout):
        if layout in emitted or layout.box[2] - layout.box[0] < 8 or layout.box[3] - layout.box[1] < 8:
            return False
        emitted.add(layout)
        return True

    if current is not None and unique(current):
        yield current
    first = offset % len(ANGLES)
    if overlay is not None and overlay.size == frame.size:
        found = find_digit_row(overlay, rules["integer_digits"], rules["fraction_digits"])
        if found:
            left, top, right, bottom = found[0]
            layout = Layout(found[0], 0, found[1],
                            normalize_digit_boxes(found[2], (right - left, bottom - top)))
            if unique(layout):
                yield layout
    for angle in (ANGLES[first], 0, ANGLES[(first + 1) % len(ANGLES)]):
        if len(emitted) >= MAX_LAYOUTS_PER_IMAGE:
            return
        adjusted = turn_crop(frame, angle, expand=False)
        detected = find_raw_digit_row(adjusted, rules["integer_digits"], rules["fraction_digits"])
        if detected:
            box = unrotate_box(detected[0], frame.size, angle)
            left, top, right, bottom = box
            frames = normalize_digit_boxes(detected[2], (right - left, bottom - top)) if angle == 0 else ()
            alternate = candidate(box, angle, padding=2)
            turned = turn_crop(crop_register(frame, alternate.box), angle)
            optimized = propose_digit_boxes(turned, [], alternate.width, rules["integer_digits"], rules["fraction_digits"])
            variants = (Layout(box, angle, detected[1], frames),
                        Layout(alternate.box, angle, alternate.width, tuple(map(tuple, optimized))))
            for layout in variants:
                if len(emitted) >= MAX_LAYOUTS_PER_IMAGE:
                    return
                if unique(layout):
                    yield layout
    if len(emitted) < MAX_LAYOUTS_PER_IMAGE and rules["crop_mode"] == "manual":
        box = crop_coordinates(rules["crop"], rules["width"], rules["rotation"])
        trial = candidate(box, ANGLES[first], padding=2)
        if unique(trial):
            yield trial


@dataclass
class Calibration:
    limit: int
    started: float
    state: str = "waiting"
    stage: str = "queued"
    rotation: int | None = None
    variant: int | None = None
    seen: set = field(default_factory=set)
    last_stamp: float = 0
    candidate: Layout | None = None
    counter: dict = field(default_factory=dict)
    confirmations: int = 0
    attempts: int = 0
    best: Layout | None = None
    best_confirmations: int = 0
    anchored: bool = False
    advanced: bool = False
    verification_pending: bool = False

    def expired(self, now):
        return now - self.started >= TIME_LIMIT

    def status(self, now):
        return {"state": self.state, "stage": self.stage, "rotation": self.rotation, "variant": self.variant,
                "tested": len(self.seen), "limit": self.limit, "duration": TIME_LIMIT,
                "attempts": self.attempts, "max_attempts": MAX_ATTEMPTS,
                "confirmations": self.confirmations, "required": MIN_IMAGES,
                "seconds": max(0, ceil(TIME_LIMIT - (now - self.started)))}

    def remember_image(self, frame, stamp):
        digest = sha256(frame.convert("RGB").tobytes()).digest()
        if stamp <= self.last_stamp or digest in self.seen:
            return False
        self.seen.add(digest)
        self.last_stamp = stamp
        return True

    def verify(self, frame, sample, stamp, rules, read, stop, on_image=None):
        """Confirm the exact saved geometry with the regular OCR retry routine."""
        if self.attempts >= MAX_ATTEMPTS or not self.remember_image(frame, stamp):
            return None
        self.attempts += 1
        if on_image is not None:
            on_image()
        has_reference = sample.get("reference_required") is not False
        precision = rules["decimals"] if has_reference else rules["fraction_digits"]
        digits = rules["integer_digits"]
        try:
            value, confirmed, _ = read_with_retries(
                lambda profile: read(self.candidate, profile), sample, precision,
                max_attempts=max(2, rules["attempts"]), standalone=not has_reference,
                integer_digits=digits, stop_before_attempt=stop,
            )
            status, _ = compare_sample(sample, value, precision, ocr_confirmed=confirmed, integer_digits=digits)
            if status != ("match" if has_reference else "ocr_only") or (has_reference and not sample.get("reference_time")):
                raise ValueError("Unconfirmed crop")
            accumulate_consumption(self.counter, "calibration", stamp, value, precision,
                                   rules["max_flow_lph"], digits)
        except (OSError, ValueError, subprocess.SubprocessError):
            self.verification_pending = False
            self.candidate, self.counter = None, {}
            self.confirmations, self.anchored, self.advanced = 0, False, False
            return None
        return self.candidate

    def examine(self, frame, overlay, sample, stamp, rules, read, stop, baseline=None, on_attempt=None,
                on_image=None):
        """Return a verified layout, checking two OCR profiles per distinct image."""
        if not self.remember_image(frame, stamp):
            return None
        if on_image is not None:
            on_image()
        has_reference = sample.get("reference_required") is not False
        # Without an outside reference, read every displayed digit to check movement.
        precision = rules["decimals"] if has_reference else rules["fraction_digits"]
        digits = rules["integer_digits"]
        flow = rules["max_flow_lph"]
        candidates = layouts(frame, overlay, rules, len(self.seen) - 1, self.candidate)
        for index, layout in enumerate(candidates, start=1):
            if stop() or self.attempts >= MAX_ATTEMPTS:
                return None
            self.attempts += 1
            if on_attempt is not None:
                on_attempt(index, layout.rotation)
            try:
                readings = [read(layout, OCR_PROFILES[0])]
                if stop():
                    return None
                readings.append(read(layout, OCR_PROFILES[1]))
                prefixes = [meter_prefix(value, precision, digits) for value in readings]
                if prefixes[0] is None or prefixes[0] != prefixes[1]:
                    continue
                if has_reference and (
                    not sample.get("reference_time") or
                    compare_sample(sample, readings[0], precision, integer_digits=digits)[0] != "match"
                ):
                    continue
                same = layout == self.candidate
                anchor = self.counter if same else baseline or {}
                counter = accumulate_consumption(anchor, "calibration", stamp, readings[0], precision,
                                                flow, digits)
            except (OSError, ValueError, subprocess.SubprocessError):
                continue
            self.confirmations = self.confirmations + 1 if same else 1
            self.anchored = (same and self.anchored) or has_reference or bool(baseline)
            self.advanced = same and (self.advanced or counter["reading_litres"] > anchor["reading_litres"])
            self.candidate, self.counter = layout, counter
            if self.confirmations > self.best_confirmations:
                self.best, self.best_confirmations = layout, self.confirmations
            if self.confirmations >= MIN_IMAGES and (self.anchored or self.advanced):
                return layout
            # Preserve a reproducible candidate and test it on the next photograph.
            return None
        if not stop():
            self.candidate, self.counter = None, {}
            self.confirmations, self.anchored, self.advanced = 0, False, False
        return None
