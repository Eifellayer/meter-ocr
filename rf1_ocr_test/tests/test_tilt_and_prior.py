"""0.1.7: fine tilt from the digit row, 0.1° rotation input, last confirmed reading as a reading aid."""

import sys
from pathlib import Path
from unittest import TestCase

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks import note_skew, plausible_integer_digits, resolve_ocr_readings, skew_offset, SKEW_SAMPLES
from layout import digit_row_tilt, split_rotation

FONT = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)


def row(digits):
    image = Image.new("RGB", (460, 100), (20, 20, 20))
    draw = ImageDraw.Draw(image)
    boxes = []
    for index, char in enumerate(digits):
        left = 20 + index * 60
        draw.text((left + 5, 25), char, font=FONT, fill=(220, 220, 220))
        boxes.append((left, 15, left + 45, 85))
    return image, boxes


class TiltTests(TestCase):
    def test_level_row_measures_almost_zero_and_tilts_are_found(self):
        for digits in ("10478", "23596"):
            image, boxes = row(digits)
            self.assertLess(abs(digit_row_tilt(image, boxes)), .2)
            for angle in (-2, -1.5, 1, 2.5):
                tilted = image.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=(20, 20, 20))
                self.assertAlmostEqual(angle, digit_row_tilt(tilted, boxes), delta=.35)

    def test_one_turning_roller_does_not_tip_the_line(self):
        image, boxes = row("1047")
        ImageDraw.Draw(image).text((20 + 4 * 60 + 5, 50), "8", font=FONT, fill=(220, 220, 220))
        boxes.append((260, 15, 305, 85))
        self.assertLess(abs(digit_row_tilt(image, boxes)), .5)  # a plain line fit gives about 2°

    def test_offset_moves_only_after_several_agreeing_measurements(self):
        state = {}
        for _ in range(SKEW_SAMPLES - 1):
            state = note_skew(state, -1.4)
        self.assertEqual(0.0, skew_offset(state))
        state = note_skew(state, -1.6)
        self.assertEqual(-1.4, skew_offset(state))
        self.assertEqual([], state["samples"])

    def test_scattered_or_small_measurements_change_nothing(self):
        state = {}
        for value in (-2, 2, -2, 2, -2, 2, -2):
            state = note_skew(state, value)
        self.assertEqual(0.0, skew_offset(state))
        state = {}
        for _ in range(SKEW_SAMPLES):
            state = note_skew(state, .2)
        self.assertEqual(0.0, skew_offset(state))

    def test_rotation_input_accepts_tenths_of_a_degree(self):
        self.assertEqual((-2, 0.5), split_rotation("-1.5"))
        self.assertEqual((-1, -0.3), split_rotation("-1,3"))
        self.assertEqual((3, 0.0), split_rotation("3"))
        with self.assertRaises(ValueError):
            split_rotation("400")


class PriorReadingTests(TestCase):
    def test_an_eight_read_as_six_is_ruled_out_by_the_last_confirmed_reading(self):
        allowed = plausible_integer_digits(10478548, 1000.0, 2260.0, 6000, 5)
        readings = ["10478.65?", "10476.65?", "?0478.65?", "10476.65?", "1047?.?5?"]
        self.assertEqual("1047?.65?", resolve_ocr_readings(readings, 3, 5, standalone=True,
                                                           standalone_composition=True)[0])
        self.assertEqual("10478.65?", resolve_ocr_readings(readings, 3, 5, standalone=True,
                                                           standalone_composition=True, allowed=allowed)[0])

    def test_no_aid_without_a_recent_confirmed_reading(self):
        self.assertIsNone(plausible_integer_digits(None, None, 0, 6000, 5))
        self.assertIsNone(plausible_integer_digits(10478548, 0.0, 30 * 86400.0, 6000, 5))
