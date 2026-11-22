"""0.5.29: "find the counter" is ticked only for a plausible reading, a frame turned by 180° is not confirmed."""

import os
import sys
import unittest
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import calibration  # noqa: E402
from calibration import (Calibration, Layout, closer_half_turn, half_turn_layout, half_turned,  # noqa: E402
                         setup_flow_limit)
from checks import OCR_PROFILES  # noqa: E402
from consumption import accumulate_consumption  # noqa: E402
import run  # noqa: E402
from test_ingress import IngressFixture  # noqa: E402

RULES = {"decimals": 3, "fraction_digits": 3, "integer_digits": 5, "max_flow_lph": 6000, "learned_flow_lph": None}
# A meter hanging sideways: the right frame and the same digits turned by another 180°.
RIGHT = Layout((302, 44, 362, 418), -86, 240, method="register_window")
TURNED = Layout((300, 40, 360, 420), 95, 240, method="register_window")
UPRIGHT = Layout((200, 200, 520, 260), 0, 200, method="register_window")
START = 1000


def last_reading(value="10516.24", stamp=START):
    return accumulate_consumption({}, "calibration", stamp, value, 2, 6000, 5, confirmed=True)


def by_direction(right, turned):
    """The right value at a negative turn, the other value at the opposite turn."""
    return lambda layout, profile: right if layout.rotation < 0 else turned


def setup_picture(found, read, hours, *, read_slot=None):
    job = Calibration(5, 3, simplified=True, rank_candidates=True)
    decisions = []
    with patch.object(calibration, "layouts", return_value=list(found)), \
            patch.object(calibration, "quarter_turn_layouts", return_value=[]):
        job.examine(Image.new("RGB", (800, 600), (40, 40, 40)), None, {"reference_required": False},
                    START + hours * 3600, RULES, read, lambda: False, last_reading(),
                    on_decision=decisions.append, read_slot=read_slot)
    return job, decisions


class SetupFlowTests(unittest.TestCase):
    def test_a_learned_flow_limits_a_new_frame(self):
        self.assertEqual(2400, setup_flow_limit({"max_flow_lph": 6000, "learned_flow_lph": 2400}))
        self.assertEqual(6000, setup_flow_limit({"max_flow_lph": 6000, "learned_flow_lph": 9000}))

    def test_without_a_learned_flow_half_the_maximum_and_at_least_one_and_a_half_cubic_metres(self):
        self.assertEqual(3000, setup_flow_limit({"max_flow_lph": 6000, "learned_flow_lph": None}))
        self.assertEqual(1500, setup_flow_limit({"max_flow_lph": 2000}))
        # Never above the configured maximum.
        self.assertEqual(1000, setup_flow_limit({"max_flow_lph": 1000}))


class HalfTurnTests(unittest.TestCase):
    def test_frames_on_the_same_digits_turned_by_180_degrees(self):
        self.assertTrue(half_turned(TURNED, RIGHT))
        self.assertFalse(half_turned(TURNED, replace(RIGHT, rotation=5)))
        self.assertFalse(half_turned(TURNED, Layout((500, 40, 560, 420), -86, 240)))

    def test_the_turned_frame_mirrors_its_digit_boxes(self):
        layout = Layout((0, 0, 10, 10), -86, 5, ((0, 0, 400, 1000), (500, 100, 900, 900)))
        turned = half_turn_layout(layout, 2)
        self.assertEqual(94, turned.rotation)
        self.assertEqual(((100, 100, 500, 900), (600, 0, 1000, 1000)), turned.digit_boxes)
        self.assertEqual((), half_turn_layout(layout, 3).digit_boxes)
        self.assertEqual(-85, half_turn_layout(TURNED, 8).rotation)
        self.assertEqual(180, half_turn_layout(UPRIGHT, 8).rotation)
        self.assertEqual(0, half_turn_layout(replace(UPRIGHT, rotation=180), 8).rotation)

    def test_the_reading_closer_to_the_last_reading_wins(self):
        tried = [(None, RIGHT, ["10516.73?", "10516.72?"])]
        self.assertEqual(RIGHT, closer_half_turn(TURNED, "10521.90?", tried, last_reading(), 2, 5))
        self.assertIsNone(closer_half_turn(RIGHT, "10516.73?", [(None, TURNED, ["10521.90?"])],
                                           last_reading(), 2, 5))
        # A value below the last reading is no evidence: the meter never runs backwards.
        self.assertIsNone(closer_half_turn(TURNED, "10521.90?", [(None, RIGHT, ["10510.00?"])],
                                           last_reading(), 2, 5))


