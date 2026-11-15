"""Regression tests for the automatic worker, camera sources and local OCR."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks import (FRESH_SAMPLE_AGE, NORMAL_INTERVAL, RETRY_INTERVAL, WINDOW_SECONDS,
                    explain_uncertain_positions, read_register, record_sample, rolling_summary,
                    schedule_next_check)
from layout import find_digit_row
from settings import load_options
import run


def sample(now):
    return dict(esp_timestamp=now.isoformat(), raw_value="12345.170", actual_value="12345.170")


def synthetic_meter():
    image = Image.new("RGB", (500, 100), "white")
    font = ImageFont.truetype("DejaVuSansMono.ttf", 66)
    ImageDraw.Draw(image).text((18, 50), "12345", font=font, fill="black", anchor="lm")
    return image


class SourceTests(TestCase):
    def test_slfork_checks_cycle_on_both_sides_of_image_download(self):
        expected = {"timestamp_processed": {"main": "2026-11-15T08:01:00"},
                    "raw_value": {"main": "12345.170"}, "actual_value": {"main": "12345.170"}}
        changed = {**expected, "timestamp_processed": {"main": "2026-11-15T08:02:00"}}
        with patch.object(run, "get_bytes", side_effect=[json.dumps(expected), b"image",
                                                         OSError(), json.dumps(changed)]):
            self.assertIsNone(run.capture("http://meter", {}))
        with patch.object(run, "get_bytes", side_effect=[json.dumps(expected), b"image",
                                                         OSError(), json.dumps(expected)]):
            image, overlay, result = run.capture("http://meter", {})
            self.assertEqual((b"image", None, "12345.170"), (image, overlay, result["actual_value"]))
        with patch.object(run, "get_bytes", return_value=b"[]"):
            with self.assertRaises(ValueError):
                run.capture("http://meter", {})

    def test_camera_reference_validation_and_no_reference_mode(self):
        now = datetime.now(timezone.utc)
        for attributes, reported, expected in (
            ({"unit_of_measurement": "m³"}, now.isoformat(), "12345.170"),
            ({"unit_of_measurement": "kWh"}, now.isoformat(), None),
            ({"unit_of_measurement": "m³"}, (now - timedelta(minutes=6)).isoformat(), None),
            ({"unit_of_measurement": "m³"}, "2026-11-15T08:01:00", None),
        ):
            with self.subTest(attributes=attributes, reported=reported):
                state = dict(attributes=attributes, last_reported=reported, state="12345.170")
                with patch.object(run, "get_bytes", side_effect=[b"image", json.dumps(state)]) as fetch:
                    _, _, result = run.capture_camera("camera.meter", "sensor.meter", "dummy", timezone.utc)
                self.assertTrue(result["reference_required"])
                self.assertEqual(expected, result["actual_value"])
                self.assertEqual(2, fetch.call_count)
        with patch.object(run, "get_bytes", return_value=b"image") as fetch:
            _, _, result = run.capture_camera("camera.meter", "", "dummy", timezone.utc)
        self.assertFalse(result["reference_required"])
        self.assertEqual(1, fetch.call_count)

    def test_automatic_overlay_and_manual_fallback(self):
        overlay = Image.new("RGB", (360, 130), "white")
        draw = ImageDraw.Draw(overlay)
        for index in range(8):
            left = 35 + index * 34
            draw.rectangle((left, 40, left + 28, 85), outline=(0, 180, 0), width=2)
        layout = find_digit_row(overlay)
        self.assertIsNotNone(layout)
        with BytesIO() as encoded:
            overlay.save(encoded, format="PNG")
            frame = Image.new("RGB", overlay.size, "white")
            crop, width, whole, fractions, mode = run.select_register(frame, encoded.getvalue(), (0, 0, 100, 100), 80)
        self.assertEqual(("auto", 5, 3), (mode, len(whole), len(fractions)))
        self.assertLess(width, crop.width)
        result = run.select_register(frame, b"bad overlay", (0, 0, 100, 100), 80)
        self.assertEqual("manual", result[-1])
        with self.assertRaises(ValueError):
            run.select_register(frame, None, (0, 0, 400, 100), 80)


class OCRTests(TestCase):
    def test_tesseract_reads_a_synthetic_register(self):
        image = synthetic_meter()
        self.assertEqual("12345", read_register(image, False, force_polarity=True))
        self.assertEqual("12345", read_register(image, False))

    def test_no_reads_do_not_invent_digit_positions(self):
        detail = explain_uncertain_positions(["?????.???"] * 5, 2)
        self.assertIn("Keine Ziffern lesbar", detail)
        self.assertNotIn("Vorkommastelle", detail)


class StateTests(TestCase):
    def test_startup_upgrade_keeps_values_and_supervisor_overrides(self):
        options = load_options({"ocr_versuche": 8}, {"options": {"esp_url": "http://my-meter",
                                                               "ausschnitt": "1,2,50,55",
                                                               "ocr_versuche": 6,
                                                               "intervall_sekunden": 20}})
        self.assertEqual(("http://my-meter", "1,2,50,55", 8),
                         (options["esp_url"], options["ausschnitt"], options["ocr_versuche"]))
        self.assertNotIn("intervall_sekunden", options)

    def test_rolling_window_survives_restart_without_duplicate_confirmation(self):
        now = datetime.now(timezone.utc)
        history = {}
        self.assertTrue(record_sample(history, sample(now), "12345.???", timezone.utc, now))
        history = json.loads(json.dumps(history))
        self.assertFalse(record_sample(history, sample(now), "12345.???", timezone.utc, now))
        older = now - timedelta(seconds=FRESH_SAMPLE_AGE + 1)
        self.assertFalse(record_sample(history, sample(older), "12345.???", timezone.utc, now))
        self.assertEqual(1, rolling_summary(history, now)["matches_last_24h"])
        self.assertEqual(0, rolling_summary(history, now + timedelta(seconds=WINDOW_SECONDS))["matches_last_24h"])
        schedule_next_check(history, "difference", now.timestamp())
        self.assertEqual(now.timestamp() + RETRY_INTERVAL, history["next_check_at"])
        schedule_next_check(history, "match", now.timestamp())
        self.assertNotIn("failure_since", history)
        self.assertEqual(now.timestamp() + NORMAL_INTERVAL, history["next_check_at"])

    def test_standalone_sensor_retains_exact_precision_and_rejects_lower_readings(self):
        data = sample(datetime.now(timezone.utc))
        latest = run.standalone_reading("camera.meter", data, "12345.170", 2, None)
        self.assertIsNone(run.standalone_reading("camera.meter", data, "12344.990", 2, latest))
        self.assertIsNotNone(run.standalone_reading("camera.meter", data, "12345.???", 0, latest))
        with patch.object(run, "publish_state") as publish:
            run.publish_standalone({"standalone_reading": latest, "check_status": "ocr_only"}, "camera.meter", "stub")
            url, body, _ = publish.call_args.args
        self.assertTrue(url.endswith("sensor.rf1_ocr_zaehlerstand"))
        self.assertEqual("12345.17", body["state"])
        self.assertEqual("m³", body["attributes"]["unit_of_measurement"])
        self.assertNotIn("state_class", body["attributes"])
        with patch.object(run, "publish_state") as publish:
            run.publish_standalone({"standalone_reading": latest, "check_status": "ocr_unclear"}, "camera.meter", "stub")
            self.assertEqual("unavailable", publish.call_args.args[1]["state"])

    def test_main_reads_esphome_camera_and_publishes_standalone_sensor(self):
        class StopLoop(Exception):
            pass

        folder = Path(self.enterContext(TemporaryDirectory()))
        files = {name: folder / name for name in (
            "OPTIONS", "HISTORY", "EFFECTIVE_OPTIONS", "AUTO_RULES", "LANGUAGE_MODES",
            "SOURCE_SETTINGS", "NOTIFICATIONS", "DESTINATION", "GOOD_IMAGE", "TEST_IMAGE",
        )}
        files["OPTIONS"].write_text(json.dumps({"ausschnitt": "0,0,500,100", "vorkomma_breite": 350,
                                                "ocr_versuche": 1}))
        files["SOURCE_SETTINGS"].write_text(json.dumps({"mode": "esphome", "url": "", "camera": "camera.esp",
                                                        "reference": "sensor.ignored"}))
        self.enterContext(patch.multiple(run, **files))
        self.enterContext(patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}))
        with BytesIO() as stream:
            synthetic_meter().save(stream, "PNG")
            photo = stream.getvalue()
        self.enterContext(patch.object(run, "start_panel", return_value=(None, None)))
        fetch = self.enterContext(patch.object(run, "get_bytes", return_value=photo))
        recognize = self.enterContext(patch.object(run, "read_visible_digits", return_value="12345.???"))
        published = {}

        def collect(url, payload, _):
            entity = url.rsplit("/", 1)[1]
            published[entity] = payload
            if entity == run.OCR_ENTITY:
                raise StopLoop

        self.enterContext(patch.object(run, "publish_state", collect))
        with self.assertRaises(StopLoop):
            run.main()
        fetch.assert_called_once_with("http://supervisor/core/api/camera_proxy/camera.esp", "stub")
        self.assertEqual(2, recognize.call_count)
        self.assertEqual("12345", published[run.OCR_ENTITY]["state"])
        self.assertEqual("ocr_only", published[run.CHECK_ENTITY]["state"])
        self.assertEqual([], json.loads(files["HISTORY"].read_text())["confirmations"])
        with Image.open(files["DESTINATION"]) as current:
            self.assertEqual("JPEG", current.format)

    def test_main_keeps_manual_run_separate_from_automated_entities_and_history(self):
        class StopLoop(Exception):
            pass

        folder = Path(self.enterContext(TemporaryDirectory()))
        paths = {name: folder / f"{name.lower()}.json" for name in (
            "OPTIONS", "HISTORY", "EFFECTIVE_OPTIONS", "AUTO_RULES", "LANGUAGE_MODES",
            "SOURCE_SETTINGS", "NOTIFICATIONS",
            "DESTINATION", "GOOD_IMAGE", "TEST_IMAGE",
        )}
        paths["OPTIONS"].write_text(json.dumps({"esp_url": "http://meter", "ausschnitt": "0,0,500,100", "vorkomma_breite": 350}))
        self.enterContext(patch.multiple(run, **paths))
        self.enterContext(patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}))
        with BytesIO() as stream:
            synthetic_meter().save(stream, "JPEG")
            jpeg = stream.getvalue()
        history_updates = []
        published = []
        progress_updates = []

        def fake_panel(history_path, current, good, requested, *_):
            requested.put_nowait({
                "request_id": 1, "decimals": 2, "attempts": 1, "polarity": "dark",
                "crop_mode": "manual", "crop": "0,0,480,100", "width": 350,
            })
            return None, lambda *args, **kwargs: progress_updates.append((args, kwargs))

        def fake_publish(url, payload, _):
            published.append((url, payload))
            history_updates.append(json.loads(paths["HISTORY"].read_text()))
            if url.endswith(run.ENTITY):
                raise StopLoop

        data = sample(datetime.now(timezone.utc))
        self.enterContext(patch.object(run, "start_panel", fake_panel))
        self.enterContext(patch.object(run, "capture", return_value=(jpeg, None, data)))
        self.enterContext(patch.object(run, "read_visible_digits", return_value="12345.120"))
        self.enterContext(patch.object(run, "publish_state", fake_publish))
        with self.assertRaises(StopLoop):
            run.main()
        self.assertEqual("difference", progress_updates[-1][1]["outcome"])
        with Image.open(paths["TEST_IMAGE"]) as preview:
            self.assertEqual((480, 100), preview.size)
        self.assertEqual([run.CHECK_ENTITY, run.ENTITY], [url.rsplit("/", 1)[1] for url, _ in published])
        self.assertEqual("match", published[0][1]["state"])
        self.assertEqual(0, published[1][1]["attributes"]["decimal_places"])
        history = history_updates[-1]
        self.assertEqual("difference", history["manual_result"]["status"])
        self.assertEqual(1, len(history["confirmations"]))
        self.assertEqual(0, history["comparison_decimals"])
        self.assertTrue(paths["GOOD_IMAGE"].exists())
