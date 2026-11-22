"""0.2.0: hidden digits by reflection, experiments in shadow mode (synthetic)."""

from unittest import TestCase
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont

import checks
import experiments
from layout import glare_slots
import run


def roller_strip(digits="10486016", glare_at=None, keystone=1.0):
    """Light digits in a dark window, optional flash reflection over one digit."""
    strip = Image.new("RGB", (8 * 60, 140), (60, 64, 80))
    draw = ImageDraw.Draw(strip)
    font = ImageFont.truetype("DejaVuSans-Bold.ttf", 60)
    boxes = []
    for index, digit in enumerate(digits):
        x = 30 + index * 60
        draw.text((x, 70), digit, fill=(200, 205, 215), font=font, anchor="mm")
        boxes.append((x - 25, 30, x + 25, 110))
    if glare_at is not None:
        x = 30 + glare_at * 60
        draw.ellipse((x - 26, 37, x + 26, 103), fill=(255, 255, 255))
    if keystone != 1.0:
        width, height = strip.size
        centre = height / 2
        # Shrink the right side: the inverse of the correction.
        quad = (0, 0, 0, height, width, centre + centre / keystone, width, centre - centre / keystone)
        strip = strip.transform(strip.size, Image.Transform.QUAD, quad, resample=Image.Resampling.BICUBIC,
                                fillcolor=(60, 64, 80))
    return strip, boxes


class GlareTests(TestCase):
    def test_reflection_over_one_digit_is_found(self):
        strip, boxes = roller_strip(glare_at=2)
        self.assertEqual([2], glare_slots(strip, boxes))

    def test_no_reflection_no_slot(self):
        strip, boxes = roller_strip()
        self.assertEqual([], glare_slots(strip, boxes))

    def test_narrow_streak_of_light_over_one_digit_is_found(self):
        # 0.5.9, seen live on 22.11.2026: after the camera was moved, a thin bright bar lay across
        # the first decimal roller. It covers only a few percent of the frame, the setup kept
        # reading "10511.?5?" and ran into its time limit.
        strip, boxes = roller_strip()
        x = 30 + 5 * 60
        ImageDraw.Draw(strip).rounded_rectangle((x - 20, 52, x + 20, 60), radius=4, fill=(252, 252, 255))
        self.assertEqual([5], glare_slots(strip, boxes))

    def test_bright_digits_alone_are_no_streak(self):
        # A roller with clearly brighter glyphs (uneven light) must not count as a reflection.
        strip, boxes = roller_strip()
        draw = ImageDraw.Draw(strip)
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 60)
        draw.text((30 + 3 * 60, 70), "8", fill=(235, 238, 245), font=font, anchor="mm")
        self.assertEqual([], glare_slots(strip, boxes))


class HiddenDigitTests(TestCase):
    anchor = {"time": 1000.0, "value": 10483335}

    def test_unique_completion_inside_flow_range(self):
        # 5 hours later at most 6 m³/h: only 10486.16 fits, 10586.16 does not.
        result = checks.anchored_hidden_digits(["10?86.16", "10?86.16"], self.anchor, 1000 + 5 * 3600, 2, 5,
                                               6000, [2])
        self.assertEqual((["10486.16", "10486.16"], [2]), result)

    def test_only_marked_positions_may_be_filled(self):
        self.assertIsNone(checks.anchored_hidden_digits(["104?6.16", "104?6.16"], self.anchor, 1000 + 3600, 2, 5,
                                                        6000, [2]))

    def test_ambiguous_or_missing_anchor_stays_open(self):
        self.assertIsNone(checks.anchored_hidden_digits(["10486.1?", "10486.1?"], self.anchor, 1000 + 3600, 2, 5,
                                                        6000, [6]))
        self.assertIsNone(checks.anchored_hidden_digits(["10?86.16"], None, 1000 + 3600, 2, 5, 6000, [2]))

    def test_value_below_the_anchor_is_rejected(self):
        self.assertIsNone(checks.anchored_hidden_digits(["10?80.00", "10?80.00"], self.anchor, 1000 + 3600, 2, 5,
                                                        6000, [2]))

    def test_marked_or_found_reflection_gives_slots(self):
        source = {"mode": "camera", "camera_entity": "camera.x"}
        rules = {"reflection_estimate_enabled": True,
                 "setup_reflection": {"source": checks.setup_source_id(source), "positions": [2]}}
        self.assertEqual([2], run.hidden_reflection_slots(rules, source))
        self.assertEqual([], run.hidden_reflection_slots({**rules, "reflection_estimate_enabled": False}, source))

    def test_entered_reading_becomes_anchor(self):
        from zoneinfo import ZoneInfo
        anchor = run.manual_reading_anchor({"fallback_value": "10486,16", "fallback_time": "2026-11-19T23:30"},
                                           ZoneInfo("Europe/Berlin"))
        self.assertEqual(10486160, anchor["value"])
        self.assertIsNone(run.manual_reading_anchor({"fallback_value": "", "fallback_time": ""}, None))


class ExperimentTests(TestCase):
    def test_off_by_default_and_only_known_names(self):
        self.assertEqual([], experiments.enabled_experiments({}))
        self.assertEqual([], experiments.enabled_experiments({"experiments": {"perspective": True}}))
        self.assertEqual(["perspective"], experiments.enabled_experiments(
            {"experiments_enabled": True, "experiments": {"perspective": True}}))
        self.assertEqual({"perspective": False, "seven_segment": False}, run.valid_experiments({"unknown": True}))

    def test_keystone_is_measured_and_levelled(self):
        strip, boxes = roller_strip(keystone=1.15)
        measured = experiments.measure_keystone(strip, boxes)
        self.assertIsNotNone(measured)
        self.assertGreater(abs(1 - measured["ratio"]), .05)
        corrected = experiments.correct_keystone(strip, measured["ratio"])
        again = experiments.measure_keystone(corrected, boxes)
        self.assertLess(abs(1 - again["ratio"]), abs(1 - measured["ratio"]))

    def test_level_strip_is_left_alone(self):
        strip, boxes = roller_strip()
        measured = experiments.measure_keystone(strip, boxes)
        self.assertLess(abs(1 - measured["ratio"]), .05)
        self.assertIs(strip, experiments.correct_keystone(strip, 1.0))

    def test_shadow_read_only_with_spare_capacity(self):
        strip, boxes = roller_strip()
        rules = {"experiments_enabled": True, "experiments": {"perspective": True}}
        with patch.object(run, "system_idle", return_value=False):
            self.assertEqual("busy", run.shadow_experiments(rules, False, strip, boxes, "10486.01", True, True)["skipped"])
        self.assertIsNone(run.shadow_experiments({}, False, strip, boxes, "10486.01", True, True))
        with patch.object(run, "system_idle", return_value=True), \
                patch.object(run, "read_digit", return_value="1"):
            record = run.shadow_experiments(rules, False, strip, boxes, "10486.01", True, True)
        self.assertEqual("10486.01", record["stable"])
        self.assertEqual("11111111", record["perspective"]["reading"])
