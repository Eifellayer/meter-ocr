import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import background_live
import stationary
from checks import (REDUCED_PRECISION_NOTICE, STANDALONE_PENDING, STANDALONE_PENDING_NOTICE,
                    TURNING_RETRY_SECONDS, schedule_next_check, wait_reason_text)

ROOT = Path(__file__).resolve().parents[1]
RUN = (ROOT / "run.py").read_text(encoding="utf-8")
PANEL = (ROOT / "panel.py").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")


class TurningRetryTest(unittest.TestCase):
    def test_coarser_check_gets_a_new_picture_pair_soon(self):
        history = {"check_detail": REDUCED_PRECISION_NOTICE}
        schedule_next_check(history, "ocr_only", 1000, 10)
        self.assertEqual(1000 + TURNING_RETRY_SECONDS, history["next_check_at"])
        self.assertIn("drehte sich", wait_reason_text(history))
        self.assertIn("roller was turning", wait_reason_text(history, "en"))

    def test_only_once_per_series_of_coarser_checks(self):
        history = {"check_detail": REDUCED_PRECISION_NOTICE}
        schedule_next_check(history, "ocr_only", 1000, 10)
        history["check_detail"] = STANDALONE_PENDING_NOTICE
        schedule_next_check(history, STANDALONE_PENDING, 1050, 10)
        self.assertEqual("", wait_reason_text(history))
        history["check_detail"] = REDUCED_PRECISION_NOTICE
        schedule_next_check(history, "ocr_only", 1060, 10)
        # Still turning: the normal interval applies, no endless quick retries.
        self.assertEqual(1060 + 600, history["next_check_at"])
        self.assertEqual("", wait_reason_text(history))
        history["check_detail"] = "Zählerstand mit einer zweiten Aufnahme gegengeprüft."
        schedule_next_check(history, "ocr_only", 2000, 10)
        self.assertNotIn("turning_retry_used", history)
        self.assertEqual(2000 + 600, history["next_check_at"])

    def test_overview_shows_why_it_waits(self):
        self.assertIn('id="hero-wait-reason"', PANEL)
        self.assertIn('"wait_reason":', PANEL)


class BackgroundWorkTest(unittest.TestCase):
    def test_overview_has_the_toggle_and_live_list(self):
        self.assertIn('id="show-background-work"> Hintergrundaufgaben anzeigen', PANEL)
        self.assertIn("function renderBackgroundWork(items)", PANEL)
        self.assertIn('"background_work": get_background_work(language)', PANEL)
        self.assertIn("get_background_work=get_background_work", RUN)
        self.assertIn("on_start=idle_started", RUN)

    def test_fine_search_shows_step_reading_and_progress(self):
        status = {"background": True, "state": "testing", "stage": "last_digit", "attempts": 3, "max_attempts": 10,
                  "confirmations": 1, "required": 3, "tested": 4,
                  "candidates": [{"selected": True, "reading": "10511.052"}]}
        entry = background_live.fine_search(status)
        self.assertEqual("running", entry["state"])
        self.assertEqual("Letzte Rolle lesen", entry["step"])
        self.assertEqual("10511.052", entry["reading"])
        self.assertEqual((3, 10), (entry["completed"], entry["total"]))
        self.assertIsNone(background_live.fine_search({"background": False, "state": "testing"}))

    def test_waiting_time_work_and_shadow_mode(self):
        state = {"idle": {"state": "done", "reason": "experiment", "image": "2026-11-22T11:42:44+01:00",
                          "stable": "10511.05?", "at": 1.0,
                          "experiment": {"stable": "10511.05?", "perspective": {"reading": "10511.05?"}}},
                 "shadow": {"experiment": {"skipped": "busy", "load": 0.73}, "image": None, "at": 2.0},
                 "recovery": {"recovery": {"tried": True, "plan": {"done": 4, "total": 10}, "pattern": "10511.0?",
                                           "result": "timeout"}, "ocr": "10511.0??", "image": None, "at": 3.0}}
        entries = background_live.entries(state, None, None, False)
        self.assertEqual(["idle", "shadow", "recovery"], [entry["id"] for entry in entries])
        self.assertIn("Perspektivkorrektur", entries[0]["result"])
        self.assertEqual("skipped", entries[1]["state"])
        self.assertIn("Last 0.73", entries[1]["result"])
        self.assertEqual((4, 10), (entries[2]["completed"], entries[2]["total"]))
        running = background_live.entries(state, None, None, True)
        # 0.5.17: shadow mode no longer claims to run alongside the check; it shows its last result.
        self.assertNotEqual("running", running[1]["state"])
        english = background_live.entries(state, None, {"reason": "unclear_check", "image": None}, False, "en")
        self.assertEqual("waiting", english[0]["state"])
        self.assertIn("Re-reading", english[0]["step"])


