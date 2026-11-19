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


class EnergyTests(TestCase):
    def test_kwh_from_billing_factors(self):
        from consumption import CALORIFIC_RANGE, STATE_FACTOR_RANGE, energy_kwh, parse_energy_factor
        self.assertEqual(0.9636, parse_energy_factor("0,9636", STATE_FACTOR_RANGE))
        self.assertIsNone(parse_energy_factor("", CALORIFIC_RANGE))
        with self.assertRaises(ValueError):
            parse_energy_factor("50", CALORIFIC_RANGE)
        self.assertAlmostEqual(108.41, energy_kwh(10000, 0.9636, 11.25), delta=.01)
        self.assertIsNone(energy_kwh(10000, None, 11.25))
        self.assertEqual(108.4, energy_kwh(10000, None, None, 10.84))
        self.assertEqual(108.4, energy_kwh(10000, 0.9636, 11.25, 10.84))  # finished factor wins


class SetupConfirmationTests(TestCase):
    def test_same_digits_found_a_few_pixels_apart_count_as_the_same_layout(self):
        from calibration import Layout, similar_layout
        boxes = tuple((index * 120, 100, index * 120 + 100, 900) for index in range(8))
        first = Layout((50, 40, 560, 130), -1, 300, boxes, method="neighbours")
        jitter = Layout((52, 41, 561, 128), -2, 302, tuple((l + 8, t + 20, r + 6, b - 15) for l, t, r, b in boxes),
                        method="register_window")
        refined = Layout((52, 41, 561, 128), -1, 302, boxes, method="refined")
        self.assertFalse(similar_layout(first, refined))
        self.assertTrue(similar_layout(first, jitter))
        elsewhere = Layout((150, 40, 660, 130), -1, 300, boxes, method="neighbours")
        self.assertFalse(similar_layout(first, elsewhere))
        shifted_digit = Layout((50, 40, 560, 130), -1, 300, (*boxes[:-1], (900, 100, 1000, 900)), method="neighbours")
        self.assertFalse(similar_layout(first, shifted_digit))
        self.assertFalse(similar_layout(first, None))


class PartialDigitTests(TestCase):
    def test_a_frame_that_cuts_a_digit_is_recognised(self):
        from PIL import ImageFilter
        from layout import glyph_clipped
        for char in "0235679":
            image = Image.new("RGB", (200, 90), (20, 20, 20))
            ImageDraw.Draw(image).text((70, 15), char, font=FONT, fill=(220, 220, 220))
            image = image.filter(ImageFilter.GaussianBlur(1))
            self.assertFalse(glyph_clipped(image, (60, 8, 112, 82)), char)
            self.assertTrue(glyph_clipped(image, (78, 8, 130, 82)), char)

    def test_last_roller_frames_only_move_vertically(self):
        import run
        boxes = [(index * 50, 5, index * 50 + 40, 55) for index in range(8)]
        for box in run.single_digit_frames(boxes, 7, (400, 60), last_roller=True):
            self.assertEqual((boxes[7][0], boxes[7][2]), (box[0], box[2]))


class WizardEnergyTests(TestCase):
    def test_wizard_keeps_or_parses_factors(self):
        from panel import wizard_energy_factors
        form = {"kwh_conversion_factor": "10,84", "gas_state_factor": "", "calorific_value": ""}
        values = wizard_energy_factors(lambda name, default="": form.get(name, default), {})
        self.assertEqual(10.84, values["kwh_conversion_factor"])
        self.assertIsNone(values["gas_state_factor"])
        kept = wizard_energy_factors(lambda name, default="": default, {"calorific_value": 11.2})
        self.assertEqual(11.2, kept["calorific_value"])
