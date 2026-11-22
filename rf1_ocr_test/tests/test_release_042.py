"""0.4.2: frames follow a changing digit distance, turning rollers, self-repair, leading digits."""

import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import glyph_match  # noqa: E402
import run  # noqa: E402
from calibration import Calibration, Layout, MIN_IMAGES  # noqa: E402
from layout import (dark_register_cells, find_glyph_register, level_on_glyphs, scale_digit_boxes,  # noqa: E402
                    slot_positions)
from meter_learning import (GEOMETRY_FAILURE_DURATION, GEOMETRY_REPAIR_FAILURES, GEOMETRY_REPAIR_REPEAT,  # noqa: E402
                            observe_geometry_failures)

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
# Measured on the real meter (20.11.2026): black rollers about 47 px apart, the red ones 49 and 52.5.
CENTERS = (41, 88.5, 134.5, 182, 230, 279, 328, 380.5)


def unequal_strip(digits="10494557", centers=CENTERS, *, edge=True, blank=()):
    """Synthetic digit window: bright digits on dark rollers, red decimals, bright window edge."""
    strip = Image.new("RGB", (422, 96), (38, 30, 34))
    draw = ImageDraw.Draw(strip)
    draw.rectangle((255, 0, 421, 95), fill=(120, 26, 40))
    if edge:
        draw.rectangle((0, 0, 421, 4), fill=(205, 215, 225))
        draw.rectangle((0, 91, 421, 95), fill=(205, 215, 225))
    font = ImageFont.truetype(FONT, 46)
    for index, (digit, center) in enumerate(zip(digits, centers)):
        if index not in blank:
            draw.text((center, 50), digit, font=font, anchor="mm", fill=(150, 190, 215))
    return strip


class SlotModelTests(unittest.TestCase):
    def test_growing_digit_distance_is_followed_to_the_last_roller(self):
        position, pitch = slot_positions(list(range(7)), list(CENTERS[:7]))
        self.assertLess(abs(position(7) - CENTERS[7]), 3.5)
        uniform = CENTERS[0] + 7 * (CENTERS[4] - CENTERS[0]) / 4
        self.assertGreater(abs(uniform - CENTERS[7]), 8)
        self.assertGreater(pitch(7), pitch(0))

    def test_two_glyphs_give_a_plain_uniform_grid(self):
        position, pitch = slot_positions([0, 2], [10.0, 50.0])
        self.assertEqual(30.0, position(1))
        self.assertEqual(20.0, pitch(1))

    def test_change_of_distance_is_limited(self):
        position, pitch = slot_positions([0, 1, 2, 3], [0.0, 10.0, 30.0, 70.0])
        mean = 70 / 3
        self.assertLessEqual(pitch(3) - pitch(2), .045 * mean + 1e-6)


class CellFrameTests(unittest.TestCase):
    def centres(self, strip):
        cells = dark_register_cells(strip, 8)
        self.assertEqual(8, len(cells))
        return scale_digit_boxes(cells, strip.size)

    def test_frames_sit_on_unequally_spaced_rollers(self):
        boxes = self.centres(unequal_strip())
        for (left, top, right, bottom), center in zip(boxes, CENTERS):
            self.assertLess(abs((left + right) / 2 - center), 5, (left, right, center))

    def test_turning_last_roller_is_placed_by_the_grid_not_a_uniform_pitch(self):
        boxes = self.centres(unequal_strip(blank=(7,)))
        left, _, right, _ = boxes[7]
        self.assertLess(abs((left + right) / 2 - CENTERS[7]), 6)

    def test_frames_cover_the_glyph_and_leave_out_the_window_edge(self):
        strip = unequal_strip()
        for left, top, right, bottom in self.centres(strip):
            self.assertGreaterEqual(top, 5)       # bright edge rows 0..4 stay outside
            self.assertLessEqual(bottom, 91)
            self.assertLessEqual(top, 32)         # digit strokes span about 33..67
            self.assertGreaterEqual(bottom, 68)

    def test_frames_that_sit_too_high_are_moved_down_onto_the_digits(self):
        strip = unequal_strip()
        high = [(round(center - 17), 6, round(center + 17), 52) for center in CENTERS]
        levelled = level_on_glyphs(strip, high)
        for (_, top, _, bottom), (_, old_top, _, old_bottom) in zip(levelled, high):
            self.assertGreater(bottom, old_bottom + 10)
            self.assertGreaterEqual(bottom, 68)
            self.assertGreaterEqual(top, 5)

    def test_too_few_measured_rollers_leave_the_frames_alone(self):
        blank = Image.new("RGB", (422, 96), (38, 30, 34))
        frames = [(round(center - 17), 20, round(center + 17), 70) for center in CENTERS]
        self.assertEqual(frames, level_on_glyphs(blank, frames))