class SetupPictureTests(unittest.TestCase):
    def test_a_frame_turned_by_180_degrees_is_not_confirmed(self):
        # Seen live: the right frame read 10516.73, the turned frame 10521.90 and was confirmed.
        # Ten hours after the last reading the flow allows both; the turned frame is read once more.
        job, decisions = setup_picture([TURNED], by_direction("10516.730", "10521.900"), 10)
        self.assertEqual(-85, job.candidate.rotation)
        self.assertEqual(1, job.confirmations)
        self.assertEqual(["implausible", "accepted"], decisions)
        self.assertEqual([{"reason": "half_turn", "box": [300, 40, 360, 420], "rotation": 95,
                           "reading": "10521.900"}], job.rejected)

    def test_a_clean_but_implausible_frame_does_not_end_the_search(self):
        job, _ = setup_picture([TURNED, RIGHT], by_direction("10516.730", "10521.900"), 1)
        self.assertEqual(RIGHT, job.candidate)

    def test_the_right_frame_found_first_stays(self):
        job, decisions = setup_picture([RIGHT, TURNED], by_direction("10516.730", "10521.900"), 1)
        self.assertEqual(RIGHT, job.candidate)
        self.assertEqual(["accepted"], decisions)
        self.assertEqual([], job.rejected)

    def test_an_upright_meter_is_found_as_before(self):
        job, decisions = setup_picture([UPRIGHT], lambda layout, profile: (
            "10516.730" if layout.rotation == 0 else "?????.???"), 1)
        self.assertEqual(UPRIGHT, job.candidate)
        self.assertEqual(["accepted"], decisions)

    def test_a_new_frame_may_claim_only_the_setup_flow(self):
        # +5.66 m³ in one hour: within the configured 6 m³/h, beyond the setup's 3 m³/h.
        job, decisions = setup_picture([TURNED], by_direction("?????.???", "10521.900"), 1)
        self.assertIsNone(job.candidate)
        self.assertEqual(["implausible"], decisions)
        self.assertEqual("10521.900", job.rejected[0]["reading"])

    def test_a_fine_tuned_new_frame_is_checked_against_the_last_reading(self):
        # Before, a frame whose last slot was read again skipped every check of the last reading.
        def read(layout, profile):
            if layout.rotation < 0:
                return "?????.???"
            return "10521.96?" if profile == OCR_PROFILES[1] else "10521.90?"

        job, decisions = setup_picture([TURNED], read, 1, read_slot=lambda layout, index, profile: "0")
        self.assertIsNone(job.candidate)
        self.assertEqual(["implausible"], decisions)
        self.assertEqual([("implausible", "10521.90?")], [(entry["reason"], entry["reading"]) for entry in job.rejected])


class PartialHitTests(unittest.TestCase):
    def test_the_first_partial_hit_must_fit_the_last_reading(self):
        job = Calibration(5, 3, simplified=True, rank_candidates=True)
        self.assertFalse(job.partial_hit(TURNED, ["1052190", "1052196"], START + 3600, 6000, last_reading(), 3000))
        self.assertFalse(job.partial_hit(RIGHT, ["1051000", "1051000"], START + 3600, 6000, last_reading(), 3000))
        self.assertTrue(job.partial_hit(RIGHT, ["1051673", "1051672"], START + 3600, 6000, last_reading(), 3000))
        self.assertEqual(1, job.partial_hits)


class FactoryResetTests(unittest.TestCase):
    def test_the_learned_flow_stays_with_the_statistics(self):
        original = {"consumption": {"total_litres": 1240}, "flow_peaks": {"20000": 1200}, "flow_peak_samples": 40,
                    "check_status": "match"}
        kept = run.factory_reset_history(original, keep_statistics=True)
        self.assertEqual({"20000": 1200}, kept["flow_peaks"])
        self.assertEqual(40, kept["flow_peak_samples"])
        self.assertNotIn("check_status", kept)
        self.assertEqual({}, run.factory_reset_history(original))


