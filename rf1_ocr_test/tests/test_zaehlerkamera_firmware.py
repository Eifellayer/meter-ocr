"""The meter camera firmware in esphome/: files, packages, substitutions and ids fit together.

ESPHome itself only runs in the firmware workflow. These checks catch the mistakes that would
otherwise only show up there: a missing include, an undefined substitution, a lambda that
names an id nobody defines, a pin used twice, or a board the installer or workflow forgot.
"""

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FIRMWARE = ROOT / "esphome"
BOARDS = ("esp32-cam", "esp32-s3-cam", "xiao-esp32s3-sense", "waveshare-esp32s3-eth")
WIFI_BOARDS = ("esp32-cam", "esp32-s3-cam", "xiao-esp32s3-sense")
FLASH_BOARDS = ("esp32-cam", "esp32-s3-cam")


def loader_for(path):
    class Loader(yaml.SafeLoader):
        pass

    Loader.add_constructor("!include", lambda loader, node: ("include", (path.parent / loader.construct_scalar(node)).resolve()))
    Loader.add_constructor("!lambda", lambda loader, node: ("lambda", loader.construct_scalar(node)))
    Loader.add_constructor("!secret", lambda loader, node: ("secret", loader.construct_scalar(node)))
    return Loader


def load(path):
    with path.open(encoding="utf-8") as handle:
        return yaml.load(handle, Loader=loader_for(path)) or {}


def merge(old, new):
    """Like ESPHome's package merge: dictionaries key by key, lists appended, the newer value wins."""
    if isinstance(new, dict) and isinstance(old, dict):
        result = dict(old)
        for key, value in new.items():
            result[key] = merge(old[key], value) if key in old else value
        return result
    if isinstance(new, list) and isinstance(old, list):
        return old + new
    return old if new is None else new


def merged(path):
    """The configuration as ESPHome builds it: the packages first, the file itself on top."""
    config = load(path)
    result = {}
    for name, value in (config.pop("packages", None) or {}).items():
        if not (isinstance(value, tuple) and value[0] == "include"):
            raise AssertionError(f"{path.name}: package {name} is not a local !include")
        if not value[1].is_file():
            raise AssertionError(f"{path.name}: package {name} points to a missing file {value[1]}")
        result = merge(result, merged(value[1]))
    return merge(result, config)


