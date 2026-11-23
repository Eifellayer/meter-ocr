"""0.5.32: turning the frame takes effect at once, a turned twin with unclear decimals still counts."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import calibration  # noqa: E402
from calibration import Calibration, Layout, closer_half_turn  # noqa: E402
from consumption import accumulate_consumption  # noqa: E402
import run  # noqa: E402
from test_worker import sample  # noqa: E402

RULES = {"decimals": 3, "fraction_digits": 3, "integer_digits": 5, "max_flow_lph": 6000, "learned_flow_lph": None}
TURNED = Layout((300, 40, 360, 420), 95, 240, method="register_window")
# Another frame on the same digits, turned the other way, with a box of another size.
OTHER_BOX = Layout((315, 53, 371, 395), -90, 200, method="register_window")
START = 1000


def last_reading():
    return accumulate_consumption({}, "calibration", START, "10516.24", 2, 6000, 5, confirmed=True)


class WholeDigitTwinTests(unittest.TestCase):
    def test_unclear_decimals_of_the_turned_frame_still_count_by_whole_cubic_metres(self):
        # Seen live: the right frame read "10517.?7?", the wrong one "10521.90?" and was confirmed.
        tried = [(None, OTHER_BOX, ["10517.?7?", "10517.?7?"])]
        self.assertEqual(OTHER_BOX, closer_half_turn(TURNED, "10521.90?", tried, last_reading(), 2, 5))

    def test_the_same_whole_cubic_metre_is_no_evidence(self):
        tried = [(None, OTHER_BOX, ["10516.?7?"])]
        self.assertIsNone(closer_half_turn(TURNED, "10516.30?", tried, last_reading(), 2, 5))
        tried = [(None, OTHER_BOX, ["10517.?7?"])]
        self.assertIsNone(closer_half_turn(TURNED, "10517.40?", tried, last_reading(), 2, 5))


class ExactTwinTests(unittest.TestCase):
    def test_the_exact_twin_is_read_even_when_another_turned_frame_read_garbage(self):
        job = Calibration(5, 3, simplified=True, rank_candidates=True)
        decisions = []

        def read(layout, profile):
            if layout.box == OTHER_BOX.box:
                return "51754.???"
            return "10516.730" if layout.rotation < 0 else "10521.900"

        with patch.object(calibration, "layouts", return_value=[TURNED, OTHER_BOX]), \
                patch.object(calibration, "quarter_turn_layouts", return_value=[]):
            job.examine(Image.new("RGB", (800, 600), (40, 40, 40)), None, {"reference_required": False},
                        START + 10 * 3600, RULES, read, lambda: False, last_reading(),
                        on_decision=decisions.append)
        self.assertEqual(-85, job.candidate.rotation)
        self.assertEqual(TURNED.box, job.candidate.box)
        self.assertIn("half_turn", [entry["reason"] for entry in job.rejected])


class FocusAfterTurnTests(unittest.TestCase):
    def test_the_next_picture_tests_only_the_turned_frame(self):
        job = Calibration(5, 3, simplified=True, rank_candidates=True)
        sideways = Layout((264, 3, 400, 407), 97, 240, method="register_window")
        label = Layout((131, 181, 473, 297), 10, 200, method="register_window")
        job.candidate, job.shortlist = sideways, {sideways: (62, 0.0, 71), label: (25, 0.0, 30)}
        job.flip_orientation(8)
        reads = []

        def read(layout, profile):
            reads.append(layout.rotation)
            return "10517.27?" if layout.rotation < 0 else "?11??.???"

        with patch.object(calibration, "layouts", return_value=[sideways, label]), \
                patch.object(calibration, "quarter_turn_layouts", return_value=[]):
            job.examine(Image.new("RGB", (800, 600), (40, 40, 40)), None, {"reference_required": False},
                        START + 600, RULES, read, lambda: False, None)
        self.assertEqual({-83}, set(reads))
        self.assertEqual((-83, 1), (job.candidate.rotation, job.confirmations))


class ImmediateTurnTests(unittest.TestCase):
    def test_turning_ends_the_evaluation_of_the_current_picture_at_once(self):
        from threading import Event

        class Done(Exception):
            pass

        class StopAfterFrame(Event):
            def wait(self, timeout=None):
                raise Done

        with TemporaryDirectory() as folder:
            files = {name: Path(folder) / name for name in (
                "OPTIONS", "HISTORY", "EFFECTIVE_OPTIONS", "AUTO_RULES", "AUTO_PAUSED",
                "LANGUAGE_MODES", "SOURCE_SETTINGS", "NOTIFICATIONS", "DESTINATION",
                "GOOD_IMAGE", "TEST_IMAGE", "AUTOMATIC_PREVIEW",
            )}
            files["OPTIONS"].write_text(json.dumps({"ausschnitt": "0,0,100,30", "vorkomma_breite": 50}))
            files["SOURCE_SETTINGS"].write_text(json.dumps({
                "mode": "camera", "url": "", "camera": "camera.meter", "reference": "sensor.meter",
            }))
            files["AUTO_RULES"].write_text(json.dumps({
                "decimals": 2, "attempts": 2, "integer_digits": 5, "fraction_digits": 3,
            }))
            access, observed = {}, {}
            recorded = datetime.now(timezone.utc)
            picture = run.calibration_jpeg(Image.new("RGB", (100, 30), "gray"), (100, 30))
            measurement = {**sample(recorded), "raw_value": "12345.230", "actual_value": "12345.230",
                           "reference_time": recorded.timestamp(), "reference_required": True}

            def fake_panel(*args, **kwargs):
                access.update(status=kwargs["get_calibration"], control=kwargs["control_calibration"])
                kwargs["control_calibration"]("start", 4)
                return None, None, None

            def examine(job, frame, overlay, sample_now, stamp, rules, read, stop, *args, **kwargs):
                observed["before"] = stop()
                access["control"]("flip", 0)
                observed["after"] = stop()
                return None

            class InlineCalibrationThread:
                def __init__(self, target, args, **kwargs):
                    self.target, self.args = target, args

                def start(self):
                    self.target(*self.args)
                    raise Done

            with patch.multiple(run, **files, Event=StopAfterFrame), \
                    patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}), \
                    patch.object(run, "start_panel", fake_panel), \
                    patch.object(run, "Thread", InlineCalibrationThread), \
                    patch.object(run, "capture_camera", return_value=(picture, None, measurement)), \
                    patch.object(run.Calibration, "examine", examine):
                with self.assertRaises(Done):
                    run.main()
                self.assertEqual({"before": False, "after": True}, observed)
                # The turn waits for the next picture, which is taken right away.
                self.assertTrue(access["status"]()["flip_pending"])


if __name__ == "__main__":
    unittest.main()
