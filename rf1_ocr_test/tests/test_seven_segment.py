import random
import unittest

from PIL import Image, ImageDraw, ImageFilter

import seven_segment

SEGMENTS = {"0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg", "5": "acdfg",
            "6": "acdefg", "7": "abc", "8": "abcdefg", "9": "abcdfg"}
LEFT, TOP, CELL, HEIGHT = 190, 240, 54, 78


def draw_digit(draw, x, y, width, height, char, color, thick=9):
    gap = thick * .35
    fields = {"a": (x + gap, y, x + width - gap, y + thick),
              "g": (x + gap, y + height / 2 - thick / 2, x + width - gap, y + height / 2 + thick / 2),
              "d": (x + gap, y + height - thick, x + width - gap, y + height),
              "f": (x, y + gap, x + thick, y + height / 2 - gap),
              "b": (x + width - thick, y + gap, x + width, y + height / 2 - gap),
              "e": (x, y + height / 2 + gap, x + thick, y + height - gap),
              "c": (x + width - thick, y + height / 2 + gap, x + width, y + height - gap)}
    for name in SEGMENTS[char]:
        draw.rectangle(fields[name], fill=color)


def display(text, background, window, on, off=None, rotate=0, blur=1.0, seed=1, point=None):
    """A synthetic camera picture of a digital display and the frames of its digits."""
    random.seed(seed)
    image = Image.new("RGB", (800, 600), background)
    draw = ImageDraw.Draw(image)
    digits = text.replace(".", "")
    draw.rectangle((LEFT - 18, TOP - 16, LEFT + len(digits) * CELL + 12, TOP + HEIGHT + 16), fill=window)
    for index, char in enumerate(digits):
        if off:
            draw_digit(draw, LEFT + index * CELL, TOP, CELL - 14, HEIGHT, "8", off)
        draw_digit(draw, LEFT + index * CELL, TOP, CELL - 14, HEIGHT, char, on)
    if point is not None:
        x = LEFT + point * CELL
        draw.rectangle((x - 9, TOP + HEIGHT - 9, x - 2, TOP + HEIGHT), fill=on)
    if rotate:
        image = image.rotate(rotate, resample=Image.BICUBIC, fillcolor=background)
    image = image.filter(ImageFilter.GaussianBlur(blur))
    pixels = image.load()
    for _ in range(20000):
        x, y = random.randrange(800), random.randrange(600)
        noise = random.randint(-10, 10)
        pixels[x, y] = tuple(max(0, min(255, value + noise)) for value in pixels[x, y])
    boxes = [(LEFT + index * CELL - 6, TOP - 8, LEFT + index * CELL + CELL - 8, TOP + HEIGHT + 8)
             for index in range(len(digits))]
    return image, boxes


class SevenSegmentTests(unittest.TestCase):
    """Digital displays are read from their segments; Tesseract read 1 of 8 digits here."""

    LCD = dict(background=(150, 150, 145), window=(176, 190, 160), on=(25, 30, 25))
    LED = dict(background=(40, 40, 42), window=(10, 10, 10), on=(255, 60, 40))

    def test_dark_digits_on_a_light_display(self):
        for text in ("10501.823", "98765.432", "00417.069"):
            image, boxes = display(text, **self.LCD)
            self.assertEqual(text, seven_segment.read_display(image, boxes, 5))

    def test_faint_unlit_segments_are_not_read_as_lit(self):
        image, boxes = display("10501.823", off=(165, 179, 151), **self.LCD)
        self.assertEqual("10501.823", seven_segment.read_display(image, boxes, 5))

    def test_glowing_digits_on_a_dark_display(self):
        image, boxes = display("10501.823", off=(45, 14, 12), **self.LED)
        self.assertEqual("10501.823", seven_segment.read_display(image, boxes, 5))
        self.assertEqual("10501.823", seven_segment.read_display(image, boxes, 5, light_digits=True))

    def test_the_decimal_point_beside_a_digit_does_not_change_it(self):
        image, boxes = display("10501.823", point=5, **self.LCD)
        self.assertEqual("10501.823", seven_segment.read_display(image, boxes, 5))
        image, boxes = display("10501.123", point=5, off=(45, 14, 12), **self.LED)
        self.assertEqual("10501.123", seven_segment.read_display(image, boxes, 5))

    def test_blur_and_noise_are_tolerated(self):
        for seed in (1, 2, 3):
            image, boxes = display("24680.135", blur=2.0, seed=seed, **self.LCD)
            self.assertEqual("24680.135", seven_segment.read_display(image, boxes, 5))

    def test_an_empty_or_flat_cell_is_unclear_not_a_digit(self):
        flat = Image.new("RGB", (200, 100), (120, 120, 120))
        self.assertEqual("??", seven_segment.read_digits(flat, [(0, 0, 100, 100), (100, 0, 200, 100)]))
        image, boxes = display("8", **self.LCD)
        empty = (boxes[0][2] + 200, boxes[0][1], boxes[0][2] + 250, boxes[0][3])
        self.assertEqual("8?", seven_segment.read_digits(image, [boxes[0], empty]))

    def test_every_digit_has_one_pattern(self):
        for digit, lit in SEGMENTS.items():
            self.assertEqual(digit, seven_segment.DIGITS["".join(sorted(lit))])


if __name__ == "__main__":
    unittest.main()
