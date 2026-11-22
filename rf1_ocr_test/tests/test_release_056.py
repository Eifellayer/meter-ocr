import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks import (EIGHTH_DIGIT_GIVE_UP_SECONDS, eighth_digit_given_up, note_eighth_digit_search,
                    resume_optional_eighth_digit, setup_source_id)
import status_view

ROOT = Path(__file__).resolve().parents[1]
RUN = (ROOT / "run.py").read_text(encoding="utf-8")
PANEL = (ROOT / "panel.py").read_text(encoding="utf-8")


def seven_digit_rules(revision="r1"):
    source = {"selected": True, "mode": "camera", "camera": "camera.gas"}
    rules = {"decimals": 3, "fraction_digits": 3, "crop_revision": revision,
             "stationary_partial_scope": setup_source_id([source, revision])}
    return rules, source


class EighthDigitGiveUpTest(unittest.TestCase):
    def test_search_gives_up_after_several_hours(self):
        rules, source = seven_digit_rules()
        history, started = {}, []
        begin = lambda: started.append(1) or True
        self.assertTrue(resume_optional_eighth_digit(history, rules, source, 1000, begin))
        self.assertTrue(resume_optional_eighth_digit(history, rules, source, 1000 + 3600, begin))
        self.assertFalse(resume_optional_eighth_digit(
            history, rules, source, 1000 + EIGHTH_DIGIT_GIVE_UP_SECONDS, begin))
        self.assertTrue(eighth_digit_given_up(history, rules))
        self.assertEqual(2, len(started))
        # Stays given up: no more searches for this frame.
        self.assertFalse(resume_optional_eighth_digit(history, rules, source, 1000 + 10 ** 6, begin))
        self.assertEqual(2, len(started))

    def test_new_setup_starts_the_search_again(self):
        rules, source = seven_digit_rules("r1")
        history = {}
        note_eighth_digit_search(history, rules, 0)
        self.assertTrue(note_eighth_digit_search(history, rules, EIGHTH_DIGIT_GIVE_UP_SECONDS))
        new_rules, new_source = seven_digit_rules("r2")
        self.assertFalse(eighth_digit_given_up(history, new_rules))
        self.assertTrue(resume_optional_eighth_digit(history, new_rules, new_source,
                                                     EIGHTH_DIGIT_GIVE_UP_SECONDS + 1, lambda: True))

    def test_running_background_search_is_stopped_and_logged(self):
        self.assertIn('calibration.state = "gave_up"', RUN)
        self.assertIn('kind="eighth_digit_given_up"', RUN)

    def test_status_names_the_reason(self):
        self.assertIn('"last_digit_given_up": last_digit_given_up', PANEL)
        self.assertIn("Entweder ist die Bildqualität zu schlecht", PANEL)
        self.assertIn("Präzisionsmodus wirklich einschalten?", PANEL)
        self.assertIn("window.confirm(question)", PANEL)
        view = status_view.verdict({"check_status": "match"}, "de", detail="", precision_pending=False,
                                   paused=False, setup_pending=False, partial_eighth_digit=True, now=0,
                                   last_digit_given_up=True)
        self.assertIn("7 Ziffern", view["heading"])


class LastDigitPriorityTest(unittest.TestCase):
    def test_waiting_time_work_is_not_blocked_by_background_search(self):
        self.assertIn('if waiting is not None and (calibration is None or calibration.background', RUN)

    def test_background_search_waits_for_idle_machine_and_waiting_work(self):
        self.assertIn('if any(idle_state["jobs"]) or not system_idle():', RUN)


if __name__ == "__main__":
    unittest.main()
