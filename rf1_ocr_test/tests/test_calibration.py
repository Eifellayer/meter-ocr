"""Exercise the confirmation requirements independently of timing and the camera."""

import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import calibration
from calibration import Calibration, Layout, MAX_ATTEMPTS, guided_layouts, layouts, neighbour_layout, search_region, unrotate_box
from layout import find_dark_register, find_neighbour_digit_rows, find_raw_digit_row, find_raw_digit_rows, scale_digit_boxes, turn_crop
from meter_learning import widen_digit_boxes

LAYOUT = Layout((0, 0, 80, 20), -3, 80)
OTHER_LAYOUT = Layout((10, 0, 90, 20), 3, 80)
RULES = {"decimals": 0, "fraction_digits": 0, "integer_digits": 5, "max_flow_lph": 6000}


def frame(number):
    return Image.new("RGB", (100, 30), (0, 20, number))


def irregular_meter(text):
    image = Image.new("RGB", (600, 360), "#676767")
    draw = ImageDraw.Draw(image)
    draw.rectangle((152, 135, 415, 215), fill="white")
    font = ImageFont.truetype("DejaVuSansMono.ttf", 58)
    for char, x in zip(text, (180, 222, 264, 339, 385)):
        draw.text((x, 176), char, font=font, fill="black", anchor="mm")
    return image