class SetupSubstepsTest(unittest.TestCase):
    def test_running_step_unfolds_intermediate_steps(self):
        self.assertIn("step.substeps = running ? cycle : step.state === 'done' || step.state === 'current'", PANEL)
        self.assertIn("fold.open = remembered ?? step.state === 'current'", PANEL)
        self.assertIn("'Zwischenschritte'", PANEL)
        self.assertIn("'Kein neues Kamerabild – wird wiederholt'", PANEL)


def strip(digits, offset=0):
    picture = Image.new("L", (160, 60), 230)
    draw = ImageDraw.Draw(picture)
    for index, digit in enumerate(digits):
        # A roller as a dark glyph block; a turning roller shows it shifted vertically.
        top = 10 + int(digit) * 2 + (offset if index == len(digits) - 1 else 0)
        draw.rectangle((12 + index * 40, top, 26 + index * 40, min(54, top + 22)), fill=20)
        draw.rectangle((5 + index * 40, 5, 35 + index * 40, 55), outline=90)
    return picture.convert("RGB")


BOXES = [(2 + index * 40, 2, 38 + index * 40, 58) for index in range(4)]


class StationaryShadowTest(unittest.TestCase):
    def test_same_rollers_count_as_stationary(self):
        before = {"register": strip("1051"), "boxes": BOXES, "image": "a"}
        after = {"register": strip("1051"), "boxes": BOXES, "image": "b"}
        result = stationary.compare(before, after)
        self.assertTrue(result["stationary"])
        self.assertEqual("a", result["against"])
        self.assertEqual(4, len(result["diff"]))

    def test_moved_last_roller_is_reported(self):
        before = {"register": strip("1051"), "boxes": BOXES}
        after = {"register": strip("1052", offset=18), "boxes": BOXES}
        result = stationary.compare(before, after, threshold=3)
        self.assertFalse(result["stationary"])
        self.assertEqual([4], result["moving"])

    def test_other_frames_are_not_compared(self):
        before = {"register": strip("1051"), "boxes": BOXES}
        self.assertIsNone(stationary.compare(before, {"register": strip("1051"), "boxes": BOXES[:3]}))
        self.assertIsNone(stationary.compare(None, before))

    def test_only_logged(self):
        # 0.5.36: logged in the shadow log, beside the readings of both checks.
        self.assertIn('shadow_log.record("standstill"', RUN)
        self.assertIn("stationary.py", DOCKERFILE)
        self.assertIn("background_live.py", DOCKERFILE)


if __name__ == "__main__":
    unittest.main()


class FrameBelongsToItsPictureTests(unittest.TestCase):
    def test_previous_picture_is_hidden_while_the_new_one_loads(self):
        # 0.5.10: the new frame lay on the previous picture.
        self.assertIn(".calibration-photo-grid img[hidden]{{display:none}}", PANEL)
        self.assertIn("region.hidden = !regionReady || frame.dataset.shown !== String(preview.frame);", PANEL)
        self.assertIn("if (kind === 'frame') region.hidden = region.dataset.frame !== String(revision);", PANEL)

