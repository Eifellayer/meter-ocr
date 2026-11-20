import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import glyph_match  # noqa: E402

FIXTURES = Path(__file__).with_name("fixtures")
# Cut-out digit strips (no serial number) of the maintainer's deliberately blurred, tilted ESPHome
# camera with a flash reflection on the third roller. Meter shows 10486.83x and 10486.84x.
STRIPS = {
    "esphome_blur_strip_0057.png": ("10486.83", [(7, 16, 58, 84), (78, 16, 129, 84), (154, 16, 205, 84),
                                                 (229, 16, 281, 84), (295, 16, 346, 84), (354, 16, 405, 84),
                                                 (426, 16, 477, 84), (503, 16, 555, 84)]),
    "esphome_blur_strip_0107.png": ("10486.84", [(6, 15, 57, 86), (80, 15, 132, 86), (155, 15, 206, 86),
                                                 (230, 15, 281, 86), (294, 15, 345, 86), (355, 15, 405, 86),
                                                 (424, 15, 475, 86), (507, 15, 558, 86)]),
}
TEST_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def blurred_cell(digit, blur=2.5, background=40, ink=150):
    """A bright roller digit in a font that is not among the templates, blurred like a bad lens."""
    cell = Image.new("L", (52, 70), background)
    font = ImageFont.truetype(TEST_FONT, 60)
    shape = Image.new("L", (120, 120), 0)
    ImageDraw.Draw(shape).text((10, 0), digit, fill=255, font=font)
    shape = shape.crop(shape.getbbox())
    shape = shape.resize((max(1, round(shape.width * 46 / shape.height)), 46))
    cell.paste(ink, ((52 - shape.width) // 2, 12), shape)
    cell = cell.filter(ImageFilter.GaussianBlur(blur))
    return Image.merge("RGB", (cell, cell, cell))


class TemplateTests(unittest.TestCase):
    def test_templates_load(self):
        self.assertTrue(glyph_match.templates())
        self.assertEqual({item[0] for item in glyph_match.templates()}, set("0123456789"))

    @unittest.skipUnless(Path(TEST_FONT).exists(), "DejaVu fonts missing")
    def test_blurred_digits_are_read_or_left_open_never_wrong(self):
        accepted = 0
        for digit in "0123456789":
            for blur in (1.5, 2.5, 3.5):
                result = glyph_match.combine("?", glyph_match.digit_scores(blurred_cell(digit, blur), True))
                self.assertIn(result, (digit, "?"), (digit, blur))
                accepted += result == digit
        self.assertGreaterEqual(accepted, 20)

    def test_dark_digits_on_light_background(self):
        cell = blurred_cell("7", 1.5, background=220, ink=40)
        self.assertIn(glyph_match.combine("?", glyph_match.digit_scores(cell, None)), ("7", "?"))

    def test_tiny_cell_gives_no_scores(self):
        self.assertEqual(glyph_match.digit_scores(Image.new("RGB", (4, 8))), {})


class WashedOutTests(unittest.TestCase):
    def register(self, bright_index=None, background=40):
        image = Image.new("RGB", (300, 60), (background,) * 3)
        draw = ImageDraw.Draw(image)
        for index in range(6):
            draw.rectangle((index * 50 + 18, 15, index * 50 + 30, 45), fill=(150, 150, 150))
        if bright_index is not None:
            draw.rectangle((bright_index * 50, 0, bright_index * 50 + 49, 59), fill=(255, 255, 250))
        return image, [(index * 50 + 5, 5, index * 50 + 45, 55) for index in range(6)]

    def test_reflection_frame_found(self):
        image, boxes = self.register(2)
        self.assertEqual(glyph_match.washed_out(image, boxes), [2])

    def test_no_reflection_no_frame(self):
        image, boxes = self.register()
        self.assertEqual(glyph_match.washed_out(image, boxes), [])
        light, boxes = self.register(background=230)
        self.assertEqual(glyph_match.washed_out(light, boxes), [])


class CombineTests(unittest.TestCase):
    def test_tesseract_digit_kept_without_clear_conflict(self):
        self.assertEqual(glyph_match.combine("6", {"6": .70, "8": .69}), "6")
        self.assertEqual(glyph_match.combine("6", {"8": .74, "6": .70}), "6")

    def test_clear_conflict_becomes_unclear(self):
        self.assertEqual(glyph_match.combine("6", {"8": .80, "6": .60}), "?")

    def test_template_fills_silent_tesseract_only_when_clear(self):
        self.assertEqual(glyph_match.combine("?", {"0": .78, "8": .70}), "0")
        self.assertEqual(glyph_match.combine("?", {"8": .72, "6": .70}), "?")
        self.assertEqual(glyph_match.combine("?", {"8": .65, "6": .50}), "?")
        self.assertEqual(glyph_match.combine("?", {}), "?")


class AnchoredWholeTests(unittest.TestCase):
    def scores(self, **known):
        flat = {digit: .5 for digit in "0123456789"}
        return [dict(flat, **{known[str(index)]: .8}) if str(index) in known else dict(flat) for index in range(5)]

    def test_single_candidate_is_taken(self):
        self.assertEqual(glyph_match.anchored_whole("10?86", [{}] * 5, 10483, 10537), "10486")

    def test_template_evidence_decides_between_candidates(self):
        scores = self.scores(**{"3": "8"})
        scores[3]["9"] = .6
        # Candidates 10486, 10496, 10506 ...; the fourth cell clearly shows an 8.
        self.assertEqual(glyph_match.anchored_whole("10??6", scores, 10483, 10537), "10486")

    def test_close_evidence_stays_open(self):
        scores = self.scores()
        scores[3].update({"8": .70, "9": .66})
        self.assertEqual(glyph_match.anchored_whole("10??6", scores, 10483, 10537), "10??6")

    def test_cell_without_visible_glyph_carries_no_evidence(self):
        scores = self.scores()
        scores[2] = {digit: .3 for digit in "0123456789"}
        scores[2]["5"] = .55
        # 10486 and 10586 differ only at the washed-out third cell.
        self.assertEqual(glyph_match.anchored_whole("10?86", scores, 10480, 10600), "10?86")

    def test_visible_digits_must_match_and_range_is_respected(self):
        self.assertEqual(glyph_match.anchored_whole("20?86", [{}] * 5, 10483, 10537), "20?86")
        self.assertEqual(glyph_match.anchored_whole("10?86", [{}] * 5, None, None), "10?86")
        self.assertEqual(glyph_match.anchored_whole("10486", [{}] * 5, 10483, 10537), "10486")


class BlurredCameraStripTests(unittest.TestCase):
    """End to end on real cut-out strips: Tesseract plus templates plus last known reading."""

    def read(self, name, whole_range):
        import run
        from checks import OCR_PROFILES

        _, boxes = STRIPS[name]
        with Image.open(FIXTURES / name) as image:
            register = image.convert("RGB")
        return run.read_visible_digits(
            register, boxes[5][0], boxes[:5], boxes[5:], True, "auto", profile=OCR_PROFILES[0],
            whole_digits=5, fraction_digits=2, prefer_boxes=True, whole_range=whole_range,
        )

    def test_strips_read_completely_with_last_known_reading(self):
        for name, (expected, _) in STRIPS.items():
            with self.subTest(name=name):
                # Last confirmed reading 10483.335 nine hours earlier, maximum flow 6 m³/h.
                self.assertEqual(self.read(name, (10483, 10537)), expected)

    def test_reflection_frame_is_never_read(self):
        import run
        from checks import OCR_PROFILES

        _, boxes = STRIPS["esphome_blur_strip_0107.png"]
        with Image.open(FIXTURES / "esphome_blur_strip_0107.png") as image:
            register = image.convert("RGB")
        calls = []

        def invent_seven(picture, light, digits, **kwargs):
            calls.append(picture.size)
            return "7" if digits == 1 else None

        value = run.read_visible_digits(
            register, boxes[5][0], boxes[:5], boxes[5:], True, "auto", profile=OCR_PROFILES[0],
            whole_digits=5, fraction_digits=2, prefer_boxes=True, recognize=invent_seven,
        )
        # The washed-out third frame is skipped instead of trusting an invented 7.
        self.assertEqual(value[2], "?")
        self.assertEqual(len(calls), 6)
        filled = run.read_visible_digits(
            register, boxes[5][0], boxes[:5], boxes[5:], True, "auto", profile=OCR_PROFILES[0],
            whole_digits=5, fraction_digits=2, prefer_boxes=True, whole_range=(10486, 10487),
        )
        self.assertEqual(filled, "10486.84")

    def test_strips_without_known_reading_never_show_a_wrong_digit(self):
        for name, (expected, _) in STRIPS.items():
            with self.subTest(name=name):
                value = self.read(name, None)
                self.assertEqual(len(value), len(expected))
                self.assertTrue(all(char in (want, "?") for char, want in zip(value, expected)), value)
                self.assertGreaterEqual(sum(char == want for char, want in zip(value, expected)), 5, value)


if __name__ == "__main__":
    unittest.main()
