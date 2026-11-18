"""The last roller: find its centre, search vertically, re-search a frame that sits beside it."""

import sys
from pathlib import Path
from unittest import TestCase

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calibration import Layout, last_digit_candidates
from checks import relocate_last_digit_due
from layout import roll_center

FONT = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)


def register(extra_gap, last_digit=True, width=480):
    image = Image.new("RGB", (width, 80), (20, 20, 20))
    draw = ImageDraw.Draw(image)
    lefts = [20 + index * 50 for index in range(7)] + [20 + 7 * 50 + extra_gap]
    boxes = []
    for index, left in enumerate(lefts):
        if index < 7 or last_digit:
            draw.rectangle((left - 4, 5, left + 34, 75), fill=(40, 40, 40))
            # The last roller is turning: its digit sits lower than the others.
            draw.text((left + 3, 12 if index < 7 else 30), str(index), font=FONT, fill=(200, 200, 200))
        boxes.append((left - 2, 8, left + 32, 72))
    evenly_spaced = (boxes[-2][0] + 50, 8, boxes[-2][2] + 50, 72)
    return image, [*boxes[:-1], evenly_spaced], (boxes[-1][0] + boxes[-1][2]) / 2


class RollCentreTests(TestCase):
    def test_finds_a_last_roller_that_sits_farther_away_than_the_even_spacing(self):
        for gap in (0, 8, 14, 20):
            for width in (420, 480):
                image, boxes, expected = register(gap, width=width)
                found = roll_center(image, boxes)
                self.assertIsNotNone(found, (gap, width))
                self.assertLessEqual(abs(found - expected), 34 / 6, (gap, width))

    def test_no_roller_no_guess(self):
        image, boxes, _ = register(10, last_digit=False)
        self.assertIsNone(roll_center(image, boxes))

    def test_untrustworthy_image_gives_no_centre(self):
        image = Image.new("RGB", (480, 80), (30, 30, 30))
        boxes = [(18 + index * 50, 8, 52 + index * 50, 72) for index in range(8)]
        self.assertIsNone(roll_center(image, boxes))


class CandidateTests(TestCase):
    BOXES = tuple((index * 110, 100, index * 110 + 90, 700) for index in range(7)) + ((750, 100, 840, 700),)

    def test_known_centre_keeps_the_frame_on_the_roller_and_only_moves_vertically(self):
        layout = Layout((0, 0, 100, 30), 0, 55, self.BOXES)
        candidates = last_digit_candidates(layout, roll_center=817)
        lefts = {trial.digit_boxes[-1][0] for trial in candidates[:-1]}
        self.assertEqual(1, len(lefts))
        self.assertLessEqual(abs(next(iter(lefts)) + 45 - 817), 9)
        tops = {trial.digit_boxes[-1][1] for trial in candidates}
        self.assertGreater(len(tops), 4)
        # The off-centre saved frame is only a last resort.
        self.assertEqual(layout, candidates[-1])

    def test_without_centre_no_jumps_by_half_a_digit_width(self):
        layout = Layout((0, 0, 100, 30), 0, 55, self.BOXES)
        for trial in last_digit_candidates(layout):
            left = trial.digit_boxes[-1][0]
            # Even spacing (pitch 110) predicts 770; the larger gap of the last roller up to 1.2 × pitch.
            self.assertTrue(741 <= left <= 795, left)
            self.assertLessEqual(abs(trial.digit_boxes[-1][1] - 100), 600 * 3 / 8 + 1)


class RelocationTests(TestCase):
    RULES = {"decimals": 3, "fraction_digits": 3}

    def test_only_when_requested_with_three_decimals_and_after_cooldown(self):
        self.assertFalse(relocate_last_digit_due({}, self.RULES, 100))
        self.assertTrue(relocate_last_digit_due({"last_digit_relocate_due": True}, self.RULES, 100))
        self.assertFalse(relocate_last_digit_due({"last_digit_relocate_due": True, "last_digit_relocate_at": 200},
                                                 self.RULES, 100))
        self.assertFalse(relocate_last_digit_due({"last_digit_relocate_due": True},
                                                 {"decimals": 2, "fraction_digits": 3}, 100))