def jpeg(size):
    with BytesIO() as stream:
        Image.new("RGB", size, "gray").save(stream, "JPEG")
        return stream.getvalue()


class FindStepTest(IngressFixture):
    def test_find_the_counter_is_ticked_only_after_a_plausible_reading(self):
        from playwright.sync_api import sync_playwright

        self.setup_pending = False
        self.source_selected = True
        self.control_calibration("setup", 20)
        self.calibration_images["frame", "15"] = jpeg((800, 600))
        self.calibration_images["crop", "15"] = jpeg((400, 80))
        self.calibration.update(
            state="testing", stage="ocr", tested=2, attempts=9, variant=1, rotation=95, confirmations=0,
            seconds=600,
            preview={"frame": 15, "crop": 15, "region": [0.3, 0.1, 0.1, 0.6], "angle": 95,
                     "reading": "10521.90?", "reason": "unclear"},
            candidates=[{"number": 1, "percent": 88, "reading": "10521.90?", "rotation": 95,
                         "box": [300, 40, 360, 420], "selected": True}],
            rejected=[{"reason": "half_turn", "box": [300, 40, 360, 420], "rotation": 95, "reading": "10521.900"},
                      {"reason": "implausible", "box": [302, 44, 362, 418], "rotation": -85, "reading": "10517.71"}],
            rounds=[{"image": 1, "reason": "unclear", "reading": "10521.90?", "seconds": 40.0, "confirmations": 0}])
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            page = browser.new_page(viewport={"width": 1280, "height": 1000}, locale="de-DE",
                                    reduced_motion="reduce")
            page.set_default_timeout(7000)
            page.goto(self.base + "/?ui=overview")
            timeline = page.locator("#calibration-overview .setup-timeline")
            current = timeline.locator('li[data-state="current"]')
            current.filter(has_text="Zählwerk finden").wait_for()
            self.assertEqual("find", current.get_attribute("data-step"))
            self.assertNotIn("Zählwerk gefunden", timeline.inner_text())
            self.assertIn("9 Rahmen getestet", current.locator(".setup-step-detail").inner_text())
            # The tested frame is drawn dashed and called so; it is not the found counter yet.
            photo = page.locator("#calibration-overview .calibration-photo-panel")
            region = photo.locator(".calibration-crop-region")
            region.wait_for(state="visible")
            self.assertEqual("testing", region.get_attribute("data-state"))
            self.assertEqual("dashed", region.evaluate("node => getComputedStyle(node).borderTopStyle"))
            self.assertIn("Rahmen wird geprüft", photo.locator(".calibration-frame-caption").inner_text())
            # Rejected frames are listed with what they read.
            panel = page.locator("#calibration-overview .calibration-candidate-panel")
            panel.locator("summary").first.click()
            rejected = panel.locator(".calibration-rejected")
            rejected.locator("summary").click()
            text = rejected.inner_text()
            self.assertIn("um 180° verdreht gelesen", text)
            self.assertIn("las 10521,900", text)
            self.assertIn("passt nicht zum letzten bekannten Zählerstand · las 10517,71", text)
            page.screenshot(path="/tmp/setup-find-0529.png", full_page=True)

            self.calibration.update(
                stage="verify_wait", confirmations=1, rotation=-85,
                preview={"frame": 15, "crop": 15, "region": [0.3, 0.1, 0.1, 0.6], "angle": -85,
                         "reading": "10516.73?", "reason": "accepted_partial"},
                rounds=[{"image": 1, "reason": "unclear", "reading": "10521.90?", "seconds": 40.0, "confirmations": 0},
                        {"image": 2, "reason": "accepted_partial", "reading": "10516.73?", "seconds": 30.0,
                         "confirmations": 1}])
            timeline.locator('li[data-state="current"]').filter(has_text="(1/3)").wait_for()
            found = timeline.locator('li[data-step="find"]')
            self.assertEqual("done", found.get_attribute("data-state"))
            self.assertIn("Zählwerk gefunden", found.inner_text())
            page.wait_for_function(
                "document.querySelector('#calibration-overview .calibration-crop-region').dataset.state === 'found'")
            self.assertIn("Rahmen passt", photo.locator(".calibration-frame-caption").inner_text())
            browser.close()


if __name__ == "__main__":
    unittest.main()
