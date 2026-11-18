"""Regression tests for the automatic worker, camera sources and local OCR."""

from datetime import datetime, timedelta, timezone
from email.message import Message
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks import (EIGHTH_DIGIT_RETRY_SECONDS, eighth_digit_retry_due, resume_optional_eighth_digit,
                    FRESH_SAMPLE_AGE, NORMAL_INTERVAL, OCR_PROFILES, RETRY_INTERVAL, WINDOW_SECONDS,
                    LAST_DIGIT_NOTICE, LAST_DIGIT_PASS, compare_sample, explain_uncertain_positions,
                    automatic_interval_minutes, defer_duplicate_cycle, last_check_at, read_register, read_with_retries, record_sample,
                    reschedule_next_check, rolling_summary, schedule_next_check, slfork_reference,
                    estimate_missing_digit, single_missing_digit, track_reflection)
from consumption import EXCESSIVE_INCREASE, FALLBACK_PLAUSIBLE, FALLBACK_UNKNOWN_TIME, LOWER_READING, fallback_detail
from layout import crop_coordinates, find_digit_row, rotated_width, turn_crop
from settings import load_options
from source_settings import discovered_sources
import run


def sample(now):
    return dict(esp_timestamp=now.isoformat(), raw_value="12345.170", actual_value="12345.170")


def synthetic_meter():
    image = Image.new("RGB", (500, 100), "white")
    font = ImageFont.truetype("DejaVuSansMono.ttf", 66)
    ImageDraw.Draw(image).text((18, 50), "12345", font=font, fill="black", anchor="lm")
    return image


class SourceTests(TestCase):
    def test_discovery_falls_back_to_state_api_when_template_has_no_results(self):
        states = [{"entity_id": "camera.meter",
                   "attributes": {"friendly_name": "Meter camera"}, "state": "idle"}]
        with patch.object(run, "open_core", return_value=BytesIO(b'{"cameras": [], "devices": []}')):
            with patch.object(run, "get_bytes", return_value=json.dumps(states).encode()) as fallback:
                self.assertEqual([{"mode": "esphome", "camera": "camera.meter", "label": "Meter camera"}],
                                 run.discover_ha_sources("test-token"))
        fallback.assert_called_once_with("http://supervisor/core/api/states", "test-token", timeout=5)

    def test_optional_factory_reset_keeps_only_consumption_statistics(self):
        original = {
            "consumption": {"source": ["camera", "camera.meter"], "total_litres": 1240,
                            "timestamp": 100, "reading_litres": 32100, "step_litres": 10},
            "consumption_statistics": {"source": "camera.meter", "samples": [[100, 1240, 10]]},
            "manual_result": {"ocr": "12345.001"}, "confirmations": [100], "check_status": "match",
        }
        kept = run.factory_reset_history(original, keep_statistics=True)
        self.assertEqual({"consumption", "consumption_statistics", "statistics_preserved_after_reset"}, set(kept))
        self.assertEqual(1240, kept["consumption"]["total_litres"])
        self.assertEqual([[100, 1240, 10]], kept["consumption_statistics"]["samples"])
        kept["consumption_statistics"]["samples"].append([101, 1300, 10])
        self.assertEqual(1, len(original["consumption_statistics"]["samples"]))
        self.assertEqual({}, run.factory_reset_history(original))

    def test_failed_angle_correction_requests_fresh_image_for_mismatch_or_uncertainty(self):
        for outcome in ("difference", "ocr_unclear"):
            with self.subTest(outcome=outcome):
                self.assertTrue(run.failed_angle_requires_fresh_image(1, outcome))
        for outcome in ("match", "ocr_only", "standalone_pending", "stale_sample"):
            with self.subTest(outcome=outcome):
                self.assertFalse(run.failed_angle_requires_fresh_image(1, outcome))
        self.assertFalse(run.failed_angle_requires_fresh_image(0, "difference"))

    def test_row_ocr_only_fills_a_missing_cell_when_other_digits_agree(self):
        boxes = [(x, 2, x + 15, 28) for x in range(0, 75, 15)]
        image = Image.new("RGB", (75, 30), "white")
        for row, expected in (("12345", "12345"), ("18345", "12?45")):
            with self.subTest(row=row):
                reads = iter(("1", "2", None, "4", "5", row))
                self.assertEqual(expected, run.read_visible_digits(
                    image, 75, boxes, [], False, "auto", profile=OCR_PROFILES[0],
                    whole_digits=5, fraction_digits=0, prefer_boxes=True,
                    recognize=lambda *_args, **_kwargs: next(reads)))

    def test_small_signed_rotation_restores_ocr_alignment(self):
        upright = synthetic_meter()
        tilted = turn_crop(upright, 6)
        self.assertEqual(rotated_width(*upright.size, 6), tilted.width)
        recovered = turn_crop(tilted, -6)
        self.assertEqual(rotated_width(*tilted.size, -6), recovered.width)
        self.assertEqual((0, 0, tilted.width, tilted.height), crop_coordinates(
            f"0,0,{tilted.width},{tilted.height}", recovered.width, -6
        ))
        self.assertEqual("12345", read_register(recovered, False, profile=OCR_PROFILES[2]))

    def test_camera_finds_digit_strip_when_default_crop_cuts_off_digits(self):
        frame = Image.new("RGB", (640, 480), "#467b88")
        draw = ImageDraw.Draw(frame)
        draw.rectangle((85, 52, 408, 110), fill="#031426")
        draw.rectangle((285, 52, 408, 110), fill="#461629")
        font = ImageFont.truetype("DejaVuSansMono.ttf", 38)
        for index, digit in enumerate("10449227"):
            draw.text((105 + 39 * index, 82), digit, font=font, anchor="mm", fill="#70cad5")
        draw.text((110, 145), "GAS SER 29823", font=font, fill="#102427")
        register, width, whole, fractions, mode = run.select_register(
            frame, None, (52, 79, 564, 151), 350, detect_raw=True
        )
        self.assertEqual(("raw_auto", 5, 3), (mode, len(whole), len(fractions)))
        self.assertEqual("10449.227",
                         run.read_visible_digits(register, width, whole, fractions, True, "auto",
                                                 profile=OCR_PROFILES[0]))

    def test_raw_detector_does_not_treat_text_without_a_meter_window_as_digits(self):
        frame = Image.new("RGB", (640, 480), "white")
        ImageDraw.Draw(frame).text(
            (85, 52), "10449227", font=ImageFont.truetype("DejaVuSansMono.ttf", 38), fill="black"
        )
        register, _, _, _, mode = run.select_register(
            frame, None, (52, 79, 564, 151), 350, detect_raw=True
        )
        self.assertEqual(("manual", (512, 72)), (mode, register.size))

    def test_edge_camera_reads_fresh_jpeg_from_either_firmware(self):
        base = "http://meter"
        modern = base + "/camera?task=capture"
        legacy = base + "/capture_with_flashlight"
        not_found = HTTPError(modern, 404, "Not found", {}, None)
        for responses, urls in (([b"jpeg"], [modern]), ([not_found, b"jpeg"], [modern, legacy])):
            with self.subTest(urls=urls), patch.object(run, "get_bytes", side_effect=responses) as fetch:
                picture, overlay, data = run.capture_edge_camera(base, timezone.utc)
                self.assertEqual((b"jpeg", None, False), (picture, overlay, data["reference_required"]))
                self.assertIsNone(data["actual_value"])
                self.assertEqual(urls, [call.args[0] for call in fetch.call_args_list])

    def test_last_wheel_reads_fragmented_mjpeg_from_esp_and_home_assistant(self):
        def jpg(ink):
            with BytesIO() as buffer:
                Image.new("RGB", (80, 45), ink).save(buffer, "JPEG")
                return buffer.getvalue()

        class Stream(BytesIO):
            elapsed = 0

            def read1(self, size):
                block = super().read1(min(size, 23))
                self.elapsed += .004
                return block

        images = [jpg(ink) for ink in ("black", "gray", "white", "blue")]
        for from_ha, spacing in ((False, 0), (True, 0), (False, .35), (True, .35)):
            with self.subTest(from_ha=from_ha, spacing=spacing):
                feed = bytearray()
                for picture in [b"\xff\xd8truncated\xff\xd9", images[0], *images]:
                    feed.extend(b"\r\n--meter-feed\r\nContent-Type: image/jpeg\r\n")
                    if not from_ha:
                        feed.extend(f"Content-Length: {len(picture)}\r\n".encode())
                    feed.extend(b"\r\n" + picture)
                feed.extend(b"\r\n--meter-feed--\r\n")
                stream = Stream(feed)
                stream.headers = Message()
                stream.headers["Content-Type"] = 'multipart/x-mixed-replace; boundary="meter-feed"'
                token = "test-token" if from_ha else None
                opener = "open_core" if from_ha else "urlopen"
                expected = [images[0], images[2]] if spacing else images[:3]
                with (patch.object(run, opener, return_value=stream) as request,
                      patch.object(run.time, "monotonic", side_effect=lambda: stream.elapsed),
                      patch.object(run, "LAST_WHEEL_STREAM_SPACING", spacing)):
                    self.assertEqual(expected, run.read_last_wheel_stream("http://meter/stream", token=token))
                self.assertTrue(stream.closed)
                self.assertEqual("Bearer test-token" if from_ha else None,
                                 request.call_args.args[0].get_header("Authorization"))

    def test_ocr_follows_a_synthetic_five_to_six_image_sequence(self):
        font = ImageFont.truetype("DejaVuSansMono-Bold.ttf", 47)
        frames = []
        for digit in ("5", "5", "6"):
            frame = Image.new("L", (64, 68), 15)
            ImageDraw.Draw(frame).text((14, 4), digit, 245, font=font)
            with BytesIO() as encoded:
                frame.save(encoded, "JPEG")
                encoded.seek(0)
                with Image.open(encoded) as decoded:
                    frames.append(decoded.copy())
        for profile in OCR_PROFILES[:2]:
            values = [read_register(frame, True, 1, force_polarity=True, profile=profile) for frame in frames]
            self.assertEqual(("5", "6"), run.last_wheel_transition(values))

    def test_last_wheel_stream_transition_requires_a_forward_adjacent_pair(self):
        for frames, observed in ((("5", "?", "6"), ("5", "6")), (("9", "0", "0"), ("9", "0")),
                                 (("5", "5", "5"), None), (("5", "?", "5"), None),
                                 (("6", "5"), None), (("4", "6"), None), (("5", "6", "5"), None)):
            with self.subTest(frames=frames):
                self.assertEqual(observed, run.last_wheel_transition(frames))

    def test_discovery_lists_only_camera_entities_and_valid_esp_addresses(self):
        sources = discovered_sources({
            "cameras": [{"camera": "camera.test", "label": "Camera"}, {"camera": "sensor.extra"},
                        {"camera": "camera.gasmeter", "label": "Zählerbild"}],
            "devices": [{"url": "http://meter/", "label": "Meter"}, {"url": "http://meter"},
                        {"ip": "192.168.0.10", "label": "Second meter"},
                        {"url": "http://user:secret@meter"}, {"url": "file:///tmp/example"}],
        })
        self.assertEqual(["camera.gasmeter", "http://meter", "http://192.168.0.10", "camera.test"],
                         [source.get("camera") or source["url"] for source in sources])

    def test_slfork_aborted_cycle_skips_aligned_images(self):
        payload = {"process_error": -2, "timestamp_processed": {"main": "2026-11-15T08:01:00"}}
        diagnostics = {}
        with patch.object(run, "get_bytes", return_value=json.dumps(payload)) as fetch:
            self.assertIsNone(run.capture("http://meter", diagnostics))
            fetch.assert_called_once_with("http://meter/process_data")
        self.assertTrue(run.slfork_cycle_failed(diagnostics))

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

    def test_slfork_fallback_timestamps_do_not_masquerade_as_new_measurements(self):
        now = datetime.now(timezone.utc)
        stamp = now.timestamp()
        earlier = now - timedelta(minutes=10)
        data = {**sample(now), "actual_value": "12346.0416", "raw_value": "12340",
                "slfork_fallback_value": "12346.0416",
                "slfork_value_status": "Rate Too High (<) | Use Fallback",
                "slfork_last_valid_timestamp": now.isoformat()}
        self.assertIsNone(slfork_reference(data, stamp, timezone.utc, {})["reference_time"])
        known = {"reading": "12346.04160", "time": earlier.timestamp()}
        info = slfork_reference(data, stamp, timezone.utc, known)
        self.assertTrue(info["reference_is_fallback"])
        self.assertEqual(("12346.0416", earlier.timestamp()), (info["reference"], info["reference_time"]))
        self.assertEqual("slfork_unclear", compare_sample({**data, **info}, "12346.337", 0)[0])
        self.assertEqual("slfork_unclear", compare_sample(
            {**data, **info, "raw_value": "12346.0416"}, "12346.041", 3)[0])
        old_timestamp = {**data, "slfork_last_valid_timestamp": earlier.isoformat(), "slfork_value_status": None}
        self.assertEqual(info, slfork_reference(old_timestamp, stamp, timezone.utc, {}))
        fresh = {**data, "slfork_value_status": "000 Valid", "raw_value": "12346.0416"}
        self.assertEqual({"reference": "12346.0416", "reference_time": stamp, "reference_is_fallback": False},
                         slfork_reference(fresh, stamp, timezone.utc, known))

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


    def test_camera_crop_is_readable_at_all_four_rotations(self):
        upright = synthetic_meter()
        rotations = {
            0: None,
            90: Image.Transpose.ROTATE_90,
            180: Image.Transpose.ROTATE_180,
            270: Image.Transpose.ROTATE_270,
        }
        for rotation, transform in rotations.items():
            with self.subTest(rotation=rotation):
                raw = upright if transform is None else upright.transpose(transform)
                frame = Image.new("RGB", (3000, 1200), "gray")
                left, top = 2190, 310
                frame.paste(raw, (left, top))
                crop_text = f"{left},{top},{left + raw.width},{top + raw.height}"
                crop = crop_coordinates(crop_text, upright.width, rotation=rotation)
                register, width, _, _, mode = run.select_register(
                    frame, None, crop, upright.width, rotation=rotation)

                self.assertEqual("manual", mode)
                self.assertEqual(upright.size, register.size)
                self.assertEqual(upright.width, width)
                self.assertEqual(upright.tobytes(), register.tobytes())
                self.assertEqual("12345", read_register(register, False))
        with self.assertRaises(ValueError):
            crop_coordinates("2190,310,2290,810", upright.width)


