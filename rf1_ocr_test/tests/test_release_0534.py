"""0.5.34: the camera picture can be turned in quarter turns in the running setup."""

from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auto_rules import changed_rules, default_rules, stored_rules, valid_image_rotation  # noqa: E402
import run  # noqa: E402
from settings import DEFAULTS  # noqa: E402
from test_worker import sample  # noqa: E402


def picture(kind="JPEG"):
    """40 × 20, the left half white."""
    image = Image.new("RGB", (40, 20), "black")
    image.paste((255, 255, 255), (0, 0, 20, 20))
    with BytesIO() as stream:
        image.save(stream, kind)
        return stream.getvalue()


def white(content, point):
    with Image.open(BytesIO(content)) as image:
        return image.convert("RGB").getpixel(point)[0] > 200, image.size


class QuarterTurnTests(unittest.TestCase):
    def test_a_quarter_turn_to_the_right_brings_the_left_side_to_the_top(self):
        turned = run.oriented_picture(picture(), rotation=90)
        self.assertEqual((True, (20, 40)), white(turned, (10, 5)))
        self.assertFalse(white(turned, (10, 35))[0])

    def test_half_and_three_quarter_turns(self):
        self.assertTrue(white(run.oriented_picture(picture(), rotation=180), (35, 10))[0])
        three = run.oriented_picture(picture(), rotation=270)
        self.assertEqual((True, (20, 40)), white(three, (10, 35)))

    def test_mirrored_first_then_turned(self):
        # Mirrored, the white half is on the right; turned right, it comes to the bottom.
        both = run.oriented_picture(picture(), mirrored=True, rotation=90)
        self.assertTrue(white(both, (10, 35))[0])

    def test_captures_follow_the_rules(self):
        result = (picture(), picture("PNG"), {"esp_timestamp": "x"})
        self.assertIs(result, run.mirror_capture(result, {"image_rotation": 0}))
        turned, overlay, _ = run.mirror_capture(result, {"image_rotation": 90})
        self.assertEqual((20, 40), white(turned, (0, 0))[1])
        self.assertEqual((20, 40), white(overlay, (0, 0))[1])
        self.assertIs(result[0], run.oriented_picture(result[0]))

    def test_the_setting_is_kept_and_checked(self):
        rules = default_rules(DEFAULTS)
        self.assertEqual(0, rules["image_rotation"])
        self.assertEqual(90, stored_rules({**rules, "image_rotation": 90}, DEFAULTS)["image_rotation"])
        self.assertEqual(0, stored_rules({**rules, "image_rotation": 45}, DEFAULTS)["image_rotation"])
        self.assertEqual(270, changed_rules(rules, {**rules, "image_rotation": 270})["image_rotation"])
        self.assertEqual(0, valid_image_rotation("90"))


class TurnInRunningSetupTests(unittest.TestCase):
    def test_a_quarter_turn_restarts_the_setup_with_the_turned_picture(self):
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
            access, seen = {}, []
            recorded = datetime.now(timezone.utc)
            frame = run.calibration_jpeg(Image.new("RGB", (100, 30), "gray"), (100, 30))
            measurement = {**sample(recorded), "raw_value": "12345.230", "actual_value": "12345.230",
                           "reference_time": recorded.timestamp(), "reference_required": True}

            def fake_panel(*args, **kwargs):
                access.update(status=kwargs["get_calibration"], control=kwargs["control_calibration"],
                              rules=args[6])
                kwargs["control_calibration"]("start", 4)
                first = kwargs["get_calibration"]()
                kwargs["control_calibration"]("turn-right", 0)
                access["first_limit"] = first["limit"]
                return None, None, None

            def examine(job, frame_now, overlay, sample_now, stamp, rules, read, stop, *args, **kwargs):
                seen.append(frame_now.size)
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
                    patch.object(run, "capture_camera", return_value=(frame, None, measurement)), \
                    patch.object(run.Calibration, "examine", examine):
                with self.assertRaises(Done):
                    run.main()
                self.assertEqual(90, access["rules"]()["image_rotation"])
                status = access["status"]()
                self.assertEqual(90, status["image_rotation"])
                self.assertEqual(access["first_limit"], status["limit"])
                # The setup searched the picture turned by 90°: 100 × 30 became 30 × 100.
                self.assertEqual([(30, 100)], seen)


if __name__ == "__main__":
    unittest.main()
