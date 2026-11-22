"""0.4.0: setup groups and skew, recheck plan with resume and permanent improvements."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import calibration  # noqa: E402
import optimizer  # noqa: E402
from calibration import Calibration, Layout, estimate_skew, layouts, same_register  # noqa: E402

FIXTURES = Path(__file__).with_name("fixtures")


def tilted_meter(angle, serial=True):
    """The cut-out digit strip (no serial number from the real meter) on a synthetic meter face."""
    strip = Image.open(FIXTURES / "esphome_blur_strip_0107.png").convert("RGB")
    frame = Image.new("RGB", (900, 600), (95, 95, 95))
    draw = ImageDraw.Draw(frame)
    draw.rectangle((150, 180, 750, 300), fill=(30, 30, 30))
    frame.paste(strip, (166, 192))
    if serial:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        draw.text((250, 380), "Nr. 7302458196 2019", font=font, fill=(235, 235, 235))
        for x in range(250, 520, 6):
            draw.rectangle((x, 430, x + (2 if x % 12 else 4), 480), fill=(15, 15, 15))
    # PIL turns counter-clockwise; ``turn_crop(frame, angle)`` levels it again.
    return frame.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=(95, 95, 95))


class SkewTests(unittest.TestCase):
    def test_measured_skew_levels_a_fourteen_degree_meter(self):
        for angle in (-14, 14, -7, 0, 19):
            with self.subTest(angle=angle):
                self.assertEqual(angle, estimate_skew(tilted_meter(angle)))

    def test_flat_picture_has_no_skew(self):
        self.assertIsNone(estimate_skew(Image.new("RGB", (300, 200), (90, 90, 90))))

    def test_first_image_searches_the_measured_angle_first(self):
        seen = []

        def rows(image, whole, fraction, limit=4):
            seen.append(image.info.get("angle"))
            return []

        original = calibration.turn_crop

        def turned(image, angle, expand=True):
            result = original(image, angle, expand=expand)
            result.info["angle"] = angle
            return result

        rules = {"decimals": 3, "fraction_digits": 3, "integer_digits": 5, "max_flow_lph": 6000}
        with patch.object(calibration, "find_raw_digit_rows", side_effect=rows), \
                patch.object(calibration, "turn_crop", side_effect=turned):
            list(layouts(Image.new("RGB", (200, 100)), None, rules, 0, skew=-14))
        self.assertEqual([-14, -15, -13, -16, -12], seen[:5])


FRAME = Image.new("RGB", (400, 200), (0, 0, 0))
RULES = {"decimals": 0, "fraction_digits": 0, "integer_digits": 5, "max_flow_lph": 6000}


def frame(number):
    return Image.new("RGB", (400, 200), (0, 20, number))


class GroupTests(unittest.TestCase):
    def test_hits_of_near_identical_frames_are_counted_for_one_register(self):
        job = Calibration(10, 0, rank_candidates=True)
        a = Layout((100, 50, 300, 100), -12, 150, method="register_window")
        b = Layout((101, 50, 301, 101), -13, 150, method="refined")
        self.assertTrue(same_register(a, b))
        for stamp, layout in ((1, a), (2, b), (3, b)):
            job.current_stamp = stamp
            job.note_group(layout, ["12345", "12345"], True, 5)
        self.assertEqual(1, len(job.groups))
        self.assertEqual(3, len(job.groups[0]["hits"]))

    def test_best_frame_of_the_register_is_saved_not_the_first_confirmed(self):
        job = Calibration(10, 0, rank_candidates=True)
        boxes = tuple((i * 200, 0, i * 200 + 180, 1000) for i in range(5))
        first = Layout((100, 50, 300, 100), -12, 150, boxes)
        better = Layout((100, 51, 300, 101), -14, 150, boxes)
        for stamp in (1, 2, 3):
            job.current_stamp = stamp
            job.note_group(first, ["123?5", "123?5"], True, 5)
            job.note_group(better, ["12345", "12345"], True, 5)
        self.assertEqual(better, job.best_of_group(first))

    def test_single_image_cannot_replace_the_confirmed_frame(self):
        job = Calibration(10, 0, rank_candidates=True)
        boxes = tuple((i * 200, 0, i * 200 + 180, 1000) for i in range(5))
        first = Layout((100, 50, 300, 100), -12, 150, boxes)
        other = Layout((100, 51, 300, 101), -14, 150, boxes)
        for stamp in (1, 2):
            job.current_stamp = stamp
            job.note_group(first, ["123?5", "123?5"], True, 5)
        job.note_group(other, ["12345", "12345"], True, 5)
        self.assertEqual(first, job.best_of_group(first))

    def test_status_lists_one_row_per_register_with_hits_and_merged_frames(self):
        job = Calibration(10, 0, rank_candidates=True)
        a = Layout((100, 50, 300, 100), -12, 150)
        b = Layout((101, 50, 301, 101), -13, 150)
        serial = Layout((100, 150, 200, 170), 0, 80)
        job.shortlist = {a: (88, 5.0, 88), b: (88, 4.9, 88), serial: (40, 1.0, 40)}
        job.current_stamp = 1
        job.note_group(a, ["12345", "12345"], True, 5)
        job.current_stamp = 2
        job.note_group(b, ["12345", "12345"], True, 5)
        job.note_group(serial, ["?3???", "?3???"], False, 5)
        rows = job.status(0)["candidates"]
        self.assertEqual(2, len(rows))
        self.assertEqual((2, 1, "confirm"), (rows[0]["hits"], rows[0]["merged"], rows[0]["role"]))
        self.assertEqual("hint", rows[1]["role"])

    def test_register_with_hits_is_listed_after_leaving_the_shortlist(self):
        """0.4.1: two matches with hits were missing from the candidate list."""
        job = Calibration(10, 0, rank_candidates=True)
        hit = Layout((100, 50, 300, 100), -13, 150)
        job.current_stamp = 1
        job.note_group(hit, ["12345", "12345"], True, 5)
        job.groups[0]["percent"] = 86
        job.current_stamp = 2
        job.note_group(hit, ["12345", "12345"], True, 5)
        # Five other frames with a higher percentage but no hits fill the shortlist.
        others = [Layout((100, 150 + 30 * i, 300, 170 + 30 * i), 0, 150) for i in range(5)]
        job.shortlist = {layout: (95 - i, 5.0, 95 - i) for i, layout in enumerate(others)}
        for layout in others:
            job.note_group(layout, ["?2???", "?3???"], False, 5)
        rows = job.status(0)["candidates"]
        self.assertEqual(6, len(rows))
        self.assertEqual((1, 2, -13, "12345"),
                         (rows[0]["number"], rows[0]["hits"], rows[0]["rotation"], rows[0]["reading"]))
        self.assertEqual(list(range(1, 7)), [row["number"] for row in rows])

    def test_later_worse_image_does_not_lower_a_frames_best_score(self):
        """0.4.2: a better frame was overwritten by a later 75 % reading."""
        job = Calibration(10, 0, rank_candidates=True)
        layout = Layout((100, 50, 300, 100), -14, 150)
        with patch.object(calibration, "agreement_percent", side_effect=[88, 88, 75, 75]), \
                patch.object(calibration, "crop_quality", return_value=5.0):
            job.current_stamp = 1
            job.record_intermediate(layout, ["12345", "12345"], {}, 0, 5, 0, FRAME)
            job.current_stamp = 2
            job.record_intermediate(layout, ["12345", "12345"], {}, 0, 5, 0, FRAME)
        self.assertEqual(88, job.shortlist[layout][0])
        self.assertEqual(88, job.groups[0]["percent"])

    def test_one_decimal_less_still_agrees_for_setup_hits(self):
        """0.4.2: 10494.2?? next to a confirmed 10494.27? was not counted."""
        agree = calibration.agreeing_prefixes
        self.assertEqual(2, agree(["10494.27?", "10494.27?"], 2, 5))
        self.assertEqual(1, agree(["10494.2??", "10494.2??"], 2, 5))
        self.assertIsNone(agree(["10494.2??", "10494.3??"], 2, 5))
        self.assertIsNone(agree(["10494.???", "10494.???"], 2, 5))
        self.assertIsNone(agree(["10494.???", "10494.???"], 1, 5))
        self.assertIsNone(agree(["10494.2??"], 2, 5))

    def test_confirmed_frame_stays_listed_when_its_score_fell_out(self):
        job = Calibration(10, 0, rank_candidates=True)
        job.candidate = Layout((10, 10, 200, 60), -13, 120)
        job.confirmations = 2
        rows = job.status(0)["candidates"]
        self.assertEqual(1, len(rows))
        self.assertTrue(rows[0]["selected"])

    def test_prefilter_drops_serial_number_and_far_turned_frames_with_reason(self):
        job = Calibration(10, 0, rank_candidates=True,
                          known_good_layout=Layout((100, 40, 400, 120), -13, 200))
        register = Layout((102, 41, 401, 121), -14, 200)
        serial = Layout((150, 160, 260, 185), -13, 80)
        sideways = Layout((100, 40, 400, 120), 90, 200)
        kept = list(job.prefilter([register, serial, sideways]))
        self.assertEqual([register], kept)
        self.assertEqual({"small_label", "quarter_turn"}, {entry["reason"] for entry in job.status(0)["rejected"]})

    def test_hopeless_first_profile_skips_the_second_read(self):
        job = Calibration(10, 0, rank_candidates=True)
        calls = []

        def read(layout, profile):
            calls.append(profile)
            return "??3??"

        serial = Layout((10, 10, 120, 40), 0, 80)
        with patch.object(calibration, "layouts", return_value=[serial]), \
                patch.object(calibration, "quarter_turn_layouts", return_value=[]):
            sample = {"reference_required": False}
            job.examine(frame(1), None, sample, 1, RULES, read, lambda: False)
        self.assertEqual(1, len(calls))

    def test_hint_below_threshold_is_not_confirmed_when_a_frame_reaches_it(self):
        job = Calibration(10, 0, rank_candidates=True)
        good = Layout((10, 10, 300, 60), 0, 200)
        weak = Layout((10, 120, 300, 170), 0, 200)
        job.shortlist = {good: (100, 5.0, 100), weak: (60, 4.0, 60)}
        self.assertEqual([(None, good, None)],
                         calibration.worth_intensive([(None, good, None), (None, weak, None)],
                                                     job.shortlist, 100, 80))


class OptimizerTests(unittest.TestCase):
    def test_trials_start_with_angles_then_vertical_shifts(self):
        self.assertEqual(["a+1", "a-1", "a+2", "a-2"], list(optimizer.TRIALS[:4]))
        self.assertTrue(all(trial.startswith("v") for trial in optimizer.TRIALS[4:]))

    def test_plan_resumes_on_the_next_picture(self):
        state = optimizer.plan({}, ["key"])
        self.assertEqual(["a+1", "a-1"], optimizer.next_trials(state, 2))
        optimizer.advance(state, 2)
        self.assertEqual((2, 10), optimizer.progress(state))
        self.assertEqual(["a+2", "a-2", "v+2"], optimizer.next_trials(state, 3))
        # A changed geometry starts again, but keeps the measured speed of this machine.
        state["read_s"] = 7.0
        optimizer.plan(state, ["other"])
        self.assertEqual((0, 10), optimizer.progress(state))
        self.assertEqual(7.0, state["read_s"])

    def test_budget_follows_the_measured_time_per_read(self):
        state = {}
        optimizer.note_read_time(state, 21.6, 3)
        self.assertEqual(7.2, state["read_s"])
        self.assertEqual(43, optimizer.recheck_seconds(state))
        self.assertEqual(1, optimizer.trials_per_image(state))
        fast = optimizer.note_read_time({}, 4.0, 4)
        self.assertEqual(25, optimizer.recheck_seconds(fast))
        self.assertEqual(7, optimizer.trials_per_image(fast))

    def test_only_a_trial_better_over_several_pictures_is_adopted(self):
        state = optimizer.plan({}, ["key"])
        base = ["10493.4??", "10493.4??"]
        better = ["10493.48?", "10493.48?"]
        for _ in range(2):
            optimizer.note_result(state, "a-1", better, base, 8)
        self.assertIsNone(optimizer.best_trial(state))
        optimizer.note_result(state, "a-1", better, base, 8)
        self.assertEqual("a-1", optimizer.best_trial(state))

    def test_a_contradiction_blocks_the_trial(self):
        state = optimizer.plan({}, ["key"])
        base = ["10493.4??", "10493.4??"]
        for reading in ("10493.48?", "10493.48?", "10493.78?", "10493.48?"):
            optimizer.note_result(state, "v+2", [reading, reading], base, 8)
        self.assertIsNone(optimizer.best_trial(state))

    def test_vertical_trial_moves_only_the_decimal_frames(self):
        boxes = [[i * 120, 100, i * 120 + 100, 900] for i in range(8)]
        rotation, moved = optimizer.trial_geometry("v+4", -13, boxes, 200, 5)
        self.assertEqual(-13, rotation)
        self.assertEqual(boxes[:5], moved[:5])
        self.assertEqual([[i * 120, 120, i * 120 + 100, 920] for i in range(5, 8)], moved[5:])
        self.assertEqual((-15, boxes), optimizer.trial_geometry("a-2", -13, boxes, 200, 5))
        self.assertIsNone(optimizer.trial_geometry("v+6", -13, [[0, 0, 10, 995]] * 8, 200, 5))

    def test_full_round_without_winner_rests(self):
        state = optimizer.plan({}, ["key"])
        optimizer.advance(state, len(optimizer.TRIALS))
        self.assertEqual(1, state["rounds"])
        self.assertEqual([], optimizer.next_trials(state, 3))


if __name__ == "__main__":
    unittest.main()


class DigitLibraryTests(unittest.TestCase):
    FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    def cell(self, digit, blur=1.6, dx=0, dy=0):
        from PIL import ImageFilter
        image = Image.new("RGB", (52, 72), (25, 25, 25))
        ImageDraw.Draw(image).text((26 + dx, 36 + dy), digit, font=ImageFont.truetype(self.FONT, 54),
                                   fill=(210, 210, 210), anchor="mm")
        return image.filter(ImageFilter.GaussianBlur(blur))

    def library(self, digits="0123456789", samples=3):
        import digit_library
        library = digit_library.DigitLibrary()
        for round_ in range(samples):
            library.learn([(self.cell(d, blur=1.4 + .2 * round_, dx=round_ - 1), d) for d in digits], True)
        return library

    def test_learned_digit_fills_an_unclear_cell(self):
        library = self.library()
        self.assertEqual({str(d): 3 for d in range(10)}, library.samples())
        self.assertEqual("8", library.fill(self.cell("8", blur=2.2, dx=1, dy=1), True))
        self.assertEqual(1, library.take_filled())
        self.assertEqual(0, library.take_filled())

    def test_nothing_is_filled_before_most_digits_are_known(self):
        library = self.library(digits="0168")
        self.assertIsNone(library.fill(self.cell("8"), True))

    def test_empty_cell_stays_unclear(self):
        library = self.library()
        self.assertIsNone(library.fill(Image.new("RGB", (52, 72), (25, 25, 25)), True))

    def test_library_survives_a_restart_and_is_cleared_by_reset(self):
        import tempfile
        import digit_library
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "digit-library.json"
            library = digit_library.DigitLibrary(path)
            library.learn([(self.cell("8"), "8")], True)
            self.assertEqual({"8": 1}, digit_library.DigitLibrary(path).samples())
            library.clear()
            self.assertFalse(path.exists())

    def test_confirmed_check_teaches_only_cells_both_profiles_read(self):
        import digit_library
        import run
        register = Image.new("RGB", (8 * 52, 72), (25, 25, 25))
        for index, digit in enumerate("10493482"):
            register.paste(self.cell(digit), (index * 52, 0))
        boxes = [(index * 52, 0, index * 52 + 52, 72) for index in range(8)]
        with patch.object(digit_library, "LIBRARY", digit_library.DigitLibrary()):
            learned = run.learn_confirmed_digits(register, boxes, ["10493.48?", "10493.4??"], "10493.482",
                                                 True, skip_last=True)
            self.assertEqual(6, learned)
            self.assertEqual({"0": 1, "1": 1, "3": 1, "4": 2, "9": 1}, digit_library.LIBRARY.samples())


class RecheckWorkerTests(unittest.TestCase):
    def test_recheck_tries_the_angle_first_and_continues_the_plan(self):
        import json
        import os
        from datetime import datetime, timezone
        from io import BytesIO
        from tempfile import TemporaryDirectory
        import run

        class StopLoop(Exception):
            pass

        folder = Path(self.enterContext(TemporaryDirectory()))
        paths = {key: folder / key for key in (
            "OPTIONS", "HISTORY", "EFFECTIVE_OPTIONS", "SOURCE_SETTINGS", "AUTO_RULES", "NOTIFICATIONS",
            "LANGUAGE_MODES", "AUTO_PAUSED", "DESTINATION", "GOOD_IMAGE", "AUTOMATIC_PREVIEW",
        )}
        source = {"mode": "esphome", "url": "", "camera": "camera.meter", "reference": ""}
        boxes = [[index * 125, 50, index * 125 + 110, 950] for index in range(8)]
        paths["OPTIONS"].write_text("{}")
        paths["SOURCE_SETTINGS"].write_text(json.dumps(source))
        paths["AUTO_RULES"].write_text(json.dumps({
            "decimals": 2, "attempts": 5, "crop_mode": "manual", "crop": "0,0,500,100", "width": 300,
            "rotation": -13, "digit_boxes": boxes,
            "setup_completed": {"source": run.setup_source_id({**source, "selected": True}),
                                "time": datetime.now(timezone.utc).timestamp()},
        }))
        self.enterContext(patch.multiple(run, **paths))
        self.enterContext(patch.dict(os.environ, {"SUPERVISOR_TOKEN": "stub"}))
        self.enterContext(patch.object(run, "start_panel", return_value=(None, None, None)))
        image = Image.new("RGB", (500, 100), "white")
        with BytesIO() as stream:
            image.save(stream, "JPEG")
            self.enterContext(patch.object(run, "get_bytes", return_value=stream.getvalue()))
        angles = []
        original_select = run.select_register

        def select(frame, overlay, crop, width, rotation=0, *args, **kwargs):
            angles.append(rotation)
            return original_select(frame, overlay, crop, width, rotation, *args, **kwargs)

        self.enterContext(patch.object(run, "select_register", side_effect=select))
        reads = iter(["10465.9?", "10465.9?"] + ["10465.94"] * 10)
        self.enterContext(patch.object(run, "read_visible_digits", side_effect=lambda *a, **k: next(reads)))
        self.enterContext(patch.object(run, "read_register", return_value="?"))
        self.enterContext(patch.object(run, "publish_state"))
        self.enterContext(patch.object(run, "publish_consumption", side_effect=StopLoop))
        with self.assertRaises(StopLoop):
            run.main()
        history = json.loads(paths["HISTORY"].read_text())
        self.assertEqual("optimizer", history["ocr_method"])
        self.assertEqual("10465.94", history["standalone_candidate"]["reading"])
        # The first trial turned the picture by +1° around the saved −13°.
        self.assertIn(-12, [round(angle) for angle in angles])
        self.assertEqual(1, history["optimizer"]["cursor"])
        self.assertEqual(1, history["optimizer"]["stats"]["a+1"]["images"])
