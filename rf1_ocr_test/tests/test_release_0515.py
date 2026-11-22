"""0.5.15: tiles with slide switches, calmer test picture, background tasks taking turns."""
import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import idle_work  # noqa: E402

PANEL = (Path(__file__).resolve().parents[1] / "panel.py").read_text(encoding="utf-8")


class TakingTurnsTests(unittest.TestCase):
    def test_tasks_alternate_between_pauses(self):
        due = ["unclear_check", "experiment"]
        self.assertEqual(["experiment", "unclear_check", "experiment"],
                         [idle_work.next_reason(due, turn) for turn in (1, 2, 3)])

    def test_single_or_no_task(self):
        self.assertEqual("experiment", idle_work.next_reason(["experiment"], 7))
        self.assertEqual("", idle_work.next_reason([], 3))

    def test_hidden_digit_is_not_reread(self):
        from run import idle_job
        register = Image.new("RGB", (80, 10))
        boxes = [(i * 10, 0, i * 10 + 9, 10) for i in range(8)]
        self.assertIsNone(idle_job("unclear_check", register, boxes, "10511.?95", False, False, "t", 0, skip=[5]))
        self.assertIsNotNone(idle_job("unclear_check", register, boxes, "1051?.?95", False, False, "t", 0, skip=[5]))


class LookTests(unittest.TestCase):
    def test_options_are_tiles_with_a_switch(self):
        self.assertIn('label.check-option input[type="checkbox"]{{appearance:none', PANEL)
        self.assertIn(".check-option:has(input:checked)", PANEL)

    def test_background_switch_sits_at_the_end_of_the_card(self):
        self.assertLess(PANEL.index('id="test-preview"'), PANEL.index('id="show-background-work"'))

    def test_filled_and_uncompared_digits_get_their_own_colour(self):
        sys.path.insert(0, "/tmp/wsstub")
        from run import draw_test_preview
        image = Image.new("RGB", (400, 60), (30, 30, 30))
        boxes = [(i * 50 + 3, 3, i * 50 + 47, 57) for i in range(8)]
        out = draw_test_preview(image, 250, boxes[:5], boxes[5:], "10511.99?", 5, 3, readings=["10511.99?"] * 3,
                                filled_slots=[5], quiet_slots=range(7, 8))
        pixel = lambda index: out.getpixel((boxes[index][0] + 1, boxes[index][3] - 3))
        self.assertEqual((36, 170, 92), pixel(0))
        self.assertEqual((241, 184, 54), pixel(5))
        self.assertEqual((128, 140, 150), pixel(7))


if __name__ == "__main__":
    unittest.main()