class NeighbourGeometryTests(TestCase):
    def test_dark_register_is_located_with_gaps_and_a_separate_small_label(self):
        photo = Image.new("RGB", (640, 480), "#9c9c9c")
        draw = ImageDraw.Draw(photo)
        draw.rectangle((95, 80, 540, 140), fill="#161616")
        font = ImageFont.truetype("DejaVuSansMono.ttf", 35)
        draw.text((125, 90), "12  56 8", fill="#dbdbdb", font=font)
        draw.text((200, 225), "968712", fill="black", font=font)
        box = find_dark_register(photo, 8)
        self.assertIsNotNone(box)
        self.assertLess(box[1], 100)
        self.assertGreater(box[2] - box[0], 400)
        first = next(layouts(photo, None, {**RULES, "fraction_digits": 3}, 0))
        self.assertEqual("register_window", first.method)

    def test_large_partial_row_is_tried_before_a_small_complete_row(self):
        small = ((2, 2, 32, 12), 30, [])
        large = ((10, 13, 90, 29), 80, [(i, 0, i + 16, 16) for i in range(0, 80, 16)])
        with patch.object(calibration, "find_raw_digit_rows", return_value=[(small, 30)]), \
             patch.object(calibration, "find_neighbour_digit_rows", return_value=[large]):
            first = next(layouts(frame(1), None, RULES, 0))
        self.assertEqual(large[0], first.box)

    def test_larger_register_ranks_above_a_serial_with_the_same_length(self):
        photo = Image.new("RGB", (640, 480), "#626262")
        draw = ImageDraw.Draw(photo)
        for y, size, value in ((90, 34, "96871"), (320, 75, "12345")):
            font = ImageFont.truetype("DejaVuSansMono.ttf", size)
            l, t, r, b = draw.textbbox((320, y), value, font=font, anchor="mm")
            margin = max(5, round((b - t) * .24))
            draw.rectangle((l - margin, t - margin, r + margin, b + margin), fill="white")
            draw.text((320, y), value, font=font, fill="black", anchor="mm")
        rows = find_raw_digit_rows(photo, 5, 0)
        self.assertGreaterEqual(len(rows), 2)
        self.assertGreater(rows[0][0][0][1], 200)
        self.assertLess(rows[1][0][0][1], 150)

    def test_widened_digit_boxes_are_a_separate_safe_trial(self):
        boxes = [(200, 0, 400, 1000), (400, 0, 600, 1000), (600, 0, 800, 1000)]
        widened = widen_digit_boxes(boxes, (50, 20), pixels=2)
        self.assertEqual(3, len(widened))
        self.assertTrue(all(0 <= left < right <= 1000 for left, _, right, _ in widened))
        self.assertTrue(all((widened[i][0] + widened[i][2]) <
                            (widened[i + 1][0] + widened[i + 1][2]) for i in range(2)))

    def test_one_visible_digit_can_seed_neighbours_inside_a_visible_window(self):
        photo = irregular_meter("  3  ")
        self.assertIsNone(find_raw_digit_row(photo, 5, 0))
        self.assertEqual([], find_neighbour_digit_rows(Image.new("RGB", photo.size, "gray"), 5, 0))
        found = find_neighbour_digit_rows(photo, 5, 0)
        self.assertTrue(found)
        crop, _, boxes = found[0]
        left, _, right, _ = boxes[2]
        self.assertLess(crop[0] + left, 264)
        self.assertGreater(crop[0] + right, 264)
        self.assertEqual(5, len(boxes))
        self.assertLessEqual(len(found), 2)

    def test_ocr_reads_a_meter_that_the_strict_row_search_rejects(self):
        from checks import OCR_PROFILES
        from run import read_visible_digits, select_register

        photo = irregular_meter("12345")
        self.assertIsNone(find_raw_digit_row(photo, 5, 0))
        for whole, fraction, expected in ((5, 0, "12345"), (3, 2, "123.45")):
            with self.subTest(whole=whole, fraction=fraction):
                rules = {**RULES, "integer_digits": whole, "fraction_digits": fraction}
                selected = next(item for item in layouts(photo, None, rules, 0) if item.method == "neighbours")
                register = select_register(photo, None, selected.box, selected.width, selected.rotation,
                                           whole, fraction, digit_boxes=selected.digit_boxes)
                reading = read_visible_digits(*register[:4], False, "auto", profile=OCR_PROFILES[0],
                                              whole_digits=whole, fraction_digits=fraction, prefer_boxes=True)
                self.assertEqual(expected, reading)

    def test_guided_search_ignores_a_serial_number_outside_the_marked_area(self):
        photo = irregular_meter("12345")
        draw = ImageDraw.Draw(photo)
        draw.rectangle((44, 16, 553, 99), fill="white")
        draw.text((297, 60), "9674830157", font=ImageFont.truetype("DejaVuSansMono.ttf", 52),
                  fill="black", anchor="mm")
        region = search_region("205,315,730,650")
        result = list(guided_layouts(photo, None, RULES, 0, None, region))
        self.assertTrue(result)
        self.assertTrue(all(item.box[1] >= 113 and item.box[3] <= 234 for item in result))
        with self.assertRaises(ValueError):
            search_region("205,650,730,315")

    def test_serial_number_is_not_split_into_shorter_candidate_rows(self):
        photo = Image.new("RGB", (600, 240), "#676767")
        draw = ImageDraw.Draw(photo)
        draw.rectangle((55, 70, 545, 167), fill="white")
        draw.text((300, 119), "9674830157", font=ImageFont.truetype("DejaVuSansMono.ttf", 62),
                  fill="black", anchor="mm")
        self.assertIsNone(find_raw_digit_row(photo, 5, 0))
        self.assertEqual([], find_neighbour_digit_rows(photo, 5, 0))

    def test_neighbour_boxes_fit_a_rotated_crop(self):
        photo = turn_crop(irregular_meter("12345"), 3)
        cropped = turn_crop(photo, -3, expand=False)
        candidate = find_neighbour_digit_rows(cropped, 5, 0)[0]
        selected = neighbour_layout(photo, -3, candidate, 5, 0)
        self.assertIsNotNone(selected)
        image = turn_crop(photo.crop(selected.box), -3)
        boxes = scale_digit_boxes(selected.digit_boxes, image.size)
        self.assertEqual(5, len(boxes))
        self.assertTrue(all(0 <= l < r <= image.width and 0 <= t < b <= image.height
                            for l, t, r, b in boxes))


