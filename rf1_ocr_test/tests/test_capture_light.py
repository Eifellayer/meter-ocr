import json
import unittest

from run import lit_picture
from source_settings import source_rules


class CaptureLightTest(unittest.TestCase):
    def setup_calls(self, state="off", fail_take=False, fail_on=False):
        calls = []

        reads = {"count": 0}

        def fetch(url, token, timeout=8):
            calls.append(("get", url.rsplit("/", 1)[-1]))
            reads["count"] += 1
            # First read: state before the picture; later reads: state after switching off.
            return json.dumps({"state": state if reads["count"] == 1 else "off"}).encode()

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
        # The first frame after switching on is dropped (0.5.2): it may predate the light.
        self.assertEqual([("get", "light.blitz"), ("post", "turn_on"), ("take", ""), ("take", ""),
                          ("post", "turn_off"), ("get", "light.blitz")], calls)
        self.assertEqual([1.5, 1], waits)

    def test_light_goes_off_when_the_picture_fails(self):
        calls, fetch, post, take = self.setup_calls(fail_take=True)
        with self.assertRaises(OSError):
            lit_picture("light.blitz", take, "t", fetch=fetch, post=post, sleep=lambda _: None)
        self.assertIn(("post", "turn_off"), calls)

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


class LightOffRetryTest(unittest.TestCase):
    def test_off_is_repeated_until_the_light_reports_off(self):
        from run import switch_light_off
        states = iter(["on", "on", "off"])
        posts = []
        ok = switch_light_off("light.blitz", "t",
                              fetch=lambda url, token, timeout=8: json.dumps({"state": next(states)}).encode(),
                              post=lambda url, token, payload: posts.append(url), sleep=lambda _: None)
        self.assertTrue(ok)
        self.assertEqual(3, len(posts))

    def test_gives_up_after_a_few_attempts(self):
        from run import switch_light_off
        posts = []
        ok = switch_light_off("light.blitz", "t",
                              fetch=lambda url, token, timeout=8: json.dumps({"state": "on"}).encode(),
                              post=lambda url, token, payload: posts.append(url), sleep=lambda _: None)
        self.assertFalse(ok)
        self.assertEqual(4, len(posts))


if __name__ == "__main__":
    unittest.main()


class CameraLightTest(unittest.TestCase):
    def setUp(self):
        import run
        run.CAMERA_LIGHT_CACHE.clear()

    def test_own_light_is_found_and_cached(self):
        from run import camera_light
        calls = []

        def post(url, token, payload):
            calls.append(payload["template"])
            return b"light.esp_blitz\n"

        self.assertEqual("light.esp_blitz", camera_light("camera.esp", "t", post=post, now=lambda: 0))
        self.assertEqual("light.esp_blitz", camera_light("camera.esp", "t", post=post, now=lambda: 60))
        self.assertEqual(1, len(calls))
        self.assertIn("device_id('camera.esp')", calls[0])

    def test_external_light_wins_and_switch_off_is_respected(self):
        from run import capture_light
        post = lambda url, token, payload: b"light.esp_blitz"
        self.assertEqual("light.keller", capture_light({"light": "light.keller"}, "camera.esp", "t", post=post))
        self.assertEqual("", capture_light({"light": "", "camera_light": False}, "camera.esp", "t", post=post))
        self.assertEqual("light.esp_blitz", capture_light({"light": ""}, "camera.esp", "t", post=post))

    def test_garbage_answer_means_no_light(self):
        from run import camera_light
        self.assertEqual("", camera_light("camera.x", "t", post=lambda u, t, p: b"<html>", now=lambda: 0))


def grey_jpeg(value):
    import io
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("L", (80, 60), value).save(buffer, "JPEG")
    return buffer.getvalue()