class RegisterWindowTests(unittest.TestCase):
    def frame(self, **kwargs):
        frame = Image.new("RGB", (800, 600), (210, 215, 220))
        # A low window: the bright meter face begins right above and below the digits.
        frame.paste(unequal_strip(edge=False, **kwargs).crop((0, 22, 422, 78)), (180, 222))
        return frame

    def test_window_leaves_room_beside_the_last_roller(self):
        left, top, right, bottom = find_glyph_register(self.frame(), 8)
        last = 180 + CENTERS[7]
        self.assertGreaterEqual(right, last + .5 * 52.5)
        self.assertLessEqual(left, 180 + CENTERS[0] - .5 * 47)

    def test_window_is_found_while_two_decimal_rollers_turn(self):
        found = find_glyph_register(self.frame(blank=(6, 7)), 8)
        self.assertIsNotNone(found)
        self.assertGreaterEqual(found[2], 180 + CENTERS[7] + 15)


class PartialSetupTests(unittest.TestCase):
    def setUp(self):
        self.job = Calibration(5, 0, rank_candidates=True, simplified=True)
        self.layout = Layout((0, 0, 400, 80), -11, 250, method="register_window")

    def test_stuck_last_roller_gives_a_provisional_setup_after_four_images(self):
        rows = ["1050105", "1050105"]
        rows = [row[:-1] + "?" for row in rows]
        for image in range(MIN_IMAGES + 1):
            self.assertFalse(self.job.stationary_crop_ready())
            self.assertTrue(self.job.partial_hit(self.layout, rows, 100 + 60 * image, 6000))
        self.assertTrue(self.job.stationary_crop_ready())
        self.assertEqual(self.layout, self.job.candidate)

    def test_partial_hits_join_full_confirmations(self):
        self.job.candidate, self.job.confirmations = self.layout, 2
        self.job.counter = {"reading_litres": 10501050, "timestamp": 100}
        self.assertTrue(self.job.partial_hit(self.layout, ["105010?", "105010?"], 160, 6000))
        self.assertFalse(self.job.stationary_crop_ready())
        self.assertTrue(self.job.partial_hit(self.layout, ["105011?", "105011?"], 220, 6000))
        self.assertTrue(self.job.stationary_crop_ready())

    def test_falling_or_jumping_partial_reading_does_not_count(self):
        self.job.candidate = self.layout
        self.job.counter = {"reading_litres": 10501050, "timestamp": 100}
        self.assertFalse(self.job.partial_hit(self.layout, ["105009?", "105009?"], 160, 6000))
        self.assertFalse(self.job.partial_hit(self.layout, ["105200?", "105200?"], 160, 6000))
        self.assertEqual(0, self.job.partial_hits)

    def test_other_register_does_not_count_for_the_candidate(self):
        self.job.candidate = self.layout
        other = Layout((0, 300, 400, 380), 0, 250)
        self.assertFalse(self.job.partial_hit(other, ["105010?", "105010?"], 160, 6000))

    def test_repair_never_ends_provisionally(self):
        self.job.automatic = True
        for image in range(MIN_IMAGES + 2):
            self.job.partial_hit(self.layout, ["105010?", "105010?"], 100 + 60 * image, 6000)
        self.assertFalse(self.job.stationary_crop_ready())


