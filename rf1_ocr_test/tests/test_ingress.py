"""Exercise the HTTP handlers and the Home Assistant parent-frame contract."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import os
from pathlib import Path
from queue import Queue
import re
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request
from unittest import TestCase
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import panel
from checks import FALLBACK_NOTICE
from consumption import FALLBACK_PLAUSIBLE
from language import browser_locale, load_preferences
from run import atomic_write
from transport import open_core

USER_DE = "a" * 32
USER_EN = "b" * 32


@contextmanager
def serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class IngressFixture(TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.history = self.root / "history.json"
        self.preview = self.root / "preview.jpg"
        self.automatic_preview = self.root / "automatic-preview.jpg"
        self.preferences = self.root / "language.json"
        self.requested = Queue(maxsize=1)
        self.rules = dict(decimals=0, attempts=3, crop_mode="auto", polarity="auto",
                          crop="0,0,400,90", width=250)
        self.profiles = {}
        self.source = dict(mode="slfork", url="http://meter", camera="", reference="")
        self.setup_pending = True
        self.source_selected = False
        self.suggestions = []
        self.reset_state = "idle"
        self.activity = {"state": "waiting", "detail": "Wartet auf die nächste automatische Prüfung."}
        self.paused = False
        self.delivery = dict(enabled=False, review_minutes=240, delivery_hours=24, push="", target="")
        self.enterContext(patch.object(panel, "SUPERVISOR_ADDRESS", "127.0.0.1"))
        self.start_panel()

    def save_source(self, values):
        self.source = values
        self.setup_pending = False
        self.source_selected = True

    def skip_setup(self):
        self.setup_pending = False

    def start_panel(self):
        def request_reset():
            self.reset_state = "pending"
            return self.reset_state

        server, self.update, self.reset_manual_progress = panel.start_panel(
            self.history, self.root / "current.jpg", self.root / "good.jpg",
            self.requested, 0, 3, lambda: dict(self.rules), self.rules.update,
            "0,0,400,90", 250, self.preview, lambda: load_preferences(self.preferences),
            lambda modes: atomic_write(self.preferences, json.dumps(modes).encode(), 0o600),
            lambda: dict(self.delivery), self.delivery.update,
            lambda: ({**self.source, "selected": self.source_selected}, self.setup_pending), self.save_source,
            address=("127.0.0.1", 0), skip_setup=self.skip_setup,
            request_factory_reset=request_reset, get_reset_status=lambda: self.reset_state,
            automatic_preview=self.automatic_preview, get_activity=lambda: dict(self.activity),
            discover_sources=lambda: self.suggestions,
            get_auto_paused=lambda: self.paused,
            save_auto_paused=lambda value: setattr(self, "paused", value),
        )
        self.server = server
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.base = f"http://127.0.0.1:{server.server_port}"
        page, _ = self.request("/")
        self.csrf = re.search(r'name="csrf" value="([^"]+)"', page)[1]

    def request(self, path, *, user=USER_DE, data=None, accept="de"):
        headers = {"Accept-Language": accept}
        if user:
            headers["X-Remote-User-Id"] = user
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = urlencode(data).encode()
        with open_core(Request(self.base + path, data=data, headers=headers)) as result:
            return result.read().decode(), result.status

    def submit(self, path, *, user=USER_DE, **data):
        with self.assertRaises(HTTPError) as caught:
            self.request(path, user=user, data=dict(csrf=self.csrf, **data))
        return caught.exception.code, caught.exception.headers.get("Location")


class IngressTests(IngressFixture):
    def test_factory_reset_clears_manual_result_after_pending_response(self):
        self.setup_pending = False
        form = dict(decimals=0, attempts=3, crop_mode="auto", polarity="auto")
        self.assertEqual((303, "./?test=queued"), self.submit("/pruefen", **form))
        job = self.requested.get_nowait()
        self.preview.write_bytes(b"preview")
        self.update(job["request_id"], "done", "Prüfung beendet.", 3, 100,
                    outcome="match", preview=True, ocr="12345")
        self.assertTrue(json.loads(self.request("/status")[0])["preview"])

        self.assertEqual((303, "./?reset=pending&ui=settings"), self.submit("/werkreset"))
        self.assertIn("Werkreset läuft noch.", self.request("/?reset=pending&ui=settings")[0])
        self.reset_manual_progress()
        self.reset_state = "done"
        self.update(job["request_id"], "done", "Veraltetes Ergebnis", preview=True)
        status = json.loads(self.request("/status")[0])
        self.assertEqual(("idle", None, False), (status["phase"], status["ocr"], status["preview"]))
        page = self.request("/?reset=pending&ui=settings")[0]
        self.assertIn("Werkseinstellungen wiederhergestellt.", page)
        self.assertIn('data-first-run="true"', page)

    def test_first_missing_image_has_an_immediate_yellow_status(self):
        self.history.write_text(json.dumps({"check_status": "capture_unavailable", "failure_since": time.time()}))
        status = json.loads(self.request("/automatic")[0])
        self.assertEqual(("warning", "Noch kein aktuelles Zählerbild"), (status["tone"], status["heading"]))
        self.assertIn("versucht es automatisch erneut", status["detail"])

    def test_mismatch_immediately_explains_what_to_do(self):
        self.history.write_text(json.dumps({"check_status": "difference", "failure_since": time.time()}))
        status = json.loads(self.request("/automatic")[0])
        self.assertEqual(("warning", "Ablesung und Vergleichswert weichen ab"),
                         (status["tone"], status["heading"]))
        self.assertIn("prüft automatisch erneut", status["detail"])
        self.assertIn("direkt am Zähler", status["detail"])
        status_en = json.loads(self.request("/automatic?lang=en")[0])
        self.assertIn("value on the meter itself", status_en["detail"])

    def test_last_digit_warning_and_optional_precision_mode(self):
        self.rules.update(decimals=3)
        page = self.request("/")[0]
        self.assertIn('data-precision-options >', page)
        self.assertNotIn('name="precision_mode" value="1" checked', page)
        form = dict(decimals=3, attempts=3, crop_mode="auto", polarity="auto", precision_mode=1)
        self.assertEqual((303, "./?saved=1"), self.submit("/automatik", **form))
        self.assertTrue(self.rules["precision_mode"])
        self.assertIn('name="precision_mode" value="1" checked', self.request("/")[0])
        self.rules["precision_mode"] = False
        self.history.write_text(json.dumps({
            "check_status": "match_with_warning", "comparison_decimals": 3,
            "check_detail": "Die ersten zwei Nachkommastellen stimmen überein. Die dritte Stelle bleibt unbestätigt.",
        }))
        status = json.loads(self.request("/automatic")[0])
        self.assertEqual(("warning", "Prüfung bestanden mit Hinweis"), (status["tone"], status["heading"]))


    def test_automatic_status_explains_three_retry_attempts_and_one_hour_wait(self):
        self.history.write_text(json.dumps({
            "check_status": "ocr_unclear", "failure_attempts": 2,
            "next_check_at": time.time() + 3500,
        }))
        status = json.loads(self.request("/automatic")[0])
        self.assertEqual(2, status["failure_attempts"])
        self.assertIn("2 von 3", status["recovery_notice"])
        self.assertNotIn("fünf Minuten", status["recovery_notice"])
        self.assertGreater(status["next_check"] - time.time(), 300)
        self.assertFalse(status["retry_suppressed"])

        self.history.write_text(json.dumps({
            "check_status": "ocr_unclear", "failure_attempts": 3,
            "retry_suppressed": True, "next_check_at": time.time() + 3_600,
        }))
        status = json.loads(self.request("/automatic")[0])
        self.assertIn("3 automatische Prüfungen fehlgeschlagen", status["recovery_notice"])
        self.assertIn("höheren Zählerstand", status["recovery_notice"])
        self.assertNotIn("einer Stunde", status["recovery_notice"])
        self.assertTrue(status["retry_suppressed"])

    def test_automatic_checks_can_be_paused_and_resumed_without_blocking_manual_tests(self):
        self.assertEqual((303, "./?paused=1"), self.submit("/automatik-pause", paused="1"))
        page, _ = self.request("/")
        self.assertTrue(self.paused)
        self.assertIn('id="paused-notice"', page)
        self.assertIn("Automatik pausiert", page)
        self.assertNotIn('id="paused-notice" hidden', page)
        self.assertIn('id="manual-form"', page)
        status = json.loads(self.request("/automatic")[0])
        self.assertTrue(status["paused"])
        self.assertEqual((303, "./?paused=0"), self.submit("/automatik-pause", paused="0"))
        self.assertFalse(self.paused)
        self.assertFalse(json.loads(self.request("/automatic")[0])["paused"])
        self.assertIn('id="pause-auto-form"', self.request("/")[0])

    def test_language_defaults_and_is_user_specific_after_restart(self):
        self.assertEqual("en", browser_locale("fr-FR,de;q=.4,en-US;q=.8"))
        self.assertEqual("de", browser_locale("en;q=0,fr-FR"))
        self.assertEqual((303, "./"), self.submit("/sprache", mode="en"))
        page, _ = self.request("/")
        self.assertIn('<html lang="en">', page)
        self.assertIn('value="en" selected', page)
        self.assertNotIn("frontend/get_user_data", page)
        page, _ = self.request("/?ui=de", user=USER_EN, accept="en")
        self.assertIn('<html lang="de">', page)
        self.assertIn("Automatisch (Home Assistant: Deutsch)", page)
        self.start_panel()
        self.assertIn('value="en" selected', self.request("/")[0])
        self.assertEqual((303, "./"), self.submit("/sprache", mode="auto"))
        self.assertIn("frontend/get_user_data", self.request("/")[0])

    def test_unknown_user_keeps_selection_through_navigation_without_storing_it(self):
        self.assertEqual((303, "./?mode=en"), self.submit("/sprache", user=None, mode="en"))
        self.assertFalse(self.preferences.exists())
        self.assertIn('value="en" selected', self.request("/?mode=en", user=None)[0])
        verdict, location = self.submit("/automatik", user=None, mode="en", lang="en",
                                        decimals=2, attempts=4, crop_mode="auto", polarity="dark")
        self.assertEqual((303, "./?saved=1&mode=en"), (verdict, location))
        self.assertEqual((2, 4, "dark"),
                         (self.rules["decimals"], self.rules["attempts"], self.rules["polarity"]))

    def test_csrf_and_supervisor_address_are_required(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/sprache", data={"mode": "en"})
        self.assertEqual(403, caught.exception.code)
        with patch.object(panel, "SUPERVISOR_ADDRESS", "172.30.32.2"):
            with self.assertRaises(HTTPError) as caught:
                self.request("/")
        self.assertEqual(403, caught.exception.code)

    def test_queue_does_not_replace_a_running_job_and_crop_is_bound_to_result(self):
        form = dict(decimals=2, attempts=3, crop_mode="manual", polarity="dark",
                    crop="1925,5,2005,390", width=220, rotation=90)
        self.assertEqual((303, "./?test=queued"), self.submit("/pruefen", **form))
        job = self.requested.get_nowait()
        self.update(job["request_id"], "ocr", "OCR-Versuch 2 von 3 läuft …", 1)
        self.assertEqual((303, "./?test=busy"), self.submit("/pruefen", **form))
        self.assertTrue(self.requested.empty())
        status = json.loads(self.request("/status?lang=en")[0])
        self.assertEqual("ocr", status["phase"])
        self.assertIn("2 of 3", status["message"])
        self.assertEqual(409, self.submit("/ausschnitt-uebernehmen", checked_at="100.0")[0])
        self.preview.write_bytes(b"test image")
        self.history.write_text(json.dumps({"manual_result": {
            "checked_at": 100.0, "settings": job, "can_apply_crop": True, "status": "match",
        }}))
        self.update(job["request_id"], "done", "Prüfung beendet.", 2, 100.0,
                    outcome="match", preview=True, can_apply_crop=True, ocr="12345.120")
        status = json.loads(self.request("/status?lang=en")[0])
        self.assertEqual("12345.120", status["ocr"])
        self.assertEqual(409, self.submit("/ausschnitt-uebernehmen", checked_at="90.0")[0])
        self.assertEqual((303, "./?saved=crop&ui=settings"), self.submit(
            "/ausschnitt-uebernehmen", checked_at=status["crop_id"]))
        self.assertEqual(("manual", "1925,5,2005,390", 220, 90, 0),
                         (self.rules["crop_mode"], self.rules["crop"], self.rules["width"],
                          self.rules["rotation"], self.rules["decimals"]))

    def test_manual_test_accepts_only_a_small_jpeg_or_png_upload(self):
        image = Image.new("RGB", (32, 24), "white")
        encoded = BytesIO()
        image.save(encoded, format="JPEG")
        picture = encoded.getvalue()
        boundary = "meter-ocr-test-boundary"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"csrf\"\r\n\r\n{self.csrf}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"meter.jpg\"\r\n"
            "Content-Type: image/jpeg\r\n\r\n"
        ).encode() + picture + f"\r\n--{boundary}--\r\n".encode()
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}",
                   "X-Remote-User-Id": USER_DE}
        with self.assertRaises(HTTPError) as caught:
            open_core(Request(self.base + "/pruefen", data=body, headers=headers))
        self.assertEqual(303, caught.exception.code)
        self.assertEqual(picture, self.requested.get_nowait()["image"])

        unsupported = body.replace(b"image/jpeg", b"image/gif")
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        with self.assertRaises(HTTPError) as caught:
            open_core(Request(self.base + "/pruefen", data=unsupported, headers=headers))
        self.assertEqual(400, caught.exception.code)
        self.assertTrue(self.requested.empty())

        oversized = body.replace(picture, b"x" * (panel.MAX_MANUAL_IMAGE_BYTES + 1))
        with self.assertRaises(HTTPError) as caught:
            open_core(Request(self.base + "/pruefen", data=oversized, headers=headers))
        self.assertEqual(400, caught.exception.code)
        self.assertTrue(self.requested.empty())

    def test_invalid_manual_crop_returns_localized_form_error(self):
        for language, message in (("en", "Check the form values"), ("de", "Bitte die Formulareingaben prüfen")):
            with self.subTest(language=language), self.assertRaises(HTTPError) as caught:
                self.request("/pruefen", data={"csrf": self.csrf, "lang": language, "crop_mode": "manual",
                                               "crop": "20,10,5,100", "width": 20})
            with caught.exception as response:
                self.assertEqual(400, response.code)
                self.assertIn(message, response.read().decode())
        self.assertTrue(self.requested.empty())

    def test_manual_options_and_fallback_value_persist_for_the_next_click(self):
        values = {"polarity": "dark", "decimals": 1, "attempts": 4, "crop_mode": "manual",
                  "crop": "10,10,410,110", "width": 300, "manual_reference": "12345.6"}
        self.assertEqual((303, "./?test=queued"), self.submit("/pruefen", **values))
        self.assertTrue((self.root / "manual-test-settings.json").exists())
        self.assertEqual("12345.6", self.requested.get_nowait()["manual_reference"])
        page = self.request("/")[0]
        self.assertIn('name="manual_reference" form="manual-form" value="12345.6"', page)
        self.assertIn('<option value="dark" selected>', page)
        self.assertIn('<option value="1" selected>1 Nachkommastelle</option>', page)

    def test_initial_source_selection_and_later_changes(self):
        page = self.request("/")[0]
        self.assertIn('id="source-settings" open', page)
        self.assertIn('id="wizard-source-mode" required><option value="" selected>', page)
        self.assertIn('class="source-mode-guide"', page)
        self.assertEqual(400, self.submit("/einrichtung", camera="camera.esp")[0])
        self.assertEqual(400, self.submit("/bildquelle", source_mode="", camera="camera.esp")[0])
        self.skip_setup()
        self.assertIn('id="wizard-source-mode" required><option value="" selected>', self.request("/")[0])
        self.assertEqual(400, self.submit("/bildquelle", source_mode="esphome", camera="sensor.invalid")[0])
        self.assertEqual((303, "./?saved=source"),
                         self.submit("/bildquelle", source_mode="esphome", camera="camera.esp"))
        self.assertFalse(self.setup_pending)
        self.assertEqual("esphome", self.source["mode"])
        self.assertIn('<option value="esphome" selected>ESPHome / Kamera</option>', self.request("/")[0])
        self.assertNotIn('id="source-settings" open', self.request("/")[0])
        self.assertEqual((303, "./?saved=source"),
                         self.submit("/bildquelle", source_mode="camera",
                                     camera="camera.esp", reference="sensor.meter"))
        self.assertEqual("sensor.meter", self.source["reference"])
        self.submit("/bildquelle", source_mode="camera", reference="")
        self.assertEqual("", self.source["reference"])
        self.assertEqual((303, "./?saved=source"),
                         self.submit("/bildquelle", source_mode="slfork", url="http://new-meter"))
        self.assertEqual("http://new-meter", self.source["url"])
        self.assertEqual((303, "./?saved=source"),
                         self.submit("/bildquelle", source_mode="slfork", esp_camera_only=1))
        self.assertEqual("slfork_camera", self.source["mode"])
        self.assertIn('name="esp_camera_only" value="1" checked', self.request("/")[0])
        self.assertEqual((303, "./?saved=source"), self.submit("/bildquelle", source_mode="slfork"))
        self.assertEqual("slfork", self.source["mode"])
        self.assertEqual("http://new-meter", self.source["url"])

    def test_setup_wizard_saves_source_meter_format_crop_schedule_and_notifications(self):
        page = self.request("/")[0]
        self.assertIn('id="setup-dialog"', page)
        self.assertIn('data-first-run="true"', page)
        self.assertIn('setupDialog.showModal()', page)
        self.assertIn('name="integer_digits"', page)
        values = {
            "source_mode": "camera", "camera": "camera.meter", "reference": "sensor.meter",
            "url": "http://meter", "meter_display": "mixed", "integer_digits": 6,
            "fraction_digits": 2, "decimals": 1, "attempts": 4, "polarity": "dark",
            "crop_mode": "manual", "crop": "10,10,410,110", "width": 300, "rotation": 0,
            "interval_minutes": 30, "max_flow": "6.5", "fallback_value": "123456.7",
            "fallback_time": time.strftime("%Y-%m-%dT%H:%M", time.localtime()),
            "notifications_enabled": 1, "review_minutes": 60, "delivery_hours": 0,
            "push": "notify.mobile_app_phone", "target": "notify.email",
        }
        self.assertEqual((303, "./?saved=setup&ui=overview"), self.submit("/einrichtung", **values))
        page = self.request("/?saved=setup&ui=overview")[0]
        self.assertNotIn('aria-labelledby="tab-overview" hidden', page)
        self.assertIn('id="automatic-progress"', page)
        self.assertIn('id="setup-image-test"', page)
        self.assertEqual("camera", self.source["mode"])
        self.assertEqual("sensor.meter", self.source["reference"])
        self.assertEqual((6, 2, "mixed", 1), (self.rules["integer_digits"], self.rules["fraction_digits"],
                                               self.rules["meter_display"], self.rules["decimals"]))
        self.assertEqual((30, 6500, "123456.7"), (self.rules["interval_minutes"],
                                                   self.rules["max_flow_lph"],
                                                   self.rules["fallback_value"]))
        self.assertTrue(self.delivery["enabled"])
        values.update(source_mode="slfork", esp_camera_only=1, camera="")
        self.assertEqual((303, "./?saved=setup&ui=overview"), self.submit("/einrichtung", **values))
        self.assertEqual("slfork_camera", self.source["mode"])
        self.assertEqual("http://meter", self.source["url"])

    def test_setup_wizard_rejects_fallback_without_timestamp_and_keeps_old_settings(self):
        before = dict(self.source)
        values = {
            "source_mode": "camera", "camera": "camera.meter", "reference": "",
            "meter_display": "rollers", "integer_digits": 5, "fraction_digits": 3,
            "decimals": 0, "attempts": 3, "polarity": "auto", "crop_mode": "auto",
            "crop": "0,0,400,90", "width": 250, "rotation": 0,
            "interval_minutes": 60, "max_flow": "6", "fallback_value": "12345.6",
            "fallback_time": "", "review_minutes": 240, "delivery_hours": 24,
            "push": "", "target": "",
        }
        self.assertEqual(400, self.submit("/einrichtung", **values)[0])
        self.assertEqual(before, self.source)

    def test_notification_form_saves_and_can_disable_channels(self):
        settings = dict(review_minutes=15, delivery_hours=0, push="notify.mobile_app_phone",
                        target="notify.email")
        self.assertEqual((303, "./?saved=notifications"),
                         self.submit("/benachrichtigungen", enabled=1, **settings))
        self.assertEqual(dict(enabled=True, **settings), self.delivery)
        self.assertEqual(400, self.submit("/benachrichtigungen", review_minutes=0, delivery_hours=0)[0])
        self.assertEqual((303, "./?saved=notifications"),
                         self.submit("/benachrichtigungen", **settings))
        self.assertFalse(self.delivery["enabled"])

    def test_current_automatic_failure_takes_precedence_over_previous_match(self):
        self.history.write_text(json.dumps({"status": "match", "last_reference": 0,
                                           "check_status": "stale_sample",
                                           "check_detail": "Das Bild ist zu alt oder wurde schon ausgewertet.",
                                           "failure_since": time.time() - 3600,
                                           "comparison_decimals": 0}))
        status = json.loads(self.request("/automatic?lang=en")[0])
        self.assertEqual("0", status["reference"])
        self.assertIn("too old", status["detail"])
        self.assertEqual("warning", status["tone"])

    def test_fallback_details_appear_after_one_hour_and_keep_the_reference_timestamp(self):
        now = time.time()
        saved = {"check_status": "slfork_unclear", "failure_since": now - 3550,
                 "check_detail": f"{FALLBACK_NOTICE} {FALLBACK_PLAUSIBLE}",
                 "last_reference": "12346.0416", "last_reference_time": now - 3660,
                 "last_reference_is_fallback": True}
        self.history.write_text(json.dumps(saved))
        status = json.loads(self.request("/automatic?lang=en")[0])
        self.assertEqual(("warning", "Last check failed", "", ""),
                         (status["tone"], status["heading"], status["detail"], status["incident"]))
        self.assertTrue(status["reference_is_fallback"])
        self.assertEqual(saved["last_reference_time"], status["reference_time"])
        self.history.write_text(json.dumps({**saved, "failure_since": now - 3600}))
        status = json.loads(self.request("/automatic?lang=en")[0])
        self.assertEqual("warning", status["tone"])
        self.assertIn("fallback reading. OCR increase looks plausible", status["detail"])
        self.assertTrue(status["incident"])
        self.history.write_text(json.dumps({**saved, "failure_since": now - 3600, "capture_failure_since": now,
                                           "check_status": "capture_unavailable"}))
        self.assertEqual("warning", json.loads(self.request("/automatic")[0])["tone"])
        self.history.write_text(json.dumps({**saved, "failure_since": now - 3700,
                                           "capture_failure_since": now - 3600,
                                           "check_status": "capture_unavailable"}))
        self.assertEqual("problem", json.loads(self.request("/automatic")[0])["tone"])

    def test_interval_save_updates_a_legacy_schedule(self):
        now = time.time()
        self.history.write_text(json.dumps({"check_status": "match", "next_check_at": now + 3600}))
        form = dict(decimals=0, attempts=3, polarity="auto", crop_mode="auto")
        self.assertIn('name="interval_minutes" type="number"', self.request("/")[0])
        self.assertEqual((303, "./?saved=1"), self.submit("/automatik", interval_minutes=15, **form))
        status = json.loads(self.request("/automatic")[0])
        self.assertEqual(15, self.rules["interval_minutes"])
        self.assertEqual(now + 900, status["next_check"])
        self.assertEqual(now, status["last_check"])
        self.assertEqual(400, self.submit("/automatik", interval_minutes=0, **form)[0])
        self.assertEqual(15, self.rules["interval_minutes"])
        crop = dict(crop_mode="manual", crop="1,2,304,88", width=270)
        self.assertEqual((303, "./?saved=1"), self.submit("/automatik", **{**form, **crop}))
        page = self.request("/")[0].split('id="manual-form"', 1)[1].split("</form>", 1)[0]
        self.assertIn('value="manual" selected', page)
        self.assertIn('value="1,2,304,88"', page)


class RedirectTests(TestCase):
    def test_core_redirect_does_not_forward_credentials(self):
        paths = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                paths.append(self.path)
                self.send_response(302)
                self.send_header("Location", "/elsewhere")
                self.end_headers()

            def log_message(self, *_):
                pass

        with serve(Handler) as base:
            with self.assertRaises(HTTPError) as caught:
                open_core(Request(base + "/core", headers={"Authorization": "Bearer test-only"}))
            self.assertEqual(302, caught.exception.code)
        self.assertEqual(["/core"], paths)


class BrowserTests(IngressFixture):
    def test_selecting_a_discovered_meter_prefills_the_wizard(self):
        from playwright.sync_api import sync_playwright

        self.suggestions = [
            {"mode": "slfork", "url": "http://esp-meter", "label": "Gas meter"},
            {"mode": "esphome", "camera": "camera.water_meter", "label": "Water meter"},
        ]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            page = browser.new_page(locale="de-DE")
            page.set_default_timeout(7000)
            page.goto(self.base)
            mode = page.locator("#wizard-source-mode")
            self.assertEqual("", mode.input_value())
            discovered = page.locator("#wizard-discovered-source")
            discovered.select_option(label="AI on the Edge · Gas meter")
            self.assertEqual("slfork", mode.input_value())
            self.assertEqual("http://esp-meter", page.locator("#wizard-source-url input").input_value())
            page.locator("#wizard-esp-camera-only input").check()
            discovered.select_option(label="Kamera · Water meter")
            self.assertEqual("esphome", mode.input_value())
            self.assertEqual("camera.water_meter", page.locator("#wizard-source-camera input").input_value())
            self.assertFalse(page.locator("#wizard-esp-camera-only").is_visible())
            browser.close()

    def test_automatic_status_and_image_update_when_a_check_runs(self):
        from playwright.sync_api import sync_playwright

        self.setup_pending = False
        self.activity = {"state": "working", "detail": "Warte auf Bild und Messwerte vom ESP …"}
        current = self.root / "current.jpg"
        Image.new("RGB", (240, 60), "white").save(current, "JPEG")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            page = browser.new_page(locale="de-DE")
            page.set_default_timeout(7000)
            page.goto(self.base)
            page.locator("#automatic-progress").wait_for(state="visible")
            page.locator("#automatic-images summary").click()
            preview = page.locator("#test-preview-image")
            self.assertEqual(240, preview.evaluate("async image => { await image.decode(); return image.naturalWidth; }"))
            self.assertFalse(page.locator("#preview-legend").is_visible())
            page.wait_for_function("document.querySelector('.activity-status').dataset.offline === 'false'")
            Image.new("RGB", (200, 45), "white").save(self.automatic_preview, "JPEG")
            self.activity = {"state": "working", "detail": "Bild wird vorbereitet.", "completed": 2, "total": 5}
            page.wait_for_function("document.querySelector('#automatic-progress').value === 2")
            page.wait_for_function("document.querySelector('#test-preview-image').naturalWidth === 200")
            self.assertTrue(page.locator("#preview-legend").is_visible())
            self.activity = {"state": "waiting", "detail": "Wartet auf die nächste automatische Prüfung."}
            page.locator("#automatic-progress").wait_for(state="hidden")
            self.assertEqual("false", page.locator(".activity-status").get_attribute("data-offline"))
            browser.close()

    def test_profile_and_manual_override_on_a_narrow_screen(self):
        from playwright.sync_api import sync_playwright

        class Parent(BaseHTTPRequestHandler):
            def proxy(inner):
                url = urlsplit(inner.path)
                _, _, ingress_user, endpoint = url.path.split("/", 3)
                upstream = self.base + "/" + endpoint + ("?" + url.query if url.query else "")
                length = int(inner.headers.get("Content-Length", 0))
                headers = {name: inner.headers[name] for name in ("Content-Type", "Accept-Language")
                           if name in inner.headers}
                headers["X-Remote-User-Id"] = ingress_user
                request = Request(upstream, data=inner.rfile.read(length) if length else None,
                                  headers=headers, method=inner.command)
                try:
                    response = open_core(request)
                except HTTPError as error:
                    response = error
                with response:
                    inner.send_response(response.code)
                    for name in ("Content-Type", "Content-Length", "Location", "Cache-Control"):
                        if name in response.headers:
                            inner.send_header(name, response.headers[name])
                    inner.end_headers()
                    inner.wfile.write(response.read())

            def do_POST(inner):
                inner.proxy()

            def do_GET(inner):
                if inner.path.startswith("/ingress/"):
                    inner.proxy()
                    return
                if inner.path == "/favicon.ico":
                    inner.send_error(404)
                    return
                profile_data = self.profiles[urlsplit(inner.path).query]
                user, profile, forwarded = profile_data[:3]
                delay_ms = profile_data[3] if len(profile_data) > 3 else 0
                script = (
                    "document.querySelector('home-assistant').hass = {"
                    f"user: {{id: '{user}'}}, "
                    "callWS: request => { window.calls++;"
                    "if (request.type !== 'frontend/get_user_data' || request.key !== 'language')"
                    "throw new Error('Unexpected HA command');"
                    "return Promise.resolve({value: {language: window.haLanguage}});"
                    "}};"
                )
                script = f"window.haLanguage='{profile}';{script}"
                if delay_ms:
                    script = f"setTimeout(() => {{{script}}}, {delay_ms});"
                result = (f"<home-assistant></home-assistant><script>window.calls=0;{script}</script>"
                          f"<iframe src='/ingress/{forwarded}/' style='width:100%;height:1000px'></iframe>").encode()
                inner.send_response(200)
                inner.send_header("Content-Type", "text/html")
                inner.end_headers()
                inner.wfile.write(result)

            def log_message(self, *_):
                pass

        self.profiles.update(en=(USER_EN, "en-US", USER_EN), de=(USER_DE, "de-AT", USER_DE),
                             unsupported=(USER_EN, "fr-FR", USER_EN),
                             mismatch=(USER_DE, "de", USER_EN),
                             late_de=(USER_DE, "de-AT", USER_DE, 900))
        with serve(Parent) as parent, sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            page = browser.new_page(viewport={"width": 320, "height": 850}, locale="en-US")
            page.set_default_timeout(7000)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            frame = page.frame_locator("iframe")

            def expect_language(language):
                heading = frame.locator(f"html[lang='{language}'] h1")
                heading.wait_for()
                self.assertEqual("AI Meter Reader", heading.inner_text())
                self.assertTrue(frame.locator("html").evaluate(
                    "element => element.scrollWidth <= element.clientWidth"))

            page.goto(parent + "/?de")
            expect_language("de")
            self.assertEqual(2, page.evaluate("window.calls"))
            self.assertIn("Home Assistant: Deutsch", frame.locator("#language-select").inner_text())
            page.goto(parent + "/?late_de")
            expect_language("de")
            self.assertEqual(2, page.evaluate("window.calls"))
            page.goto(parent + "/?en")
            expect_language("en")
            page.evaluate("window.haLanguage='de-AT'")
            expect_language("de")
            page.evaluate("window.haLanguage='en-US'")
            expect_language("en")
            if frame.locator("#setup-dialog").evaluate("dialog => dialog.open"):
                frame.locator("#setup-skip").click()
            frame.locator("#open-manual-settings").click()
            frame.locator("#manual-form select[name=crop_mode]").select_option("manual")
            frame.locator("#manual-form input[name=crop]").fill("0,0,90,400")
            frame.locator("#manual-form select[name=rotation]").select_option("90")
            frame.locator("#start-check").click()
            frame.get_by_text("Request accepted", exact=True).wait_for()
            frame.locator("#test-progress").wait_for(state="visible")
            self.assertEqual("neutral", frame.locator("#test-box").get_attribute("data-result"))
            frame.locator("#language-select").select_option("de")
            expect_language("de")
            frame.get_by_text("Anfrage angenommen", exact=True).wait_for()
            job = self.requested.get(timeout=2)
            Image.new("RGB", (400, 90), "white").save(self.preview, "JPEG")
            self.history.write_text(json.dumps({"manual_result": {
                "checked_at": 110.0, "settings": job, "can_apply_crop": True, "status": "match",
            }}))
            self.update(job["request_id"], "done", "Prüfung beendet.", 1, 110.0,
                        outcome="match", detail="Bestätigt: Volle Kubikmeter stimmen überein.",
                        readings=["12345.???"], ocr="12345.???", reference="12345.000",
                        preview=True, can_apply_crop=True)
            frame.get_by_text("Test erfolgreich", exact=True).wait_for()
            self.assertEqual("match", frame.locator("#test-box").get_attribute("data-result"))
            self.assertEqual("12345.???", frame.locator("#manual-ocr").inner_text())
            frame.locator("#test-preview-image").wait_for()
            self.assertEqual(400, frame.locator("#test-preview-image").evaluate(
                "async image => { await image.decode(); return image.naturalWidth; }"))
            frame.locator("#apply-crop-form button").click()
            frame.locator("#tab-settings").click()
            automatic_settings = frame.locator("#automatic-settings")
            if not automatic_settings.evaluate("section => section.open"):
                automatic_settings.locator("summary").click()
            frame.locator("#view-settings").wait_for(state="visible")
            self.assertEqual("manual", self.rules["crop_mode"])
            self.assertEqual(90, self.rules["rotation"])
            frame.locator("#auto-form select[name=decimals]").select_option("2")
            frame.locator("#auto-form input[name=max_flow]").fill("4,5")
            self.assertEqual("60", frame.locator("#auto-form input[name=interval_minutes]").input_value())
            frame.locator("#auto-form input[name=interval_minutes]").fill("15")
            frame.locator("#auto-form button").click()
            frame.get_by_text("Automatische Prüfregeln gespeichert.", exact=True).wait_for()
            self.assertEqual(4500, self.rules["max_flow_lph"])
            self.assertEqual(15, self.rules["interval_minutes"])
            self.assertEqual("de", frame.locator("#language-select").input_value())
            page.reload()
            expect_language("de")
            frame.locator("#language-select").select_option("auto")
            expect_language("en")
            page.set_viewport_size({"width": 1280, "height": 900})
            self.assertIsNone(frame.locator("#manual-panel").get_attribute("open"))
            frame.locator("#start-check").click()
            frame.get_by_text("Request accepted", exact=True).wait_for()
            self.assertEqual("neutral", frame.locator("#test-box").get_attribute("data-result"))
            for profile in ("unsupported", "mismatch"):
                page.goto(parent + "/?" + profile)
                expect_language("en")
                self.assertIn("Automatic (Home Assistant)", frame.locator("#language-select").inner_text())
            self.assertEqual(0, page.evaluate("window.calls"))
            self.history.write_text(json.dumps({"status": "match", "check_status": "match",
                                               "check_detail": "Bestätigt", "comparison_decimals": 2}))
            page.goto(parent + "/?en")
            frame.get_by_text("Meter reading confirmed", exact=True).wait_for()
            self.assertEqual("ok", frame.locator("#automatic-banner").get_attribute("data-tone"))
            self.history.write_text(json.dumps({"check_status": "slfork_unclear", "comparison_decimals": 2,
                                               "failure_since": time.time(), "last_reference": "12346.0416",
                                               "last_reference_is_fallback": True, "last_reference_time": 1709999000}))
            page.reload()
            frame.get_by_text("Last check failed", exact=True).wait_for()
            self.assertEqual("warning", frame.locator("#automatic-banner").get_attribute("data-tone"))
            self.assertIn("ESP fallback reading", frame.locator("#automatic-reference-note").inner_text())
            failed = {"check_status": "capture_unavailable", "failure_since": 100, "comparison_decimals": 2}
            self.history.write_text(json.dumps(failed))
            page.reload()
            frame.get_by_text("Check the meter reading", exact=True).wait_for()
            frame.get_by_role("button", name="Ignore").click()
            frame.locator("#automatic-banner").wait_for(state="hidden")
            page.reload()
            frame.locator("#automatic-banner").wait_for(state="hidden")
            self.history.write_text(json.dumps({**failed, "failure_since": 200}))
            page.reload()
            frame.get_by_text("Check the meter reading", exact=True).wait_for()
            frame.locator("#tab-settings").click()
            frame.locator("#notification-settings summary").first.click()
            frame.get_by_text("How are notifications sent?", exact=False).click()
            frame.get_by_text("Leave both optional fields blank", exact=False).wait_for()
            self.assertEqual([], errors)
            browser.close()
