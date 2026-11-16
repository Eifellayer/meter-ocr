"""Exercise the confirmation requirements independently of timing and the camera."""

import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import calibration
from calibration import Calibration, Layout, MAX_ATTEMPTS, unrotate_box

LAYOUT = Layout((0, 0, 80, 20), -3, 80)
OTHER_LAYOUT = Layout((10, 0, 90, 20), 3, 80)
RULES = {"decimals": 0, "fraction_digits": 0, "integer_digits": 5, "max_flow_lph": 6000}


def frame(number):
    return Image.new("RGB", (100, 30), (0, 20, number))


class CalibrationTests(TestCase):
    def setUp(self):
        self.job = Calibration(5, 0)
        self.candidates = self.enterContext(patch.object(calibration, "layouts", return_value=[LAYOUT]))

    def examine(self, number, time, reading="12345", *, reference=True, fallback=False, stop=lambda: False):
        sample = {"reference_required": reference, "reference_is_fallback": fallback,
                  "reference_time": time, "raw_value": reading, "actual_value": reading}
        return self.job.examine(frame(number), None, sample, time, RULES,
                                lambda *_: reading, stop)

    def test_three_distinct_photos_confirm_the_same_layout(self):
        self.assertIsNone(self.examine(1, 100))
        self.assertIsNone(self.examine(1, 101))
        self.assertIsNone(self.examine(2, 102))
        self.assertEqual(LAYOUT, self.examine(3, 103))
        self.assertEqual(3, self.job.status(104)["tested"])
        self.assertEqual(3, self.job.confirmations)

    def test_changing_layout_cannot_reuse_confirmations(self):
        self.examine(1, 100)
        self.examine(2, 101)
        self.candidates.return_value = [OTHER_LAYOUT]
        self.assertIsNone(self.examine(3, 102))
        self.assertEqual(1, self.job.confirmations)

    def test_fallback_is_not_live_confirmation(self):
        self.examine(1, 100, fallback=True)
        self.assertEqual(0, self.job.confirmations)

    def test_without_reference_requires_plausible_forward_movement(self):
        self.examine(1, 100, reference=False)
        self.examine(2, 101, reference=False)
        self.assertIsNone(self.examine(3, 102, reference=False))
        self.assertEqual(LAYOUT, self.examine(4, 103, "12346", reference=False))

    def test_deadline_and_stop(self):
        self.assertFalse(self.job.expired(899.9))
        self.assertTrue(self.job.expired(900))
        self.assertIsNone(self.examine(1, 100, stop=lambda: True))
        self.assertEqual(0, self.job.confirmations)

    def test_crop_attempt_budget_and_best_proposal_survive_failed_confirmation(self):
        self.examine(1, 100)
        self.assertEqual(LAYOUT, self.job.best)
        self.candidates.return_value = []
        self.examine(2, 101)
        self.assertIsNone(self.job.candidate)
        self.assertEqual(LAYOUT, self.job.best)

        self.candidates.return_value = [LAYOUT, OTHER_LAYOUT]
        self.job.attempts = MAX_ATTEMPTS - 1
        self.examine(3, 102, fallback=True)
        self.assertEqual(100, self.job.attempts)
        self.assertEqual(900, self.job.status(0)["duration"])

    def test_normal_ocr_must_accept_one_more_new_image_before_saving(self):
        self.examine(1, 100)
        self.examine(2, 101)
        self.assertEqual(LAYOUT, self.examine(3, 102))
        self.job.verification_pending = True
        rules = {**RULES, "attempts": 3}
        sample = {"reference_time": 103, "raw_value": "12345", "actual_value": "12345"}
        self.assertIsNone(self.job.verify(frame(3), sample, 103, rules, lambda *_: "12345", lambda: False))
        self.assertTrue(self.job.verification_pending)
        self.assertIsNone(self.job.verify(frame(4), sample, 104, rules, lambda *_: "?????", lambda: False))
        self.assertFalse(self.job.verification_pending)
        self.assertEqual(0, self.job.confirmations)

    def test_boxes_transform_back_to_the_original_image(self):
        self.assertEqual((30, 10, 50, 20), unrotate_box((60, 10, 70, 30), (100, 60), 90))


class CalibrationImageTests(TestCase):
    def test_real_ocr_learns_the_same_crop_and_angle_on_three_synthetic_photos(self):
        from PIL import ImageDraw, ImageFont
        from layout import turn_crop
        from run import read_visible_digits, select_register

        job = Calibration(50, 0)
        font = ImageFont.truetype("DejaVuSansMono.ttf", 72)
        for index in range(3):
            im = Image.new("RGB", (640, 480), (80 + index,) * 3)
            draw = ImageDraw.Draw(im)
            draw.rectangle((160, 180, 480, 285), fill="white")
            draw.text((320, 235), "12345", font=font, fill="black", anchor="mm")
            photo = turn_crop(im, 3)
            timestamp = 100 + index
            sample = {"reference_time": timestamp, "actual_value": "12345", "raw_value": "12345"}

            def read(layout, profile):
                register = select_register(photo, None, layout.box, layout.width, layout.rotation, 5, 0)
                return read_visible_digits(*register[:4], False, "auto", profile=profile, fraction_digits=0)

            selected = job.examine(photo, None, sample, timestamp, {**RULES, "crop_mode": "auto"},
                                   read, lambda: False)
            if index < 2:
                self.assertIsNone(selected)
        self.assertIsNotNone(selected)
        self.assertEqual(-3, selected.rotation)
        self.assertEqual(3, job.confirmations)
