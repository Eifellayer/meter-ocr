import json
import unittest

import run
from checks import disputed_integer_positions, read_with_retries, resolve_ocr_readings


class DisputedWholeDigitTest(unittest.TestCase):
    """20.11.2026: 3 of 5 readings said 10491.4, 2 said 10490.4; the meter showed 10490.6."""

    def test_disputed_ones_digit_is_not_decided_by_majority(self):
        readings = ["10490.4??", "10491.4??", "10491.4??", "10490.4??", "10491.4??"]
        for decimals in (1, 2):
            value, confirmed = resolve_ocr_readings(readings, decimals, 5, standalone=True,
                                                    standalone_composition=True)
            self.assertFalse(confirmed)
            self.assertEqual("1049?", value[:5])

    def test_single_outlier_still_uses_the_majority(self):
        value, confirmed = resolve_ocr_readings(["10490.4??", "10491.4??", "10490.4??", "10490.4??"], 1, 5,
                                                standalone=True, standalone_composition=True)
        self.assertTrue(confirmed)
        self.assertEqual("10490.4", value[:7])

    def test_turning_roller_with_carry_is_not_a_dispute(self):
        self.assertEqual(set(), disputed_integer_positions(
            ["10489.9", "10490.0", "10490.0", "10489.9"], 5, 1) - {3, 4} or set())
        self.assertNotIn(4, disputed_integer_positions(["10490.9", "10491.0", "10491.0", "10490.9"], 5, 1))
        self.assertIn(4, disputed_integer_positions(["10490.4", "10491.4", "10491.4", "10490.4"], 5, 1))

    def test_even_split_over_many_reads_stays_open(self):
        readings = ["12345.120"] * 8 + ["12346.120"] * 7
        self.assertEqual({4}, disputed_integer_positions(readings, 5, 3))

    def test_far_apart_digits_are_always_disputed(self):
        self.assertIn(1, disputed_integer_positions(["10490.0", "18490.0", "18490.0", "10490.0"], 5, 1))

    def test_early_stable_result_is_dropped_on_a_dispute(self):
        values = iter(["10491.46", "10490.46", "10491.46", "10490.46", "10491.46"])
        value, confirmed, _ = read_with_retries(lambda profile: next(values), {"reference_required": False}, 2,
                                                max_attempts=5, standalone=True)
        self.assertFalse(confirmed)


def grey_jpeg(level):
    import io
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("L", (80, 60), level).save(buffer, "JPEG")
    return buffer.getvalue()


class CameraGainTest(unittest.TestCase):
    def setUp(self):
        run.LIT_BRIGHTNESS.clear()
        run.GAIN_ADJUSTED.clear()

    def make(self, gain="2.0", entity="number.esp_verstarkung"):
        calls = []

        def fetch(url, token, timeout=8):
            calls.append(("get", url.rsplit("/", 1)[-1]))
            if url.endswith(entity):
                return json.dumps({"state": gain, "attributes": {"min": 0, "max": 30}}).encode()
            return json.dumps({"state": "off"}).encode()

        def post(url, token, payload):
            calls.append(("post", url.rsplit("/", 1)[-1], payload))
            if url.endswith("/template"):
                return entity.encode()
            return b"[]"

        return calls, fetch, post

    def test_dark_with_light_raises_gain_in_bounded_steps(self):
        run.LIT_BRIGHTNESS["light.blitz"] = 79
        calls, fetch, post = self.make()
        pictures = iter([grey_jpeg(20), grey_jpeg(24), grey_jpeg(25), grey_jpeg(25)])  # first one is dropped (0.5.2)
        run.lit_picture("light.blitz", lambda: next(pictures), "t", fetch=fetch, post=post, sleep=lambda _: None)
        sets = [call[2] for call in calls if call[0] == "post" and call[1] == "set_value"]
        self.assertEqual([{"entity_id": "number.esp_verstarkung", "value": 6}], sets)

    def test_late_light_gets_a_second_longer_wait(self):
        run.LIT_BRIGHTNESS["light.blitz"] = 79
        calls, fetch, post = self.make()
        bright = grey_jpeg(80)
        pictures = iter([grey_jpeg(20), grey_jpeg(24), grey_jpeg(25), bright])  # first one is dropped (0.5.2)
        waits = []
        picture = run.lit_picture("light.blitz", lambda: next(pictures), "t", fetch=fetch, post=post,
                                  sleep=waits.append)
        self.assertEqual(bright, picture)
        self.assertIn(3.0, waits)
        self.assertFalse([call for call in calls if call[0] == "post" and call[1] == "set_value"])

    def test_gain_is_adjusted_at_most_every_few_minutes(self):
        run.LIT_BRIGHTNESS["light.blitz"] = 79
        calls, fetch, post = self.make()
        clock = iter([0, 60, 400]).__next__
        results = [run.raise_camera_gain("light.blitz", 24, "t", fetch=fetch, post=post, now=clock)
                   for _ in range(2)]
        self.assertEqual([7.0, None], results)

    def test_gain_never_exceeds_the_ceiling(self):
        run.LIT_BRIGHTNESS["light.blitz"] = 79
        calls, fetch, post = self.make(gain="18")
        self.assertEqual(20, run.raise_camera_gain("light.blitz", 24, "t", fetch=fetch, post=post))
        run.GAIN_ADJUSTED.clear()
        calls, fetch, post = self.make(gain="20")
        self.assertIsNone(run.raise_camera_gain("light.blitz", 24, "t", fetch=fetch, post=post))

    def test_camera_without_gain_control_is_left_alone(self):
        run.LIT_BRIGHTNESS["light.blitz"] = 79
        calls, fetch, post = self.make(entity="")
        self.assertIsNone(run.raise_camera_gain("light.blitz", 24, "t", fetch=fetch, post=post))
        self.assertFalse([call for call in calls if call[0] == "post" and call[1] == "set_value"])


if __name__ == "__main__":
    unittest.main()


class StandaloneSensorTest(unittest.TestCase):
    def test_sensor_keeps_the_booked_value_after_a_new_setup(self):
        sent = []
        history = {"consumption": {"source": ["esphome", "camera.gas", ""], "anchor_litres": 10490400,
                                   "anchor_step": 100, "anchor_time": 1.0}}
        from unittest.mock import patch
        with patch.object(run, "publish_state", lambda url, payload, token: sent.append(payload)):
            run.publish_standalone(history, "camera.gas", "t")
            run.publish_standalone(history, "camera.other", "t")
        self.assertEqual("10490.4", sent[0]["state"])
        self.assertTrue(sent[0]["attributes"]["is_fallback"])
        self.assertEqual("unavailable", sent[1]["state"])
