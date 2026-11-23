"""0.5.43: standstill compared on the digits both checks read; low success rate in the camera diagnosis."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import camera_diagnosis  # noqa: E402
import run  # noqa: E402

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


class StandstillTests(unittest.TestCase):
    def test_two_decimals_are_enough(self):
        # With two compared decimals the third one is never read; before, nothing was compared.
        self.assertTrue(run.standstill_agrees({"stationary": True}, "10518.07?", "10518.07?"))
        self.assertFalse(run.standstill_agrees({"stationary": True}, "10518.07?", "10518.08?"))
        self.assertTrue(run.standstill_agrees({"stationary": False}, "10518.07?", "10518.1??"))

    def test_unread_whole_digits_or_no_common_decimal_tell_nothing(self):
        self.assertIsNone(run.standstill_agrees({"stationary": True}, "1051?.07?", "10518.07?"))
        self.assertIsNone(run.standstill_agrees({"stationary": True}, "10518.???", "10518.07?"))
        self.assertIsNone(run.standstill_agrees({"stationary": True}, "10518.07", None))


class SuccessRateTests(unittest.TestCase):
    def log(self, successful, failed):
        entries = [{"kind": "automatic", "outcome": "ocr_only"}] * successful + \
                  [{"kind": "automatic", "outcome": "ocr_unclear"}] * failed
        return "\n".join(json.dumps({"time": (NOW - timedelta(minutes=index)).isoformat(), **entry})
                         for index, entry in enumerate(entries))

    def test_a_low_success_rate_is_named(self):
        result = camera_diagnosis.diagnose(None, None, None, self.log(43, 144), NOW)
        self.assertIn("low_success", result["problems"])
        self.assertIn("Nur 43 von 187 Prüfungen", " ".join(result["hints"]))

    def test_a_first_picture_waiting_for_the_second_is_no_failure(self):
        text = self.log(10, 0) + "\n" + "\n".join(json.dumps({"time": NOW.isoformat(), "kind": "automatic",
                                                              "outcome": "standalone_pending"}) for _ in range(10))
        result = camera_diagnosis.diagnose(None, None, None, text, NOW)
        self.assertEqual((10, 10, 10), (result["counts"]["checks"], result["counts"]["successful"],
                                        result["counts"]["waiting"]))
        self.assertNotIn("low_success", result["problems"])

    def test_a_good_rate_or_few_checks_are_not(self):
        self.assertNotIn("low_success", camera_diagnosis.diagnose(None, None, None, self.log(8, 2), NOW)["problems"])
        self.assertNotIn("low_success", camera_diagnosis.diagnose(None, None, None, self.log(1, 5), NOW)["problems"])


if __name__ == "__main__":
    unittest.main()
