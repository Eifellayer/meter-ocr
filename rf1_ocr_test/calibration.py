"""Bounded search for a reproducible meter crop and rotation."""

from dataclasses import dataclass, field, replace
from hashlib import sha256
from math import ceil, cos, floor, radians, sin
import subprocess

from checks import OCR_PROFILES, compare_sample, crop_register, meter_prefix, read_with_retries
from consumption import accumulate_consumption
from layout import (crop_coordinates, digit_box_settings, find_digit_row, find_neighbour_digit_rows,
                    find_raw_digit_row, normalize_digit_boxes, rotated_width, turn_crop)

from meter_learning import propose_digit_boxes, widen_digit_boxes

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
    method: str = field(default="", compare=False)

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


def neighbour_layout(frame, angle, detected, whole_digits, fraction_digits):
    """Translate a grid from the rotated camera view into the saved rotated crop."""
    bounds, _, boxes = detected
    outer = unrotate_box(bounds, frame.size, angle)
    left, top, right, bottom = outer
    if not (right - left >= 8 and bottom - top >= 8):
        return None
    register = turn_crop(crop_register(frame, outer), angle)
    w, h = register.size
    x = (left + right - frame.width) / 2
    y = (top + bottom - frame.height) / 2
    c, s = cos(radians(angle)), sin(radians(angle))
    dx = round(bounds[0] - (frame.width / 2 + c * x - s * y - w / 2))
    dy = round(bounds[1] - (frame.height / 2 + s * x + c * y - h / 2))
    shifted = [(max(0, l + dx), max(0, t + dy), min(w, r + dx), min(h, b + dy)) for l, t, r, b in boxes]
    try:
        normalized = digit_box_settings(normalize_digit_boxes(shifted, register.size), whole_digits + fraction_digits)
    except ValueError:
        return None
    whole_width = round((shifted[whole_digits - 1][2] + shifted[whole_digits][0]) / 2) if fraction_digits else w
    if not 0 < whole_width <= w:
        return None
    return Layout(outer, angle, whole_width, tuple(map(tuple, normalized)), method="neighbours")


def layouts(frame, overlay, rules, offset, current=None, prefer_configured=False):
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

    if (current is not None and current.box[2] <= frame.width and current.box[3] <= frame.height
            and unique(current)):
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
    configured = None
    if "crop" in rules:
        box = crop_coordinates(rules["crop"], rules["width"], rules["rotation"])
        if box[2] <= frame.width and box[3] <= frame.height:
            configured = Layout(box, rules["rotation"], rules["width"],
                                tuple(map(tuple, rules.get("digit_boxes", []))))
    if prefer_configured and configured and unique(configured):
        yield configured
    # Reserve space for neighbour inference and, where possible, the regular crop.
    neighbour_limit = MAX_LAYOUTS_PER_IMAGE - int(configured is not None and not prefer_configured)
    raw_limit = neighbour_limit - 1
    for angle in (ANGLES[first], 0, ANGLES[(first + 1) % len(ANGLES)]):
        if len(emitted) >= raw_limit:
            break
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
            if optimized:
                widened = widen_digit_boxes(optimized, turned.size)
                if widened and tuple(map(tuple, widened)) != tuple(map(tuple, optimized)):
                    variants += (Layout(alternate.box, angle, alternate.width,
                                        tuple(map(tuple, widened)), method="widened"),)
            for layout in variants:
                if len(emitted) >= raw_limit:
                    break
                if unique(layout):
                    yield layout
    whole, fraction = rules["integer_digits"], rules["fraction_digits"]
    for angle in (0, ANGLES[first]):
        if len(emitted) >= neighbour_limit:
            break
        adjusted = turn_crop(frame, angle, expand=False)
        for detected in find_neighbour_digit_rows(adjusted, whole, fraction):
            layout = neighbour_layout(frame, angle, detected, whole, fraction)
            if layout and unique(layout):
                yield layout
            if len(emitted) >= neighbour_limit:
                break
    if configured:
        for trial in (configured, candidate(configured.box, ANGLES[first], padding=2)):
            if len(emitted) >= MAX_LAYOUTS_PER_IMAGE:
                return
            if unique(trial):
                yield trial


def search_region(value):
    if not value:
        return None
    parts = tuple(map(int, value.split(",")))
    left, top, right, bottom = parts
    if not (0 <= left < right <= 1000 and 0 <= top < bottom <= 1000
            and right - left >= 20 and bottom - top >= 20):
        raise ValueError("Invalid calibration search region")
    return parts


def guided_layouts(frame, overlay, rules, offset, current, region):
    left, top, right, bottom = (round(value * size / 1000) for value, size in
                                zip(region, (frame.width, frame.height) * 2))
    if right - left < 8 or bottom - top < 8:
        return
    area = left, top, right, bottom
    local_rules = {key: value for key, value in rules.items() if key != "crop"}
    seed = None
    if current:
        a, b, c, d = current.box
        if left <= a < c <= right and top <= b < d <= bottom:
            seed = replace(current, box=(a - left, b - top, c - left, d - top))
    cropped_overlay = overlay.crop(area) if overlay is not None and overlay.size == frame.size else None
    for layout in layouts(frame.crop(area), cropped_overlay, local_rules, offset, seed):
        a, b, c, d = layout.box
        yield replace(layout, box=(a + left, b + top, c + left, d + top))


