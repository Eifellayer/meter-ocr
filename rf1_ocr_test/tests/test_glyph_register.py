"""Meter window search on dim, uneven ESPHome camera images (synthetic, no private photos)."""

from unittest import TestCase

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from calibration import glyph_register_layout
from layout import find_dark_register, find_glyph_register, scale_digit_boxes, turn_crop
import run


def esphome_like_meter(tilt=6.0, glare=True):
    """Grey window with light digits, a red fraction field, glare, barcode and small print below."""
    photo = Image.new("RGB", (800, 600), (118, 122, 140))
    draw = ImageDraw.Draw(photo)
    draw.rectangle((140, 150, 745, 250), fill=(70, 72, 88))
    draw.rectangle((505, 150, 745, 250), fill=(150, 70, 90))
    font = ImageFont.truetype("DejaVuSans.ttf", 62)
    for index, digit in enumerate("10485337"):
        x = 140 + 37 + index * 74
        draw.rectangle((x - 28, 158, x + 28, 242), fill=(55, 57, 72) if index < 5 else (135, 58, 78))
        draw.text((x, 200), digit, fill=(190, 192, 205), font=font, anchor="mm")
    if glare:
        draw.ellipse((300, 150, 380, 200), fill=(250, 250, 255))
    for x in range(380, 700, 7):
        draw.rectangle((x, 262, x + (x % 3) + 1, 312), fill=(30, 30, 40))
    small = ImageFont.truetype("DejaVuSans.ttf", 26)
    draw.text((380, 320), "7 PIP00 0390 4551", fill=(30, 30, 40), font=small)
    draw.text((150, 270), "e-regio", fill=(30, 30, 40), font=small)
    draw.text((760, 255), "m", fill=(30, 30, 40), font=ImageFont.truetype("DejaVuSans.ttf", 44))
    photo = photo.rotate(-tilt, resample=Image.Resampling.BICUBIC, fillcolor=(118, 122, 140))
    return photo.filter(ImageFilter.GaussianBlur(2.2))


class GlyphRegisterTests(TestCase):
    def test_tilted_window_with_glare_and_barcode_is_found_and_levelled(self):
        photo = esphome_like_meter()
        found = find_glyph_register(photo, 8, with_tilt=True)
        self.assertIsNotNone(found)
        box, tilt = found
        self.assertAlmostEqual(6.0, tilt, delta=1.5)
        level = find_glyph_register(turn_crop(photo, round(-tilt), expand=False), 8, with_tilt=True)
        self.assertIsNotNone(level)
        (left, top, right, bottom), rest = level
        self.assertLess(abs(rest), 1.5)
        self.assertLess(abs(left - 140), 30)
        self.assertLess(abs(right - 745), 40)
        # Neither the barcode nor the serial number below belongs to the window.
        self.assertLess(bottom, 285)
        self.assertGreater(top, 120)

    def test_layout_has_eight_digit_frames_on_the_rollers(self):
        photo = esphome_like_meter()
        layout = glyph_register_layout(photo, 5, 3)
        self.assertIsNotNone(layout)
        self.assertEqual("register_window", layout.method)
        self.assertEqual(8, len(layout.digit_boxes))
        self.assertLessEqual(abs(layout.rotation + 6), 1)

    def test_dark_print_on_a_light_label_is_not_taken_for_a_window(self):
        photo = Image.new("RGB", (640, 480), (225, 225, 225))
        draw = ImageDraw.Draw(photo)
        font = ImageFont.truetype("DejaVuSans.ttf", 40)
        draw.text((80, 200), "1 2 3 4 5 6 7 8", fill=(20, 20, 20), font=font)
        self.assertIsNone(find_glyph_register(photo.filter(ImageFilter.GaussianBlur(1)), 8))

    def test_level_register_without_glare_still_found(self):
        self.assertIsNotNone(find_dark_register(esphome_like_meter(tilt=0, glare=False), 8))


class SetupAutostartTests(TestCase):
    def test_setup_restarts_once_per_installed_version(self):
        history = {}
        before = lambda: True
        self.assertTrue(run.setup_autostart_due(history, "0.1.25", None, before))
        history["setup_autostart_build"] = "0.1.25"
        self.assertFalse(run.setup_autostart_due(history, "0.1.25", None, before))
        self.assertTrue(run.setup_autostart_due(history, "0.1.26", None, before))

    def test_running_setup_unknown_version_or_no_earlier_setup_is_left_alone(self):
        self.assertFalse(run.setup_autostart_due({}, "0.1.25", object(), lambda: True))
        self.assertFalse(run.setup_autostart_due({}, "", None, lambda: True))
        self.assertFalse(run.setup_autostart_due({}, "0.1.25", None, lambda: False))

    def test_unfinished_setup_is_recognised_from_the_debug_log(self):
        # Setup timed out after 20 min, the automatic then read "?????.9??".
        start = '{"kind": "setup_start", "trigger": "user"}'
        timeout = '{"kind": "setup_end", "state": "timeout", "purpose": "setup"}'
        unclear = '{"kind": "automatic", "outcome": "ocr_unclear"}'
        log = lambda *lines: "\n".join(lines)
        self.assertTrue(run.last_setup_unfinished(log(start, timeout, unclear, unclear)))
        self.assertFalse(run.last_setup_unfinished(log(start, timeout, '{"kind": "automatic", "outcome": "ocr_only"}')))
        self.assertFalse(run.last_setup_unfinished(
            log(start, '{"kind": "setup_end", "state": "saved", "purpose": "setup"}', unclear)))
        self.assertFalse(run.last_setup_unfinished(
            log(start, '{"kind": "setup_end", "state": "cancelled", "purpose": "setup"}')))
        # A background search that failed is no reason to redo the whole setup.
        self.assertFalse(run.last_setup_unfinished('{"kind": "setup_end", "state": "failed", "purpose": "background"}'))
        self.assertFalse(run.last_setup_unfinished(start))
        self.assertFalse(run.last_setup_unfinished("kaputt"))


class SetupRetryTests(TestCase):
    def test_quick_retries_then_hourly_without_limit(self):
        self.assertEqual(run.SETUP_RETRY_SECONDS, run.setup_retry_delay(0))
        self.assertEqual(run.SETUP_RETRY_SECONDS, run.setup_retry_delay(run.SETUP_RETRY_LIMIT - 1))
        self.assertEqual(3600, run.setup_retry_delay(run.SETUP_RETRY_LIMIT))
        self.assertEqual(3600, run.setup_retry_delay(50))

    def test_long_retry_notice_is_translated(self):
        import i18n
        self.assertIn(run.SETUP_RETRY_LONG_NOTICE, i18n.EN_UI)
