"""Recovery from a single misread that was too high (the meter cannot run backwards)."""

from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from consumption import (LOWER_PENDING, LOWER_READING, LOWER_RECOVERY_SECONDS, ImplausibleReading,
                         accumulate_consumption, track_lower_series)
import run
from test_worker import synthetic_meter

FLOW = 6_000
SOURCE = ["slfork_camera", "http://esp", ""]


class LowerSeriesTests(TestCase):
    def test_three_consistent_readings_over_fifteen_minutes_confirm_the_lower_meter(self):
        series, confirmed = track_lower_series([], 0, "10472.20", 2, FLOW)
        self.assertFalse(confirmed)
        series, confirmed = track_lower_series(series, 600, "10472.25", 2, FLOW)
        self.assertFalse(confirmed)
        series, confirmed = track_lower_series(series, LOWER_RECOVERY_SECONDS, "10472.31", 2, FLOW)
        self.assertTrue(confirmed)
        self.assertEqual(3, len(series))

    def test_too_short_too_jumpy_or_falling_series_does_not_confirm(self):
        series, _ = track_lower_series([], 0, "10472.20", 2, FLOW)
        series, _ = track_lower_series(series, 60, "10472.21", 2, FLOW)
        series, confirmed = track_lower_series(series, 120, "10472.22", 2, FLOW)
        self.assertFalse(confirmed)  # three readings, but only two minutes apart
        series, _ = track_lower_series(series, 600, "10470.00", 2, FLOW)
        self.assertEqual(1, len(series))  # falling by more than one step restarts the series
        series, _ = track_lower_series(series, 900, "10479.00", 2, FLOW)
        self.assertEqual(1, len(series))  # faster than the maximum flow restarts it
        same, confirmed = track_lower_series(series, 900, "10479.00", 2, FLOW)
        self.assertEqual(series, same)  # the same image does not count twice
        self.assertEqual(([], False), track_lower_series(series, 1000, "1047?.00", 2, FLOW))


class CounterRecoveryTests(TestCase):
    def test_misread_high_value_is_corrected_without_negative_or_double_booking(self):
        counter = accumulate_consumption({}, SOURCE, 0, "10472.00", 2, FLOW)
        counter = accumulate_consumption(counter, SOURCE, 600, "10472.00", 2, FLOW)
        # The same misread on two checks in a row (+2 m³ within an hour) gets confirmed.
        counter = accumulate_consumption(counter, SOURCE, 3600, "10474.00", 2, FLOW)
        counter = accumulate_consumption(counter, SOURCE, 3900, "10474.00", 2, FLOW)
        self.assertEqual(2000, counter["total_litres"])
        with self.assertRaises(ImplausibleReading) as rejected:
            accumulate_consumption(counter, SOURCE, 4200, "10472.20", 2, FLOW)
        self.assertEqual(LOWER_READING, str(rejected.exception))
        # After the lower series is confirmed, the real reading is taken over.
        counter = accumulate_consumption(counter, SOURCE, 4800, "10472.30", 2, FLOW, allow_lower=True)
        self.assertEqual((10472300, 10474000, 10472300, 2000),
                         tuple(counter[key] for key in ("reading_litres", "anchor_litres", "floor_litres",
                                                        "total_litres")))
        # Booked consumption is never taken back or booked twice below the confirmed maximum.
        counter = accumulate_consumption(counter, SOURCE, 5400, "10473.10", 2, FLOW)
        counter = accumulate_consumption(counter, SOURCE, 6000, "10472.80", 2, FLOW)
        self.assertEqual(2000, counter["total_litres"])
        counter = accumulate_consumption(counter, SOURCE, 7200, "10474.10", 2, FLOW)
        counter = accumulate_consumption(counter, SOURCE, 7800, "10474.20", 2, FLOW)
        self.assertEqual(2100, counter["total_litres"])
        self.assertEqual(10474100, counter["floor_litres"])

    def test_misread_start_value_is_corrected_without_losing_consumption(self):
        counter = accumulate_consumption({}, SOURCE, 0, "10475.70", 2, FLOW)
        counter = accumulate_consumption(counter, SOURCE, 600, "10475.70", 2, FLOW)
        counter = accumulate_consumption(counter, SOURCE, 1200, "10475.12", 2, FLOW, allow_lower=True)
        self.assertEqual(10475120, counter["anchor_litres"])
        counter = accumulate_consumption(counter, SOURCE, 1500, "10475.20", 2, FLOW)
        counter = accumulate_consumption(counter, SOURCE, 1800, "10475.30", 2, FLOW)
        self.assertEqual(80, counter["total_litres"])

    def test_legacy_corrected_misread_without_bookings_stops_waiting(self):
        # State left by 0.1.0 on 18.11.2026: anchor at the misread 10475.70, floor corrected.
        old = {"source": SOURCE, "timestamp": 0, "reading_litres": 10475290, "anchor_litres": 10475700,
               "floor_litres": 10475290, "step_litres": 10, "total_litres": 0}
        counter = accumulate_consumption(old, SOURCE, 600, "10475.40", 2, FLOW)
        counter = accumulate_consumption(counter, SOURCE, 900, "10475.50", 2, FLOW)
        self.assertEqual(110, counter["total_litres"])

    def test_counters_without_floor_behave_as_before(self):
        old = {"source": SOURCE, "timestamp": 0, "reading_litres": 10472000, "anchor_litres": 10472000,
               "step_litres": 10, "total_litres": 500}
        with self.assertRaises(ImplausibleReading):
            accumulate_consumption(old, SOURCE, 600, "10471.90", 2, FLOW)
        updated = accumulate_consumption(old, SOURCE, 600, "10472.10", 2, FLOW)
        self.assertEqual((500, 10472000, 10472100),
                         (updated["total_litres"], updated["floor_litres"], updated["pending_litres"]))
        confirmed = accumulate_consumption(updated, SOURCE, 900, "10472.20", 2, FLOW)
        self.assertEqual(600, confirmed["total_litres"])


