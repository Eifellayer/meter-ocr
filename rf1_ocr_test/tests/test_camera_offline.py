import io
import unittest
from datetime import timezone
from unittest.mock import patch
from urllib.error import HTTPError

import run
from i18n import EN_UI
from source_settings import CAMERA_MISSING, CAMERA_OFFLINE, CameraOffline, camera_problem


def gone(*_args, **_kwargs):
    raise HTTPError("http://supervisor", 404, "Not Found", None, io.BytesIO())


class CameraProblemTests(unittest.TestCase):
    def test_unavailable_camera_gets_a_concrete_reason(self):
        self.assertEqual(CAMERA_OFFLINE, camera_problem("camera.gas", "t", lambda *_a, **_k: b'{"state": "unavailable"}'))

    def test_removed_camera_is_named_as_removed(self):
        self.assertEqual(CAMERA_MISSING, camera_problem("camera.gas", "t", gone))

    def test_working_or_unknown_state_gives_no_reason(self):
        self.assertEqual("", camera_problem("camera.gas", "t", lambda *_a, **_k: b'{"state": "idle"}'))
        self.assertEqual("", camera_problem("camera.gas", "t", lambda *_a, **_k: b"kein json"))

        def offline(*_args, **_kwargs):
            raise OSError("down")
        self.assertEqual("", camera_problem("camera.gas", "t", offline))

    def test_both_reasons_are_translated(self):
        self.assertIn(CAMERA_OFFLINE, EN_UI)
        self.assertIn(CAMERA_MISSING, EN_UI)


class WizardPreviewTests(unittest.TestCase):
    source = {"mode": "camera", "camera": "camera.gas", "light": "", "camera_light": False}

    def test_failed_picture_of_an_unavailable_camera_says_so(self):
        with patch.object(run, "capture_camera", side_effect=OSError("500")), \
                patch.object(run, "capture_light", return_value=""), \
                patch.object(run, "get_bytes", return_value=b'{"state": "unavailable"}'):
            with self.assertRaises(CameraOffline) as raised:
                run.wizard_camera_preview(self.source, "t", timezone.utc)
        self.assertEqual(CAMERA_OFFLINE, str(raised.exception))

    def test_other_failures_stay_the_general_error(self):
        with patch.object(run, "capture_camera", side_effect=OSError("500")), \
                patch.object(run, "capture_light", return_value=""), \
                patch.object(run, "get_bytes", return_value=b'{"state": "idle"}'):
            with self.assertRaises(OSError) as raised:
                run.wizard_camera_preview(self.source, "t", timezone.utc)
        self.assertNotIsInstance(raised.exception, CameraOffline)


if __name__ == "__main__":
    unittest.main()
