"""Exercise the confirmation requirements independently of timing and the camera."""

import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import calibration
from calibration import Calibration, Layout, MAX_ATTEMPTS, guided_layouts, layouts, neighbour_layout, search_region, unrotate_box
from layout import dark_register_cells, find_dark_register, find_neighbour_digit_rows, find_raw_digit_row, find_raw_digit_rows, scale_digit_boxes, turn_crop
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
    def test_dark_window_fit_follows_visible_digits_instead_of_unequal_side_margins(self):
        register = Image.new("RGB", (490, 87), "#09151b")
        draw = ImageDraw.Draw(register)
        font = ImageFont.truetype("DejaVuSansMono.ttf", 47)
        centers = [32, 86, 140, 194, 248, 302, 356, 410]
        for x, digit in zip(centers, "1246587"):
            draw.text((x, 45), digit, fill="#83cfdf", font=font, anchor="mm")
        boxes = scale_digit_boxes(dark_register_cells(register, 8), register.size)
        self.assertEqual(8, len(boxes))
        self.assertTrue(all(abs((box[0] + box[2]) / 2 - x) <= 4 for box, x in zip(boxes, centers)))

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

    def test_first_image_can_turn_a_sideways_or_upside_down_meter_upright(self):
        from checks import read_register

        def read(layout, profile):
            register = turn_crop(photo.crop(layout.box), layout.rotation)
            return read_register(register, False, force_polarity=True, profile=profile)

        sample = {"reference_time": 100, "actual_value": "12345", "raw_value": "12345"}
        for rotation in (90, -90, 180):
            with self.subTest(rotation=rotation):
                turned = turn_crop(irregular_meter("12345"), -rotation)
                photo = Image.new("RGB", (680, 640), "#676767")
                photo.paste(turned, (photo.width - turned.width, 0))
                job = Calibration(5, 0, rank_candidates=True)
                self.assertIsNone(job.examine(photo, None, sample, 100, RULES, read, lambda: False))
                self.assertEqual(1, job.confirmations)
                self.assertEqual(rotation, job.candidate.rotation)

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
        self.rotated_candidates = self.enterContext(patch.object(calibration, "quarter_turn_layouts", return_value=[]))

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

    def test_known_good_crop_is_tried_before_detection_and_still_needs_fresh_hits(self):
        self.job = Calibration(5, 0, rank_candidates=True, known_good_layout=OTHER_LAYOUT)
        sample = {"reference_time": 100, "raw_value": "12345", "actual_value": "12345"}
        attempted = []

        def read(layout, profile):
            attempted.append(layout)
            return "12345"

        self.assertIsNone(self.job.examine(frame(1), None, sample, 101, RULES, read, lambda: False))
        self.assertEqual({OTHER_LAYOUT}, set(attempted))
        self.assertEqual(1, self.job.confirmations)
        self.candidates.assert_not_called()
        self.assertTrue(self.job.status(101)["known_good_available"])

    def test_known_good_crop_is_tried_first_even_outside_a_chosen_region(self):
        # A mistaken tap on a region proposal must not replace a working, confirmed frame.
        self.job = Calibration(5, 0, rank_candidates=True, known_good_layout=OTHER_LAYOUT,
                               region=(0, 0, 50, 50))
        sample = {"reference_time": 100, "raw_value": "12345", "actual_value": "12345"}
        attempted = []

        def read(layout, profile):
            attempted.append(layout)
            return "12345"

        with patch.object(calibration, "guided_layouts", return_value=[LAYOUT]) as guided:
            self.assertIsNone(self.job.examine(frame(1), None, sample, 101, RULES, read, lambda: False))
        self.assertEqual({OTHER_LAYOUT}, set(attempted))
        self.assertEqual(1, self.job.confirmations)
        guided.assert_not_called()

    def test_search_resumes_when_the_known_good_crop_no_longer_reads(self):
        self.job = Calibration(5, 0, rank_candidates=True, known_good_layout=OTHER_LAYOUT)
        sample = {"reference_time": 100, "raw_value": "12345", "actual_value": "12345"}
        attempted = []

        def read(layout, profile):
            attempted.append(layout)
            return "?????" if layout == OTHER_LAYOUT else "12345"

        self.assertIsNone(self.job.examine(frame(1), None, sample, 101, RULES, read, lambda: False))
        self.assertEqual([OTHER_LAYOUT, OTHER_LAYOUT, LAYOUT], attempted[:3])
        self.candidates.assert_called_once()
        self.assertEqual(LAYOUT, self.job.candidate)

    def test_initial_calibration_verifies_two_digits_when_the_third_is_open(self):
        self.job.simplified = True
        rules = {**RULES, "decimals": 3, "fraction_digits": 3, "attempts": 3}
        reference = calibration.two_decimal_reading("12345.239")
        sample = {"reference_time": 100, "raw_value": reference, "actual_value": reference}
        read = lambda *_: "12345.23?"
        for index in range(1, 4):
            layout = self.job.examine(frame(index), None, sample, 100 + index, rules, read, lambda: False)
        self.assertEqual(LAYOUT, layout)
        self.assertEqual(LAYOUT, self.job.verify(frame(4), sample, 104, rules, read, lambda: False))
        self.assertTrue(self.job.status(105)["simplified"])

        strict = Calibration(5, 0)
        strict.examine(frame(1), None, {**sample, "raw_value": "12345.239", "actual_value": "12345.239"},
                       101, rules, read, lambda: False)
        self.assertEqual(0, strict.confirmations)

    def test_changing_layout_cannot_reuse_confirmations(self):
        self.examine(1, 100)
        self.candidates.return_value = [OTHER_LAYOUT]
        self.assertIsNone(self.examine(2, 101))
        self.assertEqual(1, self.job.confirmations)

    def test_two_hits_keep_the_same_crop_through_an_unreadable_image(self):
        self.examine(1, 100)
        self.examine(2, 101)
        self.candidates.return_value = [OTHER_LAYOUT]
        attempted = []

        def read(layout, profile):
            attempted.append(layout)
            return "12?45" if layout == LAYOUT else "12345"

        sample = {"reference_time": 102, "raw_value": "12345", "actual_value": "12345"}
        self.assertIsNone(self.job.examine(frame(3), None, sample, 102, RULES, read, lambda: False))
        self.assertEqual([LAYOUT, LAYOUT], attempted)
        self.assertEqual(2, self.job.confirmations)
        self.assertEqual(LAYOUT, self.examine(4, 103))

    def test_initial_image_hints_detect_dark_low_contrast_and_soft_crops(self):
        dark = Image.new("RGB", (100, 30), (20, 20, 20))
        self.assertEqual(["dark", "low_contrast"], calibration.image_quality_hints(dark, LAYOUT))
        bright = Image.new("RGB", (100, 30), (230, 230, 230))
        self.assertEqual(["bright", "low_contrast"], calibration.image_quality_hints(bright, LAYOUT))
        soft = Image.linear_gradient("L").rotate(90).resize((100, 30))
        self.assertEqual(["soft"], calibration.image_quality_hints(soft, LAYOUT))

    def test_intensive_verification_has_its_own_deadline_after_the_third_hit(self):
        job = Calibration(20, 0, intensive=True, duration=240, spent=239, attempts=20, attempt_limit=20)
        self.assertEqual(1, job.remaining(300))
        job.begin_verification(300)
        self.assertTrue(job.verification_pending)
        self.assertEqual(240, job.remaining(300))
        self.assertFalse(job.search_exhausted())
        job.spent = 245
        job.begin_verification(310)
        self.assertFalse(job.expired(539))
        self.assertTrue(job.expired(540))

    def test_fine_evidence_keeps_the_best_image_after_a_poor_verification_frame(self):
        self.job.retain_fine_evidence(88, False, {"frame": 1}, {"frame": b"partial"})
        self.job.retain_fine_evidence(100, True, {"frame": 2}, {"frame": b"best"})
        self.job.retain_fine_evidence(0, False, {"frame": 3}, {"frame": b"unreadable"})
        self.job.retain_fine_evidence(100, False, {"frame": 4}, {"frame": b"single"})
        _, preview, images = self.job.fine_evidence
        self.assertEqual({"frame": 2, "best_fine_score": 100}, preview)
        self.assertEqual(b"best", images["frame"])

    def test_last_digit_fine_check_shifts_only_last_box_and_uses_fresh_images(self):
        boxes = tuple((index * 120, 100, index * 120 + 100, 900) for index in range(8))
        initial = Layout((0, 0, 80, 20), -1, 50, boxes)
        job = Calibration(7, 0, intensive=True)
        attempts = []

        def read(trial, _):
            self.assertEqual(initial.box, trial.box)
            self.assertEqual(initial.rotation, trial.rotation)
            self.assertEqual(initial.digit_boxes[:-1], trial.digit_boxes[:-1])
            attempts.append(trial)
            return "4" if trial != initial else "?"

        def check(number, stamp, layout):
            return job.check_last_digit(frame(number), {"reference_required": False}, stamp,
                                        layout, 5, read, lambda: False, lambda: None, lambda _: None)

        self.assertIsNone(check(1, 101, initial))
        chosen = job.candidate
        self.assertNotEqual(initial, chosen)
        self.assertEqual(1, job.confirmations)
        self.assertIsNone(check(1, 102, chosen))
        self.assertEqual(1, job.confirmations)
        self.assertIsNone(check(2, 103, chosen))
        self.assertEqual(chosen, check(3, 104, chosen))
        job.begin_verification(104)
        attempts.clear()
        self.assertEqual(chosen, check(4, 105, chosen))
        self.assertEqual([chosen, chosen], attempts)
        self.assertIsNone(job.reference_reading)

    def test_followup_confirms_the_found_crop_after_reaching_search_limit(self):
        job = Calibration(7, 0, intensive=True, followup=True, previous_layout=LAYOUT, attempt_limit=20)
        job.attempts = 19
        rules = {**RULES, "decimals": 3, "fraction_digits": 3, "attempts": 3}
        sample = {"reference_time": 100, "raw_value": "12345.239", "actual_value": "12345.239"}
        read = lambda *_: "12345.239"
        stop = lambda: False

        self.assertIsNone(job.examine(frame(1), None, sample, 101, rules, read, stop))
        self.assertEqual(20, job.attempts)
        self.assertFalse(job.search_exhausted())
        self.assertIsNone(job.examine(frame(2), None, sample, 102, rules, lambda *_: "12345.23?", stop))
        self.assertEqual(1, job.confirmations)
        self.assertIsNone(job.examine(frame(3), None, sample, 103, rules, read, stop))
        self.assertEqual(LAYOUT, job.examine(frame(4), None, sample, 104, rules, read, stop))
        self.assertEqual(LAYOUT, job.verify(frame(5), sample, 105, rules, read, stop))
        self.assertEqual(20, job.attempts)

    def test_two_confirmations_trigger_same_image_search_for_leading_digits(self):
        boxes = tuple((125 * index, 80, 125 * (index + 1), 920) for index in range(8))
        current = Layout((0, 0, 80, 20), -1, 50, boxes)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "actual_value": "10459.982", "raw_value": "10459.982"}
        self.candidates.return_value = [current]
        for adjusted in (False, True):
            with self.subTest(adjusted=adjusted):
                job = Calibration(7, 0, rank_candidates=True)
                for index in (1, 2):
                    job.examine(frame(index), None, sample, 100 + index, rules,
                                lambda *_: "10459.982", lambda: False)
                self.assertEqual(2, job.confirmations)
                visited, positions = [], []

                def read_slot(layout, index, _):
                    visited.append(index)
                    self.assertEqual(current.box, layout.box)
                    self.assertEqual(current.rotation, layout.rotation)
                    self.assertEqual(boxes[2:], layout.digit_boxes[2:])
                    for original, trial in zip(boxes, layout.digit_boxes):
                        self.assertEqual((original[2] - original[0], original[3] - original[1]),
                                         (trial[2] - trial[0], trial[3] - trial[1]))
                    if adjusted and layout.digit_boxes[index] == boxes[index]:
                        return "?"
                    return "10"[index]

                accepted = job.examine(frame(3), None, sample, 103, rules, lambda *_: "??459.982",
                                       lambda: False, read_slot=read_slot,
                                       on_refine=lambda _, __, slots: positions.append(slots))
                self.assertEqual({0, 1}, set(visited))
                self.assertEqual([[1, 2]], positions)
                self.assertEqual(3, len(job.seen))
                if adjusted:
                    self.assertIsNone(accepted)
                    self.assertEqual(1, job.confirmations)
                    self.assertEqual(current, job.best)
                    self.assertNotEqual(boxes[:2], job.candidate.digit_boxes[:2])
                else:
                    self.assertEqual(current, accepted)
                    self.assertEqual(3, job.confirmations)

    def test_leading_search_never_promotes_approximate_boxes(self):
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "actual_value": "10459.982", "raw_value": "10459.982"}
        job = Calibration(7, 0, rank_candidates=True)
        for index in (1, 2):
            job.examine(frame(index), None, sample, 100 + index, rules, lambda *_: "10459.982", lambda: False)

        visited = []

        def read_slot(layout, index, _):
            visited.append(index)
            self.assertEqual(LAYOUT, layout)
            self.assertFalse(layout.digit_boxes)
            return "?"

        self.assertIsNone(job.examine(frame(3), None, sample, 103, rules, lambda *_: "??459.982",
                                     lambda: False, read_slot=read_slot))
        self.assertEqual([0, 0], visited)
        self.assertEqual(LAYOUT, job.candidate)
        self.assertEqual(2, job.confirmations)

    def test_fine_check_retries_only_the_penultimate_digit_and_keeps_the_same_frame_hits(self):
        job = Calibration(7, 0, intensive=True, followup=True, previous_layout=LAYOUT, attempt_limit=20)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "raw_value": "12345.239", "actual_value": "12345.239"}
        for index in (1, 2):
            job.examine(frame(index), None, sample, 100 + index, rules, lambda *_: "12345.239", lambda: False)
        checked = []

        def retry(layout, profile):
            self.assertEqual(LAYOUT, layout)
            self.assertIn(profile, calibration.OCR_PROFILES[2:4])
            return "12345.239"

        accepted = job.examine(frame(3), None, sample, 103, rules, lambda *_: "12345.2?9", lambda: False,
                               refine_read=retry, on_refine=lambda _, __, positions: checked.append(positions))
        self.assertEqual(LAYOUT, accepted)
        self.assertEqual([[7]], checked)
        self.assertEqual(3, job.confirmations)

    def test_fine_check_can_reuse_the_verified_penultimate_box_without_transferring_hits(self):
        boxes = tuple((125 * index, 0, 125 * (index + 1), 1000) for index in range(8))
        current = Layout((0, 0, 80, 20), 0, 50, boxes)
        verified_boxes = (*boxes[:6], (755, 0, 880, 1000), boxes[-1])
        known_good = Layout(current.box, current.rotation, current.width, verified_boxes)
        job = Calibration(7, 0, intensive=True, followup=True, previous_layout=current,
                          known_good_layout=known_good, attempt_limit=20)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "raw_value": "12345.239", "actual_value": "12345.239"}
        for index in (1, 2):
            job.examine(frame(index), None, sample, 100 + index, rules, lambda *_: "12345.239", lambda: False)
        job.attempts = 20

        def retry(layout, profile):
            return "12345.239" if layout == known_good else "12345.249"

        self.assertIsNone(job.examine(frame(3), None, sample, 103, rules, lambda *_: "12345.249", lambda: False,
                                      refine_read=retry))
        self.assertEqual(known_good, job.candidate)
        self.assertEqual(1, job.confirmations)
        self.assertEqual(current, job.best)

    def test_fine_check_keeps_two_hits_when_both_last_digits_are_unreadable(self):
        job = Calibration(7, 0, intensive=True, followup=True, previous_layout=LAYOUT)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "raw_value": "12345.239", "actual_value": "12345.239"}
        for index in (1, 2):
            job.examine(frame(index), None, sample, 100 + index, rules, lambda *_: "12345.239", lambda: False)

        def unexpected_retry(*_):
            self.fail("Targeted retry requires a readable last digit")

        job.examine(frame(3), None, sample, 103, rules, lambda *_: "12345.2??", lambda: False,
                    refine_read=unexpected_retry)
        self.assertEqual(2, job.confirmations)
        self.assertEqual(LAYOUT, job.candidate)

    def test_followup_tries_only_the_saved_crop_and_refines_the_last_digit(self):
        saved = Layout(LAYOUT.box, LAYOUT.rotation, 50)
        self.job = Calibration(5, 0, intensive=True, followup=True, previous_layout=saved)
        self.candidates.return_value = [OTHER_LAYOUT]
        sample = {"reference_time": 100, "raw_value": "12345.239", "actual_value": "12345.239"}
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        positions = []

        def read(trial, profile):
            self.assertEqual(LAYOUT.box, trial.box)
            self.assertEqual(LAYOUT.rotation, trial.rotation)
            return "12345.239" if trial.digit_boxes else "12345.23?"

        self.job.examine(frame(1), None, sample, 101, rules, read, lambda: False, refine_read=read,
                         on_refine=lambda _, __, weak: positions.append(weak))
        self.candidates.assert_not_called()
        self.assertEqual([8], positions[0])
        self.assertEqual(1, self.job.confirmations)
        self.assertEqual(LAYOUT.box, self.job.candidate.box)

    def test_probe_uses_the_reference_digit_without_adding_confirmations(self):
        saved = Layout(LAYOUT.box, LAYOUT.rotation, 50)
        probe = Calibration(0, 0, intensive=True, followup=True, attempt_limit=9)
        sample = {"reference_time": 100, "raw_value": "12345.239", "actual_value": "12345.239"}
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}

        def read(trial, profile):
            return "12345.239" if trial.digit_boxes else "12345.232"

        proposal = probe.probe_open_digit(saved, sample, rules, read, lambda: False, lambda *_: None)
        self.assertTrue(proposal.digit_boxes)
        self.assertEqual(saved.box, proposal.box)
        self.assertEqual(0, probe.confirmations)
        self.assertEqual(set(), probe.seen)

    def test_fifty_coarse_tests_then_only_the_five_ranked_candidates(self):
        self.job = Calibration(100, 0, rank_candidates=True)
        self.candidates.return_value = [Layout((x, 0, x + 80, 20), 0, 80) for x in range(5)]
        sample = {"reference_time": 100, "raw_value": "12345", "actual_value": "12345"}
        read = lambda *_: "123??"
        intensive = []
        for index in range(1, 11):
            self.job.examine(frame(index), None, sample, 100 + index, RULES, read, lambda: False,
                             on_shortlist=lambda number, _: intensive.append(number))
        self.assertEqual(50, self.job.coarse_attempts)
        self.assertEqual([60] * 5, list(self.job.status(110)["shortlist"]))
        self.assertEqual([], intensive)
        self.candidates.return_value = [OTHER_LAYOUT]
        self.job.examine(frame(11), None, sample, 111, RULES, read, lambda: False,
                         on_shortlist=lambda number, _: intensive.append(number))
        self.assertEqual([1, 2, 3, 4, 5], intensive)
        self.assertEqual(50, self.job.coarse_attempts)

    def test_matching_first_photo_ends_coarse_search_without_skipping_confirmations(self):
        self.job = Calibration(5, 0, rank_candidates=True)
        self.assertIsNone(self.examine(1, 100))
        self.assertTrue(self.job.optimizing)
        self.assertEqual(1, self.job.coarse_attempts)
        self.assertEqual(1, self.job.confirmations)
        self.assertEqual(100, self.job.status(100)["candidate_agreement"])
        self.candidates.return_value = [OTHER_LAYOUT]
        self.candidates.reset_mock()
        self.assertIsNone(self.examine(2, 101))
        self.candidates.assert_not_called()
        self.assertEqual(LAYOUT, self.job.candidate)
        self.assertEqual(2, self.job.confirmations)

    def test_complete_zero_angle_hit_still_compares_small_rotations(self):
        base = Layout((0, 0, 90, 25), 0, 90)
        self.candidates.return_value = [base]
        sample = {"reference_time": 100, "raw_value": "12345", "actual_value": "12345"}
        profiles = calibration.OCR_PROFILES

        for improved, expected in ((True, 2), (False, 0)):
            with self.subTest(improved=improved):
                job = Calibration(5, 0, rank_candidates=True, known_good_layout=base)
                angles = []
                calls = []

                def read(layout, profile):
                    calls.append((layout.rotation, profile))
                    if layout.rotation == -2:
                        return "12346"
                    if improved and layout.rotation != 2 and profile in profiles[2:5]:
                        return "1234?"
                    return "12345"

                job.examine(frame(1), None, sample, 100, RULES, read, lambda: False,
                            angle_read=read, on_angle=lambda _, angle: angles.append(angle))
                self.assertEqual([-1, 1, -2, 2], angles)
                self.assertEqual(expected, job.candidate.rotation)
                self.assertEqual(5, job.coarse_attempts)
                self.assertEqual(1, job.confirmations)
                self.assertEqual(list(profiles[:5]), [profile for angle, profile in calls if angle == expected])

    def test_seven_digit_hit_compares_angles_before_confirming_an_existing_candidate(self):
        base = Layout((0, 0, 90, 25), 0, 55)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "actual_value": "12345.234", "raw_value": "12345.234"}
        job = Calibration(7, 0, rank_candidates=True, simplified=True,
                          candidate=base, confirmations=1, full_hits=1, known_good_layout=base)
        angles = []

        def read(layout, profile):
            if layout.rotation == 2:
                return "12345.234"
            return "12345.23?"

        job.examine(frame(1), None, sample, 101, rules, read, lambda: False, angle_read=read,
                    on_angle=lambda _, angle: angles.append(angle))
        self.assertEqual([-1, 1, -2, 2], angles)
        self.assertEqual(2, job.candidate.rotation)
        self.assertEqual(1, job.confirmations)
        chosen = job.candidate
        job.examine(frame(2), None, sample, 102, rules, read, lambda: False, angle_read=read,
                    on_angle=lambda _, angle: angles.append(angle))
        self.assertEqual(chosen, job.candidate)
        self.assertEqual(2, job.confirmations)
        self.assertEqual([-1, 1, -2, 2], angles)

    def test_intensive_last_digit_can_recover_a_frame_too_far_above_and_left(self):
        boxes = tuple((index * 110, 100, index * 110 + 90, 700) for index in range(7))
        boxes += ((750, 50, 840, 650),)
        initial = Layout((0, 0, 100, 30), 0, 55, boxes)
        job = Calibration(7, 0, intensive=True, previous_layout=initial)
        attempts = []

        def read(trial, profile):
            self.assertEqual(initial.box, trial.box)
            self.assertEqual(initial.rotation, trial.rotation)
            self.assertEqual(initial.digit_boxes[:-1], trial.digit_boxes[:-1])
            attempts.append(trial.digit_boxes[-1])
            left, top, right, bottom = trial.digit_boxes[-1]
            self.assertEqual((90, 600), (right - left, bottom - top))
            return "9" if left >= 785 and top >= 180 else "?"

        job.check_last_digit(frame(1), {"reference_required": False}, 101, initial, 5,
                             read, lambda: False, lambda: None, lambda _: None)
        self.assertEqual(1, job.confirmations)
        self.assertGreaterEqual(job.candidate.digit_boxes[-1][0], 785)
        self.assertGreaterEqual(job.candidate.digit_boxes[-1][1], 180)
        self.assertLessEqual(len(attempts), 28)

    def test_green_reading_without_reference_gets_extra_profiles_but_no_confirmation(self):
        self.job = Calibration(5, 0, rank_candidates=True)
        sample = {"reference_time": None, "raw_value": "12345", "actual_value": "12345"}
        profiles, reasons = [], []

        def read(layout, profile):
            profiles.append(profile)
            return "12345"

        self.job.examine(frame(1), None, sample, 100, RULES, read, lambda: False, on_decision=reasons.append)
        self.assertEqual(list(calibration.OCR_PROFILES[:5]), profiles)
        self.assertEqual(["reference_unavailable"], reasons)
        self.assertEqual(0, self.job.confirmations)
        self.assertEqual(1, len(self.job.seen))

    def test_blurred_verification_image_is_skipped_even_if_ocr_could_match(self):
        rules = {**RULES, "attempts": 3}
        sample = {"reference_time": 100, "raw_value": "12345", "actual_value": "12345"}

        def photo(marker):
            image = frame(marker)
            draw = ImageDraw.Draw(image)
            for x in range(8, 80, 8):
                draw.rectangle((x, 5, x + 2, 15), fill="white")
            return image

        read = lambda *_: "12345"
        for index in range(1, 4):
            self.job.examine(photo(index), None, sample, 100 + index, rules, read, lambda: False)
        self.job.verification_pending = True
        reasons = []
        attempts = self.job.attempts
        blurry = photo(4).filter(ImageFilter.GaussianBlur(4))
        self.assertIsNone(self.job.verify(blurry, sample, 104, rules, read, lambda: False,
                                          on_decision=reasons.append))
        self.assertEqual(["soft_image"], reasons)
        self.assertEqual(attempts, self.job.attempts)
        self.assertEqual(3, self.job.confirmations)
        self.assertEqual(LAYOUT, self.job.verify(photo(5), sample, 105, rules, read, lambda: False))

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

    def test_first_photo_tries_a_quarter_turn_after_an_unreliable_candidate(self):
        sample = {"reference_time": 100, "actual_value": "12345", "raw_value": "12345"}
        rotated = Layout((0, 0, 20, 30), 90, 30)
        invalid = Layout((0, -1, 20, 30), 90, 31)
        self.rotated_candidates.return_value = [invalid, rotated]
        image = frame(1)

        def read(layout, profile):
            return "12345" if layout == rotated else "23456"

        self.job.examine(image, None, sample, 100, RULES, read, lambda: False)
        self.rotated_candidates.assert_called_once_with(image, RULES, None)
        self.assertEqual(rotated, self.job.candidate)
        self.assertEqual(1, self.job.confirmations)
        self.assertEqual(2, self.job.attempts)

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

    def test_ranked_crop_compares_regions_before_trying_its_angle(self):
        initial = Layout((0, 0, 80, 20), 0, 60)
        self.candidates.return_value = [initial, OTHER_LAYOUT]
        self.job = Calibration(5, 0, rank_candidates=True, simplified=True)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "raw_value": "12345.23?", "actual_value": "12345.23?"}
        attempted = []
        angles = []

        def read(layout, profile):
            attempted.append(layout.box)
            return "12345.23?" if layout.rotation == -1 else "1234?.23?"

        self.job.examine(frame(1), None, sample, 101, rules, read, lambda: False, angle_read=read,
                         on_angle=lambda _, angle: angles.append(angle))
        self.assertEqual([-1], angles)
        self.assertEqual([initial.box] * 2 + [OTHER_LAYOUT.box] * 2, attempted[:4])
        self.assertEqual(1, self.job.confirmations)
        self.assertEqual(-1, self.job.candidate.rotation)
        self.assertEqual(3, self.job.coarse_attempts)

    def test_new_search_prefers_larger_display_and_checks_small_angles_for_a_partial_match(self):
        small = Layout((0, 0, 35, 18), 0, 25)
        large = Layout((0, 8, 90, 29), 0, 65)
        self.candidates.return_value = [small, large]
        self.job = Calibration(5, 0, rank_candidates=True, simplified=True)
        angles = []
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "raw_value": "12345.23?", "actual_value": "12345.23?"}
        self.job.examine(frame(1), None, sample, 101, rules, lambda *_: "12345.23?", lambda: False,
                         angle_read=lambda *_: "12345.23?", on_angle=lambda _, angle: angles.append(angle))
        self.assertEqual([-1, 1, -2, 2], angles)
        self.assertEqual(large, self.job.candidate)

    def test_ranked_crop_enters_intensive_search_at_ninety_percent(self):
        initial = Layout((0, 0, 80, 20), 0, 50)
        self.candidates.return_value = [initial]
        self.job = Calibration(5, 0, rank_candidates=True)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "raw_value": "12345.239", "actual_value": "12345.239"}
        checked = []

        def read(layout, profile):
            return "12345.23?" if profile == calibration.OCR_PROFILES[0] else "12345.239"

        initial_score = calibration.agreement_percent(["12345.23?", "12345.239"], sample, 3, 5)
        self.assertEqual(94, initial_score)
        self.job.examine(frame(1), None, sample, 101, rules, read, lambda: False,
                         on_shortlist=lambda number, _: checked.append(number))
        self.assertEqual([1], checked)
        self.assertEqual(0, self.job.confirmations)

    def test_first_full_hit_checks_only_the_best_crop_on_that_image(self):
        self.job = Calibration(5, 0, rank_candidates=True)
        sample = {"reference_time": 100, "raw_value": "12345", "actual_value": "12345"}
        self.candidates.return_value = [LAYOUT, OTHER_LAYOUT]
        checks = []

        def read(layout, profile):
            checks.append((layout, profile))
            return "12345"

        self.job.examine(frame(1), None, sample, 101, RULES, read, lambda: False, angle_read=read)
        self.assertEqual([(LAYOUT, profile) for profile in calibration.OCR_PROFILES[:5]], checks)
        self.assertEqual(1, self.job.confirmations)
        self.assertEqual([100], self.job.status(101)["shortlist"])

    def test_third_full_hit_triggers_intensive_profiles_before_verification(self):
        job = Calibration(5, 0, rank_candidates=True)
        sample = {"reference_time": 100, "raw_value": "12345", "actual_value": "12345"}
        profiles = []

        def read(layout, profile):
            profiles.append(profile)
            return "1234?" if profile == calibration.OCR_PROFILES[4] else "12345"

        for index in (1, 2):
            self.assertIsNone(job.examine(frame(index), None, sample, 100 + index, RULES, read, lambda: False))
        profiles.clear()
        self.candidates.reset_mock()
        self.candidates.return_value = [OTHER_LAYOUT]
        self.assertEqual(LAYOUT, job.examine(frame(3), None, sample, 103, RULES, read, lambda: False))
        self.assertEqual(list(calibration.OCR_PROFILES[:5]), profiles)
        self.assertEqual(3, job.status(103)["full_hits"])
        self.assertTrue(job.status(103)["coarse_complete"])
        self.assertEqual([5], job.status(103)["stress_weak_slots"])
        self.assertEqual(80, job.status(103)["candidate_agreement"])
        self.assertLess(job.coarse_attempts, calibration.COARSE_LIMIT)
        self.candidates.assert_not_called()
        self.assertEqual(3, len(job.seen))

    def test_a_yellow_last_digit_keeps_the_visible_score_below_one_hundred(self):
        self.job = Calibration(5, 0, rank_candidates=True, simplified=True)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "raw_value": "12345.23?", "actual_value": "12345.23?"}
        for index in (1, 2):
            self.job.examine(frame(index), None, sample, 100 + index, rules,
                             lambda *_: "12345.23?", lambda: False)
            status = self.job.status(100 + index)
            self.assertEqual([88], status["shortlist"])
            self.assertEqual(88, status["candidate_agreement"])
            self.assertEqual(index, self.job.confirmations)

    def test_intensive_agreement_uses_the_configured_threshold(self):
        sample = {"reference_time": 100, "raw_value": "123456789.239", "actual_value": "123456789.239"}
        rules = {**RULES, "integer_digits": 9, "decimals": 3, "fraction_digits": 3}
        read = lambda *_: "1234567??.239"
        for override, expected in (({}, True), ({"intensive_agreement": 90}, False)):
            with self.subTest(override=override):
                job = Calibration(5, 0, rank_candidates=True)
                checked = []
                job.examine(frame(1), None, sample, 101, {**rules, **override}, read, lambda: False,
                            on_shortlist=lambda number, _: checked.append(number))
                self.assertEqual([83], job.status(101)["shortlist"])
                self.assertEqual(expected, bool(checked))
                self.assertEqual(0, job.confirmations)

    def test_unsuccessful_intensive_check_resumes_coarse_search_on_the_next_image(self):
        self.job = Calibration(5, 0, rank_candidates=True)
        sample = {"reference_time": 100, "raw_value": "12345", "actual_value": "12345"}
        checked = []
        self.job.examine(frame(1), None, sample, 101, RULES, lambda *_: "1234?", lambda: False,
                         on_shortlist=lambda number, _: checked.append(number))
        self.assertEqual([1], checked)
        self.assertEqual(0, self.job.confirmations)
        self.assertFalse(self.job.optimizing)

        self.candidates.return_value = [OTHER_LAYOUT]
        self.job.examine(frame(2), None, sample, 102, RULES, lambda *_: "12345", lambda: False)
        self.assertEqual(2, self.job.coarse_attempts)
        self.assertEqual(OTHER_LAYOUT, self.job.candidate)
        self.assertEqual(1, self.job.confirmations)

    def test_simplified_near_hit_moves_only_second_decimal_on_same_image(self):
        boxes = tuple((125 * index, 80, 125 * (index + 1), 920) for index in range(8))
        current = Layout((0, 0, 80, 20), -2, 50, boxes)
        self.candidates.return_value = [current, OTHER_LAYOUT]
        job = Calibration(8, 0, simplified=True, rank_candidates=True)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "actual_value": "10462.84?", "raw_value": "10462.84?"}
        calls, angles, positions = [], [], []

        def read(layout, _):
            return "10462.8??" if layout == current else "1????.???"

        def read_slot(layout, index, _):
            calls.append(layout.digit_boxes[index])
            self.assertEqual(6, index)
            self.assertEqual(boxes[:6] + boxes[7:], layout.digit_boxes[:6] + layout.digit_boxes[7:])
            self.assertEqual((-2, current.box), (layout.rotation, layout.box))
            left, top, right, bottom = boxes[index]
            return "4" if layout.digit_boxes[index] == (left + 5, top, right + 5, bottom) else "?"

        self.assertIsNone(job.examine(
            frame(1), None, sample, 101, rules, read, lambda: False, read_slot=read_slot,
            angle_read=lambda *args: angles.append(args), on_refine=lambda _, __, slots: positions.append(slots),
        ))
        self.assertEqual([], angles)
        self.assertEqual([[7]], positions)
        self.assertEqual(1, len(job.seen))
        self.assertEqual(1, job.confirmations)
        self.assertEqual("10462.84?", job.reference_reading)
        self.assertEqual(calls[-1], job.candidate.digit_boxes[6])

    def test_marked_interior_reflection_can_confirm_geometry_without_reading(self):
        self.candidates.return_value = [LAYOUT]
        job = Calibration(8, 0, reflected_layout=LAYOUT, reflected_positions=(2,))
        sample = {"reference_required": False}
        reasons = []
        for stamp in (101, 102, 103):
            self.assertIsNone(job.examine(frame(stamp - 100), None, sample, stamp, RULES,
                                          lambda *_: "12?45", lambda: False, on_decision=reasons.append))
        self.assertEqual(["reflected_geometry"] * 3, reasons)
        self.assertTrue(job.reflection_crop_ready())
        self.assertIsNone(job.reference_reading)
        self.assertEqual(0, job.confirmations)

    def test_near_hit_tries_small_shifts_then_a_degree_around_current_angle(self):
        boxes = tuple((125 * index, 80, 125 * (index + 1), 920) for index in range(8))
        layout = Layout((0, 0, 80, 20), -2, 50, boxes)
        self.candidates.return_value = [layout]
        job = Calibration(8, 0, simplified=True, rank_candidates=True)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "actual_value": "10462.84?", "raw_value": "10462.84?"}
        steps = []

        def read_slot(trial, index, _):
            self.assertEqual(-2, trial.rotation)
            self.assertEqual(boxes[:2] + boxes[3:], trial.digit_boxes[:2] + trial.digit_boxes[3:])
            steps.append(("slot", index))
            return "?"

        def read_angle(trial, _):
            steps.append(("angle", trial.rotation))
            return "10462.84?" if trial.rotation == -1 else "10?62.84?"

        job.examine(frame(1), None, sample, 101, rules, lambda *_: "10?62.84?", lambda: False,
                    read_slot=read_slot, angle_read=read_angle)
        self.assertEqual(("slot", 2), steps[0])
        self.assertEqual({("slot", 2), ("angle", -3), ("angle", -1)}, set(steps))
        self.assertEqual(-1, job.candidate.rotation)
        self.assertEqual(1, job.confirmations)

    def test_optional_last_slot_after_verification_is_only_a_hint(self):
        boxes = tuple((125 * index, 80, 125 * (index + 1), 920) for index in range(8))
        current = Layout((0, 0, 80, 20), -2, 50, boxes)
        self.candidates.return_value = [current]
        job = Calibration(8, 0, simplified=True)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3, "attempts": 3}
        sample = {"reference_time": 100, "actual_value": "10462.87?", "raw_value": "10462.87?"}
        for stamp in (101, 102, 103):
            job.examine(frame(stamp - 100), None, sample, stamp, rules, lambda *_: "10462.87?", lambda: False)
        verified = job.verify(frame(4), sample, 104, rules, lambda *_: "10462.87?", lambda: False)
        visited = []

        def read_slot(layout, index, _):
            visited.append(index)
            self.assertEqual(boxes[:-1], layout.digit_boxes[:-1])
            return "2" if layout.digit_boxes[-1] != boxes[-1] else "?"

        trial, readings = job.probe_optional_last_slot(verified, rules, read_slot, lambda: False)
        self.assertEqual(["10462.872"] * 2, readings)
        self.assertEqual({7}, set(visited))
        self.assertNotEqual(boxes[-1], trial.digit_boxes[-1])
        self.assertEqual(3, job.confirmations)
        self.assertEqual(current, job.candidate)
        self.assertEqual("10462.87?", job.reference_reading)

    def test_only_one_open_required_slot_triggers_intensive_search(self):
        self.job = Calibration(5, 0, rank_candidates=True, simplified=True)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "raw_value": "12345.23?", "actual_value": "12345.23?"}
        checked = []
        self.job.examine(frame(1), None, sample, 101, rules, lambda *_: "12345.2??", lambda: False,
                         on_shortlist=lambda number, _: checked.append(number))
        self.assertEqual([1], checked)
        self.assertEqual(0, self.job.confirmations)

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

    def test_ranked_simplified_setup_counts_seven_digits_without_fresh_reference(self):
        job = Calibration(8, 0, simplified=True, rank_candidates=True)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": None, "actual_value": "12345.23?", "raw_value": "12345.23?"}
        reasons = []
        for index in (1, 2, 3):
            self.assertIsNone(job.examine(frame(index), None, sample, 100 + index, rules,
                                          lambda *_: "12345.23?", lambda: False, on_decision=reasons.append))
            self.assertEqual(index, job.confirmations)
        self.assertEqual(["accepted_geometry"] * 3, reasons)
        self.assertTrue(job.stationary_crop_ready())

    def test_temporarily_rotating_seventh_digit_uses_fresh_image_not_a_failed_setup(self):
        job = Calibration(8, 0, simplified=True, rank_candidates=True)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "actual_value": "12345.230",
                  "raw_value": "12345.230"}
        events = []

        def check(number, reading):
            return job.examine(
                frame(number), None, sample, 100 + number, rules,
                lambda *_: reading, lambda: False, on_decision=events.append,
            )

        self.assertIsNone(check(1, "12345.23?"))
        first = job.candidate
        self.assertIsNotNone(first)
        self.assertEqual(1, job.confirmations)
        # Only the second decimal/7th roller is obscured mid-transition.
        self.assertIsNone(check(2, "12345.2??"))
        self.assertEqual(first, job.candidate)
        self.assertEqual(1, job.confirmations)
        self.assertIn("await_clear_roller", events)
        self.assertIsNone(check(3, "12345.23?"))
        self.assertEqual(2, job.confirmations)
        self.assertEqual(0, job.unclear_frames)
        self.assertEqual(first, check(4, "12345.23?"))
        self.assertEqual(3, job.confirmations)

    def test_repeated_unreadable_seventh_digit_eventually_releases_bad_candidate(self):
        job = Calibration(10, 0, simplified=True, rank_candidates=True)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "actual_value": "12345.230",
                  "raw_value": "12345.230"}
        job.examine(frame(1), None, sample, 101, rules,
                    lambda *_: "12345.23?", lambda: False)
        self.assertIsNotNone(job.candidate)
        for n in (2, 3, 4):
            job.examine(frame(n), None, sample, 100 + n, rules,
                        lambda *_: "12345.2??", lambda: False)
            self.assertIsNotNone(job.candidate)
            self.assertEqual(1, job.confirmations)
        job.examine(frame(5), None, sample, 105, rules,
                    lambda *_: "12345.2??", lambda: False)
        self.assertEqual(0, job.confirmations)
        self.assertIsNone(job.candidate)

    def test_ranked_simplified_setup_uses_extra_profile_for_a_matching_prefix(self):
        job = Calibration(8, 0, simplified=True, rank_candidates=True)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "actual_value": "12345.23?", "raw_value": "12345.23?"}

        def read(_, profile):
            return "12345.2??" if profile == calibration.OCR_PROFILES[0] else "12345.23?"

        reasons = []
        job.examine(frame(1), None, sample, 101, rules, read, lambda: False, on_decision=reasons.append)
        self.assertEqual(1, job.confirmations)
        self.assertEqual(["accepted_partial"], reasons)

    def test_simplified_setup_does_not_count_a_conflicting_reference(self):
        job = Calibration(8, 0, simplified=True, rank_candidates=True)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_time": 100, "actual_value": "12345.23?", "raw_value": "12345.23?"}
        job.examine(frame(1), None, sample, 101, rules, lambda *_: "12345.29?", lambda: False)
        self.assertEqual(0, job.confirmations)

    def test_stationary_simplified_setup_can_save_geometry_after_three_fresh_images(self):
        self.job = Calibration(8, 0, simplified=True)
        rules = {**RULES, "decimals": 3, "fraction_digits": 3}
        sample = {"reference_required": False}
        for index in (1, 2, 3):
            self.assertIsNone(self.job.examine(frame(index), None, sample, 100 + index, rules,
                                               lambda *_: "12345.23?", lambda: False))
            self.assertEqual(index == 3, self.job.stationary_crop_ready())
        self.assertFalse(self.job.verification_pending)
        self.assertEqual(LAYOUT, self.job.candidate)
        self.job.simplified = False
        self.assertFalse(self.job.stationary_crop_ready())

    def test_without_reference_requires_plausible_forward_movement(self):
        self.examine(1, 100, reference=False)
        self.examine(2, 101, reference=False)
        self.assertIsNone(self.examine(3, 102, reference=False))
        self.assertTrue(self.job.status(102)["awaiting_start_value"])
        self.job.state = "testing"
        self.assertTrue(self.job.status(103)["awaiting_start_value"])
        self.assertEqual(LAYOUT, self.examine(4, 103, "12346", reference=False))
        self.assertFalse(self.job.status(103)["awaiting_start_value"])

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
        self.assertFalse(self.job.expired(1199.9))
        self.assertTrue(self.job.expired(1200))
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
        self.assertEqual(1200, self.job.status(0)["duration"])

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
        self.assertTrue(self.job.verification_pending)
        self.assertEqual(3, self.job.confirmations)
        self.assertEqual(LAYOUT, self.job.verify(frame(5), sample, 105, rules, lambda *_: "12345", lambda: False))

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