class OCRTests(TestCase):
    def test_tesseract_reads_a_synthetic_register(self):
        image = synthetic_meter()
        self.assertEqual("12345", read_register(image, False, force_polarity=True))
        self.assertEqual("12345", read_register(image, False))

    def test_ocr_for_light_digits_and_slightly_tilted_image(self):
        meter = synthetic_meter().convert("L")
        light_digits = ImageOps.invert(meter).point(lambda value: 20 + value // 4)
        self.assertEqual("12345", read_register(light_digits, False))
        tilted = meter.rotate(6, expand=True, fillcolor=255)
        self.assertEqual("12345", read_register(tilted, False))

    def test_lighting_correction_recovers_a_display_under_a_gradient(self):
        size = (305, 116)
        gradient = Image.linear_gradient("L").transpose(Image.Transpose.ROTATE_90).resize(size)
        gradient = gradient.point(lambda value: int(45 + value * 0.73))
        font = ImageFont.truetype("DejaVuSansMono.ttf", 82)
        for number, contrast in (("27536", -37), ("38605", 36)):
            with self.subTest(light_digits=contrast > 0):
                mask = Image.new("L", size, 0)
                ImageDraw.Draw(mask).text((18, 61), number, font=font, fill=255, anchor="lm")
                ink = gradient.point(lambda level: min(255, max(0, level + contrast)))
                meter = Image.composite(ink, gradient, mask)
                self.assertEqual(number, read_register(meter, False, profile=OCR_PROFILES[2]))
        self.assertIsNone(read_register(gradient, False, profile=OCR_PROFILES[2]))

    def test_no_reads_do_not_invent_digit_positions(self):
        detail = explain_uncertain_positions(["?????.???"] * 5, 2)
        self.assertIn("Keine Ziffern lesbar", detail)
        self.assertNotIn("Vorkommastelle", detail)

    def test_isolated_digit_needs_agreement_between_alternate_segmentation_modes(self):
        image = Image.new("L", (40, 60), "white")
        ImageDraw.Draw(image).line([(9, 17), (29, 17), (17, 46)], fill=0, width=4)
        for alternate, expected in ((b"7", "7"), (b"1", None)):
            with self.subTest(alternate=alternate), patch("checks.subprocess.run") as process:
                process.side_effect = [Mock(stdout=result) for result in (b"", b"", b"", b"7", alternate)]
                self.assertEqual(expected, read_register(image, False, 1, force_polarity=True,
                                                         isolated_digit=True))
                self.assertEqual(["10", "10", "10", "8", "13"],
                                 [call.args[0][6] for call in process.call_args_list])


class SingleDigitRecheckTests(TestCase):
    def test_reads_only_the_shifted_second_decimal_and_preserves_the_other_boxes(self):
        register = Image.new("RGB", (400, 100))
        boxes = [(50 * index + 5, 20, 50 * index + 45, 80) for index in range(8)]
        layout = (register, 250, boxes[:5], boxes[5:])
        read = Mock(return_value="4")
        result, used = run.recover_single_digit(
            layout, "10465.9?", "10465.9?2", 5, 3, read, 10, lambda *_: None,
            lambda: False, lambda reading: reading == "10465.942",
        )
        recovered, whole, fraction = result
        self.assertEqual("10465.942", recovered)
        self.assertEqual(2, used)
        self.assertEqual(boxes[:6], [*whole, fraction[0]])
        self.assertEqual(boxes[7], fraction[2])
        self.assertNotEqual(boxes[6], fraction[1])
        self.assertEqual([fraction[1], fraction[1]], [call.args[0] for call in read.call_args_list])

    def test_rejects_disagreement_and_respects_the_remaining_budget(self):
        register = Image.new("RGB", (400, 100))
        boxes = [(50 * index + 5, 20, 50 * index + 45, 80) for index in range(8)]
        layout = (register, 250, boxes[:5], boxes[5:])
        read = Mock(side_effect=["4", "7", "4", "7"])
        result, used = run.recover_single_digit(
            layout, "10465.9?", "10465.9?2", 5, 3, read, 4, lambda *_: None,
            lambda: False, lambda _: True,
        )
        self.assertIsNone(result)
        self.assertEqual(4, used)
    def test_moves_a_missing_whole_or_decimal_digit_horizontally_with_fixed_size(self):
        image = Image.new("RGB", (400, 100))
        boxes = [(50 * index + 5, 20, 50 * index + 45, 80) for index in range(8)]
        layout = (image, 250, boxes[:5], boxes[5:])
        value = "10465.942"
        for index in (1, 6):
            position = index + (index >= 5)
            digit = value[position]
            pattern = value[:position] + "?" + value[position + 1:]
            left, top, right, bottom = boxes[index]
            self.assertEqual([(left - 2, top, right - 2, bottom), (left + 2, top, right + 2, bottom)],
                             list(run.single_digit_frames(boxes, index, image.size)))
            for dx in (-2, 2):
                with self.subTest(index=index, dx=dx):
                    preferred = (left + dx, top, right + dx, bottom)
                    read = Mock(side_effect=lambda box, _: digit if box == preferred else "?")
                    result, _ = run.recover_single_digit(
                        layout, pattern, pattern, 5, 3, read, 10, lambda *_: None,
                        lambda: False, lambda candidate: candidate == value,
                    )
                    recovered, whole, fraction = result
                    expected = boxes.copy()
                    expected[index] = preferred
                    self.assertEqual(value, recovered)
                    self.assertEqual(expected, [*whole, *fraction])
                    for call in read.call_args_list:
                        x0, y0, x1, y1 = call.args[0]
                        self.assertEqual((right - left, bottom - top), (x1 - x0, y1 - y0))

    def test_last_roller_can_be_checked_higher_or_lower_without_changing_neighbours(self):
        image = Image.new("RGB", (400, 100))
        boxes = [(50 * index + 5, 0, 50 * index + 45, 100) for index in range(8)]
        layout = (image, 250, boxes[:5], boxes[5:])
        left, top, right, bottom = boxes[7]
        preferred = (left, top + 7, right, bottom)
        read = Mock(side_effect=lambda box, _: "2" if box == preferred else "?")
        result, used = run.recover_single_digit(layout, "10465.94?", "10465.94?", 5, 3, read, 6,
                                                 lambda *_: None, lambda: False, lambda _: True)
        self.assertEqual("10465.942", result[0])
        self.assertEqual(3, used)
        self.assertEqual(boxes[:7], [*result[1], *result[2][:-1]])
        self.assertEqual(preferred, result[2][-1])


class StateTests(TestCase):
    def test_reflection_estimate_requires_one_digit_and_unique_time_bounds(self):
        previous = {"time": 100, "value": 12345110}
        following = {"time": 220, "value": 12345120}
        self.assertEqual({"left": "12345.1", "digit": "1", "right": "5", "time": 160},
                         estimate_missing_digit("12345.1?5", 160, previous, following, 3, 6000))
        self.assertIsNone(estimate_missing_digit(
            "12345.1?5", 160, previous, {**following, "value": 12345126}, 3, 6000))
        self.assertIsNone(estimate_missing_digit("12345.1?5", 160, previous, following, 3, 60))
        self.assertIsNone(single_missing_digit("12345.1??", ["12345.1??"] * 3, 3, 5))
        self.assertIsNone(single_missing_digit("12345.1?5", ["12345.1?5", "12345.1?4"], 3, 5))

    def test_reflection_can_start_with_a_manual_value_and_await_a_confirmed_reading(self):
        history = {}
        rules = {"decimals": 3, "integer_digits": 5, "max_flow_lph": 6000}
        for stamp in (140, 150, 160):
            track_reflection(history, "12345.1?5", ["12345.1?5"] * 2, stamp,
                             verified=False, unclear=True, enabled=False, **rules)
        self.assertEqual(3, history["reflection_streak"]["count"])
        self.assertNotIn("reflection_pending", history)

        manual = {"time": 100, "value": 12345110}
        track_reflection(history, "12345.1?5", ["12345.1?5"] * 2, 160,
                         verified=False, unclear=True, enabled=True, manual_anchor=manual, **rules)
        track_reflection(history, "12345.120", [], 200, verified=False, unclear=False, enabled=True, **rules)
        self.assertNotIn("reflection_estimate", history)
        track_reflection(history, "12345.120", [], 220, verified=True, unclear=False, enabled=True, **rules)
        self.assertEqual("1", history["reflection_estimate"]["digit"])
        self.assertEqual({"time": 220, "value": 12345120}, history["reflection_anchor"])
        self.assertNotIn("reflection_pending", history)

    def test_partial_seven_digit_compare_never_rounds_an_unknown_eighth(self):
        now = datetime.now(timezone.utc)
        data = {**sample(now), "raw_value": "10475.155", "actual_value": "10475.155"}
        self.assertEqual("difference", compare_sample(data, "10475.15?", 2)[0])
        status, detail = compare_sample(data, "10475.15?", 2, exact_prefix=True)
        self.assertEqual("match", status)
        self.assertIn("ohne Rundung", detail)
        self.assertEqual("difference", compare_sample(data, "10475.14?", 2, exact_prefix=True)[0])
        self.assertEqual("ocr_unclear", compare_sample(
            data, "10475.1??", 2, exact_prefix=True,
        )[0])
        self.assertEqual("ocr_unclear", compare_sample(
            data, "10475.15?", 2, ocr_confirmed=False, exact_prefix=True,
        )[0])
        self.assertEqual("slfork_unclear", compare_sample(
            {**data, "raw_value": "10475.145"}, "10475.15?", 2, exact_prefix=True,
        )[0])
        self.assertEqual("slfork_unclear", compare_sample(
            {**data, "reference_is_fallback": True}, "10475.15?", 2, exact_prefix=True,
        )[0])
        reading, confirmed, attempts = read_with_retries(
            lambda _: "10475.15?", data, 2, max_attempts=2, exact_prefix=True,
        )
        self.assertEqual(("10475.15?", True, 1), (reading, confirmed, attempts))
        history = {}
        self.assertTrue(record_sample(history, data, "10475.15?", timezone.utc, now, 2,
                                      readings=("10475.15?",), exact_prefix=True))
        self.assertEqual("match", history["status"])
        self.assertEqual(1, len(history["confirmations"]))

    def test_optional_eighth_digit_search_restarts_only_after_due_time(self):
        source = {"mode": "camera", "camera": "camera.meter", "reference": "sensor.meter", "selected": True}
        rules = {"decimals": 3, "fraction_digits": 3, "precision_mode": False,
                 "crop_revision": "saved",
                 "stationary_partial_scope": run.calibration_source_id([source, "saved"])}
        history = {}
        now = 1600000000
        calls = []

        def begin():
            calls.append("start")
            return True

        self.assertTrue(eighth_digit_retry_due(rules, source, history, now))
        self.assertTrue(resume_optional_eighth_digit(history, rules, source, now, begin))
        self.assertEqual(now + EIGHTH_DIGIT_RETRY_SECONDS, history["eighth_digit_retry_at"])
        self.assertFalse(resume_optional_eighth_digit(history, rules, source, now + 60, begin))
        self.assertEqual(["start"], calls)
        self.assertTrue(resume_optional_eighth_digit(
            history, rules, source, now + EIGHTH_DIGIT_RETRY_SECONDS, begin,
        ))
        self.assertEqual(["start", "start"], calls)
        # Simulate a restart: the persisted next-at time prevents an immediate
        # duplicate scan. Older histories without this field start the fine check.
        restored = dict(history)
        self.assertFalse(eighth_digit_retry_due(rules, source, restored, now + EIGHTH_DIGIT_RETRY_SECONDS + 10))
        self.assertTrue(eighth_digit_retry_due(rules, source, {}, now))
        self.assertFalse(resume_optional_eighth_digit({}, {**rules, "precision_mode": True},
                                                      source, now, begin))
        self.assertFalse(resume_optional_eighth_digit({}, {**rules, "crop_revision": "other"},
                                                      source, now, begin))
        self.assertFalse(resume_optional_eighth_digit({}, rules, {**source, "camera": "other"},
                                                      now, begin))
        self.assertFalse(resume_optional_eighth_digit({}, {**rules, "fraction_digits": 2},
                                                      source, now, begin))
        self.assertEqual(["start", "start"], calls)
        refused = {}
        self.assertFalse(resume_optional_eighth_digit(refused, rules, source, now, lambda: False))
        self.assertNotIn("eighth_digit_retry_at", refused)

    def test_provisional_precision_is_bound_to_the_saved_source_and_crop(self):
        source = {"mode": "camera", "camera": "camera.meter"}
        rules = {"decimals": 3, "precision_mode": False, "crop_revision": "42",
                 "stationary_partial_scope": run.calibration_source_id([source, "42"])}
        self.assertTrue(run.stationary_partial_active(rules, source))
        self.assertFalse(run.stationary_partial_active(rules, {**source, "camera": "camera.other"}))
        self.assertFalse(run.stationary_partial_active({**rules, "crop_revision": "43"}, source))
        self.assertFalse(run.stationary_partial_active({**rules, "precision_mode": True}, source))

    def test_existing_calibration_seed_requires_a_verified_matching_crop_revision(self):
        rules = {"crop_mode": "manual", "crop": "0,0,400,90", "width": 250, "rotation": 0,
                 "integer_digits": 5, "fraction_digits": 3, "crop_revision": "123"}
        source = ["camera", "camera.meter", ""]
        history = {"check_status": "ocr_only", "last_epoch": 100,
                   "geometry_recovery": {"key": run.geometry_check_key(rules, source), "stamp": 100, "failures": 0}}
        self.assertEqual(rules, run.last_verified_configured_geometry(history, rules, source))
        self.assertIsNone(run.last_verified_configured_geometry(history, {**rules, "crop_revision": "124"}, source))
        self.assertIsNone(run.last_verified_configured_geometry(history, rules, ["camera", "camera.other", ""]))
        self.assertIsNone(run.last_verified_configured_geometry(
            {**history, "check_status": "standalone_pending"}, rules, source))

    def test_seven_digit_setup_completes_before_optional_last_digit_check(self):
        from threading import Event

        class Done(Exception):
            pass

        class StopAfterFrame(Event):
            def wait(self, timeout=None):
                raise Done

        for decimals in (2, 3):
            with self.subTest(decimals=decimals), TemporaryDirectory() as folder:
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
                    "decimals": decimals, "attempts": 2, "integer_digits": 5, "fraction_digits": 3,
                }))
                access = {}
                boxes = tuple((i * 120, 100, i * 120 + 100, 900) for i in range(8))
                layout = run.Layout((0, 0, 100, 30), 0, 60, boxes)
                recorded = datetime.now(timezone.utc)
                picture = run.calibration_jpeg(Image.new("RGB", (100, 30), "gray"), (100, 30))
                measurement = {**sample(recorded), "raw_value": "12345.230", "actual_value": "12345.230",
                               "reference_time": recorded.timestamp(), "reference_required": True}

                def fake_panel(*args, **kwargs):
                    access.update(status=kwargs["get_calibration"], rules=args[6],
                                  control=kwargs["control_calibration"])
                    kwargs["control_calibration"]("start", 4)
                    return None, None, None

                def found(job, *args, **kwargs):
                    job.candidate = layout
                    job.confirmations = 3
                    job.reference_reading = "12345.23?"
                    job.counter = {"step_litres": 10, "timestamp": recorded.timestamp()}
                    return layout

                class InlineCalibrationThread:
                    def __init__(self, target, args, **kwargs):
                        self.target, self.args = target, args

                    def start(self):
                        self.target(*self.args)
                        raise Done

                with patch.multiple(run, **files, Event=StopAfterFrame),                      patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}),                      patch.object(run, "start_panel", fake_panel),                      patch.object(run, "Thread", InlineCalibrationThread),                      patch.object(run, "capture_camera", return_value=(picture, None, measurement)),                      patch.object(run.Calibration, "examine", found):
                    with self.assertRaises(Done):
                        run.main()
                    status = access["status"]()
                    self.assertEqual("waiting" if decimals == 3 else "saved", status["state"])
                    self.assertEqual(decimals == 3, status["intensive"])
                    self.assertEqual(decimals == 3, status["background"])
                    self.assertFalse(status["simplified"] if decimals == 3 else status["intensive"])
                    rules = access["rules"]()
                    self.assertIsNotNone(rules["setup_success"])
                    self.assertEqual("manual", rules["crop_mode"])
                    self.assertEqual(layout.settings()["crop"], rules["crop"])
                    configured_source = {"mode": "camera", "url": "",
                                         "camera": "camera.meter", "reference": "sensor.meter",
                                         "selected": True}
                    self.assertEqual(decimals == 3,
                                     run.stationary_partial_active(rules, configured_source))
                    if decimals == 3:
                        # The eighth digit starts automatically as a secondary
                        # job; it must not mutate or replace the seven-digit crop.
                        self.assertTrue(access["status"]()["followup"])
                        self.assertTrue(access["status"]()["background"])
                        self.assertEqual(rules, access["rules"]())

    def test_calibration_preview_shows_real_ocr_on_a_rotated_synthetic_camera_image(self):
        from threading import Event

        class Done(Exception):
            pass

        class StopAfterFrame(Event):
            def wait(self, timeout=None):
                raise Done

        folder = Path(self.enterContext(TemporaryDirectory()))
        files = {name: folder / name for name in (
            "OPTIONS", "HISTORY", "EFFECTIVE_OPTIONS", "AUTO_RULES", "AUTO_PAUSED",
            "LANGUAGE_MODES", "SOURCE_SETTINGS", "NOTIFICATIONS", "DESTINATION",
            "GOOD_IMAGE", "TEST_IMAGE", "AUTOMATIC_PREVIEW",
        )}
        files["OPTIONS"].write_text(json.dumps({"ausschnitt": "0,0,640,480", "vorkomma_breite": 350}))
        files["SOURCE_SETTINGS"].write_text(json.dumps({
            "mode": "camera", "url": "", "camera": "camera.meter", "reference": "sensor.meter",
        }))
        files["AUTO_RULES"].write_text(json.dumps({
            "decimals": 0, "attempts": 2, "integer_digits": 5, "fraction_digits": 0,
        }))
        self.enterContext(patch.multiple(run, **files, Event=StopAfterFrame))
        self.enterContext(patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}))
        camera = Image.new("RGB", (640, 480), (80, 80, 80))
        draw = ImageDraw.Draw(camera)
        draw.rectangle((160, 180, 480, 285), fill="white")
        draw.text((320, 235), "12345", font=ImageFont.truetype("DejaVuSansMono.ttf", 72),
                  fill="black", anchor="mm")
        photo = turn_crop(camera, 3)
        recorded = datetime.now(timezone.utc)
        measurement = {**sample(recorded), "raw_value": "12345", "actual_value": "12345",
                       "reference_time": recorded.timestamp(), "reference_required": True}
        self.enterContext(patch.object(run, "capture_camera", return_value=(
            run.calibration_jpeg(photo, photo.size), None, measurement,
        )))
        access = {}

        def fake_panel(*args, **kwargs):
            access.update(status=kwargs["get_calibration"], image=kwargs["get_calibration_image"],
                          control=kwargs["control_calibration"], rules=args[6], save=args[7])
            access["control"]("start", 4)
            return None, None, None

        self.enterContext(patch.object(run, "start_panel", fake_panel))
        observed = []
        recognize = run.read_visible_digits

        def check_pending(*args, **kwargs):
            status = access["status"]()
            preview = status["preview"]
            observed.append((status["stage"], preview["reading"], preview["crop"], preview["angle"]))
            return recognize(*args, **kwargs)

        self.enterContext(patch.object(run, "read_visible_digits", side_effect=check_pending))
        class InlineCalibrationThread:
            def __init__(self, target, args, **kwargs):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)
                raise Done

        self.enterContext(patch.object(run, "Thread", InlineCalibrationThread))
        with self.assertRaises(Done):
            run.main()
        self.assertEqual(("ocr", None), observed[0][:2])
        preview = access["status"]()["preview"]
        self.assertEqual("12345", preview["reading"])
        tried_angles = {angle for stage, _, _, angle in observed if stage == "angle"}
        self.assertTrue({-2, -1, 1, 2} <= tried_angles)
        self.assertIn(preview["angle"], tried_angles | {0})
        self.assertEqual(4, len(preview["region"]))
        self.assertGreater(preview["crop"], observed[0][2])
        for kind in ("frame", "crop"):
            content = access["image"](kind, str(preview[kind]))
            with Image.open(BytesIO(content)) as image:
                self.assertEqual("JPEG", image.format)
                self.assertGreater(image.width, 10)
        self.assertIsNone(access["image"]("frame", "0"))
        access["control"]("cancel", 0)
        access["control"]("start", 4)
        self.assertEqual({}, access["status"]()["preview"])
        self.assertIsNone(access["image"]("frame", str(preview["frame"])))
        access["control"]("cancel", 0)
        access["control"]("repair", 20)
        self.assertEqual(240, access["status"]()["duration"])
        self.assertTrue(access["status"]()["automatic"])
        backup = json.loads(files["HISTORY"].with_name("geometry-backup.json").read_text())
        self.assertEqual(backup["rules"], access["rules"]())
        access["control"]("cancel", 0)
        access["save"]({**access["rules"](), "width": 200, "interval_minutes": 75})
        access["control"]("restore", 0)
        self.assertEqual(backup["rules"]["width"], access["rules"]()["width"])
        self.assertEqual(75, access["rules"]()["interval_minutes"])

        access["save"]({**access["rules"](), "decimals": 3, "fraction_digits": 3, "crop_mode": "manual"})
        access["control"]("start", 4)
        self.assertTrue(access["status"]()["simplified"])
        access["control"]("intensive", 4)
        self.assertFalse(access["status"]()["simplified"])
        self.assertTrue(access["status"]()["intensive"])
        access["save"]({**access["rules"](), "precision_mode": True})
        access["control"]("start", 4)
        self.assertFalse(access["status"]()["simplified"])

        layout = run.Layout((120, 160, 525, 315), 1, 280)
        fine = run.Calibration(limit=4, started=0, intensive=True, candidate=layout, confirmations=2)
        with patch.object(run, "Calibration", return_value=fine):
            access["control"]("intensive", 4)
        self.assertIsNone(access["status"]()["skip_verification_id"])
        fine.confirmations = 3
        fine.counter = {"step_litres": 1, "timestamp": 100}
        fine.reference_reading = "12345.239"
        fine.begin_verification(1)
        fine.state = "timeout"
        verification_id = access["status"]()["skip_verification_id"]
        self.assertTrue(verification_id)
        with self.assertRaises(ValueError):
            access["control"]("skip-verification", 0, verification_id="stale")
        self.assertNotEqual(layout.settings()["crop"], access["rules"]()["crop"])
        with patch.object(run, "atomic_write", side_effect=OSError):
            with self.assertRaises(OSError):
                access["control"]("skip-verification", 0, verification_id=verification_id)
        self.assertEqual(verification_id, access["status"]()["skip_verification_id"])
        access["control"]("skip-verification", 0, verification_id=verification_id)
        status = access["status"]()
        self.assertEqual("saved_without_verification", status["state"])
        self.assertIsNone(status.get("skip_verification_id"))
        self.assertEqual(layout.settings()["crop"], status["settings"]["crop"])
        stored_rules = json.loads(files["AUTO_RULES"].read_text())
        self.assertEqual(layout.settings()["crop"], stored_rules["crop"])
        self.assertEqual("12345.239", stored_rules["calibration_reference"]["reading"])
        self.assertEqual(100, stored_rules["calibration_reference"]["time"])
        with self.assertRaises(ValueError):
            access["control"]("skip-verification", 0, verification_id=verification_id)

        source = {**run.source_rules(json.loads(files["SOURCE_SETTINGS"].read_text())), "selected": True}
        stamp = 10000
        access["save"]({**access["rules"](), "setup_completed": {
            "source": run.setup_source_id(source), "time": stamp,
        }})
        with patch.object(run.time, "time", return_value=stamp + 3599):
            self.assertFalse(access["control"]("repair", 20))
            self.assertTrue(access["control"]("start", 4))
            self.assertFalse(access["status"]()["automatic"])
        access["control"]("cancel", 0)
        with patch.object(run.time, "time", return_value=stamp + 3600):
            self.assertTrue(access["control"]("repair", 20))
            self.assertTrue(access["status"]()["automatic"])

    def test_edge_camera_only_publishes_local_ocr_without_the_esp_reading(self):
        class StopLoop(Exception):
            pass

        folder = Path(self.enterContext(TemporaryDirectory()))
        files = {key: folder / key for key in (
            "OPTIONS", "HISTORY", "EFFECTIVE_OPTIONS", "AUTO_RULES", "AUTO_PAUSED",
            "LANGUAGE_MODES", "SOURCE_SETTINGS", "NOTIFICATIONS", "DESTINATION",
            "GOOD_IMAGE", "TEST_IMAGE", "AUTOMATIC_PREVIEW",
        )}
        files["OPTIONS"].write_text(json.dumps({
            "ausschnitt": "0,0,500,100", "vorkomma_breite": 350, "ocr_versuche": 1,
        }))
        files["SOURCE_SETTINGS"].write_text(json.dumps({
            "mode": "slfork_camera", "url": "http://meter", "camera": "", "reference": "",
        }))
        self.enterContext(patch.multiple(run, **files))
        self.enterContext(patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}))
        self.enterContext(patch.object(run, "start_panel", return_value=(None, None, None)))
        with BytesIO() as stream:
            synthetic_meter().save(stream, "JPEG")
            photo = stream.getvalue()
        fetch = self.enterContext(patch.object(run, "get_bytes", return_value=photo))
        recognize = self.enterContext(patch.object(run, "read_visible_digits", return_value="12345.???"))
        published = self.enterContext(patch.object(run, "publish_state"))
        self.enterContext(patch.object(run, "publish_consumption", side_effect=StopLoop))
        with self.assertRaises(StopLoop):
            run.main()
        fetch.assert_called_once_with("http://meter/camera?task=capture")
        self.assertEqual(2, recognize.call_count)
        sensor = published.call_args.args[1]
        self.assertEqual("unavailable", sensor["state"])
        self.assertEqual("http://meter", sensor["attributes"]["source_camera"])
        history = json.loads(files["HISTORY"].read_text())
        self.assertEqual("standalone_pending", history["check_status"])
        self.assertIsNone(history["last_reference"])
        self.assertNotIn("consumption", history)
        self.assertAlmostEqual(5, history["next_check_at"] - history["last_epoch"], delta=1)

        history["next_check_at"] = 0
        files["HISTORY"].write_text(json.dumps(history))
        with Image.open(BytesIO(fetch.return_value)) as source:
            fresh = source.convert("RGB")
            fresh.paste("white", (0, 0, 12, 12))
            with BytesIO() as stream:
                fresh.save(stream, "JPEG")
                fetch.return_value = stream.getvalue()
        recognize.reset_mock()
        recognize.side_effect = lambda frame, *_, **__: "12345.???" if frame.width > 500 else "?????.???"
        with self.assertRaises(StopLoop):
            run.main()
        history = json.loads(files["HISTORY"].read_text())
        self.assertEqual("ocr_only", history["check_status"])
        self.assertEqual("12345.???", history["last_reference"])
        self.assertEqual(-6, history["ocr_rotation_adjustment"])
        self.assertEqual(10, recognize.call_count)
        self.assertEqual("12345", published.call_args.args[1]["state"])
        self.assertEqual(-6, history["learned_rotation"]["adjustment"])

        history["next_check_at"] = 0
        files["HISTORY"].write_text(json.dumps(history))
        recognize.reset_mock()
        with self.assertRaises(StopLoop):
            run.main()
        history = json.loads(files["HISTORY"].read_text())
        self.assertEqual("standalone_pending", history["check_status"])
        self.assertEqual(-6, history["standalone_candidate"]["rotation_adjustment"])
        self.assertEqual(2, recognize.call_count)
    def test_skipping_setup_does_not_fetch_the_placeholder_slfork_url(self):
        class WaitingForSource(Exception):
            pass

        class StopOnWait(run.Event):
            def wait(self, timeout=None):
                raise WaitingForSource

        folder = Path(self.enterContext(TemporaryDirectory()))
        files = {key: folder / key for key in (
            "OPTIONS", "HISTORY", "EFFECTIVE_OPTIONS", "AUTO_RULES", "AUTO_PAUSED",
            "LANGUAGE_MODES", "SOURCE_SETTINGS", "NOTIFICATIONS",
        )}
        files["OPTIONS"].write_text("{}")
        self.enterContext(patch.multiple(run, **files, Event=StopOnWait))
        self.enterContext(patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}))

        def skip_in_panel(*_, **kwargs):
            kwargs["skip_setup"]()
            return None, None, None

        self.enterContext(patch.object(run, "start_panel", skip_in_panel))
        capture = self.enterContext(patch.object(run, "capture"))
        with self.assertRaises(WaitingForSource):
            run.main()
        capture.assert_not_called()

    def test_saving_only_a_camera_keeps_automatic_check_off_across_restart(self):
        class WaitingForSetup(Exception):
            pass

        class StopOnWait(run.Event):
            def wait(self, timeout=None):
                raise WaitingForSetup

        folder = Path(self.enterContext(TemporaryDirectory()))
        files = {key: folder / key for key in (
            "OPTIONS", "HISTORY", "EFFECTIVE_OPTIONS", "AUTO_RULES", "AUTO_PAUSED",
            "LANGUAGE_MODES", "SOURCE_SETTINGS", "NOTIFICATIONS",
        )}
        files["OPTIONS"].write_text("{}")
        self.enterContext(patch.multiple(run, **files, Event=StopOnWait))
        self.enterContext(patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}))
        status = []

        def configure_source_then_restart(*args, **kwargs):
            if not files["SOURCE_SETTINGS"].exists():
                args[16]({"mode": "esphome", "url": "", "camera": "camera.gasmeter", "reference": ""})
            status.append(kwargs["get_activity"]()["state"])
            return None, None, None

        self.enterContext(patch.object(run, "start_panel", configure_source_then_restart))
        capture = self.enterContext(patch.object(run, "capture_camera"))
        for _ in range(2):
            with self.assertRaises(WaitingForSetup):
                run.main()
        self.assertEqual(["setup_wait", "setup_wait"], status)
        capture.assert_not_called()

    def test_last_digit_can_pass_with_warning_after_three_distinct_samples(self):
        now = datetime.now(timezone.utc)
        for strict in (False, True):
            with self.subTest(strict=strict):
                history = {}
                for index in range(3):
                    data = sample(now - timedelta(seconds=3 - index))
                    data.update(raw_value="12345.2276", actual_value="12345.2276")
                    readings = ("12345.222", "12345.22?", "12345.222")
                    self.assertTrue(record_sample(history, data, "12345.222", timezone.utc, now, 3,
                                                  readings=readings, precision_mode=strict))
                    self.assertFalse(record_sample(history, data, "12345.222", timezone.utc, now, 3,
                                                   readings=readings, precision_mode=strict))
                    if index < 2 or strict:
                        self.assertEqual(("difference", LAST_DIGIT_NOTICE),
                                         (history["status"], history["check_detail"]))
                    else:
                        self.assertEqual(("match_with_warning", LAST_DIGIT_PASS),
                                         (history["status"], history["check_detail"]))
                    schedule_next_check(history, history["status"], now.timestamp())
                self.assertEqual([], history["confirmations"])
                self.assertNotIn("last_match_at", history)
                if not strict:
                    self.assertNotIn("failure_since", history)
                    self.assertEqual(now.timestamp() + NORMAL_INTERVAL, history["next_check_at"])

    def test_last_digit_warning_requires_agreeing_prefixes_and_valid_reference(self):
        now = datetime.now(timezone.utc)
        expected = {**sample(now), "raw_value": "12345.2276", "actual_value": "12345.2276"}
        for data, reading, readings in (
            (expected, "12345.212", ("12345.212",) * 3),
            (expected, "12345.222", ("12345.212", "12345.222", "12345.21?")),
            ({**expected, "reference_is_fallback": True}, "12345.222", ("12345.222",) * 3),
            ({**expected, "raw_value": "12345.2376"}, "12345.222", ("12345.222",) * 3),
        ):
            with self.subTest(data=data, reading=reading):
                history = {"last_digit_failures": 2}
                self.assertTrue(record_sample(history, data, reading, timezone.utc, now, 3, readings=readings))
                self.assertNotEqual("match_with_warning", history["status"])
                self.assertNotIn("last_digit_failures", history)

    def test_saving_settings_bypasses_the_previous_interval(self):
        self.check_interactive_automatic_run(on_demand=False)

    def test_requested_automatic_run_uses_regular_checks_and_keeps_the_next_deadline(self):
        self.check_interactive_automatic_run(on_demand=True)

    def check_interactive_automatic_run(self, *, on_demand):
        class StopLoop(Exception):
            pass

        class NoWait(run.Event):
            def wait(self, timeout=None):
                raise AssertionError(f"Worker waited {timeout}s instead of checking the saved settings")

        folder = Path(self.enterContext(TemporaryDirectory()))
        files = {name: folder / name for name in (
            "OPTIONS", "HISTORY", "EFFECTIVE_OPTIONS", "AUTO_RULES", "AUTO_PAUSED",
            "LANGUAGE_MODES", "SOURCE_SETTINGS", "NOTIFICATIONS", "DESTINATION",
            "GOOD_IMAGE", "TEST_IMAGE", "AUTOMATIC_PREVIEW",
        )}
        files["OPTIONS"].write_text(json.dumps({
            "esp_url": "http://meter", "ausschnitt": "0,0,500,100", "vorkomma_breite": 350,
        }))
        self.enterContext(patch.multiple(run, **files, Event=NoWait))
        self.enterContext(patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}))
        with BytesIO() as stream:
            synthetic_meter().save(stream, "JPEG")
            photo = stream.getvalue()
        rules = {}

        def fake_panel(*args, **kwargs):
            rules.update(read=args[6], save=args[7], activity=kwargs["get_activity"],
                         start=kwargs["start_automatic_check"])
            return None, None, None

        self.enterContext(patch.object(run, "start_panel", fake_panel))
        capture = self.enterContext(patch.object(run, "capture", side_effect=(
            (photo, None, sample(datetime.now(timezone.utc) - timedelta(seconds=5))),
            (photo, None, sample(datetime.now(timezone.utc))),
        )))
        self.enterContext(patch.object(run, "read_visible_digits", return_value="12345.170"))
        self.enterContext(patch.object(run, "publish_state"))
        published = []

        def publish(history, _):
            published.append(dict(history))
            if len(published) == 1:
                if on_demand:
                    self.assertTrue(rules["start"]())
                    self.assertFalse(rules["start"]())
                else:
                    rules["save"]({**rules["read"](), "interval_minutes": 120})
                self.assertEqual("queued", rules["activity"]()["state"])
            else:
                raise StopLoop

        self.enterContext(patch.object(run, "publish_consumption", side_effect=publish))
        with self.assertRaises(StopLoop):
            run.main()
        self.assertEqual(2, capture.call_count)
        if on_demand:
            self.assertEqual(published[0]["next_check_at"], published[1]["next_check_at"])
        else:
            self.assertEqual(120, published[-1]["check_interval_minutes"])
        self.assertEqual("match", published[-1]["check_status"])

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

    def test_interval_change_keeps_the_original_check_and_failure_times(self):
        history = {"check_status": "match", "next_check_at": 4600}
        self.assertTrue(reschedule_next_check(history, 15))
        self.assertEqual((1000, 1900), (last_check_at(history), history["next_check_at"]))
        self.assertTrue(reschedule_next_check(history, 45))
        self.assertEqual((1000, 3700), (last_check_at(history), history["next_check_at"]))
        schedule_next_check(history, "slfork_unclear", 2000, 45)
        self.assertEqual(2300, history["next_check_at"])
        self.assertTrue(reschedule_next_check(history, 1))
        self.assertEqual((2000, 2060, 2000),
                         (last_check_at(history), history["next_check_at"], history["failure_since"]))

    def test_initial_automatic_checks_require_source_and_meter_input(self):
        source = {"mode": "esphome", "url": "", "camera": "camera.meter", "reference": "", "selected": True}
        scope = run.setup_source_id(source)
        key = run.source_check_key(source)
        rules = {"crop_mode": "auto"}
        self.assertFalse(run.automatic_inputs_ready(rules, source, {}))
        self.assertFalse(run.automatic_inputs_ready(rules, source, {
            "check_source": key, "last_epoch": 1000, "check_status": "ocr_unclear",
        }))
        self.assertTrue(run.automatic_inputs_ready(rules, source, {"manual_setup_source": scope}))
        self.assertTrue(run.automatic_inputs_ready(rules, source, {"consumption": {"source": key}}))
        self.assertTrue(run.automatic_inputs_ready(rules, source, {"check_source": key, "last_match_at": 1000}))
        configured = {**rules, "crop_mode": "manual", "setup_input_source": scope}
        self.assertTrue(run.automatic_inputs_ready(configured, source, {}))
        self.assertFalse(run.automatic_inputs_ready(configured, {**source, "camera": "camera.other"}, {}))
        self.assertFalse(run.automatic_inputs_ready(configured, {**source, "selected": False}, {}))
        self.assertTrue(run.automatic_inputs_ready({
            **rules, "setup_completed": {"source": scope, "time": 1000},
        }, source, {}))
        self.assertTrue(run.automatic_inputs_ready({
            **rules, "fallback_value": "12345.6", "fallback_time": "2026-11-17T10:00", "setup_input_source": scope,
        }, source, {}))

    def test_setup_windows_survive_serialization_and_end_independently(self):
        source = {"mode": "camera", "camera": "camera.meter", "selected": True}
        rules = {"setup_completed": {"source": run.setup_source_id(source), "time": 1000}}
        restored = json.loads(json.dumps(rules))
        stabilize, pause = run.setup_deadlines(restored, source)
        self.assertEqual((2200, 4600), (stabilize, pause))
        self.assertEqual(5, run.stabilization_interval(60, stabilize, 2199))
        self.assertEqual(3, run.stabilization_interval(3, stabilize, 2199))
        self.assertEqual(60, run.stabilization_interval(60, stabilize, 2200))
        self.assertEqual((0, 0), run.setup_deadlines(restored, {**source, "camera": "camera.other"}))
        self.assertEqual((0, 0), run.setup_deadlines({}, source))

    def test_slfork_interval_floor_and_duplicate_cycle_without_counting_a_failure(self):
        self.assertEqual(5, automatic_interval_minutes(1, "slfork"))
        self.assertEqual(60, automatic_interval_minutes(60, "slfork"))
        self.assertEqual(1, automatic_interval_minutes(1, "slfork_camera"))
        self.assertEqual(1, automatic_interval_minutes(1, "esphome"))

        # Older history did not store the last check time separately.
        history = {"check_status": "ocr_unclear", "next_check_at": 1300, "failure_attempts": 1,
                   "check_interval_minutes": 5, "failure_since": 1000, "confirmations": []}
        defer_duplicate_cycle(history, 1300, 5)
        self.assertEqual((1000, 1600, 1, 1000),
                         (last_check_at(history), history["next_check_at"],
                          history["failure_attempts"], history["failure_since"]))
        self.assertEqual([], history["confirmations"])

    def test_fallback_plausibility_uses_time_repeatable_digits_and_flow_limit(self):
        reference = {"reference": "12346.0416", "reference_time": 1000}
        source = ["slfork", "http://meter", ""]
        for ocr, expected in (("12346.337", FALLBACK_PLAUSIBLE),
                              ("12340.000", LOWER_READING),
                              ("12347.500", EXCESSIVE_INCREASE)):
            with self.subTest(ocr=ocr):
                self.assertIn(expected, fallback_detail(reference, 1600, ocr, [ocr] * 3, {}, source, 6000))
        self.assertIn(FALLBACK_UNKNOWN_TIME, fallback_detail(
            {**reference, "reference_time": None}, 1600, "12346.337", ["12346.337"] * 3, {}, source, 6000))
        self.assertIn("OCR-Stand unsicher", fallback_detail(
            reference, 1600, "12346.337", ["12346.337", "12345.337", "12347.337"], {}, source, 6000))

    def test_main_does_not_count_fallback_and_recovers_with_a_new_reference(self):
        class StopLoop(Exception):
            pass

        folder = Path(self.enterContext(TemporaryDirectory()))
        files = {name: folder / name for name in (
            "OPTIONS", "HISTORY", "EFFECTIVE_OPTIONS", "AUTO_RULES", "LANGUAGE_MODES",
            "SOURCE_SETTINGS", "NOTIFICATIONS", "DESTINATION", "GOOD_IMAGE", "TEST_IMAGE", "AUTOMATIC_PREVIEW",
        )}
        files["OPTIONS"].write_text(json.dumps({"esp_url": "http://meter", "ausschnitt": "0,0,500,100",
                                                "vorkomma_breite": 350, "vergleich_nachkommastellen": 3}))
        self.enterContext(patch.multiple(run, **files))
        self.enterContext(patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}))
        self.enterContext(patch.object(run, "start_panel", return_value=(None, None, None)))
        with BytesIO() as stream:
            synthetic_meter().save(stream, "JPEG")
            photo = stream.getvalue()
        capture = self.enterContext(patch.object(run, "capture"))
        recognize = self.enterContext(patch.object(run, "read_visible_digits"))
        publish = self.enterContext(patch.object(run, "publish_consumption", side_effect=StopLoop))
        self.enterContext(patch.object(run, "publish_state"))
        now = datetime.now(timezone.utc)
        original = now - timedelta(minutes=10)

        def check(payload, ocr):
            recognize.return_value = ocr

            def fake_capture(_, diagnostics):
                diagnostics["slfork_process_error"] = payload.get("slfork_process_error")
                return None if run.slfork_cycle_failed(diagnostics) else (photo, None, dict(payload))

            capture.side_effect = fake_capture
            if files["HISTORY"].exists():
                history = json.loads(files["HISTORY"].read_text())
                files["HISTORY"].write_text(json.dumps({**history, "next_check_at": 0}))
            with self.assertRaises(StopLoop):
                run.main()
            return publish.call_args.args[0]

        initial = check({**sample(original), "raw_value": "12346.0416", "actual_value": "12346.0416"}, "12346.042")
        fallback_stamp = now - timedelta(minutes=1)
        fallback = {**sample(fallback_stamp), "slfork_value_status": "E92 Rate Too High (<) | Use Fallback",
                    "slfork_last_valid_timestamp": fallback_stamp.isoformat(), "slfork_fallback_value": "12346.0416",
                    "actual_value": "12346.0416", "raw_value": "12340"}
        pending = check(fallback, "12346.337")
        self.assertEqual("slfork_unclear", pending["check_status"])
        self.assertIn(FALLBACK_PLAUSIBLE, pending["check_detail"])
        self.assertEqual(original.timestamp(), pending["last_reference_time"])
        self.assertEqual(initial["consumption"], pending["consumption"])
        self.assertEqual(initial["confirmations"], pending["confirmations"])
        repeated = check(fallback, "12346.337")
        self.assertEqual(pending["failure_since"], repeated["failure_since"])
        self.assertEqual(pending["check_detail"], repeated["check_detail"])
        recovered = check({**sample(now), "raw_value": "12346.351", "actual_value": "12346.351"}, "12346.351")
        self.assertEqual("match", recovered["check_status"])
        self.assertNotIn("failure_since", recovered)
        self.assertFalse(recovered["last_reference_is_fallback"])
        self.assertEqual(309, recovered["consumption"]["total_litres"])
        self.assertEqual(2, len(recovered["confirmations"]))

        old_sample = {**sample(now - timedelta(minutes=30)), "actual_value": "12346.351"}
        for payload in (old_sample, {**sample(now), "slfork_process_error": -2}):
            with self.subTest(payload=payload):
                with patch.object(run, "get_bytes", return_value=photo) as fetch:
                    local = check(payload, "12346.351")
                    fetch.assert_called_once_with("http://meter/camera?task=capture")
                self.assertEqual("ocr_only", local["check_status"])
                self.assertEqual("12346.351", local["ocr_value"])
                self.assertIsNone(local["last_reference"])
                self.assertEqual(run.SLFORK_RAW_SUCCESS, local["source_connection_detail"])
                self.assertEqual("stale", local["source_connection_status"])
                self.assertEqual(recovered["confirmations"], local["confirmations"])
                self.assertEqual(recovered["consumption"], local["consumption"])

        with patch.object(run, "get_bytes", return_value=photo):
            uncertain = check(old_sample, "?????.???")
        self.assertEqual("ocr_unclear", uncertain["check_status"])
        self.assertNotEqual(run.SLFORK_RAW_SUCCESS, uncertain["source_connection_detail"])

        for index in range(3):
            timestamp = datetime.now(timezone.utc) + timedelta(seconds=index + 1)
            marginal = check({
                **sample(timestamp), "raw_value": "12346.3530", "actual_value": "12346.3530",
            }, "12346.354")
        self.assertEqual("match_with_warning", marginal["check_status"])
        self.assertEqual(12346353, marginal["consumption"]["reading_litres"])
        self.assertEqual(recovered["consumption"]["total_litres"] + 2, marginal["consumption"]["total_litres"])
        self.assertEqual(recovered["confirmations"], marginal["confirmations"])
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
            self.assertEqual("12345.17", publish.call_args.args[1]["state"])
            self.assertTrue(publish.call_args.args[1]["attributes"]["is_fallback"])
            run.publish_standalone({"standalone_reading": latest, "check_status": "ocr_unclear"}, "camera.other", "stub")
            self.assertEqual("unavailable", publish.call_args.args[1]["state"])

    def test_main_reads_esphome_camera_and_publishes_standalone_sensor(self):
        class StopLoop(Exception):
            pass

        folder = Path(self.enterContext(TemporaryDirectory()))
        files = {name: folder / name for name in (
            "OPTIONS", "HISTORY", "EFFECTIVE_OPTIONS", "AUTO_RULES", "LANGUAGE_MODES",
            "SOURCE_SETTINGS", "NOTIFICATIONS", "DESTINATION", "GOOD_IMAGE", "TEST_IMAGE",
            "AUTOMATIC_PREVIEW",
        )}
        files["OPTIONS"].write_text(json.dumps({"ausschnitt": "0,0,500,100", "vorkomma_breite": 350,
                                                "ocr_versuche": 1}))
        files["AUTO_RULES"].write_text(json.dumps({
            "decimals": 0, "attempts": 1, "crop_mode": "manual", "crop": "0,0,500,100", "width": 350,
        }))
        files["SOURCE_SETTINGS"].write_text(json.dumps({"mode": "esphome", "url": "", "camera": "camera.esp",
                                                        "reference": "sensor.ignored"}))
        self.enterContext(patch.multiple(run, **files))
        self.enterContext(patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}))
        with BytesIO() as stream:
            synthetic_meter().save(stream, "PNG")
            photo = stream.getvalue()
        self.enterContext(patch.object(run, "start_panel", return_value=(None, None, None)))
        fetch = self.enterContext(patch.object(run, "get_bytes", return_value=photo))
        recognize = self.enterContext(patch.object(run, "read_visible_digits", return_value="12345.???"))
        published = {}

        def collect(url, payload, _):
            entity = url.rsplit("/", 1)[1]
            published[entity] = payload

        self.enterContext(patch.object(run, "publish_state", collect))
        publish_consumption = run.publish_consumption

        def finish_run(history, token):
            publish_consumption(history, token)
            raise StopLoop

        self.enterContext(patch.object(run, "publish_consumption", finish_run))

        snapshots = 0

        def check(ocr, *, cached=False):
            nonlocal snapshots
            recognize.return_value = ocr
            if not cached:
                snapshots += 1
                fresh = synthetic_meter().convert("RGB")
                fresh.putpixel((0, 0), (snapshots, 0, 0))
                with BytesIO() as stream:
                    fresh.save(stream, "PNG")
                    fetch.return_value = stream.getvalue()
            if files["HISTORY"].exists():
                history = json.loads(files["HISTORY"].read_text())
                history["next_check_at"] = 0
                files["HISTORY"].write_text(json.dumps(history))
            with self.assertRaises(StopLoop):
                run.main()
            return json.loads(files["HISTORY"].read_text())

        pending = check("12345.???")
        fetch.assert_called_once_with("http://supervisor/core/api/camera_proxy/camera.esp", "stub", timeout=8)
        self.assertEqual(2, recognize.call_count)
        self.assertEqual("standalone_pending", pending["check_status"])
        self.assertEqual("unavailable", published[run.OCR_ENTITY]["state"])
        self.assertNotIn(run.CONSUMPTION_ENTITY, published)
        self.assertAlmostEqual(5, pending["next_check_at"] - pending["last_epoch"], delta=1)
        recognize.reset_mock()
        still_pending = check("12345.???", cached=True)
        self.assertEqual("standalone_pending", still_pending["check_status"])
        self.assertEqual(pending["last_epoch"], still_pending["last_epoch"])
        recognize.assert_not_called()
        initial = check("12345.???")
        self.assertEqual("12345", published[run.OCR_ENTITY]["state"])
        self.assertEqual("ocr_only", published[run.CHECK_ENTITY]["state"])
        self.assertEqual([], initial["confirmations"])
        self.assertEqual("0", published[run.CONSUMPTION_ENTITY]["state"])
        attributes = published[run.CONSUMPTION_ENTITY]["attributes"]
        self.assertEqual(("gas", "total_increasing", "m³"),
                         (attributes["device_class"], attributes["state_class"], attributes["unit_of_measurement"]))
        with Image.open(files["DESTINATION"]) as current:
            self.assertEqual("JPEG", current.format)
        with Image.open(files["AUTOMATIC_PREVIEW"]) as overlay:
            self.assertEqual("JPEG", overlay.format)
            self.assertGreater(overlay.width, 0)

        initial["consumption"]["timestamp"] -= 3600
        files["HISTORY"].write_text(json.dumps(initial))
        self.assertEqual("standalone_pending", check("12347.???")["check_status"])
        self.assertEqual("12345", published[run.OCR_ENTITY]["state"])
        second = check("12347.???")
        self.assertEqual("2", published[run.CONSUMPTION_ENTITY]["state"])
        self.assertEqual("standalone_pending", check("12347.???")["check_status"])
        rejected = check("13347.???")
        self.assertEqual("2", published[run.CONSUMPTION_ENTITY]["state"])
        self.assertEqual("12347", published[run.OCR_ENTITY]["state"])
        self.assertTrue(published[run.OCR_ENTITY]["attributes"]["is_fallback"])
        self.assertEqual("ocr_unclear", published[run.CHECK_ENTITY]["state"])
        self.assertIn(EXCESSIVE_INCREASE, rejected["check_detail"])
        self.assertIn("zweite Aufnahme", rejected["check_detail"])
        self.assertEqual(second["consumption"], rejected["consumption"])

        files["HISTORY"].unlink()
        source = {**run.source_rules(json.loads(files["SOURCE_SETTINGS"].read_text())), "selected": True}
        files["AUTO_RULES"].write_text(json.dumps({
            "decimals": 0, "attempts": 1, "crop_mode": "manual",
            "crop": "0,0,500,100", "width": 350, "setup_pending_source": run.setup_source_id(source),
            "setup_pending_started": datetime.now(timezone.utc).timestamp() - 60,
            "setup_pending_metrics": {"frames_tested": 12, "images_checked": 4},
        }))
        pending = check("12346.???")
        self.assertEqual("standalone_pending", pending["check_status"])
        self.assertNotIn("automatic_completed_at", pending)
        self.assertIsNone(json.loads(files["AUTO_RULES"].read_text()).get("setup_completed"))
        verified = check("12346.???")
        self.assertEqual("ocr_only", verified["check_status"])
        completed = json.loads(files["AUTO_RULES"].read_text())
        self.assertEqual("12346", completed["calibration_reference"]["reading"])
        self.assertIsNone(completed["setup_pending_source"])
        self.assertIsNone(completed["setup_pending_started"])
        self.assertGreaterEqual(completed["setup_completed"]["duration_seconds"], 60)
        self.assertEqual(12, completed["setup_completed"]["frames_tested"])
        self.assertEqual(4, completed["setup_completed"]["images_checked"])
        self.assertEqual([[verified["consumption"]["timestamp"], verified["consumption"]["total_litres"], 1000]],
                         verified["consumption_statistics"]["samples"])
        self.assertNotIn("consumption_statistics", pending)
        self.assertNotIn("automatic_completed_at", verified)
        subsequent = check("12346.???")
        self.assertEqual("standalone_pending", subsequent["check_status"])
        self.assertNotIn("automatic_completed_at", subsequent)
        self.assertGreater(check("12346.???")["automatic_completed_at"], completed["setup_completed"]["time"])
        self.assertGreater(run.setup_deadlines(completed, source)[1], datetime.now(timezone.utc).timestamp())
        files["HISTORY"].unlink()
        files["AUTO_RULES"].write_text(json.dumps({
            "decimals": 0, "attempts": 1, "crop_mode": "manual",
            "crop": "0,0,500,100", "width": 350,
            "setup_completed": {"source": run.setup_source_id(source), "time": datetime.now(timezone.utc).timestamp()},
            "calibration_reference": {
                "source": run.calibration_source_id(source), "integer_digits": 5, "precision": 0,
                "reading": "12346", "time": datetime.now(timezone.utc).timestamp() - 10,
            },
        }))
        # After a statistics-preserving reset, a newly configured camera may
        # use a fresh calibration reference. It must retain the previous total.
        prior_time = datetime.now(timezone.utc).timestamp() - 120
        files["HISTORY"].write_text(json.dumps({
            "consumption": {"source": ["esphome", "camera.old", ""], "timestamp": prior_time,
                            "reading_litres": 12345000, "anchor_litres": 12345000,
                            "step_litres": 1000, "total_litres": 2100},
            "consumption_statistics": {"source": "old-camera", "samples": [[prior_time, 2100, 1000]]},
            "statistics_preserved_after_reset": True,
        }))
        started = check("12346.???")
        self.assertEqual(2100, started["consumption"]["total_litres"])
        self.assertEqual([2100, 2100], [sample[1] for sample in
                                          started["consumption_statistics"]["samples"]])
        self.assertNotIn("statistics_preserved_after_reset", started)
        self.assertEqual("ocr_only", started["check_status"])
        self.assertEqual("12346", started["last_reference"])
        self.assertEqual(5, started["check_interval_minutes"])
        self.assertNotIn("standalone_candidate", started)
        saved = json.loads(files["HISTORY"].with_name("known-good-geometry.json").read_text())
        self.assertEqual("0,0,500,100", saved["geometry"]["crop"])
        self.assertEqual("standalone_pending", check("12346.???")["check_status"])
        failed = check("12345.???")
        self.assertEqual("ocr_unclear", failed["check_status"])
        self.assertEqual(started["consumption"], failed["consumption"])
        self.assertEqual("12346", json.loads(files["AUTO_RULES"].read_text())["calibration_reference"]["reading"])

    def test_automatic_run_rechecks_a_single_digit_during_stabilization(self):
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
            "setup_completed": {"source": run.setup_source_id({**source, "selected": True}),
                                "time": datetime.now(timezone.utc).timestamp()},
        }))
        self.enterContext(patch.multiple(run, **paths))
        self.enterContext(patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}))
        self.enterContext(patch.object(run, "start_panel", return_value=(None, None, None)))
        with BytesIO() as stream:
            synthetic_meter().save(stream, "JPEG")
            capture = self.enterContext(patch.object(run, "get_bytes", return_value=stream.getvalue()))
        whole = self.enterContext(patch.object(run, "read_visible_digits", return_value="10465.9?2"))
        digit = self.enterContext(patch.object(run, "read_register", return_value="4"))
        self.enterContext(patch.object(run, "publish_state"))
        self.enterContext(patch.object(run, "publish_consumption", side_effect=StopLoop))
        with self.assertRaises(StopLoop):
            run.main()
        history = json.loads(paths["HISTORY"].read_text())
        self.assertEqual(run.STANDALONE_PENDING, history["check_status"])
        self.assertEqual("10465.942", history["standalone_candidate"]["reading"])
        self.assertEqual("shifted", history["ocr_method"])
        self.assertEqual(7, history["ocr_candidates"][0]["position"])
        self.assertEqual(2, whole.call_count)
        self.assertEqual(2, digit.call_count)
        capture.assert_called_once()
        self.assertNotIn("consumption", history)

    def test_main_keeps_manual_run_separate_from_automated_entities_and_history(self):
        class StopLoop(Exception):
            pass

        folder = Path(self.enterContext(TemporaryDirectory()))
        paths = {name: folder / f"{name.lower()}.json" for name in (
            "OPTIONS", "HISTORY", "EFFECTIVE_OPTIONS", "AUTO_RULES", "LANGUAGE_MODES",
            "SOURCE_SETTINGS", "NOTIFICATIONS",
            "DESTINATION", "GOOD_IMAGE", "TEST_IMAGE", "TEST_SOURCE_IMAGE",
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

        def fake_panel(history_path, current, good, requested, *_, **__):
            requested.put_nowait({
                "request_id": 1, "decimals": 2, "attempts": 1, "polarity": "dark",
                "crop_mode": "manual", "crop": "0,0,480,100", "width": 350,
                "manual_reference": "12345.129", "image": jpeg,
            })
            return None, lambda *args, **kwargs: progress_updates.append((args, kwargs)), None

        def fake_publish(url, payload, _):
            published.append((url, payload))
            history_updates.append(json.loads(paths["HISTORY"].read_text()))
            if url.endswith(run.CONSUMPTION_ENTITY):
                raise StopLoop

        data = sample(datetime.now(timezone.utc))
        self.enterContext(patch.object(run, "start_panel", fake_panel))
        capture = self.enterContext(patch.object(run, "capture", return_value=(jpeg, None, data)))
        self.enterContext(patch.object(run, "read_visible_digits", return_value="12345.120"))
        self.enterContext(patch.object(run, "publish_state", fake_publish))
        with self.assertRaises(StopLoop):
            run.main()
        self.assertEqual("difference", progress_updates[-1][1]["outcome"])
        capture.assert_called_once()
        with Image.open(paths["TEST_SOURCE_IMAGE"]) as source_image:
            self.assertEqual((500, 100), source_image.size)
        with Image.open(paths["TEST_IMAGE"]) as preview:
            self.assertEqual((480, 100), preview.size)
        self.assertEqual([run.CHECK_ENTITY, run.ENTITY, run.CONSUMPTION_ENTITY],
                         [url.rsplit("/", 1)[1] for url, _ in published])
        self.assertEqual("match", published[0][1]["state"])
        self.assertEqual(0, published[1][1]["attributes"]["decimal_places"])
        history = history_updates[-1]
        self.assertEqual("difference", history["manual_result"]["status"])
        self.assertNotIn("image", history["manual_result"]["settings"])
        self.assertEqual(1, len(history["confirmations"]))
        self.assertEqual(0, history["comparison_decimals"])
        self.assertEqual(0, history["consumption"]["total_litres"])
        self.assertTrue(paths["GOOD_IMAGE"].exists())