class LowerRecoveryWorkerTests(TestCase):
    def run_check(self, history):
        class StopLoop(Exception):
            pass

        folder = Path(self.enterContext(TemporaryDirectory()))
        paths = {key: folder / key for key in (
            "OPTIONS", "HISTORY", "EFFECTIVE_OPTIONS", "SOURCE_SETTINGS", "AUTO_RULES", "NOTIFICATIONS",
            "LANGUAGE_MODES", "AUTO_PAUSED", "DESTINATION", "GOOD_IMAGE", "AUTOMATIC_PREVIEW",
        )}
        source = {"mode": "esphome", "url": "", "camera": "camera.meter", "reference": ""}
        paths["OPTIONS"].write_text("{}")
        paths["SOURCE_SETTINGS"].write_text(json.dumps(source))
        paths["AUTO_RULES"].write_text(json.dumps({
            "decimals": 2, "attempts": 5, "crop_mode": "manual", "crop": "0,0,500,100", "width": 300,
        }))
        paths["HISTORY"].write_text(json.dumps(history))
        self.enterContext(patch.multiple(run, **paths))
        self.enterContext(patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}))
        self.enterContext(patch.object(run, "start_panel", return_value=(None, None, None)))
        with BytesIO() as stream:
            synthetic_meter().save(stream, "JPEG")
            self.enterContext(patch.object(run, "get_bytes", return_value=stream.getvalue()))
        self.enterContext(patch.object(run, "read_visible_digits", return_value="10472.304"))
        self.enterContext(patch.object(run, "read_register", return_value=None))
        self.enterContext(patch.object(run, "publish_state"))
        self.enterContext(patch.object(run, "publish_consumption", side_effect=StopLoop))
        with self.assertRaises(StopLoop):
            run.main()
        return json.loads(paths["HISTORY"].read_text())

    def stuck_history(self, now, series=()):
        source = ["esphome", "camera.meter", ""]
        return {
            "consumption": {"source": source, "timestamp": now - 3600, "reading_litres": 10474000,
                            "anchor_litres": 10474000, "step_litres": 10, "total_litres": 2000},
            "standalone_reading": {"camera": "camera.meter", "reading": "10474.00", "decimals": 2,
                                   "integer_digits": 5, "image_time": "2026-01-01T00:00:00+00:00"},
            "lower_series": [list(row) for row in series],
        }

    def test_a_single_lower_reading_is_still_rejected_and_remembered(self):
        now = datetime.now(timezone.utc).timestamp()
        history = self.run_check(self.stuck_history(now))
        self.assertEqual("ocr_unclear", history["check_status"])
        self.assertEqual(LOWER_PENDING, history["check_detail"])
        self.assertEqual(1, len(history["lower_series"]))
        self.assertEqual(2000, history["consumption"]["total_litres"])

    def test_confirmed_lower_series_takes_over_the_real_reading(self):
        now = datetime.now(timezone.utc).timestamp()
        series = ([now - 1200, 10472200], [now - 600, 10472250])
        history = self.run_check(self.stuck_history(now, series))
        # Standalone checks confirm the value with a second image before booking.
        self.assertEqual(run.STANDALONE_PENDING, history["check_status"])
        self.assertEqual("10472.304", history["standalone_candidate"]["reading"])
        candidate = history["standalone_candidate"]["counter"]
        self.assertEqual((10472300, 10474000, 2000),
                         (candidate["floor_litres"], candidate["anchor_litres"], candidate["total_litres"]))
        self.assertEqual(3, len(history["lower_series"]))


