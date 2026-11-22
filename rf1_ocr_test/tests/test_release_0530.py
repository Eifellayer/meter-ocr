"""0.5.30: the shown meter reading does not step back after a new setup."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run  # noqa: E402
from test_worker import synthetic_meter  # noqa: E402

CAMERA = "camera.meter"
SOURCE_KEY = ["esphome", CAMERA, ""]


def shown(reading, decimals=2, camera=CAMERA):
    return {"camera": camera, "reading": reading, "decimals": decimals, "integer_digits": 5, "image_time": 1}


class NewestAnchorTests(TestCase):
    def test_a_later_but_lower_entry_does_not_replace_a_counted_reading(self):
        counted = {"value": 10514000, "time": 100}
        entered = {"value": 10513400, "time": 200}
        self.assertIs(counted, run.newest_anchor(entered, counted, 300))
        self.assertIs(counted, run.newest_anchor(counted, entered, 300))

    def test_otherwise_the_newest_anchor_wins(self):
        counted = {"value": 10514000, "time": 100}
        entered = {"value": 10514300, "time": 200}
        self.assertIs(entered, run.newest_anchor(counted, entered, 300))
        same = {"value": 10514000, "time": 200}
        self.assertIs(same, run.newest_anchor(counted, same, 300))
        # Only anchors before the picture count.
        self.assertIs(counted, run.newest_anchor(counted, {"value": 10513000, "time": 400}, 300))
        self.assertIsNone(run.newest_anchor(None, None, 300))


class NextStandaloneTests(TestCase):
    def test_a_lower_reading_keeps_the_shown_one(self):
        history = {"standalone_reading": shown("10514.00")}
        self.assertIsNone(run.next_standalone(history, shown("10513.42")))

    def test_a_proven_misread_may_be_corrected(self):
        history = {"standalone_reading": shown("10514.00")}
        latest = shown("10513.42")
        self.assertIs(latest, run.next_standalone(history, latest, lower_recovered=True))

    def test_higher_and_equal_readings_are_shown(self):
        history = {"standalone_reading": shown("10514.00")}
        for value in ("10514.00", "10514.05", "10515.10"):
            latest = shown(value)
            self.assertIs(latest, run.next_standalone(history, latest))

    def test_a_coarser_reading_still_keeps_the_finer_one(self):
        history = {"standalone_reading": shown("10514.03")}
        kept = run.next_standalone(history, {**shown("10514.0", decimals=1), "image_time": 2})
        self.assertEqual("10514.03", kept["reading"])
        self.assertEqual(2, kept["image_time"])

    def test_after_a_reset_the_booked_value_shown_counts(self):
        history = {"consumption": {"source": SOURCE_KEY, "anchor_litres": 10514000, "anchor_step": 10}}
        self.assertIsNone(run.next_standalone(history, shown("10513.42")))
        latest = shown("10514.01")
        self.assertIs(latest, run.next_standalone(history, latest))

    def test_another_camera_is_not_compared(self):
        history = {"standalone_reading": shown("10514.00", camera="camera.other")}
        latest = shown("10513.42")
        self.assertIs(latest, run.next_standalone(history, latest))


class HiddenDigitAfterSetupTests(TestCase):
    """A reading entered by hand after a counted one, but lower, must not fill the hidden digit."""

    def run_check(self, entered, ocr):
        class StopLoop(Exception):
            pass

        folder = Path(self.enterContext(TemporaryDirectory()))
        paths = {key: folder / key for key in (
            "OPTIONS", "HISTORY", "EFFECTIVE_OPTIONS", "SOURCE_SETTINGS", "AUTO_RULES", "NOTIFICATIONS",
            "LANGUAGE_MODES", "AUTO_PAUSED", "DESTINATION", "GOOD_IMAGE", "AUTOMATIC_PREVIEW",
        )}
        source = {"mode": "esphome", "url": "", "camera": CAMERA, "reference": ""}
        now = datetime.now(timezone.utc)
        entered_at = (now - timedelta(minutes=2)).astimezone(ZoneInfo("Europe/Berlin")).strftime("%Y-%m-%dT%H:%M")
        paths["OPTIONS"].write_text("{}")
        paths["SOURCE_SETTINGS"].write_text(json.dumps(source))
        paths["AUTO_RULES"].write_text(json.dumps({
            "decimals": 2, "attempts": 5, "crop_mode": "manual", "crop": "0,0,500,100", "width": 300,
            "fallback_value": entered, "fallback_time": entered_at,
        }))
        counted_at = now.timestamp() - 300
        paths["HISTORY"].write_text(json.dumps({"consumption": {
            "source": SOURCE_KEY, "timestamp": counted_at, "reading_litres": 10514000, "step_litres": 10,
            "total_litres": 36550, "start_total": 0, "anchor_litres": 10514000, "anchor_time": counted_at,
            "anchor_step": 10, "floor_litres": 10514000, "pending_litres": None, "pending_time": None,
            "pending_step": None,
        }}))
        self.enterContext(patch.multiple(run, **paths))
        self.enterContext(patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}))
        self.enterContext(patch.object(run, "start_panel", return_value=(None, None, None)))
        with BytesIO() as stream:
            synthetic_meter().save(stream, "JPEG")
            self.enterContext(patch.object(run, "get_bytes", return_value=stream.getvalue()))
        # The fifth digit hides behind a reflection.
        self.enterContext(patch.object(run, "hidden_reflection_slots", return_value=[4]))
        self.enterContext(patch.object(run, "read_visible_digits", return_value=ocr))
        self.enterContext(patch.object(run, "read_register", return_value=None))
        self.enterContext(patch.object(run, "publish_state"))
        self.enterContext(patch.object(run, "publish_consumption", side_effect=StopLoop))
        with self.assertRaises(StopLoop):
            run.main()
        return json.loads(paths["HISTORY"].read_text())

    def test_a_lower_entry_after_a_counted_reading_does_not_fill_one_cubic_metre_too_low(self):
        # Seen live after a new setup: counted 10514.0, entered 10513.40 two minutes later, read
        # "1051?.42" – the entry won by its time and the shown reading fell to 10513.42.
        history = self.run_check("10513,40", "1051?.42")
        self.assertNotEqual("anchored_hidden", history.get("ocr_method"))
        self.assertNotIn("10513.42", json.dumps(history))

    def test_a_fitting_later_entry_still_fills_the_hidden_digit(self):
        history = self.run_check("10514,30", "1051?.32")
        self.assertEqual("anchored_hidden", history.get("ocr_method"))
        self.assertEqual("10514.32", history["standalone_candidate"]["reading"])
