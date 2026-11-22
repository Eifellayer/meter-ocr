import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks import (FLOW_PEAK_MIN_SAMPLES, SLOW_ROLLER_FLOOR_LPH, learned_flow_limit, note_flow_peak,
                    slow_roller_digit, track_reflection)

ROOT = Path(__file__).resolve().parents[1]
RUN = (ROOT / "run.py").read_text(encoding="utf-8")
PANEL = (ROOT / "panel.py").read_text(encoding="utf-8")


def learned(peak_lph, samples=FLOW_PEAK_MIN_SAMPLES):
    return {"flow_peaks": {"20000": peak_lph}, "flow_peak_samples": samples}


class FlowPeakTest(unittest.TestCase):
    def test_peak_learned_from_confirmed_readings(self):
        history = {}
        start = 20000 * 86400 + 3600
        note_flow_peak(history, {"time": start, "value": 10492800}, {"time": start + 600, "value": 10492950}, 6000)
        self.assertEqual({"20000": 900}, history["flow_peaks"])
        self.assertEqual(1, history["flow_peak_samples"])

    def test_short_negative_or_implausible_steps_are_ignored(self):
        history = {}
        start = 20000 * 86400
        note_flow_peak(history, {"time": start, "value": 1000}, {"time": start + 60, "value": 1100}, 6000)
        note_flow_peak(history, {"time": start, "value": 2000}, {"time": start + 600, "value": 1000}, 6000)
        note_flow_peak(history, {"time": start, "value": 0}, {"time": start + 600, "value": 5000}, 6000)
        self.assertNotIn("flow_peaks", history)

    def test_only_last_seven_days_are_kept(self):
        history = {}
        for day in range(10):
            stamp = (20000 + day) * 86400
            note_flow_peak(history, {"time": stamp, "value": 0}, {"time": stamp + 3600, "value": 100 + day}, 6000)
        self.assertEqual(7, len(history["flow_peaks"]))
        self.assertNotIn("20000", history["flow_peaks"])

    def test_limit_needs_enough_samples_and_respects_floor_and_maximum(self):
        self.assertIsNone(learned_flow_limit(learned(900, samples=FLOW_PEAK_MIN_SAMPLES - 1), 6000))
        self.assertEqual(SLOW_ROLLER_FLOOR_LPH, learned_flow_limit(learned(300), 6000))
        self.assertEqual(1800, learned_flow_limit(learned(900), 6000))
        self.assertEqual(2000, learned_flow_limit(learned(1500), 2000))

    def test_verified_reading_teaches_the_peak(self):
        history = {"reflection_anchor": {"time": 1000.0, "value": 10492800}}
        track_reflection(history, "10492.85?", ["10492.85?", "10492.85?"], 1600.0, verified=True, unclear=False,
                         decimals=2, integer_digits=5, max_flow_lph=6000, enabled=False)
        self.assertEqual(300, next(iter(history["flow_peaks"].values())))
        self.assertEqual(10492850, history["reflection_anchor"]["value"])


class SlowRollerTest(unittest.TestCase):
    anchor = {"time": 1000.0, "value": 10492800}

    def test_first_decimal_completed_when_only_one_value_is_reachable(self):
        # 17:18 on Stefan's meter: the 8 was unreadable, the 5 behind it clear.
        filled = slow_roller_digit(["10492.?5?", "10492.?5?"], self.anchor, 1120.0, 2, 5, 1800)
        self.assertEqual((["10492.85", "10492.85"], [5]), filled)

    def test_no_completion_when_two_values_are_reachable(self):
        # Ten minutes at up to 1.8 m³/h: 10492.85 and 10492.95 are both possible.
        self.assertIsNone(slow_roller_digit(["10492.?5?", "10492.?5?"], self.anchor, 1600.0, 2, 5, 1800))

    def test_no_completion_without_learned_flow(self):
        self.assertIsNone(slow_roller_digit(["10492.?5?", "10492.?5?"], self.anchor, 1120.0, 2, 5, None))

    def test_other_digits_still_need_a_majority(self):
        self.assertIsNone(slow_roller_digit(["10492.?5?", "10492.???"], self.anchor, 1120.0, 2, 5, 1800))

    def test_second_decimal_completed_with_three_decimals(self):
        # 18:31: "10493.1?3" three minutes after the confirmed 10493.193.
        anchor = {"time": 1000.0, "value": 10493193}
        filled = slow_roller_digit(["10493.1?3", "10493.1?3"], anchor, 1180.0, 3, 5, 1500)
        self.assertEqual((["10493.193", "10493.193"], [6]), filled)

    def test_last_compared_roller_is_never_filled(self):
        anchor = {"time": 1000.0, "value": 10493190}
        self.assertIsNone(slow_roller_digit(["10493.19?", "10493.19?"], anchor, 1060.0, 3, 5, 1500))
        self.assertIsNone(slow_roller_digit(["10493.?", "10493.?"], anchor, 1060.0, 1, 5, 1500))

    def test_whole_digits_are_never_filled(self):
        self.assertIsNone(slow_roller_digit(["1049?.85?", "1049?.85?"], self.anchor, 1120.0, 2, 5, 1800))


class BackgroundSearchTest(unittest.TestCase):
    def test_background_search_reuses_automatic_pictures(self):
        self.assertIn('automatic_capture.update(seq=automatic_capture["seq"] + 1, result=result)', RUN)
        self.assertIn('if automatic_capture["seq"] <= job.automatic_seq', RUN)
        self.assertIn("if shared_result is not None:\n                result = shared_result", RUN)
        self.assertIn("job.image_wait_expired(now) and not job.background", RUN)

    def test_no_time_limit_for_background_search_in_the_view(self):
        self.assertIn("searchProgress.hidden = true;", PANEL)
        self.assertNotIn("In den nächsten 20 Minuten optimiert", PANEL)

    def test_last_match_survives_precision_change_and_counts_second_image(self):
        self.assertIn('updated["last_match_at"] = image_time', RUN)
        self.assertIn('history["last_match_at"] = time.time()', RUN)
        self.assertIn("Noch keine bestätigte Lesung seit der Einrichtung", PANEL)


if __name__ == "__main__":
    unittest.main()
