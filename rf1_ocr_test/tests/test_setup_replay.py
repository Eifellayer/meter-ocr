"""A setup replayed on real camera frames of a gas meter (0.5.0).

Every other test was green in 0.4.2 and 0.4.3 while the setup never confirmed on the real
meter. These frames are what the camera delivered on 21.11.2026: only the register window,
everything else of the meter (serial number, bar code) is painted over.
"""

import hashlib
from pathlib import Path
import shutil
import time
import unittest

from PIL import Image

import calibration
from checks import read_register
import run

STRIPS = Path(__file__).parent / "fixtures" / "setup_strips"
RULES = {"integer_digits": 5, "fraction_digits": 3, "attempts": 5, "polarity": "auto",
         "crop_mode": "auto", "max_flow_lph": 6000, "meter_display": "rollers", "fallback_value": "",
         "fallback_time": "", "digit_boxes": [], "precision_mode": False, "intensive_agreement": 80,
         "reflection_estimate_enabled": False, "experiments_enabled": False, "experiments": {}, "skew_seed": None}


def camera_frame(path):
    frame = Image.new("RGB", (800, 600), (188, 190, 196))
    frame.paste(Image.open(path).convert("RGB"), (150, 150))
    return frame


def replay(rules, files, seconds_per_image=150):
    """Run the setup the way the worker does; returns (job, saved layout or None, images used)."""
    job = calibration.Calibration(limit=100, started=time.monotonic(), rank_candidates=True,
                                  simplified=run.plain_setup(rules, "setup"))
    whole, fraction = rules["integer_digits"], rules["fraction_digits"]
    for number, path in enumerate(files, 1):
        frame, stamp, cache = camera_frame(path), 1000.0 + number * 60, {}
        deadline = time.monotonic() + seconds_per_image

        def cached(picture, light, digits, *, profile, **options):
            key = (picture.size, hashlib.sha256(picture.tobytes()).digest(), digits, profile)
            if key not in cache:
                cache[key] = read_register(picture, light, digits, profile=profile, **options)
            return cache[key]

        def register_for(layout):
            return run.select_register(frame, None, layout.box, layout.width, layout.rotation, whole, fraction,
                                       digit_boxes=layout.digit_boxes)

        def read(layout, profile):
            reduced = job.simplified or rules["decimals"] == 2
            value = run.read_visible_digits(
                *register_for(layout)[:4], False, rules["polarity"], profile=profile, whole_digits=whole,
                fraction_digits=2 if reduced else fraction, deadline=deadline,
                prefer_boxes=bool(layout.digit_boxes), recognize=cached, parallel=True)
            return calibration.two_decimal_reading(value) if reduced else value

        def read_slot(layout, index, profile):
            register, width, whole_boxes, fraction_boxes, _ = register_for(layout)
            if index < whole:
                boxes = whole_boxes or run.approximate_whole_boxes(width, register.height, whole)
            else:
                boxes, index = fraction_boxes, index - whole
            if index >= len(boxes) or boxes[index][2] <= boxes[index][0]:
                return "?"
            return run.read_digit(register, boxes[index],
                                  lambda picture, digits: cached(picture, False, digits, profile=profile))

        sample = {"reference_required": False, "timestamp": stamp}
        stop = lambda: time.monotonic() >= deadline
        if job.verification_pending:
            saved = job.verify(frame, sample, stamp, rules, read, stop)
        else:
            saved = job.examine(frame, None, sample, stamp, rules, read, stop, None, refine_read=read,
                                on_refine=lambda *_: None, on_selected=lambda *_: None, read_slot=read_slot,
                                angle_read=read)
        if saved is not None:
            return job, saved, number
    return job, None, len(files)


@unittest.skipUnless(shutil.which("tesseract"), "needs the OCR engine")
class SetupReplayTests(unittest.TestCase):
    def test_the_setup_confirms_a_real_gas_meter_within_four_images(self):
        files = sorted(STRIPS.glob("gas-*.png"))
        self.assertEqual(4, len(files))
        # "Whole cubic metres" is what the live system compared when 0.4.2 and 0.4.3 failed.
        job, saved, images = replay(dict(RULES, decimals=0), files)
        self.assertIsNotNone(saved, f"no frame after {images} images, {job.confirmations} confirmations")
        self.assertLessEqual(images, 4)
        self.assertEqual(8, len(saved.digit_boxes))
        self.assertTrue(-13 <= saved.rotation <= -8, saved.rotation)


if __name__ == "__main__":
    unittest.main()
