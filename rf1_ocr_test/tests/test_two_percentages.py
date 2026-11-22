"""0.5.11: two percentages – glyph found in the digit fields and agreement of the readings."""
import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calibration import COARSE_AGREEMENT, DIGIT_FOUND_COARSE, Calibration, Layout  # noqa: E402
from layout import digit_presence, empty_digit_slots, normalize_digit_boxes  # noqa: E402


def strip(digits="10511254", empty=(), size=(480, 80)):
    """Synthetic digit strip: white digits on black rollers, no real meter picture."""
    image = Image.new("RGB", size, (20, 20, 20))
    draw = ImageDraw.Draw(image)
    width = size[0] // len(digits)
    boxes = []
    for index, digit in enumerate(digits):
        left = index * width
        boxes.append((left + 4, 6, left + width - 4, size[1] - 6))
        if index in empty:
            continue
        # A simple upright stroke figure stands in for the glyph.
        draw.rectangle((left + width // 2 - 5, 16, left + width // 2 + 5, size[1] - 16), fill=(235, 235, 235))
        draw.rectangle((left + width // 2 - 14, 16, left + width // 2 + 5, 26), fill=(235, 235, 235))
    return image, boxes


class DigitPresenceTests(unittest.TestCase):
    def test_every_field_with_a_glyph_gives_one_hundred_percent(self):
        image, boxes = strip()
        self.assertEqual(100, digit_presence(image, boxes))

    def test_empty_fields_lower_the_value(self):
        image, boxes = strip(empty=(2, 5))
        self.assertEqual(75, digit_presence(image, boxes))

    def test_plain_surface_holds_no_digits(self):
        image = Image.new("RGB", (480, 80), (120, 120, 120))
        self.assertEqual(0, digit_presence(image, strip()[1]))

    def test_hidden_field_is_left_out(self):
        image, boxes = strip(empty=(5,))
        self.assertEqual(100, digit_presence(image, boxes, skip=(5,)))

    def test_nothing_to_judge(self):
        self.assertIsNone(digit_presence(Image.new("RGB", (40, 20)), ()))


class CoarseThresholdTests(unittest.TestCase):
    def layout(self, boxes, size):
        return Layout((0, 0, *size), 0, size[0], normalize_digit_boxes(boxes, size))

    def test_frame_with_digits_in_every_field_needs_less_agreement(self):
        image, boxes = strip()
        layout = self.layout(boxes, image.size)
        job = Calibration(limit=20, started=0)
        job.note_digit_found(image, layout)
        self.assertGreaterEqual(job.digit_found[layout], DIGIT_FOUND_COARSE)
        self.assertEqual(COARSE_AGREEMENT, job.threshold_for(layout))
        job.shortlist[layout] = (62, 1.0, 62)
        self.assertTrue(job.passes(layout))
        job.shortlist[layout] = (55, 1.0, 55)
        self.assertFalse(job.passes(layout))

    def test_frame_without_digits_keeps_the_high_threshold(self):
        image, boxes = strip(empty=(1, 2, 3, 6))
        layout = self.layout(boxes, image.size)
        job = Calibration(limit=20, started=0)
        job.note_digit_found(image, layout)
        self.assertEqual(job.agreement_threshold, job.threshold_for(layout))
        job.shortlist[layout] = (75, 1.0, 75)
        self.assertFalse(job.passes(layout))

    def test_frame_without_digit_fields_behaves_as_before(self):
        job = Calibration(limit=20, started=0)
        layout = Layout((0, 0, 100, 20), 0, 100)
        job.note_digit_found(Image.new("RGB", (100, 20)), layout)
        self.assertEqual(job.agreement_threshold, job.threshold_for(layout))
        self.assertIn("coarse_threshold", job.status(0))



class EmptyFieldTests(unittest.TestCase):
    """0.5.16: a frame on the bare housing read a "1"."""

    def shifted(self):
        # Eight frames shifted one field to the left: the first one lies on the bare housing,
        # with the dark edge of the counter at its right side.
        image, boxes = strip()
        housing = Image.new("RGB", (60, image.height), (170, 175, 185))
        ImageDraw.Draw(housing).rectangle((54, 0, 59, image.height), fill=(20, 20, 20))
        wide = Image.new("RGB", (image.width + 60, image.height))
        wide.paste(housing, (0, 0))
        wide.paste(image, (60, 0))
        boxes = [(4, 6, 56, image.height - 6)] + [(left + 60, top, right + 60, bottom) for left, top, right, bottom in boxes[:7]]
        return wide, boxes

    def test_frame_on_the_bare_housing_is_empty(self):
        image, boxes = self.shifted()
        self.assertEqual([0], empty_digit_slots(image, boxes))

    def test_full_strip_has_no_empty_field(self):
        image, boxes = strip()
        self.assertEqual([], empty_digit_slots(image, boxes))

    def test_unclear_strip_is_left_alone(self):
        image = Image.new("RGB", (480, 80), (120, 120, 120))
        self.assertEqual([], empty_digit_slots(image, strip()[1]))

    def test_digit_read_in_an_empty_field_becomes_unclear(self):
        image, boxes = self.shifted()
        layout = Layout((0, 0, *image.size), 0, image.size[0], normalize_digit_boxes(boxes, image.size))
        job = Calibration(limit=20, started=0)
        self.assertEqual(["?0511.25", "?0511.25"], job.mask_empty_fields(image, layout, ["10511.25", "10511.25"]))


if __name__ == "__main__":
    unittest.main()
