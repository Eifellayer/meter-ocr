from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import idle_work


def write(path, content, mode):
    path.write_bytes(content)


class IdleWorkTests(unittest.TestCase):
    """The two pictures the app may work with between checks."""

    def setUp(self):
        self.folder = Path(self.enterContext(TemporaryDirectory()))

    def test_the_last_two_check_pictures_are_kept_newest_first(self):
        for content in (b"first", b"second", b"third"):
            self.assertTrue(idle_work.remember_check_image(self.folder, content, write))
        self.assertEqual([b"third", b"second"], idle_work.kept_images(self.folder))
        self.assertEqual(2, len(list(self.folder.iterdir())))

    def test_the_same_picture_is_not_kept_twice(self):
        idle_work.remember_check_image(self.folder, b"first", write)
        idle_work.remember_check_image(self.folder, b"second", write)
        self.assertFalse(idle_work.remember_check_image(self.folder, b"second", write))
        self.assertEqual([b"second", b"first"], idle_work.kept_images(self.folder))

    def test_empty_oversized_or_unwritable_pictures_are_skipped(self):
        self.assertFalse(idle_work.remember_check_image(self.folder, b"", write))
        self.assertFalse(idle_work.remember_check_image(self.folder, None, write))
        self.assertFalse(idle_work.remember_check_image(
            self.folder, b"x" * (idle_work.MAX_IMAGE_BYTES + 1), write))

        def refuse(*_):
            raise OSError
        self.assertFalse(idle_work.remember_check_image(self.folder, b"picture", refuse))
        self.assertEqual([], idle_work.kept_images(self.folder))

    def test_a_reset_forgets_the_pictures(self):
        idle_work.remember_check_image(self.folder, b"first", write)
        idle_work.forget_images(self.folder)
        self.assertEqual([], idle_work.kept_images(self.folder))


class IdleBudgetTests(unittest.TestCase):
    """Extra work only with a reason, on an idle machine, away from the checks."""

    IDLE = {"cpu_percent": 5, "memory_used_percent": 40, "temperature_c": 45.0}

    def budget(self, now=300.0, reason="unclear_check", sample=None, used=0, last=0.0, following=600.0):
        return idle_work.budget(now, last, following, self.IDLE if sample is None else sample, reason, used)

    def test_a_few_reads_with_a_reason_on_an_idle_machine(self):
        self.assertEqual(idle_work.MAX_READS_PER_WAIT, self.budget())
        self.assertEqual(idle_work.MAX_READS_PER_WAIT - 4, self.budget(used=4))
        self.assertEqual(0, self.budget(used=idle_work.MAX_READS_PER_WAIT))

    def test_nothing_without_a_reason(self):
        self.assertEqual(0, self.budget(reason=None))
        self.assertEqual(0, self.budget(reason="because"))
        for reason in idle_work.REASONS:
            self.assertGreater(self.budget(reason=reason), 0)

    def test_nothing_right_after_or_shortly_before_a_check(self):
        self.assertEqual(0, self.budget(now=10.0))
        self.assertEqual(0, self.budget(now=560.0))
        self.assertEqual(0, idle_work.budget(300.0, None, 600.0, self.IDLE, "experiment"))

    def test_nothing_on_a_loaded_or_hot_machine(self):
        for change in ({"cpu_percent": 60}, {"memory_used_percent": 90}, {"temperature_c": 75.0}):
            self.assertEqual(0, self.budget(sample={**self.IDLE, **change}), change)
        # Unknown values (first sample, no sensor) do not block.
        self.assertGreater(self.budget(sample={"cpu_percent": None, "temperature_c": None}), 0)


class IdleStepTests(unittest.TestCase):
    """The waiting time looks again at the last check picture; diagnostic only (run.idle_step)."""

    calm = {"cpu_percent": 5, "memory_used_percent": 40, "temperature_c": 45}

    def job(self, reason="unclear_check", ocr="1049?.6?"):
        import run
        from PIL import Image
        boxes = [[i * 10, 0, i * 10 + 10, 20] for i in range(7)]
        return run.idle_job(reason, Image.new("RGB", (70, 20)), boxes, ocr, False, False, "bild-1", 1000.0)

    def test_only_unclear_checks_with_matching_frames_leave_work(self):
        import run
        self.assertIsNone(self.job(ocr="10490.67"))
        self.assertIsNone(self.job(ocr="1049?"))
        self.assertIsNone(run.idle_job("", None, [], "1?", False, False, "b", 1.0))
        self.assertEqual("1049?6?", self.job()["digits"])

    def test_unclear_digits_are_read_again_with_the_second_profile(self):
        import run
        from unittest.mock import patch
        with patch.object(run, "read_register", return_value="7") as read:
            used, record = run.idle_step(self.job(), {}, 1100.0, 1400.0, 0, sample=self.calm)
        self.assertEqual(2, used)
        self.assertEqual({"reread": [{"position": 5, "digit": "7"}, {"position": 7, "digit": "7"}]}, record)
        self.assertEqual({run.OCR_PROFILES[1]}, {call.kwargs["profile"] for call in read.call_args_list})

    def test_nothing_runs_on_a_loaded_machine_or_close_to_a_check(self):
        import run
        from unittest.mock import patch
        with patch.object(run, "read_register") as read:
            self.assertEqual((0, None), run.idle_step(self.job(), {}, 1100.0, 1400.0, 0,
                                                      sample={**self.calm, "cpu_percent": 80}))
            self.assertEqual((0, None), run.idle_step(self.job(), {}, 1005.0, 1400.0, 0, sample=self.calm))
            self.assertEqual((0, None), run.idle_step(self.job(), {}, 1100.0, 1130.0, 0, sample=self.calm))
        read.assert_not_called()

    def test_skipped_experiment_is_caught_up_once(self):
        import run
        from unittest.mock import patch
        job = self.job("experiment", "10490.67")
        with patch.object(run, "shadow_experiments", return_value={"stable": "10490.67", "seven_segment": {}}) as shadow:
            used, record = run.idle_step(job, {"experiments_enabled": True}, 1100.0, 1400.0, 0, sample=self.calm)
            self.assertEqual((run.idle_work.MAX_READS_PER_WAIT, {"experiment": shadow.return_value}), (used, record))
        with patch.object(run, "shadow_experiments", return_value={"skipped": "busy"}):
            self.assertEqual((0, None), run.idle_step(job, {}, 1100.0, 1400.0, 0, sample=self.calm))


class KeepRecentTests(unittest.TestCase):
    def test_only_the_work_of_the_last_two_checks_stays(self):
        jobs = idle_work.keep_recent([], {"image": "a"})
        jobs = idle_work.keep_recent(jobs, None)
        self.assertEqual([None, {"image": "a"}], jobs)
        self.assertEqual([{"image": "c"}, None], idle_work.keep_recent(jobs, {"image": "c"}))


class RegisterLightHintTests(unittest.TestCase):
    def test_dark_bright_and_flat_registers_are_named(self):
        from PIL import Image, ImageDraw
        import calibration
        self.assertEqual(["dark", "low_contrast"], calibration.register_light_hints(Image.new("RGB", (200, 60), "#101010")))
        self.assertEqual(["bright", "low_contrast"], calibration.register_light_hints(Image.new("RGB", (200, 60), "#f5f5f5")))
        good = Image.new("RGB", (200, 60), "#202020")
        ImageDraw.Draw(good).rectangle((20, 5, 180, 55), fill="#e0e0e0")
        self.assertEqual([], calibration.register_light_hints(good))


if __name__ == "__main__":
    unittest.main()