class LowerRecoveryTranslationTests(TestCase):
    def test_new_status_messages_have_english_text(self):
        from consumption import LOWER_RECOVERED
        from i18n import english_result
        self.assertIn("further consistent readings", english_result(LOWER_PENDING))
        self.assertIn("higher value was a misread", english_result(LOWER_RECOVERED))
        rejected = run.STANDALONE_REJECTED_NOTICE + " " + LOWER_PENDING
        self.assertIn("further consistent readings", english_result(rejected))


class LowerCorrectionGuardTests(TestCase):
    """0.3.1: a correction needs a plausible drop, and collecting it is no failed check."""

    def test_only_a_small_drop_counts_as_correction(self):
        from consumption import plausible_lower_drop
        stored = {"reading_litres": 10491600, "anchor_litres": 10491600, "timestamp": 0}
        # 20.11.: 10491.6 booked by mistake, the meter showed 10491.3 half an hour later.
        self.assertTrue(plausible_lower_drop(stored, 1800, "10491.33", 2, FLOW))
        # A frame shifted by one digit reads "04912.27": never a correction.
        self.assertFalse(plausible_lower_drop(stored, 1800, "04912.27", 2, FLOW))
        # Ten cubic metres lower right after the booking is no misread of the last digits ...
        self.assertFalse(plausible_lower_drop(stored, 600, "10481.60", 2, FLOW))
        # ... but allowed after a day (a wrong high value stood for a long time).
        self.assertTrue(plausible_lower_drop(stored, 24 * 3600, "10481.60", 2, FLOW))
        # Without a flow limit the default flow is used, not "anything goes".
        self.assertFalse(plausible_lower_drop(stored, 1800, "04912.27", 2, run.MAX_FLOW_LPH))
        self.assertFalse(plausible_lower_drop(stored, 1800, "10491.70", 2, FLOW))
        self.assertFalse(plausible_lower_drop(None, 1800, "10491.33", 2, FLOW))

    def test_collecting_lower_readings_does_not_start_the_failure_pause(self):
        from checks import schedule_next_check
        history = {"check_detail": LOWER_PENDING}
        for minute in range(5):
            schedule_next_check(history, "ocr_unclear", minute * 300.0, 10)
        self.assertNotIn("failure_attempts", history)
        self.assertNotIn("retry_suppressed", history)
        self.assertLessEqual(history["next_check_at"] - 1200.0, 300)
        history["check_detail"] = run.STANDALONE_REJECTED_NOTICE + " " + LOWER_PENDING
        schedule_next_check(history, "ocr_unclear", 1500.0, 10)
        self.assertNotIn("failure_attempts", history)
        history["check_detail"] = LOWER_READING
        for minute in range(3):
            schedule_next_check(history, "ocr_unclear", 1800.0 + minute * 300, 10)
        self.assertTrue(history["retry_suppressed"])


class KnownGoodGeometryTests(TestCase):
    def test_old_known_good_file_is_still_a_starting_point(self):
        geometry = {"crop": "1,2,3,4", "digit_boxes": [[0, 0, 1, 1]] * 8}
        self.assertEqual(geometry, run.usable_known_good_geometry(
            {"scope": "new", "camera": "camera.x", "geometry": geometry}, ("new", "old"), 8))
        # 0.2.9 file with a key that no longer matches: still offered when the digit count fits.
        self.assertEqual(geometry, run.usable_known_good_geometry(
            {"scope": "something-else", "geometry": geometry}, ("new", "old"), 8))
        self.assertIsNone(run.usable_known_good_geometry(
            {"scope": "something-else", "geometry": geometry}, ("new", "old"), 7))
        # New file for another camera: never.
        self.assertIsNone(run.usable_known_good_geometry(
            {"scope": "other-camera", "camera": "camera.y", "geometry": geometry}, ("new", "old"), 8))
        self.assertIsNone(run.usable_known_good_geometry(None, ("new",), 8))
