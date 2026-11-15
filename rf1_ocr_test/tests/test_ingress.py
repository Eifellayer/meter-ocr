"""Exercise the HTTP handlers and the Home Assistant parent-frame contract."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from queue import Queue
import re
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request
from unittest import TestCase
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import panel
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
        self.preferences = self.root / "language.json"
        self.requested = Queue(maxsize=1)
        self.rules = dict(decimals=0, attempts=3, crop_mode="auto", polarity="auto",
                          crop="0,0,400,90", width=250)
        self.profiles = {}
        self.source = dict(mode="slfork", url="http://meter", camera="", reference="")
        self.setup_pending = True
        self.delivery = dict(enabled=False, review_minutes=240, delivery_hours=24, push="", target="")
        self.enterContext(patch.object(panel, "SUPERVISOR_ADDRESS", "127.0.0.1"))
        self.start_panel()

    def save_source(self, values):
        self.source = values
        self.setup_pending = False

    def start_panel(self):
        server, self.update = panel.start_panel(
            self.history, self.root / "current.jpg", self.root / "good.jpg",
            self.requested, 0, 3, lambda: dict(self.rules), self.rules.update,
            "0,0,400,90", 250, self.preview, lambda: load_preferences(self.preferences),
            lambda modes: atomic_write(self.preferences, json.dumps(modes).encode(), 0o600),
            lambda: dict(self.delivery), self.delivery.update,
            lambda: (dict(self.source), self.setup_pending), self.save_source,
            address=("127.0.0.1", 0),
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
                    crop="5,5,390,85", width=220)
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
        self.assertEqual((303, "./?saved=crop"), self.submit(
            "/ausschnitt-uebernehmen", checked_at=status["crop_id"]))
        self.assertEqual(("manual", "5,5,390,85", 220, 0),
                         (self.rules["crop_mode"], self.rules["crop"],
                          self.rules["width"], self.rules["decimals"]))

    def test_invalid_manual_crop_returns_localized_form_error(self):
        for language, message in (("en", "Check the form values"), ("de", "Bitte die Formulareingaben prüfen")):
            with self.subTest(language=language), self.assertRaises(HTTPError) as caught:
                self.request("/pruefen", data={"csrf": self.csrf, "lang": language, "crop_mode": "manual",
                                               "crop": "20,10,5,100", "width": 20})
            with caught.exception as response:
                self.assertEqual(400, response.code)
                self.assertIn(message, response.read().decode())
        self.assertTrue(self.requested.empty())

    def test_initial_source_selection_and_later_changes(self):
        self.assertIn('id="source-settings" open', self.request("/")[0])
        self.assertEqual(400, self.submit("/bildquelle", source_mode="esphome", camera="sensor.invalid")[0])
        self.assertEqual((303, "./?saved=source"),
                         self.submit("/bildquelle", source_mode="esphome", camera="camera.esp"))
        self.assertFalse(self.setup_pending)
        self.assertEqual("esphome", self.source["mode"])
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
                                           "comparison_decimals": 0}))
        status = json.loads(self.request("/automatic?lang=en")[0])
        self.assertEqual("0", status["reference"])
        self.assertIn("too old", status["detail"])
        self.assertEqual("problem", status["tone"])


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
                user, profile, forwarded = self.profiles[urlsplit(inner.path).query]
                script = (
                    "document.querySelector('home-assistant').hass = {"
                    f"user: {{id: '{user}'}}, "
                    "callWS: request => { window.calls++;"
                    "if (request.type !== 'frontend/get_user_data' || request.key !== 'language')"
                    "throw new Error('Unexpected HA command');"
                    f"return Promise.resolve({{value: {{language: '{profile}'}}}});"
                    "}};"
                )
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
                             mismatch=(USER_DE, "de", USER_EN))
        with serve(Parent) as parent, sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            page = browser.new_page(viewport={"width": 320, "height": 850}, locale="en-US")
            page.set_default_timeout(7000)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            frame = page.frame_locator("iframe")

            def expect_heading(title):
                frame.get_by_role("heading", name=title, exact=True).wait_for()
                self.assertTrue(frame.locator("html").evaluate(
                    "element => element.scrollWidth <= element.clientWidth"))

            page.goto(parent + "/?de")
            expect_heading("Gaszähler OCR-Kontrolle")
            self.assertEqual(1, page.evaluate("window.calls"))
            self.assertIn("Home Assistant: Deutsch", frame.locator("#language-select").inner_text())
            page.goto(parent + "/?en")
            expect_heading("Gas Meter OCR Verification")
            frame.locator("#manual-panel summary").first.click()
            frame.locator("#manual-form select[name=crop_mode]").select_option("manual")
            frame.locator("#start-check").click()
            frame.get_by_text("Request accepted", exact=True).wait_for()
            self.assertEqual("neutral", frame.locator("#test-box").get_attribute("data-result"))
            frame.locator("#language-select").select_option("de")
            expect_heading("Gaszähler OCR-Kontrolle")
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
            frame.get_by_text("Getesteten Bildausschnitt für die Automatik übernommen.", exact=True).wait_for()
            self.assertEqual("manual", self.rules["crop_mode"])
            frame.locator("#auto-form select[name=decimals]").select_option("2")
            frame.locator("#auto-form button").click()
            frame.get_by_text("Automatische Prüfregeln gespeichert.", exact=True).wait_for()
            self.assertEqual("de", frame.locator("#language-select").input_value())
            page.reload()
            expect_heading("Gaszähler OCR-Kontrolle")
            frame.locator("#language-select").select_option("auto")
            expect_heading("Gas Meter OCR Verification")
            page.set_viewport_size({"width": 1280, "height": 900})
            frame.locator("#manual-panel summary").first.click()
            frame.locator("#start-check").click()
            frame.get_by_text("Request accepted", exact=True).wait_for()
            self.assertEqual("neutral", frame.locator("#test-box").get_attribute("data-result"))
            for profile in ("unsupported", "mismatch"):
                page.goto(parent + "/?" + profile)
                expect_heading("Gas Meter OCR Verification")
                self.assertIn("Automatic (Home Assistant)", frame.locator("#language-select").inner_text())
            self.assertEqual(0, page.evaluate("window.calls"))
            self.history.write_text(json.dumps({"status": "match", "check_status": "match",
                                               "check_detail": "Bestätigt", "comparison_decimals": 2}))
            page.goto(parent + "/?en")
            frame.get_by_text("Meter reading confirmed", exact=True).wait_for()
            self.assertEqual("ok", frame.locator("#automatic-banner").get_attribute("data-tone"))
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
            frame.locator("#notification-settings summary").first.click()
            frame.get_by_text("How are notifications sent?", exact=False).click()
            frame.get_by_text("Leave both optional fields blank", exact=False).wait_for()
            self.assertEqual([], errors)
            browser.close()
