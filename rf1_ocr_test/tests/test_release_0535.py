"""0.5.35: the direction of a frame follows its free reading, not the reading it was completed to."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import calibration  # noqa: E402
from calibration import (Calibration, Layout, behind_newest, closer_half_turn, newest_seen,  # noqa: E402
                         orientation_agreement)
from consumption import accumulate_consumption  # noqa: E402
import panel  # noqa: E402
import run  # noqa: E402

RULES = {"decimals": 3, "fraction_digits": 3, "integer_digits": 5, "max_flow_lph": 6000, "learned_flow_lph": None}
START = 1000
SETUP = START + 3 * 3600
# Seen live: a sideways meter, the frame at 90° shows the digits upside down. Completed from the
# known reading it read "10517.12?"; the same frame at -90° shows the meter, 10517.83.
UPSIDE_DOWN = Layout((315, 96, 371, 437), 90, 240, method="neighbours")
RANGE = (10517, 10518)


def last_reading():
    """Booked three hours before the setup, read again (not yet booked) ten minutes before it."""
    booked = accumulate_consumption({}, "calibration", START, "10516.24", 2, 6000, 5, confirmed=True)
    return accumulate_consumption(booked, "calibration", SETUP - 600, "10517.80", 2, 6000, 5)


def completed_reads(layout, profile):
    return "10517.12?" if layout.rotation > 0 else "10517.83?"


def free_scores(free):
    def score(layout, profile):
        return orientation_agreement(free[layout.rotation > 0], RANGE)
    return score


def run_setup(read, orientation_score, layouts=(UPSIDE_DOWN,), job=None):
    job = job or Calibration(5, 3, simplified=True, rank_candidates=True)
    decisions = []
    with patch.object(calibration, "layouts", return_value=list(layouts)), \
            patch.object(calibration, "quarter_turn_layouts", return_value=[]):
        job.examine(Image.new("RGB", (800, 600), (40, 40, 40)), None, {"reference_required": False},
                    SETUP, RULES, read, lambda: False, last_reading(), on_decision=decisions.append,
                    orientation_score=orientation_score)
    return job, decisions


class AgreementTests(unittest.TestCase):
    def test_real_strips_read_freely_fit_the_meter_only_upright(self):
        # Free readings of the cut-out strips of tests/fixtures (10486.83x and 10486.84x), upright
        # and turned by 180° on the same digit frames.
        self.assertEqual(3, orientation_agreement("10??6.83?", (10486, 10486)))
        self.assertEqual(0, orientation_agreement("??89?.?01", (10486, 10486)))
        self.assertEqual(4, orientation_agreement("10?86.842", (10485, 10487)))
        self.assertEqual(-2, orientation_agreement("?7?9?.?01", (10485, 10487)))

    def test_the_live_frames(self):
        for upside_down in ("??1??.1?", "????2.1?", "?2???.1?", "??1??.13"):
            self.assertLessEqual(orientation_agreement(upside_down, RANGE), 1)
        self.assertEqual(5, orientation_agreement("10517.83?", RANGE))

    def test_a_frame_one_roller_off_still_fits(self):
        self.assertEqual(4, orientation_agreement("05178.3?", RANGE))
        self.assertEqual(5, orientation_agreement("?1051.7?", RANGE))

    def test_positions_any_digit_fits_count_nothing(self):
        self.assertEqual(3, orientation_agreement("10599.99", (10400, 10600)))

    def test_without_a_known_range_the_read_digits_count(self):
        self.assertEqual(6, orientation_agreement("10517.8?", None))
        self.assertEqual(0, orientation_agreement(None, RANGE))
        self.assertEqual(5, orientation_agreement("10517", RANGE))


class NewestReadingTests(unittest.TestCase):
    def test_the_newest_reading_seen_counts_besides_the_booked_one(self):
        self.assertEqual(10517800, newest_seen(last_reading()))
        self.assertIsNone(newest_seen(None))

    def test_a_reading_clearly_below_it_lies_behind(self):
        self.assertTrue(behind_newest("10517.12?", last_reading(), 2, 5))
        self.assertTrue(behind_newest("10517.1??", last_reading(), 2, 5))
        self.assertFalse(behind_newest("10517.83?", last_reading(), 2, 5))
        self.assertFalse(behind_newest("10517.7??", last_reading(), 2, 5))
        self.assertFalse(behind_newest("?????.???", last_reading(), 2, 5))
        self.assertFalse(behind_newest("10517.12?", None, 2, 5))

    def test_a_turned_frame_behind_it_is_never_the_closer_one(self):
        twin = Layout(UPSIDE_DOWN.box, -90, 240, method="neighbours")
        self.assertIsNone(closer_half_turn(twin, "10517.83?", [(None, UPSIDE_DOWN, ["10517.12?"])],
                                           last_reading(), 2, 5))
        # Without a newer reading than the booked one the old comparison stays.
        booked = accumulate_consumption({}, "calibration", START, "10516.24", 2, 6000, 5, confirmed=True)
        self.assertEqual(UPSIDE_DOWN, closer_half_turn(twin, "10517.83?", [(None, UPSIDE_DOWN, ["10517.12?"])],
                                                       booked, 2, 5))


class SetupDirectionTests(unittest.TestCase):
    def test_the_free_reading_decides_the_direction(self):
        job, _ = run_setup(completed_reads, free_scores({True: "??1??.1?", False: "10517.83?"}))
        self.assertEqual(-90, job.candidate.rotation)
        self.assertEqual(UPSIDE_DOWN.box, job.candidate.box)
        self.assertIn(("half_turn", 90), [(entry["reason"], entry["rotation"]) for entry in job.rejected])

    def test_without_clear_evidence_a_reading_behind_the_newest_is_not_taken(self):
        job, _ = run_setup(completed_reads, lambda layout, profile: 3)
        self.assertEqual(-90, job.candidate.rotation)
        self.assertIn(("behind", 90), [(entry["reason"], entry["rotation"]) for entry in job.rejected])

    def test_a_frame_that_reads_clearly_better_stays(self):
        # Turned the other way round: the free reading of the upright frame wins although the
        # completed reading of its twin lies closer to the booked reading.
        def read(layout, profile):
            return "10517.83?" if layout.rotation > 0 else "10517.12?"

        upright = Layout(UPSIDE_DOWN.box, 90, 240, method="neighbours")
        job, _ = run_setup(read, free_scores({True: "10517.83?", False: "??1??.1?"}), layouts=(upright,))
        self.assertEqual(90, job.candidate.rotation)
        self.assertFalse(job.rejected)

    def test_the_first_partial_hit_checks_the_direction_too(self):
        def read(layout, profile):
            if layout.rotation > 0:
                return "10517.1??" if profile == calibration.OCR_PROFILES[0] else "10517.13?"
            return "10517.83?"

        job, _ = run_setup(read, free_scores({True: "??1??.1?", False: "10517.83?"}))
        self.assertEqual(-90, job.candidate.rotation)
        self.assertEqual(0, job.partial_hits)

    def test_a_known_frame_upside_down_gives_way_to_clear_evidence_only(self):
        job = Calibration(5, 3, simplified=True, rank_candidates=True)
        job.known_good_layout = UPSIDE_DOWN
        job, _ = run_setup(completed_reads, free_scores({True: "??1??.1?", False: "10517.83?"}), job=job)
        self.assertEqual(-90, job.candidate.rotation)
        job = Calibration(5, 3, simplified=True, rank_candidates=True)
        job.known_good_layout = UPSIDE_DOWN
        job, _ = run_setup(completed_reads, lambda layout, profile: 3, job=job)
        self.assertEqual(90, job.candidate.rotation)


class WorkerTests(unittest.TestCase):
    def test_the_setup_reads_freely_and_logs_the_direction_check(self):
        source = Path(run.__file__).read_text(encoding="utf-8")
        self.assertIn("whole_range=None if free else glyph_range", source)
        self.assertIn("orientation_score=orientation_score", source)
        attempt = Calibration(5, 3)
        attempt.seen = []
        entries = run.setup_round_log(attempt, {"accepted_at": 1.0, "captured": True, "reads": [],
                                                "orientation": ["315,96,371,437 90° ??1??.1?? +1"]}, 0.0, 2.0)
        self.assertEqual(["315,96,371,437 90° ??1??.1?? +1"], entries[0]["orientation"])

    def test_the_panel_names_both_reasons(self):
        self.assertIn("behind: ['liest weniger als der zuletzt gelesene Stand", panel.PAGE)
        self.assertIn("half_turn: ['um 180° verdreht gelesen", panel.PAGE)


if __name__ == "__main__":
    unittest.main()
