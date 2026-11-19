import json
import unittest

from run import lit_picture
from source_settings import source_rules


class CaptureLightTest(unittest.TestCase):
    def setup_calls(self, state="off", fail_take=False, fail_on=False):
        calls = []

        def fetch(url, token, timeout=8):
            calls.append(("get", url.rsplit("/", 1)[-1]))
            return json.dumps({"state": state}).encode()

        def post(url, token, payload):
            calls.append(("post", url.rsplit("/", 1)[-1]))
            if fail_on and url.endswith("turn_on"):
                raise OSError("down")

        def take():
            calls.append(("take", ""))
            if fail_take:
                raise OSError("camera")
            return b"jpeg"

        return calls, fetch, post, take

    def test_light_on_wait_take_off(self):
        calls, fetch, post, take = self.setup_calls()
        waits = []
        self.assertEqual(b"jpeg", lit_picture("light.blitz", take, "t", fetch=fetch, post=post, sleep=waits.append))
        self.assertEqual([("get", "light.blitz"), ("post", "turn_on"), ("take", ""), ("post", "turn_off")], calls)
        self.assertEqual([1.5], waits)

    def test_light_goes_off_when_the_picture_fails(self):
        calls, fetch, post, take = self.setup_calls(fail_take=True)
        with self.assertRaises(OSError):
            lit_picture("light.blitz", take, "t", fetch=fetch, post=post, sleep=lambda _: None)
        self.assertEqual(("post", "turn_off"), calls[-1])

    def test_light_that_was_on_stays_on(self):
        calls, fetch, post, take = self.setup_calls(state="on")
        lit_picture("light.blitz", take, "t", fetch=fetch, post=post, sleep=lambda _: None)
        self.assertNotIn(("post", "turn_off"), calls)
        self.assertNotIn(("post", "turn_on"), calls)

    def test_picture_is_taken_even_if_the_light_fails(self):
        calls, fetch, post, take = self.setup_calls(fail_on=True)
        self.assertEqual(b"jpeg", lit_picture("light.blitz", take, "t", fetch=fetch, post=post, sleep=lambda _: None))
        self.assertNotIn(("post", "turn_off"), calls)

    def test_without_light_only_the_picture(self):
        calls, fetch, post, take = self.setup_calls()
        lit_picture("", take, "t", fetch=fetch, post=post)
        self.assertEqual([("take", "")], calls)

    def test_source_accepts_light_only_for_camera_sources(self):
        base = {"url": "http://esp.local", "camera": "camera.gas", "reference": ""}
        self.assertEqual("light.blitz", source_rules({**base, "mode": "esphome", "light": "light.blitz"})["light"])
        self.assertEqual("", source_rules({**base, "mode": "slfork", "light": "light.blitz"})["light"])
        with self.assertRaises(ValueError):
            source_rules({**base, "mode": "camera", "light": "switch.blitz"})
        self.assertEqual("", source_rules({**base, "mode": "camera"})["light"])


if __name__ == "__main__":
    unittest.main()