def strings(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from strings(item)
    elif value is not None:
        yield str(value)


def defined_ids(value):
    if isinstance(value, dict):
        if isinstance(value.get("id"), str):
            yield value["id"]
        for item in value.values():
            yield from defined_ids(item)
    elif isinstance(value, list):
        for item in value:
            yield from defined_ids(item)


REFERENCE_KEYS = {"light.turn_on", "light.turn_off", "script.execute", "script.stop", "switch.is_on",
                  "switch.is_off", "switch.turn_on", "switch.turn_off", "output"}


def referenced_ids(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in REFERENCE_KEYS and isinstance(item, str):
                yield item
            yield from referenced_ids(item)
    elif isinstance(value, list):
        for item in value:
            yield from referenced_ids(item)
    elif isinstance(value, str):
        yield from re.findall(r"\bid\((\w+)\)", value)


def pin_number(pin):
    pin = pin.get("number") if isinstance(pin, dict) else pin
    match = re.fullmatch(r"GPIO(\d+)", str(pin))
    if not match:
        raise AssertionError(f"Unexpected pin {pin!r}")
    return int(match.group(1))


def used_pins(config):
    camera = config["esp32_camera"]
    pins = [camera["external_clock"]["pin"], camera["i2c_pins"]["sda"], camera["i2c_pins"]["scl"],
            *camera["data_pins"], camera["vsync_pin"], camera["href_pin"], camera["pixel_clock_pin"]]
    pins += [camera[key] for key in ("power_down_pin", "reset_pin") if key in camera]
    for output in config.get("output", []):
        pins.append(output["pin"])
    for light in config.get("light", []):
        if "pin" in light:
            pins.append(light["pin"])
    if "status_led" in config:
        pins.append(config["status_led"]["pin"])
    ethernet = config.get("ethernet") or {}
    pins += [ethernet[key] for key in ("clk_pin", "mosi_pin", "miso_pin", "cs_pin", "interrupt_pin", "reset_pin")
             if key in ethernet]
    return [pin_number(pin) for pin in pins]


def substituted(config):
    """Replace ${name} like ESPHome does (the factory build adds firmware_version on the command line)."""
    values = {key: str(value) for key, value in (config.get("substitutions") or {}).items()}

    def replace(value):
        if isinstance(value, dict):
            return {key: replace(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, tuple):
            return tuple(replace(item) for item in value)
        if isinstance(value, str):
            return re.sub(r"\$\{(\w+)\}", lambda match: values[match.group(1)], value)
        return value

    return replace({key: value for key, value in config.items() if key != "substitutions"})


class ZaehlerkameraFirmwareTest(unittest.TestCase):
    def configs(self, suffix=".yaml"):
        return {board: merged(FIRMWARE / f"{board}{suffix}") for board in BOARDS}

    def test_every_board_has_a_board_file_and_a_factory_file(self):
        for board in BOARDS:
            with self.subTest(board=board):
                self.assertTrue((FIRMWARE / f"{board}.yaml").is_file())
                factory = load(FIRMWARE / f"{board}.factory.yaml")
                self.assertEqual(factory["substitutions"]["board"], board)
        boards = {path.name.removesuffix(".factory.yaml") for path in FIRMWARE.glob("*.factory.yaml")}
        self.assertEqual(boards, set(BOARDS))

    def test_substitutions_are_all_defined(self):
        for suffix in (".yaml", ".factory.yaml"):
            for board, config in self.configs(suffix).items():
                with self.subTest(board=board, file=suffix):
                    defined = set(config.get("substitutions") or {})
                    used = {name for text in strings({k: v for k, v in config.items() if k != "substitutions"})
                            for name in re.findall(r"\$\{(\w+)\}", text)}
                    self.assertFalse(used - defined, f"undefined substitutions: {sorted(used - defined)}")
                    substituted(config)

    def test_lambdas_and_actions_only_name_defined_ids(self):
        for board, config in self.configs(".factory.yaml").items():
            with self.subTest(board=board):
                defined = set(defined_ids(config))
                missing = set(referenced_ids(config)) - defined
                self.assertFalse(missing, f"unknown ids: {sorted(missing)}")
                ids = list(defined_ids(config))
                self.assertEqual(len(ids), len(set(ids)), "an id is defined twice")

    def test_camera_is_complete_and_keeps_the_stable_settings(self):
        for board, config in self.configs().items():
            with self.subTest(board=board):
                camera = substituted(config)["esp32_camera"]
                self.assertEqual(camera["id"], "kamera")
                self.assertEqual(len(camera["data_pins"]), 8)
                for key in ("vsync_pin", "href_pin", "pixel_clock_pin"):
                    self.assertIn(key, camera)
                self.assertEqual(set(camera["i2c_pins"]), {"sda", "scl"})
                # Proven on weak Wi-Fi: never turn these back.
                self.assertEqual(camera["external_clock"]["frequency"], "20MHz")
                self.assertEqual(camera["idle_framerate"], "0.05 fps")
                self.assertEqual(camera["resolution"], "800x600")
                self.assertIn("psram", config)

    def test_no_pin_is_used_twice(self):
        for board, config in self.configs().items():
            with self.subTest(board=board):
                pins = used_pins(substituted(config))
                self.assertEqual(len(pins), len(set(pins)), f"pins used twice: {sorted(pins)}")

    def test_network_flash_and_provisioning_per_board(self):
        for board, config in self.configs(".factory.yaml").items():
            with self.subTest(board=board):
                wifi = board in WIFI_BOARDS
                self.assertEqual("wifi" in config, wifi)
                self.assertEqual("ethernet" in config, not wifi)
                self.assertEqual("improv_serial" in config, wifi)
                if wifi:
                    self.assertEqual(config["wifi"]["power_save_mode"], "none")
                    self.assertIn("captive_portal", config)
                lights = [light["id"] for light in config.get("light", [])]
                self.assertEqual(lights, ["blitz"] if board in FLASH_BOARDS else [])

    def test_factory_firmware_updates_from_its_own_manifest(self):
        for board, config in self.configs(".factory.yaml").items():
            with self.subTest(board=board):
                config = substituted({**config, "substitutions": {**config["substitutions"], "firmware_version": "1.2.3"}})
                self.assertEqual(config["esphome"]["project"], {"name": "eifellayer.zaehlerkamera", "version": "1.2.3"})
                self.assertEqual(config["update"][0]["source"],
                                 f"https://eifellayer.github.io/meter-ocr/firmware/{board}.manifest.json")
                self.assertEqual(config["dashboard_import"]["package_import_url"],
                                 f"github://Eifellayer/meter-ocr/esphome/{board}.yaml@main")
                self.assertEqual([ota["platform"] for ota in config["ota"]], ["esphome", "http_request"])

    def test_no_secrets_in_the_firmware_files(self):
        for path in FIRMWARE.rglob("*.yaml"):
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("!secret", text)
                self.assertNotRegex(text, r"(?im)^\s*(password|key|ssid)\s*:")

    def test_workflow_and_installer_know_every_board(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/kamera-firmware.yml").read_text(encoding="utf-8"))
        matrix = [entry["board"] for entry in workflow["jobs"]["build"]["strategy"]["matrix"]["include"]]
        self.assertEqual(matrix, list(BOARDS))
        page = (FIRMWARE / "installer/index.html").read_text(encoding="utf-8")
        for board in BOARDS:
            self.assertIn(f"id: '{board}'", page)
            self.assertIn(f"'{board}': '<svg", page)
        self.assertEqual((FIRMWARE / "VERSION").read_text(encoding="utf-8").strip().count("."), 2)


if __name__ == "__main__":
    unittest.main()
