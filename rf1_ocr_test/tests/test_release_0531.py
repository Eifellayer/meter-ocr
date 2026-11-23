"""0.5.31: a frame seen upside down or mirrored is corrected right in the running setup."""

import os
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import calibration  # noqa: E402
from auto_rules import changed_rules, default_rules, stored_rules  # noqa: E402
from calibration import Calibration, Layout  # noqa: E402
from consumption import accumulate_consumption  # noqa: E402
import run  # noqa: E402
from settings import DEFAULTS  # noqa: E402
from test_ingress import IngressFixture  # noqa: E402

RULES = {"decimals": 3, "fraction_digits": 3, "integer_digits": 5, "max_flow_lph": 6000, "learned_flow_lph": None}
TURNED = Layout((300, 40, 360, 420), 95, 240, method="register_window")
ELSEWHERE = Layout((100, 400, 400, 460), 3, 200, method="register_window")
START = 1000


def by_direction(right, turned):
    return lambda layout, profile: right if layout.rotation < 0 else turned


def examine(job, found, read, hours=1, baseline=None, shade=40):
    decisions = []
    with patch.object(calibration, "layouts", return_value=list(found)), \
            patch.object(calibration, "quarter_turn_layouts", return_value=[]):
        job.examine(Image.new("RGB", (800, 600), (40, 40, shade)), None, {"reference_required": False},
                    START + hours * 3600, RULES, read, lambda: False, baseline, on_decision=decisions.append)
    return decisions


class FlipTests(unittest.TestCase):
    def test_flipping_turns_the_frames_of_that_direction_and_starts_counting_anew(self):
        job = Calibration(5, 3, simplified=True, rank_candidates=True)
        job.candidate, job.confirmations, job.counter = TURNED, 2, {"reading_litres": 1}
        job.shortlist = {TURNED: (88, 1.0, 88), ELSEWHERE: (40, 1.0, 40)}
        self.assertTrue(job.flip_orientation(8))
        self.assertEqual(-85, job.candidate.rotation)
        self.assertEqual(TURNED.box, job.candidate.box)
        self.assertEqual([-85, 3], [layout.rotation for layout in job.shortlist])
        self.assertEqual((0, {}, [95]), (job.confirmations, job.counter, job.wrong_turns))
        self.assertTrue(job.status(0)["turned_by_user"])
        # A second click turns it back.
        self.assertTrue(job.flip_orientation(8))
        self.assertEqual(95, job.candidate.rotation)
        self.assertEqual([], job.wrong_turns)

    def test_frames_found_in_the_wrong_direction_are_read_turned(self):
        job = Calibration(5, 3, simplified=True, rank_candidates=True)
        job.wrong_turns = [95]
        reads = []

        def read(layout, profile):
            reads.append(layout.rotation)
            return "10516.730" if layout.rotation < 0 else "10521.900"

        examine(job, [TURNED], read)
        self.assertEqual(-85, job.candidate.rotation)
        self.assertNotIn(95, reads)

    def test_the_direction_the_user_chose_wins_over_the_last_reading(self):
        # Ten hours after the last reading both directions are plausible; the user turned the
        # frame to 95°, so the frame is not turned back by the comparison with the last reading.
        job = Calibration(5, 3, simplified=True, rank_candidates=True)
        job.wrong_turns = [-86]
        baseline = accumulate_consumption({}, "calibration", START, "10516.24", 2, 6000, 5, confirmed=True)
        examine(job, [TURNED], by_direction("10516.730", "10521.900"), hours=10, baseline=baseline)
        self.assertEqual(95, job.candidate.rotation)
        self.assertEqual([], job.rejected)

    def test_nothing_to_flip_without_a_frame(self):
        self.assertFalse(Calibration(5, 3).flip_orientation(8))


class SidewaysTwinTests(unittest.TestCase):
    def test_an_unclear_sideways_frame_is_also_read_turned(self):
        # Seen live: only the frame at 97° stayed in the list, read "?1691.?0?" picture after
        # picture and never confirmed; the right frame at −83° was never read again.
        job = Calibration(5, 3, simplified=True, rank_candidates=True)
        sideways = Layout((264, 3, 400, 407), 97, 240, method="register_window")
        for picture_number in range(2):
            examine(job, [sideways], by_direction("10516.73?", "?1691.?0?"), hours=picture_number,
                    shade=40 + picture_number)
        self.assertEqual(-83, job.candidate.rotation)
        self.assertEqual(2, job.confirmations)

    def test_upright_frames_are_not_read_turned(self):
        job = Calibration(5, 3, simplified=True, rank_candidates=True)
        upright = Layout((200, 200, 520, 260), 2, 200, method="register_window")
        reads = []

        def read(layout, profile):
            reads.append(layout.rotation)
            return "?1691.?0?"

        examine(job, [upright], read)
        self.assertEqual({2}, set(reads))


def picture(kind="JPEG"):
    image = Image.new("RGB", (40, 20), "black")
    image.paste((255, 255, 255), (0, 0, 20, 20))
    with BytesIO() as stream:
        image.save(stream, kind)
        return stream.getvalue()


def left_and_right(content):
    with Image.open(BytesIO(content)) as image:
        rgb = image.convert("RGB")
        return rgb.getpixel((5, 10))[0], rgb.getpixel((35, 10))[0], image.format