class DarkPictureTest(unittest.TestCase):
    """A picture taken without (or with a fading) light is retaken with the light on."""

    def setUp(self):
        import run
        self.run = run
        run.LIT_BRIGHTNESS.clear()

    def tearDown(self):
        self.run.LIT_BRIGHTNESS.clear()

    def calls_for(self, pictures, states):
        calls = []
        states = list(states)
        if states and states[0] == "off":
            # The app switches the light on itself and drops the first frame (0.5.2).
            pictures.insert(0, grey_jpeg(10))

        def fetch(url, token, timeout=8):
            calls.append(("get", ""))
            return json.dumps({"state": states.pop(0) if states else "off"}).encode()

        def post(url, token, payload):
            calls.append(("post", url.rsplit("/", 1)[-1]))

        def take():
            calls.append(("take", ""))
            return pictures.pop(0)

        return calls, fetch, post, take

    def test_first_lit_picture_sets_the_reference(self):
        calls, fetch, post, take = self.calls_for([grey_jpeg(90)], ["off"])
        lit_picture("light.blitz", take, "t", fetch=fetch, post=post, sleep=lambda _: None)
        self.assertAlmostEqual(90, self.run.LIT_BRIGHTNESS["light.blitz"], delta=2)

    def test_frame_from_before_the_light_is_dropped_without_any_reference(self):
        # Seen live on 22.11.2026: light on, first frame dark, no reference after a restart,
        # so the dark frame was used and even became the reference.
        bright = grey_jpeg(90)
        calls, fetch, post, take = self.calls_for([bright], ["off"])
        self.assertEqual(bright, lit_picture("light.blitz", take, "t", fetch=fetch, post=post, sleep=lambda _: None))
        self.assertEqual(2, calls.count(("take", "")))
        self.assertAlmostEqual(90, self.run.LIT_BRIGHTNESS["light.blitz"], delta=2)

    def test_dark_picture_is_retaken_with_light(self):
        self.run.LIT_BRIGHTNESS["light.blitz"] = 85
        bright = grey_jpeg(85)
        calls, fetch, post, take = self.calls_for([grey_jpeg(48), bright], ["off"])
        picture = lit_picture("light.blitz", take, "t", fetch=fetch, post=post, sleep=lambda _: None)
        self.assertEqual(bright, picture)
        self.assertEqual(3, calls.count(("take", "")))
        self.assertEqual(2, calls.count(("post", "turn_on")))
        self.assertIn(("post", "turn_off"), calls)

    def test_light_switched_off_by_someone_else_is_switched_on_and_off_again(self):
        # The ESP's "keep flash on" switch ended right before the picture.
        self.run.LIT_BRIGHTNESS["light.blitz"] = 85
        bright = grey_jpeg(85)
        calls, fetch, post, take = self.calls_for([grey_jpeg(48), bright], ["on", "off"])
        picture = lit_picture("light.blitz", take, "t", fetch=fetch, post=post, sleep=lambda _: None)
        self.assertEqual(bright, picture)
        self.assertIn(("post", "turn_on"), calls)
        self.assertIn(("post", "turn_off"), calls)

    def test_light_that_really_stays_on_is_not_switched_off(self):
        self.run.LIT_BRIGHTNESS["light.blitz"] = 85
        calls, fetch, post, take = self.calls_for([grey_jpeg(48), grey_jpeg(84)], ["on", "on"])
        lit_picture("light.blitz", take, "t", fetch=fetch, post=post, sleep=lambda _: None)
        self.assertNotIn(("post", "turn_off"), calls)

    def test_dark_pictures_do_not_lower_the_reference(self):
        self.run.LIT_BRIGHTNESS["light.blitz"] = 85
        calls, fetch, post, take = self.calls_for([grey_jpeg(40), grey_jpeg(42), grey_jpeg(41)], ["off"])
        lit_picture("light.blitz", take, "t", fetch=fetch, post=post, sleep=lambda _: None)
        self.assertEqual(85, self.run.LIT_BRIGHTNESS["light.blitz"])

    def test_normal_lit_picture_is_taken_once(self):
        self.run.LIT_BRIGHTNESS["light.blitz"] = 85
        calls, fetch, post, take = self.calls_for([grey_jpeg(80)], ["off"])
        lit_picture("light.blitz", take, "t", fetch=fetch, post=post, sleep=lambda _: None)
        # The dropped first frame plus the picture itself; no repeat because it is bright.
        self.assertEqual(2, calls.count(("take", "")))