class CalibrationTests(TestCase):
    def setUp(self):
        self.job = Calibration(5, 0)
        self.candidates = self.enterContext(patch.object(calibration, "layouts", return_value=[LAYOUT]))

    def examine(self, number, time, reading="12345", *, reference=True, fallback=False, stop=lambda: False):
        sample = {"reference_required": reference, "reference_is_fallback": fallback,
                  "reference_time": time, "raw_value": reading, "actual_value": reading}
        return self.job.examine(frame(number), None, sample, time, RULES,
                                lambda *_: reading, stop)

    def test_three_distinct_photos_confirm_the_same_layout(self):
        self.assertIsNone(self.examine(1, 100))
        self.assertIsNone(self.examine(1, 101))
        self.assertIsNone(self.examine(2, 102))
        self.assertEqual(LAYOUT, self.examine(3, 103))
        self.assertEqual(3, self.job.status(104)["tested"])
        self.assertEqual(3, self.job.confirmations)

    def test_changing_layout_cannot_reuse_confirmations(self):
        self.examine(1, 100)
        self.examine(2, 101)
        self.candidates.return_value = [OTHER_LAYOUT]
        self.assertIsNone(self.examine(3, 102))
        self.assertEqual(1, self.job.confirmations)

    def test_fallback_is_not_live_confirmation(self):
        self.examine(1, 100, fallback=True)
        self.assertEqual(0, self.job.confirmations)

    def test_partial_row_retries_missing_slot_on_same_image_without_extra_confirmation(self):
        reference = {"reference_time": 100, "actual_value": "12345", "raw_value": "12345"}
        calls = []
        reported_positions = []

        def read(trial, profile):
            calls.append((trial, profile))
            return "12?45" if not trial.digit_boxes else "12345"

        self.assertIsNone(self.job.examine(frame(1), None, reference, 100, RULES, read,
                                           lambda: False, refine_read=read,
                                           on_refine=lambda _, __, positions: reported_positions.append(positions)))
        self.assertEqual(1, self.job.confirmations)
        self.assertEqual(1, len(self.job.seen))
        self.assertTrue(self.job.candidate.digit_boxes)
        self.assertGreater(self.job.attempts, 1)
        self.assertEqual([3], reported_positions[0])

    def test_shifted_complete_row_is_not_confirmed(self):
        reasons = []
        reference = {"reference_time": 100, "actual_value": "12345", "raw_value": "12345"}
        self.job.examine(frame(1), None, reference, 100, RULES, lambda *_: "23456", lambda: False,
                         on_decision=reasons.append)
        self.assertEqual(["position_error"], reasons)
        self.assertEqual(0, self.job.confirmations)

    def test_thirty_attempts_include_coarse_and_fine_work(self):
        self.candidates.return_value = [Layout((x, 0, x + 80, 20), 0, 80) for x in range(4)]
        sample = {"reference_time": 100, "actual_value": "12345", "raw_value": "12345"}
        self.job.examine(frame(1), None, sample, 100, RULES, lambda *_: "12?45",
                         lambda: False, refine_read=lambda *_: "12?45")
        self.assertEqual(10, self.job.attempts)
        self.assertEqual(1, len(self.job.seen))
        self.assertEqual(0, self.job.confirmations)

    def test_coarse_search_compares_small_label_and_wide_register_before_refining(self):
        label = Layout((8, 13, 38, 28), 0, 30)
        register = Layout((4, 0, 94, 17), 0, 90, method="register_window")
        self.candidates.return_value = [label, register]
        events = []

        def coarse_read(layout, profile):
            events.append(("coarse", layout.box))
            return "98765" if layout == label else "12?45"

        def fine_read(layout, profile):
            events.append(("fine", layout.box))
            return "12345"

        self.job.examine(frame(1), None, {"reference_required": False}, 100, RULES, coarse_read,
                         lambda: False, refine_read=fine_read)
        self.assertEqual([("coarse", label.box)] * 2 + [("coarse", register.box)] * 2, events[:4])
        self.assertTrue(events[4:])
        self.assertTrue(all(item == ("fine", register.box) for item in events[4:]))
        self.assertEqual(1, self.job.confirmations)

    def test_small_label_outside_detected_register_is_never_read(self):
        label = Layout((57, 19, 90, 29), 0, 33)
        register = Layout((4, 0, 94, 17), 0, 90, method="register_window")
        self.candidates.return_value = [label, register]
        seen = []

        def read(layout, profile):
            seen.append(layout)
            return "12345"

        self.job.examine(frame(1), None, {"reference_required": False}, 100, RULES, read, lambda: False)
        self.assertEqual([register, register], seen)

    def test_sweeps_in_one_degree_steps_then_refines_at_the_best_angle(self):
        base = Layout((0, 0, 90, 25), 0, 55, method="register_window")
        self.candidates.return_value = [base]
        angles, fine = [], []

        def rotate(layout, profile):
            return "12345.???" if layout.rotation == 2 else "12???.???"

        def refine(layout, profile):
            fine.append(layout.rotation)
            return "12345.678"

        self.job.examine(frame(1), None, {"reference_required": False}, 100,
                         {**RULES, "fraction_digits": 3}, rotate, lambda: False, refine_read=refine,
                         angle_read=rotate, on_angle=lambda _, angle: angles.append(angle))
        self.assertEqual([-1, 1, -2, 2, -3, 3], angles)
        self.assertTrue(fine)
        self.assertEqual({2}, set(fine))
        self.assertEqual(1, self.job.confirmations)

    def test_four_open_positions_never_start_fine_search(self):
        from unittest.mock import Mock

        fine = Mock(side_effect=AssertionError("Too few digits recognized"))
        self.job.examine(frame(1), None, {"reference_required": False}, 100,
                         {**RULES, "fraction_digits": 3}, lambda *_: "1234?.???",
                         lambda: False, refine_read=fine, angle_read=lambda *_: "1234?.???")
        fine.assert_not_called()
        self.assertEqual(0, self.job.confirmations)

    def test_preview_returns_to_original_angle_when_it_wins_the_sweep(self):
        self.candidates.return_value = [Layout((0, 0, 90, 25), 0, 55, method="register_window")]
        shown = []
        attempted = []
        self.job.examine(frame(1), None, {"reference_required": False}, 100,
                         {**RULES, "fraction_digits": 3}, lambda *_: "12345.???", lambda: False,
                         refine_read=lambda *_: "12345.???", angle_read=lambda *_: "12???.???",
                         on_angle=lambda _, angle: attempted.append(angle),
                         on_selected=lambda layout, _: shown.append(layout.rotation))
        self.assertIn(3, attempted)
        self.assertEqual([0, 0], shown)

    def test_confirmed_whole_digits_skip_fine_search_despite_uncertain_decimals(self):
        from unittest.mock import Mock

        refine = Mock(side_effect=AssertionError("Unneeded refinement"))
        sample = {"reference_time": 100, "actual_value": "12345.678", "raw_value": "12345.678"}
        readings = iter(("12345.???", "12345.6?8"))
        self.job.examine(frame(1), None, sample, 100, {**RULES, "fraction_digits": 3},
                         lambda *_: next(readings), lambda: False, refine_read=refine)
        self.assertEqual(1, self.job.confirmations)
        refine.assert_not_called()

    def test_partial_serial_is_skipped_before_fine_search(self):
        from unittest.mock import Mock

        refine = Mock(side_effect=AssertionError("Unneeded refinement"))
        sample = {"reference_time": 100, "actual_value": "12345", "raw_value": "12345"}
        self.job.examine(frame(1), None, sample, 100, RULES, lambda *_: "8?7?6", lambda: False,
                         refine_read=refine)
        self.assertEqual([LAYOUT.box], self.job.rejected_regions)
        refine.assert_not_called()

    def test_without_reference_requires_plausible_forward_movement(self):
        self.examine(1, 100, reference=False)
        self.examine(2, 101, reference=False)
        self.assertIsNone(self.examine(3, 102, reference=False))
        self.assertEqual(LAYOUT, self.examine(4, 103, "12346", reference=False))

    def test_learning_tries_the_configured_crop_when_detection_finds_nothing(self):
        photo = frame(1)
        rules = {**RULES, "crop_mode": "auto", "crop": "0,0,80,20", "rotation": 0, "width": 80}
        with patch.object(calibration, "find_raw_digit_rows", return_value=[]):
            self.assertIn(Layout((0, 0, 80, 20), 0, 80), list(layouts(photo, None, rules, 0)))

    def test_reports_why_a_detected_crop_was_rejected(self):
        reasons = []
        reference = {"reference_time": 100, "actual_value": "12345", "raw_value": "12345"}
        self.job.examine(frame(1), None, reference, 100, RULES,
                         lambda *_: "12346", lambda: False, on_decision=reasons.append)
        self.assertEqual(["reference_mismatch"], reasons)
        self.candidates.return_value = []
        self.job.examine(frame(2), None, reference, 101, RULES,
                         lambda *_: "12345", lambda: False, on_decision=reasons.append)
        self.assertEqual("accepted", reasons[-1])
        self.assertEqual(2, self.job.attempts)
        self.assertEqual(1, self.job.confirmations)

    def test_deadline_and_stop(self):
        self.assertFalse(self.job.expired(900))
        self.assertTrue(self.job.image_wait_expired(900))
        self.job.searching_since = 100
        self.assertFalse(self.job.expired(999.9))
        self.assertTrue(self.job.expired(1000))
        self.job.searching_since = None
        self.assertIsNone(self.examine(1, 100, stop=lambda: True))
        self.assertEqual(0, self.job.confirmations)

    def test_crop_attempt_budget_and_best_proposal_survive_failed_confirmation(self):
        self.examine(1, 100)
        self.assertEqual(LAYOUT, self.job.best)
        self.candidates.return_value = []
        self.examine(2, 101)
        self.assertIsNone(self.job.candidate)
        self.assertEqual(LAYOUT, self.job.best)

        self.candidates.return_value = [LAYOUT, OTHER_LAYOUT]
        self.job.attempts = MAX_ATTEMPTS - 1
        self.examine(3, 102, fallback=True)
        self.assertEqual(MAX_ATTEMPTS, self.job.attempts)
        self.assertEqual(900, self.job.status(0)["duration"])

    def test_normal_ocr_must_accept_one_more_new_image_before_saving(self):
        self.examine(1, 100)
        self.examine(2, 101)
        self.assertEqual(LAYOUT, self.examine(3, 102))
        self.job.verification_pending = True
        rules = {**RULES, "attempts": 3}
        sample = {"reference_time": 103, "raw_value": "12345", "actual_value": "12345"}
        self.assertIsNone(self.job.verify(frame(3), sample, 103, rules, lambda *_: "12345", lambda: False))
        self.assertTrue(self.job.verification_pending)
        self.assertIsNone(self.job.verify(frame(4), sample, 104, rules, lambda *_: "?????", lambda: False))
        self.assertFalse(self.job.verification_pending)
        self.assertEqual(0, self.job.confirmations)

    def test_boxes_transform_back_to_the_original_image(self):
        self.assertEqual((30, 10, 50, 20), unrotate_box((60, 10, 70, 30), (100, 60), 90))


