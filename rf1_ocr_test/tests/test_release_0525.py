"""0.5.25: add the freshly installed meter camera to Home Assistant right from the setup wizard."""

import json
import os
import unittest
from unittest.mock import patch

import panel
from test_ingress import IngressFixture

import kit_camera

FLOW = "0123456789abcdef0123456789abcdef"
OTHER = "fedcba9876543210fedcba9876543210"


def flows(*items):
    return lambda token, message: list(items) if message == {"type": "config_entries/flow/progress"} else None


def flow(flow_id=FLOW, name="Zählerkamera a1b2c3", handler="esphome", source="zeroconf"):
    return {"flow_id": flow_id, "handler": handler, "step_id": "discovery_confirm",
            "context": {"source": source, "title_placeholders": {"name": name}, "unique_id": "aa:bb"}}


class FakeSocket:
    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []
        self.closed = False

    def recv(self):
        return json.dumps(self.replies.pop(0))

    def send(self, text):
        self.sent.append(json.loads(text))

    def close(self):
        self.closed = True


class KitCameraTest(unittest.TestCase):
    def test_only_discovered_meter_cameras_are_listed(self):
        command = flows(flow(), flow(OTHER, name="zaehlerkamera-d4e5f6", source="dhcp"),
                        flow("1" * 32, name="Wohnzimmer"), flow("2" * 32, handler="shelly"),
                        flow("3" * 32, source="user"), flow("not-a-flow"), "rubbish")
        self.assertEqual([{"flow_id": FLOW, "name": "Zählerkamera a1b2c3"},
                          {"flow_id": OTHER, "name": "zaehlerkamera-d4e5f6"}],
                         kit_camera.pending_kit_cameras("token", command=command))

    def test_names_of_the_firmware_are_recognised(self):
        for name in ("Zählerkamera a1b2c3", "zaehlerkamera-a1b2c3", "ZAEHLERKAMERA", "zahlerkamera_x"):
            self.assertTrue(kit_camera.kit_name(name), name)
        for name in ("", None, "Gaszählerkamera", "zaehlerkameraxyz", "Kamera"):
            self.assertFalse(kit_camera.kit_name(name), name)

    def test_adding_confirms_only_a_listed_flow(self):
        posted = []

        def post(url, token, payload):
            posted.append((url, payload))
            return json.dumps({"type": "create_entry", "title": "Zählerkamera"}).encode()

        self.assertEqual("added", kit_camera.add_kit_camera("token", FLOW, post=post, command=flows(flow())))
        self.assertEqual([(f"http://supervisor/core/api/config/config_entries/flow/{FLOW}", {})], posted)
        with self.assertRaises(LookupError):
            kit_camera.add_kit_camera("token", OTHER, post=post, command=flows(flow()))
        with self.assertRaises(ValueError):
            kit_camera.add_kit_camera("token", "../../services", post=post, command=flows(flow()))
        self.assertEqual(1, len(posted))

    def test_a_form_or_an_error_ends_in_a_hint_instead_of_a_crash(self):
        form = lambda url, token, payload: json.dumps({"type": "form", "step_id": "encryption_key"}).encode()
        self.assertEqual("needs_attention", kit_camera.add_kit_camera("token", FLOW, post=form, command=flows(flow())))
        self.assertEqual("gone", kit_camera.safe_add("token", FLOW, post=form, command=flows()))

        def offline(url, token, payload):
            raise OSError("Home Assistant restarting")

        self.assertEqual("failed", kit_camera.safe_add("token", FLOW, post=offline, command=flows(flow())))

        def broken(token, message):
            raise ValueError("refused")

        self.assertEqual([], kit_camera.safe_pending("token", command=broken))

    def test_websocket_command_logs_in_and_returns_the_result(self):
        socket = FakeSocket([{"type": "auth_required"}, {"type": "auth_ok"},
                             {"id": 1, "type": "result", "success": True, "result": [flow()]}])
        result = kit_camera.ha_command("secret", {"type": "config_entries/flow/progress"}, connect=lambda *a, **k: socket)
        self.assertEqual([flow()], result)
        self.assertEqual([{"type": "auth", "access_token": "secret"},
                          {"id": 1, "type": "config_entries/flow/progress"}], socket.sent)
        self.assertTrue(socket.closed)
        refused = FakeSocket([{"type": "auth_required"}, {"type": "auth_invalid"}])
        with self.assertRaises(ValueError):
            kit_camera.ha_command("secret", {"type": "x"}, connect=lambda *a, **k: refused)
        self.assertTrue(refused.closed)


class KitAddWizardTest(IngressFixture):
    def setUp(self):
        self.kit_pending = []
        self.kit_confirmed = []
        original = panel.start_panel

        def start(*args, **kwargs):
            return original(*args, find_kit_cameras=lambda: list(self.kit_pending),
                            confirm_kit_camera=self.confirm, **kwargs)

        patcher = patch.object(panel, "start_panel", start)
        patcher.start()
        self.addCleanup(patcher.stop)
        super().setUp()

    def confirm(self, flow_id):
        self.kit_confirmed.append(flow_id)
        self.kit_pending = []
        return "added"

    def test_post_requires_the_form_token(self):
        from urllib.error import HTTPError

        self.kit_pending = [{"flow_id": FLOW, "name": "Zählerkamera a1b2c3"}]
        self.assertEqual(json.loads(self.request("/neue-zaehlerkameras")[0]), self.kit_pending)
        with self.assertRaises(HTTPError) as caught:
            self.request("/zaehlerkamera-hinzufuegen", data={"flow_id": FLOW, "csrf": "wrong", "lang": "de", "mode": "auto"})
        self.assertEqual(403, caught.exception.code)
        self.assertEqual([], self.kit_confirmed)
        answer, status = self.request("/zaehlerkamera-hinzufuegen",
                                      data={"flow_id": FLOW, "csrf": self.csrf, "lang": "de", "mode": "auto"})
        self.assertEqual((200, {"result": "added"}), (status, json.loads(answer)))
        self.assertEqual([FLOW], self.kit_confirmed)

    def test_wizard_offers_and_adds_the_discovered_camera(self):
        from playwright.sync_api import sync_playwright

        self.kit_pending = [{"flow_id": FLOW, "name": "Zählerkamera a1b2c3"}]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            page = browser.new_page(viewport={"width": 1200, "height": 900}, locale="de-DE")
            page.set_default_timeout(7000)
            page.goto(self.base + "/")
            page.locator("#wizard-source-cards .source-card").first.click()
            pending = page.locator("#wizard-kit-pending")
            pending.wait_for(state="visible")
            self.assertIn("Zählerkamera „Zählerkamera a1b2c3“ gefunden", pending.text_content())
            page.locator("#wizard-kit").screenshot(path="/tmp/kit-pending-1200.png")
            self.suggestions = [{"mode": "esphome", "camera": "camera.zaehlerkamera_a1b2c3_bild",
                                 "label": "Zählerkamera a1b2c3 Bild", "available": True, "kit": True}]
            page.get_by_role("button", name="In Home Assistant hinzufügen").click()
            page.wait_for_function("document.querySelector('#wizard-kit-status').dataset.state === 'found'",
                                   timeout=9000)
            self.assertEqual([FLOW], self.kit_confirmed)
            self.assertFalse(pending.is_visible())
            self.assertEqual("camera.zaehlerkamera_a1b2c3_bild",
                             page.locator('#setup-form [name="camera"]').input_value())
            browser.close()


if __name__ == "__main__":
    unittest.main()
