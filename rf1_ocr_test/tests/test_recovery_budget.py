"""0.2.4: frame nudging gets its own time budget, red fields do not count as a cut-off digit,
and the templates do not turn a flagged "1" into a "7"."""
import inspect
import re
import sys
from pathlib import Path
from unittest import TestCase

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import glyph_match  # noqa: E402
from layout import glyph_clipped  # noqa: E402


class TemplateConfusionTests(TestCase):
    def test_close_seven_does_not_replace_an_unread_one(self):
        self.assertEqual("?", glyph_match.combine("?", {"7": .86, "1": .79, "3": .75}))

    def test_clear_template_digit_is_still_taken(self):
        self.assertEqual("1", glyph_match.combine("?", {"1": .86, "7": .70, "3": .60}))
        self.assertEqual("7", glyph_match.combine("?", {"7": .90, "1": .78}))
        # Other pairs keep the normal margin.
        self.assertEqual("6", glyph_match.combine("?", {"6": .80, "8": .74}))

    def test_tesseract_one_is_kept_next_to_a_close_seven(self):
        self.assertEqual("1", glyph_match.combine("1", {"7": .85, "1": .82}))


class RedFieldClippingTests(TestCase):
    def _cell(self, glyph_left):
        # Black roller inside a red decimal field (red notch at its left edge, as next to the
        # comma), white "1" with a flag as on the meter, blurred like the camera image.
        image = Image.new("RGB", (160, 90), (200, 30, 30))
        draw = ImageDraw.Draw(image)
        draw.rectangle((40, 10, 120, 80), fill=(15, 15, 15))
        draw.rectangle((30, 10, 50, 45), fill=(200, 30, 30))
        draw.polygon([(glyph_left, 24), (glyph_left + 10, 14), (glyph_left + 14, 14), (glyph_left + 14, 76),
                      (glyph_left + 6, 76), (glyph_left + 6, 26)], fill=(225, 225, 225))
        return image.filter(ImageFilter.GaussianBlur(1.5))

    def test_red_border_inside_the_frame_is_not_a_cut_digit(self):
        image = self._cell(80)
        box = (40, 20, 100, 70)
        # The grey image alone took the red/black edge for a cut stroke and blocked every nudge.
        self.assertTrue(glyph_clipped(image.convert("L"), box))
        self.assertFalse(glyph_clipped(image, box))

    def test_a_really_cut_glyph_is_still_found(self):
        image = self._cell(80)
        self.assertTrue(glyph_clipped(image, (86, 20, 140, 70)))


class RecoveryBudgetTests(TestCase):
    def test_nudging_does_not_wait_for_the_capture_window(self):
        import run
        self.assertGreater(run.DIGIT_RECOVERY_SECONDS, 10)
        source = inspect.getsource(run)
        start = source.index("near_hit = (digit_probe_enabled")
        block = source[start:source.index("if digit_probe_enabled and not ocr_confirmed:", start)]
        self.assertNotIn("stop_ocr()", block)
        self.assertNotIn("live_deadline", block)
        self.assertIn('recovery_log = {"tried": near_hit}', block)

    def test_debug_entry_carries_the_recovery_field(self):
        import run
        source = inspect.getsource(run)
        self.assertTrue(re.search(r'recovery=local\.get\("recovery_log"\)', source))

    def test_wider_frames_for_decimal_digits_but_not_the_last_roller(self):
        import run
        boxes = [(index * 60, 5, index * 60 + 48, 55) for index in range(8)]
        middle = list(run.single_digit_frames(boxes, 6, (480, 60)))
        self.assertIn((6 * 60 + 12, 5, 6 * 60 + 60, 55), middle)
        for box in run.single_digit_frames(boxes, 7, (480, 60), last_roller=True):
            self.assertEqual((boxes[7][0], boxes[7][2]), (box[0], box[2]))


class BlurContradictionTests(TestCase):
    def test_blurred_seven_read_as_four_stays_unclear(self):
        # Runner-up close (7 vs 2), but the digit Tesseract read is far behind.
        self.assertEqual("?", glyph_match.combine("4", {"7": .74, "2": .72, "4": .50}))

    def test_six_read_as_five_stays_unclear_on_a_small_template_lead(self):
        self.assertEqual("?", glyph_match.combine("5", {"6": .80, "5": .76, "8": .74}))
        self.assertEqual("5", glyph_match.combine("5", {"5": .80, "6": .76}))

    def test_one_and_seven_need_a_large_gap_to_contradict(self):
        self.assertEqual("1", glyph_match.combine("1", {"7": .86, "1": .79}))
        self.assertEqual("?", glyph_match.combine("1", {"7": .95, "1": .70}))


class TemplateVetoTests(TestCase):
    def test_veto_only_against_a_clearly_preferred_other_digit(self):
        from unittest import mock
        import run
        register = Image.new("RGB", (40, 40))
        with mock.patch.object(run, "glyph_scores", return_value={"6": .80, "5": .78, "1": .70, "7": .73}):
            self.assertTrue(run.template_veto(register, (0, 0, 20, 30), "5", "auto", False))
            self.assertFalse(run.template_veto(register, (0, 0, 20, 30), "6", "auto", False))
        with mock.patch.object(run, "glyph_scores", return_value={"7": .85, "1": .82}):
            self.assertFalse(run.template_veto(register, (0, 0, 20, 30), "1", "auto", False))
        with mock.patch.object(run, "glyph_scores", return_value={}):
            self.assertFalse(run.template_veto(register, (0, 0, 20, 30), "3", "auto", False))

    def test_recovery_rejects_a_vetoed_agreement(self):
        from unittest.mock import Mock
        import run
        register = Image.new("RGB", (400, 100))
        boxes = [(50 * index + 5, 20, 50 * index + 45, 80) for index in range(8)]
        layout = (register, 250, boxes[:5], boxes[5:])
        read = Mock(return_value="5")
        result, _ = run.recover_single_digit(
            layout, "10487.?1", "10487.?1", 5, 3, read, 16, lambda *_, **__: None,
            lambda: False, lambda _: True, veto=lambda box, digit: digit == "5",
        )
        self.assertIsNone(result)