class CalibrationImageTests(TestCase):
    def test_real_ocr_learns_the_same_crop_and_angle_on_three_synthetic_photos(self):
        from PIL import ImageDraw, ImageFont
        from layout import turn_crop
        from run import read_visible_digits, select_register

        job = Calibration(50, 0)
        font = ImageFont.truetype("DejaVuSansMono.ttf", 72)
        for index in range(3):
            im = Image.new("RGB", (640, 480), (80 + index,) * 3)
            draw = ImageDraw.Draw(im)
            draw.rectangle((160, 180, 480, 285), fill="white")
            draw.text((320, 235), "12345", font=font, fill="black", anchor="mm")
            photo = turn_crop(im, 3)
            timestamp = 100 + index
            sample = {"reference_time": timestamp, "actual_value": "12345", "raw_value": "12345"}

            def read(layout, profile):
                register = select_register(photo, None, layout.box, layout.width, layout.rotation, 5, 0)
                return read_visible_digits(*register[:4], False, "auto", profile=profile, fraction_digits=0)

            selected = job.examine(photo, None, sample, timestamp, {**RULES, "crop_mode": "auto"},
                                   read, lambda: False)
            if index < 2:
                self.assertIsNone(selected)
        self.assertIsNotNone(selected)
        self.assertEqual(0, selected.rotation)
        self.assertEqual(3, job.confirmations)
