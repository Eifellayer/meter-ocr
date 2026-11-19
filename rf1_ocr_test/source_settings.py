"""Settings for SLFork, Home Assistant camera verification, and standalone OCR."""

import re
from ipaddress import ip_address
from urllib.parse import urlsplit

ESP_ADDRESS_MODES = ("slfork", "slfork_camera")
SOURCE_MODES = (*ESP_ADDRESS_MODES, "camera", "esphome")
CAMERA = re.compile(r"camera\.[a-z0-9_]+")
REFERENCE = re.compile(r"sensor\.[a-z0-9_]+")
LIGHT = re.compile(r"light\.[a-z0-9_]+")

DISCOVERY_TEMPLATE = """
{% set found = namespace(cameras=[], devices=[]) %}
{% for camera in states.camera %}
  {% set found.cameras = found.cameras + [{'label': camera.name, 'camera': camera.entity_id}] %}
{% endfor %}
{% for item in states.sensor if item.entity_id.endswith('_ip_address') or item.entity_id.endswith('_last_processed') %}
  {% set device = device_id(item.entity_id) %}
  {% set model = device_attr(device, 'model') | default('', true) | lower %}
  {% if 'ai-on-the-edge' in model or 'ai on the edge' in model %}
    {% set found.devices = found.devices + [
      {'label': device_attr(device, 'name_by_user') or device_attr(device, 'name'),
       'url': device_attr(device, 'configuration_url'),
       'ip': item.state if item.entity_id.endswith('_ip_address') else ''}] %}
  {% endif %}
{% endfor %}
{{ {'cameras': found.cameras, 'devices': found.devices} | to_json }}
"""


def source_rules(values):
    mode, url, camera, reference = (values[key].strip() for key in ("mode", "url", "camera", "reference"))
    if mode not in SOURCE_MODES:
        raise ValueError("Ungültige Bildquelle")
    if mode in ESP_ADDRESS_MODES:
        address = urlsplit(url)
        if (address.scheme not in ("http", "https") or not address.hostname
                or address.username is not None or address.query or address.fragment
                or any(character.isspace() for character in url)):
            raise ValueError("Ungültige SLFork-Adresse")
    elif not CAMERA.fullmatch(camera):
        raise ValueError("Ungültige Kamera-Entität")
    if mode == "camera" and reference and not REFERENCE.fullmatch(reference):
        raise ValueError("Ungültiger Referenzsensor")
    light = str(values.get("light") or "").strip() if mode not in ESP_ADDRESS_MODES else ""
    if light and not LIGHT.fullmatch(light):
        raise ValueError("Ungültige Licht-Entität")
    return dict(mode=mode, url=url, camera=camera, reference=reference, light=light)


def source_check_key(source):
    mode = source["mode"]
    camera = source["camera"] if mode not in ESP_ADDRESS_MODES else ""
    return [mode, camera or source["url"].rstrip("/"), source["reference"] if mode == "camera" else ""]


def discovery_order(source):
    label = source["label"].casefold()
    identity = f"{label} {source.get('camera', '')}"
    if re.search(r"(?:^|[\W_])gas(?:$|[\W_]|meter|zähler|zaehler)", identity):
        return 0, label
    if source["mode"] == "slfork" or re.search(r"meter|zähler|zaehler", identity):
        return 1, label
    return 2, label


def discovered_sources(data):
    choices = {}
    for item in data.get("cameras", []):
        camera = item.get("camera", "")
        if isinstance(camera, str) and CAMERA.fullmatch(camera):
            label = str(item.get("label") or camera)[:120]
            choices[camera] = {"mode": "esphome", "label": label, "camera": camera}
    for item in data.get("devices", []):
        url = str(item.get("url") or "").strip().rstrip("/")
        if not url:
            try:
                address = ip_address(item.get("ip", ""))
            except ValueError:
                continue
            url = f"http://[{address}]" if address.version == 6 else f"http://{address}"
        try:
            source_rules({"mode": "slfork", "url": url, "camera": "", "reference": ""})
        except ValueError:
            continue
        if len(url) <= 150:
            label = str(item.get("label") or url)[:120]
            choices[url] = {"mode": "slfork", "label": label, "url": url}
    return sorted(choices.values(), key=discovery_order)[:80]
