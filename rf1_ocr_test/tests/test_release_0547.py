"""0.5.47: less load on Home Assistant (unchanged states, backoff, polling, OCR processes, shutdown)."""

from pathlib import Path
import signal
import sys
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import panel  # noqa: E402
import run  # noqa: E402
import system_monitor  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
URL = "http://supervisor/core/api/states/sensor.test"


class Answer:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class StateWriteTests(TestCase):
    def setUp(self):
        run._published_states.clear()
        run._core_backoff.update(failures=0, until=0.0)
        self.sent = []

        def fake_open(request, timeout=10):
            self.sent.append(request.data)
            return Answer()

        self.enterContext(patch.object(run, "open_core", fake_open))

    def test_an_unchanged_state_is_not_sent_again(self):
        self.assertTrue(run.publish_state(URL, {"state": "1"}, "token"))
        self.assertFalse(run.publish_state(URL, {"state": "1"}, "token"))
        self.assertTrue(run.publish_state(URL, {"state": "2"}, "token"))
        self.assertEqual(2, len(self.sent))

    def test_an_unchanged_state_is_refreshed_after_the_refresh_time(self):
        run.publish_state(URL, {"state": "1"}, "token")
        body, stamp = run._published_states[URL]
        run._published_states[URL] = (body, stamp - run.STATE_REFRESH_SECONDS - 1)
        self.assertTrue(run.publish_state(URL, {"state": "1"}, "token"))
        self.assertEqual(2, len(self.sent))

    def test_a_failed_write_sends_everything_again_and_starts_the_backoff(self):
        run.publish_state(URL, {"state": "1"}, "token")

        def failing(request, timeout=10):
            raise OSError("502 Bad Gateway")

        with patch.object(run, "open_core", failing):
            with self.assertRaises(OSError):
                run.publish_state(URL + "2", {"state": "x"}, "token")
        self.assertTrue(run.core_backoff_active())
        self.assertEqual(run.CORE_BACKOFF_STEPS[0], round(run._core_backoff["until"] - run.time.monotonic()))
        # Home Assistant may have restarted: the unchanged state goes out again.
        self.assertTrue(run.publish_state(URL, {"state": "1"}, "token"))
        self.assertFalse(run.core_backoff_active())

    def test_the_backoff_grows_and_stops_at_five_minutes(self):
        def failing(request, timeout=10):
            raise OSError("down")

        with patch.object(run, "open_core", failing):
            for _ in range(6):
                with self.assertRaises(OSError):
                    run.publish_state(URL, {"state": "1"}, "token")
        self.assertEqual(300, round(run._core_backoff["until"] - run.time.monotonic()))

    def test_the_system_status_counts_the_writes(self):
        before = system_monitor.snapshot()
        run.publish_state(URL, {"state": "a"}, "token")
        run.publish_state(URL, {"state": "a"}, "token")
        after = system_monitor.snapshot()
        self.assertEqual(before["state_writes_sent"] + 1, after["state_writes_sent"])
        self.assertEqual(before["state_writes_skipped"] + 1, after["state_writes_skipped"])
        self.assertGreaterEqual(after["app_threads"], 1)
        self.assertIn("app_open_files", after)


class OcrLoadTests(TestCase):
    def test_digit_reads_leave_a_core_free(self):
        with patch.object(run, "usable_cores", return_value=4), patch.object(run.os, "getloadavg",
                                                                            return_value=(0.2, 0, 0)):
            self.assertEqual(3, run.digit_workers())
        with patch.object(run, "usable_cores", return_value=4), patch.object(run.os, "getloadavg",
                                                                            return_value=(3.6, 0, 0)):
            self.assertEqual(1, run.digit_workers())
        with patch.object(run, "usable_cores", return_value=1):
            self.assertEqual(1, run.digit_workers())

    def test_parallel_reads_keep_their_order(self):
        tasks = [lambda value=value: value for value in range(6)] + ["?"]
        with patch.object(run, "digit_workers", return_value=2):
            self.assertEqual([0, 1, 2, 3, 4, 5, "?"], run.read_digits_parallel(tasks))

    def test_tesseract_runs_with_one_thread(self):
        self.assertIn("ENV OMP_THREAD_LIMIT=1", (ROOT / "Dockerfile").read_text())


class ShutdownTests(TestCase):
    def test_sigterm_ends_the_app(self):
        previous = signal.getsignal(signal.SIGTERM)
        self.addCleanup(signal.signal, signal.SIGTERM, previous)
        with patch.object(run.os, "nice"):
            run.install_shutdown_handler()
        handler = signal.getsignal(signal.SIGTERM)
        self.assertTrue(callable(handler))
        with self.assertRaises(SystemExit):
            handler(signal.SIGTERM, None)


class PollingTests(TestCase):
    def test_the_page_polls_slowly_when_idle_and_not_when_hidden(self):
        source = Path(panel.__file__).read_text()
        self.assertIn("setInterval(pollTestStatus, 1000);", source)
        self.assertNotIn("setInterval(refreshTestStatus, 1000);", source)
        self.assertIn("statusBusy || Date.now() < statusBusyUntil ? 1000 : 5000", source)
        self.assertIn("if (document.hidden) {{ whenVisible(refreshAutomatic); return; }}", source)