def reference_rejection(sample, status):
    if sample.get("reference_is_fallback") or not sample.get("reference_time"):
        return "reference_unavailable"
    if status != "match":
        return "reference_mismatch" if status == "difference" else "reference_unavailable"
    return None


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
    automatic: bool = False
    duration: int = TIME_LIMIT
    attempt_limit: int = MAX_ATTEMPTS
    previous_layout: Layout | None = None
    region: tuple | None = None
    focused: bool = False
    near_score: int = 0

    def expired(self, now):
        return now - self.started >= self.duration

    def status(self, now):
        return {"state": self.state, "stage": self.stage, "rotation": self.rotation, "variant": self.variant,
                "tested": len(self.seen), "limit": self.limit, "duration": self.duration,
                "attempts": self.attempts, "max_attempts": self.attempt_limit, "automatic": self.automatic,
                "confirmations": self.confirmations, "required": MIN_IMAGES,
                "seconds": max(0, ceil(self.duration - (now - self.started)))}

    def remember_image(self, frame, stamp):
        digest = sha256(frame.convert("RGB").tobytes()).digest()
        if stamp <= self.last_stamp or digest in self.seen:
            return False
        self.seen.add(digest)
        self.last_stamp = stamp
        return True

    def verify(self, frame, sample, stamp, rules, read, stop, on_image=None, on_decision=lambda reason: None):
        """Confirm the exact saved geometry with the regular OCR retry routine."""
        if self.attempts >= self.attempt_limit or not self.remember_image(frame, stamp):
            return None
        self.attempts += 1
        if on_image is not None:
            on_image()
        has_reference = sample.get("reference_required") is not False
        precision = rules["decimals"] if has_reference else rules["fraction_digits"]
        digits = rules["integer_digits"]
        rejection = "unreadable"
        try:
            value, confirmed, _ = read_with_retries(
                lambda profile: read(self.candidate, profile), sample, precision,
                max_attempts=max(2, rules["attempts"]), standalone=not has_reference,
                integer_digits=digits, stop_before_attempt=stop,
            )
            status, _ = compare_sample(sample, value, precision, ocr_confirmed=confirmed, integer_digits=digits)
            rejection = (reference_rejection(sample, status) if has_reference and status != "ocr_unclear"
                         else None if status == "ocr_only" else "unclear")
            if rejection:
                raise ValueError("Unconfirmed crop")
            rejection = "implausible"
            accumulate_consumption(self.counter, "calibration", stamp, value, precision,
                                   rules["max_flow_lph"], digits)
        except (OSError, ValueError, subprocess.SubprocessError):
            on_decision(rejection)
            self.verification_pending = False
            self.candidate, self.counter = None, {}
            self.confirmations, self.anchored, self.advanced = 0, False, False
            return None
        on_decision("verified")
        return self.candidate

    def examine(self, frame, overlay, sample, stamp, rules, read, stop, baseline=None, on_attempt=None,
                on_image=None, on_decision=lambda reason: None):
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
        seed = self.candidate or self.previous_layout
        candidates = (guided_layouts(frame, overlay, rules, len(self.seen) - 1, seed, self.region)
                      if self.region else layouts(frame, overlay, rules, len(self.seen) - 1, seed,
                                                  prefer_configured=self.automatic))
        # A geometry that produced a stable OCR string is a strong signal, even
        # when it did not yet match the external reference. Stay focused on it
        # for the next fresh image instead of spending attempts on rotations
        # that are visibly worse. Alternatives are re-enabled after a real OCR
        # failure or once the focused candidate is confirmed.
        if self.focused:
            candidates = ((self.candidate,) if self.candidate is not None else ())
        examined = False
        for index, layout in enumerate(candidates, start=1):
            if stop() or self.attempts >= self.attempt_limit:
                return None
            examined = True
            self.attempts += 1
            if on_attempt is not None:
                on_attempt(index, layout.rotation)
            rejection = "unreadable"
            try:
                readings = [read(layout, OCR_PROFILES[0])]
                if stop():
                    return None
                readings.append(read(layout, OCR_PROFILES[1]))
                prefixes = [meter_prefix(value, precision, digits) for value in readings]
                if None in prefixes:
                    on_decision("unclear")
                    continue
                if prefixes[0] != prefixes[1]:
                    on_decision("disagree")
                    continue
                if has_reference:
                    status, _ = compare_sample(sample, readings[0], precision, integer_digits=digits)
                    reason = reference_rejection(sample, status)
                    if reason:
                        # Keep a candidate with two agreeing OCR profiles as
                        # the preferred geometry. The reference may be stale
                        # or the meter may simply not have advanced yet.
                        self.candidate = layout
                        self.focused = True
                        self.near_score = max(self.near_score, 2)
                        on_decision(reason)
                        return None
                rejection = "implausible"
                same = layout == self.candidate
                anchor = self.counter if same else baseline or {}
                counter = accumulate_consumption(anchor, "calibration", stamp, readings[0], precision,
                                                flow, digits)
            except (OSError, ValueError, subprocess.SubprocessError):
                on_decision(rejection)
                continue
            self.confirmations = self.confirmations + 1 if same else 1
            self.anchored = (same and self.anchored) or has_reference or bool(baseline)
            self.advanced = same and (self.advanced or (
                "reading_litres" in anchor and
                counter["reading_litres"] > anchor["reading_litres"]))
            self.candidate, self.counter = layout, counter
            self.focused = False
            self.near_score = 0
            if self.confirmations > self.best_confirmations:
                self.best, self.best_confirmations = layout, self.confirmations
            if self.confirmations >= MIN_IMAGES and not (self.anchored or self.advanced):
                on_decision("await_movement")
            else:
                on_decision("accepted")
            if self.confirmations >= MIN_IMAGES and (self.anchored or self.advanced):
                return layout
            # Preserve a reproducible candidate and test it on the next photograph.
            return None
        if not stop():
            if not examined:
                on_decision("no_region")
            self.candidate, self.counter = None, {}
            self.focused, self.near_score = False, 0
            self.confirmations, self.anchored, self.advanced = 0, False, False
        return None