class MirrorTests(unittest.TestCase):
    def test_pictures_are_mirrored_only_when_the_setup_says_so(self):
        result = (picture(), picture("PNG"), {"esp_timestamp": "x"})
        self.assertIs(result, run.mirror_capture(result, {"image_mirrored": False}))
        self.assertIsNone(run.mirror_capture(None, {"image_mirrored": True}))
        mirrored, overlay, sample = run.mirror_capture(result, {"image_mirrored": True})
        left, right, kind = left_and_right(mirrored)
        self.assertLess(left, 60)
        self.assertGreater(right, 200)
        self.assertEqual("JPEG", kind)
        self.assertEqual("PNG", left_and_right(overlay)[2])
        self.assertIs(result[2], sample)

    def test_an_unreadable_picture_stays_as_it_is(self):
        self.assertEqual(b"not a picture", run.mirrored_picture(b"not a picture"))

    def test_the_setting_is_kept_and_checked(self):
        rules = default_rules(DEFAULTS)
        self.assertFalse(rules["image_mirrored"])
        self.assertTrue(stored_rules({**rules, "image_mirrored": True}, DEFAULTS)["image_mirrored"])
        self.assertFalse(stored_rules({**rules, "image_mirrored": "yes"}, DEFAULTS)["image_mirrored"])
        self.assertTrue(changed_rules(rules, {**rules, "image_mirrored": True})["image_mirrored"])


def jpeg(size):
    with BytesIO() as stream:
        Image.new("RGB", size, "gray").save(stream, "JPEG")
        return stream.getvalue()


class OrientationButtonsTest(IngressFixture):
    def control_calibration(self, action, limit, region=None, **options):
        if action in ("turn-left", "turn-right", "mirror"):
            self.orientation_actions.append(action)
            if action == "turn-right":
                self.calibration["image_rotation"] = 90
            if action == "mirror":
                self.calibration["image_mirrored"] = True
            return True
        return super().control_calibration(action, limit, region, **options)

    def running_setup(self):
        self.orientation_actions = []
        self.setup_pending = False
        self.source_selected = True
        super().control_calibration("setup", 20)
        self.calibration_images["frame", "15"] = jpeg((800, 600))
        self.calibration_images["crop", "15"] = jpeg((400, 80))
        self.calibration.update(
            state="testing", stage="ocr", tested=2, attempts=9, variant=1, rotation=95, confirmations=0,
            seconds=600, preview={"frame": 15, "crop": 15, "region": [0.3, 0.1, 0.1, 0.6], "angle": 95,
                                  "reading": "10521.90?", "reason": "unclear"})

    def test_turned_and_mirrored_pictures_can_be_corrected_in_the_running_setup(self):
        from playwright.sync_api import sync_playwright

        self.running_setup()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            page = browser.new_page(viewport={"width": 1280, "height": 1000}, locale="de-DE")
            page.set_default_timeout(7000)
            page.goto(self.base + "/?ui=overview")
            panel = page.locator("#calibration-overview .calibration-photo-panel")
            # 0.5.34: quarter turns of the picture replace the 180° button.
            right = panel.get_by_role("button", name="↻ Bild 90° nach rechts drehen")
            right.wait_for()
            self.assertTrue(panel.get_by_role("button", name="↺ Bild 90° nach links drehen").is_visible())
            self.assertTrue(panel.get_by_role("button", name="⇋ Bild spiegeln").is_visible())
            self.assertEqual(0, panel.get_by_role("button", name="Steht auf dem Kopf? Um 180° drehen").count())
            right.click()
            page.get_by_text("Das Kamerabild wird jetzt um 90° gedreht. Die Einrichtung sucht das Zählwerk neu.").wait_for()
            self.assertEqual(["turn-right"], self.orientation_actions)
            self.assertIn("ui=overview", page.url)
            page.locator("#calibration-overview .calibration-orientation-state").filter(
                has_text="Kamerabild: um 90° nach rechts gedreht").wait_for()
            page.locator("#calibration-overview .calibration-orientation button[value='mirror']").click()
            page.get_by_text("Das Kamerabild wird jetzt gespiegelt. Die Einrichtung sucht das Zählwerk neu.").wait_for()
            self.assertEqual(["turn-right", "mirror"], self.orientation_actions)
            page.locator("#calibration-overview .calibration-orientation-state").filter(
                has_text="um 90° nach rechts gedreht, gespiegelt").wait_for()
            # Without a cut-out to look at, there is nothing to turn.
            self.calibration["preview"] = {"frame": 15}
            page.locator("#calibration-overview .calibration-orientation").wait_for(state="hidden")
            browser.close()

    def test_english_buttons(self):
        from playwright.sync_api import sync_playwright

        self.running_setup()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            page = browser.new_page(locale="en-GB")
            page.set_default_timeout(7000)
            page.goto(self.base + "/?ui=overview&lang=en")
            panel = page.locator("#calibration-overview .calibration-photo-panel")
            panel.get_by_role("button", name="↻ Turn the picture 90° right").wait_for()
            self.assertTrue(panel.get_by_role("button", name="↺ Turn the picture 90° left").is_visible())
            self.assertTrue(panel.get_by_role("button", name="⇋ Mirror the picture").is_visible())
            browser.close()


if __name__ == "__main__":
    unittest.main()
