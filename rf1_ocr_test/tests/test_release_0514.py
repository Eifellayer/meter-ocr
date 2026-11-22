"""0.5.14: bug list B1–B7 of 22.11.2026."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import status_view  # noqa: E402
from checks import (HIDDEN_FILLED_TURNING_NOTICE, REDUCED_PRECISION_NOTICE, only_known_hidden_unclear)  # noqa: E402

PANEL = (Path(__file__).resolve().parents[1] / "panel.py").read_text(encoding="utf-8")
STORE = (Path(__file__).resolve().parents[1] / "setup_store.py").read_text(encoding="utf-8")


class KnownHiddenDigitTests(unittest.TestCase):
    """B5: a digit known to be hidden is not rechecked intensively."""

    def test_only_the_hidden_digit_and_the_turning_roller_are_unclear(self):
        self.assertTrue(only_known_hidden_unclear("10511.?9?", 3, 5, [5]))
        self.assertTrue(only_known_hidden_unclear("10511.?9", 2, 5, [5]))

    def test_other_unclear_digits_are_still_rechecked(self):
        self.assertFalse(only_known_hidden_unclear("1051?.?9?", 3, 5, [5]))
        self.assertFalse(only_known_hidden_unclear("10511.??5", 3, 5, [5]))
        self.assertFalse(only_known_hidden_unclear("10511.39?", 3, 5, [5]))   # hidden digit was read
        self.assertFalse(only_known_hidden_unclear("10511.?9?", 3, 5, []))


class CalmPassTests(unittest.TestCase):
    """B6: a passed check reads as passed."""

    def verdict(self, detail):
        return status_view.verdict({"check_status": "ocr_only", "check_detail": detail}, "de", detail=detail,
                                   precision_pending=False, paused=False, setup_pending=False,
                                   partial_eighth_digit=False, now=0)

    def test_filled_or_coarser_check_is_shown_as_passed(self):
        for detail in (HIDDEN_FILLED_TURNING_NOTICE, REDUCED_PRECISION_NOTICE):
            result = self.verdict(detail)
            values = result if isinstance(result, (tuple, list)) else tuple(vars(result).values()) if hasattr(result, "__dict__") else tuple(result.values())
            self.assertIn("ok", values)
            self.assertIn("✓", values)


class SourceTests(unittest.TestCase):
    def test_reflection_setup_starts_with_two_decimals(self):   # B7
        self.assertIn("partial = provisional or reflected or verified and attempt.simplified", STORE)

    def test_marked_digit_reaches_the_setup(self):              # B2
        from calibration import Calibration
        job = Calibration(limit=20, started=0)
        job.marked_positions = (5,)
        self.assertEqual([6], job.status(0)["marked_positions"])

    def test_tap_on_frame_marks_the_digit_and_feedback_is_shown(self):   # B1, B3
        self.assertIn("frameButton.addEventListener('pointerup'", PANEL)
        self.assertIn("als verdeckt markiert. Das wird mit der Einrichtung gespeichert", PANEL)
        self.assertIn("{marked_reflection_note}", PANEL)

    def test_preview_names_its_check(self):                     # B4
        self.assertIn("Bild der vorigen Prüfung (", PANEL)
        self.assertIn("preview-outdated", PANEL)


if __name__ == "__main__":
    unittest.main()
