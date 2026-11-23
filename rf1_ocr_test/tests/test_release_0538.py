"""0.5.38: countdown on the request for a hidden digit, and the check right after it."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks import HIDDEN_ESTIMATE_AFTER, estimated_hidden_digits  # noqa: E402
import panel  # noqa: E402
import run  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PANEL = (ROOT / "panel.py").read_text(encoding="utf-8")
NOW = 1_000_000.0


class DueTests(unittest.TestCase):
    def test_the_check_after_the_countdown_comes_early(self):
        history = {"hidden_digit_prompt": {"positions": [7]}, "hidden_digit_since": NOW - 60,
                   "next_check_at": NOW + 600}
        self.assertEqual(NOW - 60 + HIDDEN_ESTIMATE_AFTER + 5, run.hidden_estimate_due(history, NOW))

    def test_an_earlier_planned_check_stays(self):
        history = {"hidden_digit_prompt": {"positions": [7]}, "hidden_digit_since": NOW - 60,
                   "next_check_at": NOW + 30}
        self.assertIsNone(run.hidden_estimate_due(history, NOW))

    def test_without_an_open_request_nothing_changes(self):
        self.assertIsNone(run.hidden_estimate_due({"hidden_digit_since": NOW, "next_check_at": NOW + 600}, NOW))
        history = {"hidden_digit_prompt": {"positions": [7]}, "hidden_digit_since": NOW - 900,
                   "next_check_at": NOW + 600}
        self.assertIsNone(run.hidden_estimate_due(history, NOW))


class FillTests(unittest.TestCase):
    def test_a_zero_unless_the_last_reading_is_higher(self):
        # Stelle 7 (second decimal) hidden: a 0, or the smallest digit not below the last reading.
        self.assertEqual(("10517.80", [6]), estimated_hidden_digits(["10517.8?", "10517.8?"], None, 2, 5, [6]))
        self.assertEqual(("10517.84", [6]), estimated_hidden_digits(["10517.8?", "10517.8?"], 10517840, 2, 5, [6]))


class PanelTests(unittest.TestCase):
    def test_the_card_shows_the_time_left(self):
        self.assertIn('id="hidden-digit-countdown"', panel.PAGE)
        self.assertIn("function showHiddenCountdown()", PANEL)
        self.assertIn('"hidden_digit_estimate_at":', PANEL)
        self.assertIn("setInterval(showHiddenCountdown, 1000);", PANEL)


if __name__ == "__main__":
    unittest.main()
