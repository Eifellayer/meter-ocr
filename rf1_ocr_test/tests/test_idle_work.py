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


if __name__ == "__main__":
    unittest.main()
