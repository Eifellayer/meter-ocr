"""Leading whole digits that cannot have changed since a verified reading."""

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

from checks import WINDOW_SECONDS, anchored_leading_digits, resolve_ocr_readings, within_anchor_bounds
from i18n import translate_page
import run


def panel_source():
    return (Path(__file__).resolve().parents[1] / "panel.py").read_text(encoding="utf-8")
from test_worker import synthetic_meter

FLOW = 6_000  # default maximum flow in litres per hour
NOW = 1_800_000_000


def anchor(reading, age=600):
    """Anchor in litres, as stored by track_reflection."""
    whole, _, fraction = reading.partition(".")
    return {"time": NOW - age, "value": int(whole) * 1000 + int(fraction.ljust(3, "0")[:3])}


class AnchoredLeadingDigitTests(TestCase):
    def test_unreadable_leading_one_from_the_real_log_is_filled(self):
        # 2026-11-18 07:27: "?0471.602" while the last verified reading was 10471.60.
        readings = ["?0471.602", "?0471.602", "10471.602", "?0471.60?", "?0471.602", "?0471.602"]
        normalized, filled = anchored_leading_digits(readings, anchor("10471.600"), NOW, 2, 5, FLOW)
        self.assertEqual([0], filled)
        self.assertTrue(all(row.startswith("1047") for row in normalized))
        value, confirmed = resolve_ocr_readings(normalized, 2, 5, standalone=True, standalone_composition=True)
        self.assertEqual("10471.602", value)
        self.assertTrue(confirmed)
        self.assertTrue(within_anchor_bounds(value, anchor("10471.600"), NOW, 2, 5, FLOW))

    def test_the_position_that_may_roll_over_is_never_filled(self):
        # 10 minutes at 6 m³/h can reach 10472.6: the fifth digit may have changed.
        readings = ["1047?.602", "1047?.602", "1047?.602"]
        self.assertIsNone(anchored_leading_digits(readings, anchor("10471.600"), NOW, 2, 5, FLOW))
        # Shortly before a carry the fourth digit is uncertain as well.
        readings = ["?04??.952", "?04??.952", "?04??.952"]
        normalized, filled = anchored_leading_digits(readings, anchor("10479.950"), NOW, 2, 5, FLOW)
        self.assertEqual([0], filled)
        self.assertEqual("?", normalized[0][3])

    def test_contradicting_majority_or_missing_anchor_does_not_fill(self):
        self.assertIsNone(anchored_leading_digits(
            ["70471.602", "70471.602", "?0471.602"], anchor("10471.600"), NOW, 2, 5, FLOW))
        readings = ["?0471.602", "?0471.602"]
        self.assertIsNone(anchored_leading_digits(readings, None, NOW, 2, 5, FLOW))
        self.assertIsNone(anchored_leading_digits(readings, anchor("10471.600", age=0), NOW, 2, 5, FLOW))
        self.assertIsNone(anchored_leading_digits(
            readings, anchor("10471.600", age=WINDOW_SECONDS + 1), NOW, 2, 5, FLOW))
        self.assertIsNone(anchored_leading_digits(readings, anchor("10471.600"), NOW, 2, 5, 0))
        # Nothing to do when every frozen digit was already readable.
        self.assertIsNone(anchored_leading_digits(
            ["10471.60?", "10471.60?"], anchor("10471.600"), NOW, 2, 5, FLOW))

    def test_a_wrong_crop_cannot_borrow_a_plausible_prefix(self):
        # Readable digits that contradict the anchor abort the fill entirely.
        self.assertIsNone(anchored_leading_digits(
            ["?8213.45?", "?8213.45?", "?8213.45?"], anchor("10471.600"), NOW, 2, 5, FLOW))
        # A matching prefix with an impossible jump is rejected by the bounds check.
        readings = ["?0479.45?", "?0479.45?", "?0479.45?"]
        normalized, _ = anchored_leading_digits(readings, anchor("10471.600"), NOW, 2, 5, FLOW)
        value, confirmed = resolve_ocr_readings(normalized, 2, 5, standalone=True, standalone_composition=True)
        self.assertEqual("10479.45?", value)
        self.assertTrue(confirmed)
        self.assertFalse(within_anchor_bounds(value, anchor("10471.600"), NOW, 2, 5, FLOW))

    def test_bounds_tolerate_one_jittering_step_but_not_a_lower_meter(self):
        reference = anchor("10472.330")
        self.assertTrue(within_anchor_bounds("10472.32", reference, NOW, 2, 5, FLOW))
        self.assertFalse(within_anchor_bounds("10472.31", reference, NOW, 2, 5, FLOW))
        self.assertFalse(within_anchor_bounds("10474.33", reference, NOW, 2, 5, FLOW))
        self.assertFalse(within_anchor_bounds("1047?.33", reference, NOW, 2, 5, FLOW))

    def test_panel_explains_the_method_in_both_languages(self):
        notice = "Unveränderliche führende Stellen aus dem zuletzt bestätigten Stand ergänzt."
        self.assertIn(f"anchored: '{notice}'", panel_source())
        self.assertIn("last confirmed reading", translate_page(notice))


class AnchoredWorkerTests(TestCase):
    def test_automatic_run_fills_the_leading_digit_from_the_verified_anchor(self):
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
        now = datetime.now(timezone.utc).timestamp()
        paths["HISTORY"].write_text(json.dumps({
            "reflection_anchor": {"time": now - 600, "value": 10465900},
        }))
        self.enterContext(patch.multiple(run, **paths))
        self.enterContext(patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}))
        self.enterContext(patch.object(run, "start_panel", return_value=(None, None, None)))
        with BytesIO() as stream:
            synthetic_meter().save(stream, "JPEG")
            self.enterContext(patch.object(run, "get_bytes", return_value=stream.getvalue()))
        self.enterContext(patch.object(run, "read_visible_digits", return_value="?0465.942"))
        self.enterContext(patch.object(run, "read_register", return_value=None))
        self.enterContext(patch.object(run, "publish_state"))
        self.enterContext(patch.object(run, "publish_consumption", side_effect=StopLoop))
        with self.assertRaises(StopLoop):
            run.main()
        history = json.loads(paths["HISTORY"].read_text())
        self.assertEqual(run.STANDALONE_PENDING, history["check_status"])
        self.assertEqual("10465.942", history["standalone_candidate"]["reading"])
        self.assertEqual("anchored", history["ocr_method"])

    def test_without_anchor_the_same_image_stays_unclear(self):
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
        self.enterContext(patch.multiple(run, **paths))
        self.enterContext(patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}))
        self.enterContext(patch.object(run, "start_panel", return_value=(None, None, None)))
        with BytesIO() as stream:
            synthetic_meter().save(stream, "JPEG")
            self.enterContext(patch.object(run, "get_bytes", return_value=stream.getvalue()))
        self.enterContext(patch.object(run, "read_visible_digits", return_value="?0465.942"))
        self.enterContext(patch.object(run, "read_register", return_value=None))
        self.enterContext(patch.object(run, "publish_state"))
        self.enterContext(patch.object(run, "publish_consumption", side_effect=StopLoop))
        with self.assertRaises(StopLoop):
            run.main()
        history = json.loads(paths["HISTORY"].read_text())
        self.assertEqual("ocr_unclear", history["check_status"])
        self.assertNotEqual("anchored", history.get("ocr_method"))