class KeptFrameTests(unittest.TestCase):
    def test_digit_from_a_nudged_frame_counts_but_the_frame_stays(self):
        boxes = tuple((100 * index + 10, 300, 100 * index + 90, 700) for index in range(7))
        layout = Layout((0, 0, 700, 100), 0, 500, boxes)
        job = Calibration(5, 0, simplified=True)
        rules = {"integer_digits": 5, "fraction_digits": 2}

        def read_slot(trial, index, profile):
            return "6" if trial.digit_boxes[index] != boxes[index] else "?"

        for keep, moved in (((6,), False), ((), True)):
            with self.subTest(keep=keep):
                result = job.retry_digit_slots(layout, ["12345.2?", "12345.2?"], rules, [6], read_slot,
                                               lambda: False, None, 100, keep_frames=keep)
                self.assertIsNotNone(result)
                adjusted, readings = result
                self.assertEqual(["12345.26", "12345.26"], readings)
                self.assertEqual(moved, adjusted.digit_boxes != boxes)


class ImpossibleDigitTests(unittest.TestCase):
    def test_single_impossible_leading_digit_is_restored(self):
        scores = [{}] * 5
        self.assertEqual("10501", glyph_match.anchored_whole("40501", scores, 10501, 10504))
        self.assertEqual("10495", glyph_match.anchored_whole("18495", scores, 10495, 10496))
        self.assertEqual("10497", glyph_match.anchored_whole("404?7", scores, 10497, 10498))

    def test_readings_far_off_stay_as_read(self):
        scores = [{}] * 5
        for whole in ("40999", "40302", "44501"):
            with self.subTest(whole=whole):
                self.assertEqual(whole, glyph_match.anchored_whole(whole, scores, 10501, 10504))

    def test_digit_that_may_change_is_never_touched(self):
        self.assertEqual("10503", glyph_match.anchored_whole("10503", [{}] * 5, 10501, 10504))
        self.assertEqual("10509", glyph_match.without_impossible_digit("10509", 10501, 10504))


class RepairScheduleTests(unittest.TestCase):
    def failures(self, state, start, count, step=600):
        results = []
        for index in range(count):
            results.append(observe_geometry_failures(state, "k", start + index * step, "ocr_unclear",
                                                     reading_problem=True))
        return results

    def test_repair_starts_after_forty_minutes_and_repeats(self):
        state = {}
        first = self.failures(state, 1000, 6)
        self.assertEqual(1, sum(first))
        self.assertTrue(first[GEOMETRY_FAILURE_DURATION // 600])
        self.assertGreaterEqual(GEOMETRY_REPAIR_FAILURES, 3)
        later = self.failures(state, 1000 + 6 * 600, 14)
        self.assertEqual(1, sum(later))
        again = 1000 + GEOMETRY_FAILURE_DURATION + GEOMETRY_REPAIR_REPEAT
        self.assertTrue(later[(again - 1000 - 6 * 600) // 600])

    def test_good_reading_resets_the_streak(self):
        state = {}
        self.failures(state, 1000, 3)
        self.assertFalse(observe_geometry_failures(state, "k", 5000, "ocr_only", reading_problem=False))
        self.assertEqual([False] * 4, self.failures(state, 6000, 4))


class ParallelDigitTests(unittest.TestCase):
    def test_results_keep_their_order_and_skipped_digits(self):
        tasks = [lambda: "1", "?", lambda: "3", lambda: "4"]
        self.assertEqual(["1", "?", "3", "4"], run.read_digits_parallel(tasks))

    def test_supplied_reader_is_called_in_order_unless_marked_safe(self):
        image = Image.new("RGB", (75, 30), "white")
        boxes = [(x, 2, x + 15, 28) for x in range(0, 75, 15)]
        reads = iter("12345")
        self.assertEqual("12345", run.read_visible_digits(
            image, 75, boxes, [], False, "auto", profile=run.OCR_PROFILES[0], whole_digits=5,
            fraction_digits=0, prefer_boxes=True, glyphs=False,
            recognize=lambda *_args, **_kwargs: next(reads)))


if __name__ == "__main__":
    unittest.main()
