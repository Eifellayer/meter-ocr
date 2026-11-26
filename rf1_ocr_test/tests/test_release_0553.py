"""0.5.53: the self-setup finds a counter hanging far askew, upside down, in grey or as a negative."""

import unittest

from PIL import Image, ImageDraw, ImageOps

from calibration import Calibration, Layout, glyph_register_layout, register_shift
from layout import find_glyph_register
from tests.test_release_040 import tilted_meter

PITCH = 50
WINDOW = (120, 70, 120 + 8 * PITCH, 130)


def counter(flipped=False, turning=False):
    """A synthetic counter: five dark whole rollers, three red decimal rollers, "m3" beside them."""
    image = Image.new("RGB", (640, 200), (225, 228, 232))
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = WINDOW
    for index in range(8):
        red = index < 3 if flipped else index >= 5
        outer = index == (0 if flipped else 7)
        fill = (120, 110, 120) if turning and outer else (190, 40, 45) if red else (28, 28, 30)
        draw.rectangle((left + index * PITCH, top, left + (index + 1) * PITCH - 1, bottom), fill=fill)
        draw.rectangle((left + index * PITCH + 20, top + 12, left + index * PITCH + 29, bottom - 12),
                       fill=(235, 235, 235))
    draw.text((right + 12, top + 15), "m3", fill=(20, 20, 20))
    return image


def grey(image):
    return ImageOps.grayscale(image).convert("RGB")


VARIANTS = {"colour": lambda image: image, "grey": grey, "negative": ImageOps.invert,
            "grey negative": lambda image: ImageOps.invert(grey(image))}


def moved(rollers):
    return WINDOW[0] + rollers * PITCH, WINDOW[1], WINDOW[2] + rollers * PITCH, WINDOW[3]


class RegisterShiftTests(unittest.TestCase):
    def test_window_beside_the_counter_is_moved_back_in_every_picture_mode(self):
        for name, change in VARIANTS.items():
            image = change(counter())
            for rollers in (-2, -1, 0, 1, 2):
                with self.subTest(mode=name, rollers=rollers):
                    self.assertEqual((-rollers, False), register_shift(image, moved(rollers), 5, 3))

    def test_upside_down_counter_is_told_by_its_decimal_colour(self):
        self.assertEqual((0, True), register_shift(counter(True), WINDOW, 5, 3))
        self.assertEqual((0, True), register_shift(ImageOps.invert(counter(True)), WINDOW, 5, 3))

    def test_turning_last_roller_does_not_hide_the_decimal_colour(self):
        self.assertEqual((0, False), register_shift(counter(turning=True), WINDOW, 5, 3))
        self.assertEqual((0, True), register_shift(counter(True, turning=True), WINDOW, 5, 3))

    def test_grey_picture_never_claims_an_upside_down_counter(self):
        self.assertEqual((0, False), register_shift(grey(counter(True)), WINDOW, 5, 3))

    def test_colour_cast_of_the_light_is_no_decimal_colour(self):
        # A bluish flash: bright rollers look bluer than dark ones, all of them are the same colour.
        image = Image.new("RGB", (640, 200), (95, 95, 95))
        draw = ImageDraw.Draw(image)
        cast = ((41, 42, 97), (60, 34, 84), (71, 80, 144), (51, 108, 179), (92, 157, 248), (123, 184, 254),
                (64, 119, 201), (28, 73, 115))
        for index, colour in enumerate(cast):
            draw.rectangle((WINDOW[0] + index * PITCH, WINDOW[1], WINDOW[0] + (index + 1) * PITCH - 1, WINDOW[3]),
                           fill=colour)
        for rollers in (-2, 0, 2):
            with self.subTest(rollers=rollers):
                self.assertEqual((0, False), register_shift(image, moved(rollers), 5, 3, colour_only=True))
                self.assertEqual((0, False), register_shift(image.transpose(Image.Transpose.ROTATE_180),
                                                            moved(rollers), 5, 3, colour_only=True))

    def test_flat_picture_says_nothing(self):
        self.assertEqual((0, False), register_shift(Image.new("RGB", (640, 200), (90, 90, 90)), WINDOW, 5, 3))


class TiltedGlyphRowTests(unittest.TestCase):
    def test_row_tilted_by_thirty_degrees_is_found_from_a_levelled_start(self):
        frame = tilted_meter(30)
        self.assertIsNone(glyph_register_layout(frame, 5, 3))
        found = glyph_register_layout(frame, 5, 3, 30)
        self.assertIsNotNone(found)
        self.assertEqual("register_window", found.method)
        self.assertLessEqual(abs(found.rotation - 30), 2)

    def test_portrait_picture_keeps_the_scale_of_a_landscape_one(self):
        landscape = tilted_meter(14)
        portrait = Image.new("RGB", (900, 1200), (95, 95, 95))
        portrait.paste(landscape, (0, 300))
        wide = find_glyph_register(landscape, 8, with_tilt=True)
        tall = find_glyph_register(portrait, 8, with_tilt=True)
        self.assertIsNotNone(wide)
        self.assertIsNotNone(tall)
        self.assertAlmostEqual(wide[0][2] - wide[0][0], tall[0][2] - tall[0][0], delta=25)
        self.assertAlmostEqual(wide[0][1] + 300, tall[0][1], delta=12)


class FrozenDigitTests(unittest.TestCase):
    LAYOUT = Layout((10, 10, 300, 80), 33, 240)

    def job(self, confirmations=1, simplified=True):
        job = Calibration(5, 0, rank_candidates=True, simplified=simplified)
        job.candidate = self.LAYOUT
        job.confirmations = confirmations
        job.counter = {"reading_litres": 10567590, "timestamp": 1000.0}
        return job

    def fill(self, job, readings, stamp=1120.0, layout=None):
        return job.frozen_digits(layout or self.LAYOUT, readings, stamp, 5, 6000)

    def test_unread_leading_digit_comes_from_the_confirmed_reading(self):
        self.assertEqual(["10567.62", "10567.62"], self.fill(self.job(), ["1?567.62", "10567.62"]))

    def test_digit_that_may_have_changed_is_never_filled(self):
        # 6 m³/h for two minutes: the last whole digit may have moved on.
        self.assertEqual(["1056?.62", "10567.62"], self.fill(self.job(), ["1056?.62", "10567.62"]))

    def test_contradicting_profile_is_left_alone(self):
        readings = ["1?567.62", "18567.62"]
        self.assertEqual(readings, self.fill(self.job(), readings))

    def test_digit_no_profile_read_is_left_open(self):
        readings = ["1?567.62", "1?567.62"]
        self.assertEqual(readings, self.fill(self.job(), readings))

    def test_nothing_is_filled_without_a_confirmed_reading_of_this_frame(self):
        readings = ["1?567.62", "10567.62"]
        self.assertEqual(readings, self.fill(self.job(confirmations=0), readings))
        self.assertEqual(readings, self.fill(self.job(simplified=False), readings))
        self.assertEqual(readings, self.fill(self.job(), readings, layout=Layout((400, 300, 700, 380), 0, 240)))
        self.assertEqual(readings, self.fill(self.job(), readings, stamp=1000.0 + 7 * 3600))


if __name__ == "__main__":
    unittest.main()
