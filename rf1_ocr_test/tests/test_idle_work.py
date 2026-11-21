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


if __name__ == "__main__":
    unittest.main()
