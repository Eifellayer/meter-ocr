"""0.5.26: switch the extras of the meter camera on and off from the setup wizard."""

import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import panel
from test_ingress import IngressFixture

import kit_camera

CAMERA = "camera.zaehlerkamera_a1b2c3_bild"
REGISTRY = [
    {"entity_id": CAMERA, "device_id": "dev1", "platform": "esphome", "original_name": "Bild", "disabled_by": None},
    {"entity_id": "sensor.zaehlerkamera_a1b2c3_wlan_kanal", "device_id": "dev1", "platform": "esphome",
     "original_name": "WLAN-Kanal", "disabled_by": "integration"},
    {"entity_id": "sensor.zaehlerkamera_a1b2c3_wlan_zugangspunkt", "device_id": "dev1", "platform": "esphome",
     "original_name": "WLAN-Zugangspunkt", "disabled_by": None},
    # Same names on another device or from another integration are never touched.
    {"entity_id": "sensor.other_wlan_kanal", "device_id": "dev2", "platform": "esphome",
     "original_name": "WLAN-Kanal", "disabled_by": "integration"},
    {"entity_id": "sensor.template_wlan_kanal", "device_id": "dev1", "platform": "template",
     "original_name": "WLAN-Kanal", "disabled_by": None},
    "rubbish",
]


class Registry:
    def __init__(self, entries=REGISTRY):
        self.entries = entries
        self.updates = []

    def __call__(self, token, message):
        if message["type"] == "config/entity_registry/list":
            return self.entries
        if message["type"] == "config/entity_registry/update":
            self.updates.append(message)
            return {"entity_entry": {}, "reload_delay": 30}
        raise AssertionError(message)


class KitExtrasTest(unittest.TestCase):
    def test_extras_of_the_cameras_own_device_are_found(self):
        self.assertEqual({"wlan_kanal": {"entity_id": "sensor.zaehlerkamera_a1b2c3_wlan_kanal", "enabled": False},
                          "wlan_zugangspunkt": {"entity_id": "sensor.zaehlerkamera_a1b2c3_wlan_zugangspunkt",
                                                "enabled": True}},
                         kit_camera.kit_extras("token", CAMERA, command=Registry()))
        self.assertEqual({}, kit_camera.kit_extras("token", "camera.unknown", command=Registry()))

    def test_switching_enables_or_disables_only_that_entity(self):
        registry = Registry()
        kit_camera.set_kit_extra("token", CAMERA, "wlan_kanal", True, command=registry)
        kit_camera.set_kit_extra("token", CAMERA, "wlan_zugangspunkt", False, command=registry)
        self.assertEqual([
            {"type": "config/entity_registry/update", "entity_id": "sensor.zaehlerkamera_a1b2c3_wlan_kanal",
             "disabled_by": None},
            {"type": "config/entity_registry/update", "entity_id": "sensor.zaehlerkamera_a1b2c3_wlan_zugangspunkt",
             "disabled_by": "user"}], registry.updates)
        with self.assertRaises(LookupError):
            kit_camera.set_kit_extra("token", "camera.unknown", "wlan_kanal", True, command=registry)

    def test_web_helpers_never_raise(self):
        self.assertEqual({"wlan_kanal": {"enabled": False}, "wlan_zugangspunkt": {"enabled": True}},
                         kit_camera.safe_extras("token", CAMERA, command=Registry()))
        self.assertEqual("saved", kit_camera.safe_set_extra("token", CAMERA, "wlan_kanal", True, command=Registry()))
        self.assertEqual("gone", kit_camera.safe_set_extra("token", CAMERA, "wlan_kanal", True, command=Registry([])))

        def broken(token, message):
            raise OSError("Home Assistant restarting")

        self.assertEqual({}, kit_camera.safe_extras("token", CAMERA, command=broken))
        self.assertEqual("failed", kit_camera.safe_set_extra("token", CAMERA, "wlan_kanal", True, command=broken))


class KitExtrasWizardTest(IngressFixture):
    def setUp(self):
        self.extras = {"wlan_kanal": {"enabled": False}, "wlan_zugangspunkt": {"enabled": True}}
        self.switched = []
        original = panel.start_panel

        def start(*args, **kwargs):
            return original(*args, get_kit_extras=lambda camera: dict(self.extras) if camera == CAMERA else {},
                            set_kit_extra=self.switch, **kwargs)

        patcher = patch.object(panel, "start_panel", start)
        patcher.start()
        self.addCleanup(patcher.stop)
        super().setUp()

    def switch(self, camera, extra, enabled):
        self.switched.append((camera, extra, enabled))
        return "saved"

    def test_routes_check_camera_extra_and_form_token(self):
        self.assertEqual(self.extras, json.loads(self.request(f"/zaehlerkamera-zusaetze?camera={CAMERA}")[0]))
        self.assertEqual({}, json.loads(self.request("/zaehlerkamera-zusaetze?camera=../../etc")[0]))
        base = {"camera": CAMERA, "extra": "wlan_kanal", "on": "1", "lang": "de", "mode": "auto"}
        with self.assertRaises(HTTPError) as caught:
            self.request("/zaehlerkamera-zusatz", data={**base, "csrf": "wrong"})
        self.assertEqual(403, caught.exception.code)
        for bad in ({"extra": "reboot"}, {"on": "yes"}, {"camera": "light.flash"}):
            with self.subTest(bad=bad), self.assertRaises(HTTPError) as caught:
                self.request("/zaehlerkamera-zusatz", data={**base, **bad, "csrf": self.csrf})
            self.assertEqual(400, caught.exception.code)
        self.assertEqual([], self.switched)
        answer, status = self.request("/zaehlerkamera-zusatz", data={**base, "csrf": self.csrf})
        self.assertEqual((200, {"result": "saved"}), (status, json.loads(answer)))
        self.assertEqual([(CAMERA, "wlan_kanal", True)], self.switched)

    def test_checkboxes_appear_with_the_camera_and_save_right_away(self):
        from playwright.sync_api import sync_playwright

        self.suggestions = [{"mode": "esphome", "camera": CAMERA, "label": "Zählerkamera a1b2c3 Bild",
                             "available": True, "kit": True}]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            page = browser.new_page(viewport={"width": 1200, "height": 900}, locale="de-DE")
            page.set_default_timeout(7000)
            page.goto(self.base + "/")
            page.locator("#wizard-source-cards .source-card").first.click()
            extras = page.locator("#wizard-kit-extras")
            extras.wait_for(state="visible")
            channel = page.locator('input[data-extra="wlan_kanal"]')
            access_point = page.locator('input[data-extra="wlan_zugangspunkt"]')
            self.assertFalse(channel.is_checked())
            self.assertTrue(access_point.is_checked())
            channel.check()
            page.wait_for_function("document.querySelector('#wizard-kit-extras-status').textContent.includes('Gespeichert')")
            self.assertEqual([(CAMERA, "wlan_kanal", True)], self.switched)
            extras.screenshot(path="/tmp/kit-extras-1200.png")
            # The checkboxes are not part of the setup form.
            self.assertEqual(0, page.evaluate("[...document.querySelector('#setup-form').elements]"
                                              ".filter(field => field.dataset && field.dataset.extra).length"))
            browser.close()


if __name__ == "__main__":
    unittest.main()
