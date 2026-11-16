"""Bridge the latest matched SLFork picture and reading to Home Assistant."""

import base64
from concurrent.futures import Future
from copy import deepcopy
from datetime import datetime
from functools import partial
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
from queue import Empty, Queue
from tempfile import NamedTemporaryFile
from threading import Event, Lock, RLock, Thread
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw
from websocket import WebSocketException

from app_channel import APP_NAME, CHECK_ENTITY, LABEL_SUFFIX, NAMESPACE

from checks import (
    DEFAULT_INTERVAL_MINUTES, FRESH_SAMPLE_AGE, RETRY_INTERVAL, REVIEW_AFTER, OCR_PROFILES,
    STANDALONE_PENDING, STANDALONE_PENDING_NOTICE, STANDALONE_REJECTED_NOTICE, STANDALONE_VERIFIED_NOTICE,
    compare_sample, crop_register, read_register, read_with_retries, record_sample,
    automatic_interval_minutes, defer_duplicate_cycle,
    LAST_DIGIT_NOTICE, LAST_DIGIT_PASS, LAST_DIGIT_RETRIES, SUCCESSFUL_CHECKS,
    differs_only_at_last_digit, last_digit_can_pass, explain_uncertain_positions,
    meter_prefix, common_exact_precision, manual_confirms_failed_auto,
    reschedule_next_check, rolling_summary, sample_epoch, sample_timestamp, schedule_next_check, slfork_reference,
    timestamp_epoch, track_reflection,
    valid_interval_minutes,
)
from calibration import Calibration, CAPTURE_INTERVAL, MIN_IMAGE_LIMIT, MAX_IMAGES, MAX_ATTEMPTS, TIME_LIMIT
from consumption import (DEFAULT_FLOW_LPH, LOWER_READING, MAX_FLOW_LPH, ImplausibleReading,
                         accumulate_consumption, fallback_detail, format_cubic_metres)
from layout import (MANUAL_ROW_UNCLEAR, RAW_ROW_UNCLEAR, crop_coordinates, find_digit_row,
                    digit_box_settings, find_raw_digit_row, rotated_width, scale_digit_boxes, turn_crop)
from meter_learning import (GEOMETRY_REPAIR_LIMIT, GEOMETRY_REPAIR_SECONDS, alignment_rollback, observe_alignment, observe_flow,
                            observe_geometry_failures, propose_digit_boxes, suggested_interval)
from reminder import Reminder
from notification_settings import (DEFAULT_DELIVERY_HOURS, DEFAULT_REVIEW_MINUTES, PUSH_SERVICE,
                                   notification_rules)
from settings import DEFAULTS, SCHEMA_VERSION, load_options
from source_settings import (CAMERA, DISCOVERY_TEMPLATE, ESP_ADDRESS_MODES, REFERENCE,
                             discovered_sources, source_rules)
from panel import start_panel
from language import load_preferences
from transport import open_core

MAX_RESPONSE_BYTES = 3_000_000
MAX_TRANSFER_BYTES = 11_000
DESTINATION = Path(f"/media/{NAMESPACE}/kontrollbild.jpg")
GOOD_IMAGE = Path(f"/media/{NAMESPACE}/letzter_treffer.jpg")
TEST_IMAGE = Path("/data/ocr-testvorschau.jpg")
AUTOMATIC_PREVIEW = Path("/data/ocr-automatikvorschau.jpg")
TEST_SOURCE_IMAGE = Path("/data/ocr-testbild.jpg")
HISTORY = Path("/data/kontrollmessung.json")
OPTIONS = Path("/data/options.json")
EFFECTIVE_OPTIONS = Path("/data/rf1-settings.json")
AUTO_RULES = Path("/data/auto-pruefregeln.json")
AUTO_PAUSED = Path("/data/automatic-paused.json")
LANGUAGE_MODES = Path("/data/rf1-language.json")
NOTIFICATIONS = Path("/data/benachrichtigungen.json")
SOURCE_SETTINGS = Path("/data/bildquelle.json")
ENTITY = f"sensor.{NAMESPACE}_kontrollbild"
CORE_URL = f"http://supervisor/core/api/states/{ENTITY}"
OCR_ENTITY = f"sensor.{NAMESPACE}_ocr_zaehlerstand"
CONSUMPTION_ENTITY = f"sensor.{NAMESPACE}_verbrauch_gesamt"
MAX_IMAGE_PIXELS = 4_000_000
LIVE_CAPTURE_WINDOW_SECONDS = 20
LIVE_CAPTURE_MAX_ATTEMPTS = 10
INTENSIVE_ROTATIONS = (-6, 6)
MAX_LEARNED_ROTATION = 18
INTENSIVE_ROTATION_STATUS = "Intensivtest: Prüfe eine leicht gedrehte Aufnahme."
SLFORK_RAW_SOURCE = "slfork_raw"
SLFORK_RAW_NOTICE = "Aufbereitetes ESP-Bild fehlt oder ist zu alt. Die App prüft ein frisches Rohbild."
SLFORK_RAW_SUCCESS = "Rohbild gelesen. Mögliche Ursache: Bildausrichtung oder Referenzmarken in AI on the Edge."
SLFORK_RAW_FAILED = "Aufbereitetes ESP-Bild nicht nutzbar. Es konnte kein frisches Rohbild geladen werden."
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def get_bytes(url, token=None, timeout=8):
    headers = {"Cache-Control": "no-cache, no-store", "Pragma": "no-cache"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    open_request = open_core if token else urlopen
    with open_request(Request(url, headers=headers), timeout=timeout) as response:
        data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("Antwort zu groß")
    return data


def sequence_value(data, key):
    value = data.get(key, {})
    return value.get("main") if isinstance(value, dict) else None


def slfork_diagnostics(data):
    return {
        "slfork_value_status": sequence_value(data, "value_status"),
        "slfork_process_status": data.get("process_status"),
        "slfork_process_state": data.get("process_state"),
        "slfork_process_error": data.get("process_error"),
        "slfork_last_valid_timestamp": sequence_value(data, "timestamp_fallbackvalue"),
        "slfork_last_processed_timestamp": sequence_value(data, "timestamp_processed"),
    }


def slfork_cycle_failed(diagnostics):
    return diagnostics.get("slfork_process_error") in (-1, -2, "-1", "-2")


def capture_esp_snapshot(url, zone, source, *, fetch=None):
    picture = (fetch or get_bytes)(url)
    return picture, None, {
        "esp_timestamp": datetime.now(zone).isoformat(),
        "image_source": source,
        "reference_required": False,
        "raw_value": None,
        "actual_value": None,
    }


def capture_slfork_raw(base, zone, *, fetch=None):
    # The buffered raw JPEG has no independent capture timestamp.
    return capture_esp_snapshot(base + "/camera?task=capture", zone, SLFORK_RAW_SOURCE, fetch=fetch)


def capture_edge_camera(base, zone, *, fetch=None):
    try:
        return capture_slfork_raw(base, zone, fetch=fetch) if fetch else capture_slfork_raw(base, zone)
    except HTTPError as error:
        if error.code not in (404, 405, 501):
            raise
        error.close()
    return capture_esp_snapshot(base + "/capture_with_flashlight", zone, "edge_camera", fetch=fetch)


def discover_ha_sources(token):
    request = Request(
        "http://supervisor/core/api/template",
        data=json.dumps({"template": DISCOVERY_TEMPLATE}).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with open_core(request, timeout=5) as response:
            data = json.loads(response.read(512_001))
        return discovered_sources(data)
    except (OSError, ValueError, TypeError, AttributeError) as error:
        print(f"Bildquellen aus Home Assistant konnten nicht geladen werden: {type(error).__name__}")
    # The state API can still provide cameras and meters with the standard MQTT sensors.
    try:
        states = json.loads(get_bytes("http://supervisor/core/api/states", token, timeout=5))
        by_id = {entity["entity_id"]: entity for entity in states if isinstance(entity.get("entity_id"), str)}
        cameras = []
        devices = []
        for entity_id, entity in by_id.items():
            if entity_id.startswith("camera."):
                cameras.append({"camera": entity_id, "label": entity.get("attributes", {}).get("friendly_name")})
            elif entity_id.startswith("sensor.") and entity_id.endswith("_ip_address"):
                prefix = entity_id.removesuffix("_ip_address")
                if prefix + "_process_state" in by_id and prefix + "_main_last_processed" in by_id:
                    label = entity.get("attributes", {}).get("friendly_name") or entity_id
                    devices.append({"label": label, "ip": entity.get("state")})
        return discovered_sources({"cameras": cameras, "devices": devices})
    except (OSError, ValueError, TypeError, AttributeError):
        return []


def capture(base, diagnostics, *, fetch=None):
    fetch = fetch or get_bytes

    def process_data():
        payload = json.loads(fetch(base + "/process_data"))
        if not isinstance(payload, dict):
            raise ValueError("Ungültige SLFork-Messdaten")
        return payload

    before = process_data()
    diagnostics.update(slfork_diagnostics(before))
    if slfork_cycle_failed(diagnostics):
        return None
    try:
        picture = fetch(base + "/img_tmp/alg.jpg")
    except HTTPError as error:
        if error.code not in (404, 410):
            raise
        return None
    try:
        overlay = fetch(base + "/img_tmp/alg_roi.jpg")
    except (OSError, ValueError):
        overlay = None
    after = process_data()
    diagnostics.update(slfork_diagnostics(after))
    if slfork_cycle_failed(diagnostics):
        return None
    timestamp = sequence_value(after, "timestamp_processed")
    if sequence_value(before, "timestamp_processed") != timestamp:
        return None
    try:
        datetime.fromisoformat(timestamp)
    except (TypeError, ValueError):
        return None
    return picture, overlay, {
        "esp_timestamp": timestamp,
        "raw_value": sequence_value(after, "raw_value"),
        "actual_value": sequence_value(after, "actual_value"),
        "slfork_fallback_value": sequence_value(after, "fallback_value"),
        **diagnostics,
    }


def capture_camera(camera, reference, token, zone, timeout=8, *, fetch=None):
    fetch = fetch or get_bytes
    base = "http://supervisor/core/api"
    picture = fetch(f"{base}/camera_proxy/{camera}", token, timeout=timeout)
    captured = datetime.now(zone)
    value = None
    reference_time = None
    if reference:
        try:
            state = json.loads(fetch(f"{base}/states/{reference}", token, timeout=timeout))
            reported = datetime.fromisoformat(state.get("last_reported") or state["last_updated"])
            if (reported.tzinfo is not None
                    and state.get("attributes", {}).get("unit_of_measurement") == "m³"
                    and abs((captured - reported).total_seconds()) <= 5 * 60):
                value = state["state"]
                reference_time = reported.timestamp()
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            print(f"Referenzsensor konnte nicht gelesen werden: {type(error).__name__}")
    return picture, None, {
        "esp_timestamp": captured.isoformat(),
        "raw_value": value,
        "actual_value": value,
        "reference": value,
        "reference_time": reference_time,
        "reference_required": bool(reference),
        "image_source": "home_assistant_camera",
    }


def apply_manual_reference(sample, reference, decimals, integer_digits):
    if not reference:
        return
    if meter_prefix(reference, decimals, integer_digits) is None:
        raise ValueError("Fallback-Wert passt nicht zur eingestellten Zähleranzeige.")
    sample["raw_value"] = sample["actual_value"] = reference
    sample["reference_required"] = True
    sample["reference_is_fallback"] = False
    sample.pop("slfork_value_status", None)
    sample.pop("slfork_process_error", None)


def select_register(frame, overlay, manual_crop, manual_width, rotation=0, whole_digits=5, fraction_digits=3,
                    *, detect_raw=False, digit_boxes=None):
    if overlay is not None:
        try:
            with Image.open(io.BytesIO(overlay)) as annotated:
                if annotated.size == frame.size and annotated.width * annotated.height <= MAX_IMAGE_PIXELS:
                    layout = find_digit_row(annotated, whole_digits, fraction_digits)
                    if layout is not None:
                        crop, width, boxes = layout
                        return crop_register(frame, crop), width, boxes[:whole_digits], boxes[whole_digits:], "auto"
        except (OSError, ValueError, Image.DecompressionBombError):
            pass
    if detect_raw:
        layout = find_raw_digit_row(frame, whole_digits, fraction_digits)
        if layout:
            crop, width, boxes = layout
            return crop_register(frame, crop), width, boxes[:whole_digits], boxes[whole_digits:], "raw_auto"
    register = turn_crop(crop_register(frame, manual_crop), rotation)
    if not 0 < manual_width <= register.width:
        raise ValueError("vorkomma_breite liegt außerhalb des Ausschnitts")
    if digit_boxes:
        boxes = scale_digit_boxes(digit_boxes, register.size)
        return register, manual_width, boxes[:whole_digits], boxes[whole_digits:], "manual"
    # Ohne Rahmen teilt der konfigurierte Ausschnitt den Rest in drei Rollen.
    right_width = register.width - manual_width
    boundaries = [manual_width + right_width * i // max(1, fraction_digits)
                  for i in range(max(1, fraction_digits) + 1)]
    boxes = [(left, 0, right, register.height)
             for left, right in zip(boundaries, boundaries[1:]) if right - left >= 8]
    return register, manual_width, [], boxes, "manual"


def select_tilted_register(frame, crop, whole_width, rotation, adjustment, whole_digits, fraction_digits, detect_raw):
    if detect_raw:
        rotated = turn_crop(frame, adjustment, expand=False)
        layout = find_raw_digit_row(rotated, whole_digits, fraction_digits)
        if layout:
            bounds, width, boxes = layout
            return crop_register(rotated, bounds), width, boxes[:whole_digits], boxes[whole_digits:], "raw_auto"
    left, top, right, bottom = crop
    width, height = right - left, bottom - top
    angle = rotation + adjustment
    adjusted_whole = max(1, round(whole_width * rotated_width(width, height, angle) /
                                  rotated_width(width, height, rotation)))
    return select_register(frame, None, crop, adjusted_whole, angle, whole_digits, fraction_digits)


def read_digit(register, box, read, trim_vertical=False):
    left, top, right, bottom = box
    if trim_vertical:
        # Keep the center of the roll and omit the edges of adjacent digits.
        margin = (bottom - top) // 8
        top += margin
        bottom -= margin
    try:
        return read(register.crop((left, top, right, bottom)), digits=1) or "?"
    except (OSError, subprocess.SubprocessError):
        return "?"


def read_visible_digits(register, integer_width, whole_boxes, fraction_boxes, light_digits, polarity, *, profile,
                        whole_digits=5, fraction_digits=3, deadline=None, prefer_boxes=False, recognize=None):
    recognize = recognize or read_register
    if polarity != "auto":
        light_digits = polarity == "light"

    def read(picture, digits=whole_digits):
        kwargs = {"deadline": deadline} if deadline is not None else {}
        return recognize(picture, light_digits, digits, force_polarity=polarity != "auto", profile=profile, **kwargs)

    whole = None if prefer_boxes else read(register.crop((0, 0, integer_width, register.height)))
    if whole is None:
        whole = "".join(read_digit(register, box, read, trim_vertical=not prefer_boxes)
                        for box in whole_boxes).ljust(whole_digits, "?")
        if prefer_boxes and whole_digits >= 4 and whole.count("?") == 1 and len(whole_boxes) == whole_digits:
            # Recover one weak cell with a tightly cropped row read. Keep
            # every independently read cell as a check on OCR alignment.
            top, bottom = min(box[1] for box in whole_boxes), max(box[3] for box in whole_boxes)
            inset = (bottom - top) // 40
            row_box = (whole_boxes[0][0], top + inset,
                       max(integer_width, whole_boxes[-1][2]), bottom - inset)
            try:
                row = read(register.crop(row_box))
                if row is None and row_box[0] > 0:
                    # Give a narrow leading digit slightly more background.
                    margin = max(1, (whole_boxes[0][2] - whole_boxes[0][0]) // 20)
                    row = read(register.crop((max(0, row_box[0] - margin), *row_box[1:])))
            except (OSError, subprocess.SubprocessError):
                row = None
            if row and len(row) == whole_digits and all(a == b or a == "?" for a, b in zip(whole, row)):
                whole = row
    fraction = "".join(read_digit(register, box, read) for box in fraction_boxes[:fraction_digits])
    return f"{whole}.{fraction.ljust(fraction_digits, '?')}" if fraction_digits else whole


def calibration_jpeg(frame, max_size):
    image = frame.convert("RGB")
    image.thumbnail(max_size, Image.Resampling.LANCZOS)
    with io.BytesIO() as buffer:
        image.save(buffer, "JPEG", quality=84)
        return buffer.getvalue()


def draw_test_preview(register, integer_width, whole_boxes, fraction_boxes, reading,
                      whole_digits=5, fraction_digits=3, readings=None, composed=False, pending=False):
    """Mark OCR digit regions and the actual read characters for manual diagnostics.

    Green: a digit was read without observed variation; yellow: attempts disagreed
    or the final reading was composed; red: the position remains unclear.
    The coordinates are approximate for manually configured crops without digit frames.
    They do NOT assert a match against the reference value.
    """
    annotated = register.convert("RGB")
    draw = ImageDraw.Draw(annotated)
    h, w = annotated.height, annotated.width
    if w <= 0 or h <= 0:
        raise ValueError("Leerer OCR-Ausschnitt")
    whole_width = max(1, min(integer_width, w))
    boxes = list(whole_boxes[:whole_digits]) if len(whole_boxes) >= whole_digits else [
        (whole_width * i // whole_digits, 0, whole_width * (i + 1) // whole_digits, h)
        for i in range(whole_digits)
    ]
    fraction = list(fraction_boxes[:fraction_digits])
    if fraction_digits and not fraction and whole_width < w:
        fraction = [
            (whole_width + (w - whole_width) * i // fraction_digits, 0,
             whole_width + (w - whole_width) * (i + 1) // fraction_digits, h)
            for i in range(fraction_digits)
        ]
    chars = (str(reading or "").split(".", 1)[0].ljust(whole_digits, "?")[:whole_digits]
             + str(reading or "").split(".", 1)[-1].ljust(fraction_digits, "?")[:fraction_digits]
             if fraction_digits and "." in str(reading or "")
             else str(reading or "").ljust(whole_digits, "?")[:whole_digits])
    uncertain = set()
    if composed:
        uncertain.update(index for index, char in enumerate(chars) if char.isdigit())
    elif readings:
        normalized = []
        for value in readings:
            parts = str(value or "").split(".", 1)
            digits = parts[0].ljust(whole_digits, "?")[:whole_digits]
            if fraction_digits:
                fraction_text = (parts[1] if len(parts) > 1 else "").ljust(fraction_digits, "?")[:fraction_digits]
                digits += fraction_text
            normalized.append(digits)
        for index, char in enumerate(chars):
            votes = [value[index] if index < len(value) else "?" for value in normalized]
            if char.isdigit() and any(vote != char for vote in votes):
                uncertain.add(index)
    stroke = max(2, min(6, w // 240))
    for idx, box in enumerate(boxes + fraction):
        if idx >= len(chars):
            break
        l, t, r, b = [int(coord) for coord in box]
        if not (0 <= l < r <= w and 0 <= t < b <= h):
            continue
        color = ((71, 157, 194) if pending else (203, 65, 77) if not chars[idx].isdigit() else
                 (241, 184, 54) if idx in uncertain else (36, 170, 92))
        draw.rectangle((l, t, r - 1, b - 1), outline=color, width=stroke)
        # The label is drawn on a filled patch for contrast against the counter.
        label = str(idx + 1) if pending else chars[idx]
        draw.rectangle((l, t, min(r, l + max(15, w // 45)), min(b, t + 16)),
                       fill=color)
        draw.text((l + 3, t + 2), label, fill=(255, 255, 255))
    return annotated


def transfer_jpeg(picture):
    rgb = picture.convert("RGB")
    for width in (640, 560, 480, 400, 320, 240, 160):
        resized = rgb.copy()
        resized.thumbnail((width, width), Image.Resampling.LANCZOS)
        for quality in (88, 78, 68, 58, 48):
            with io.BytesIO() as stream:
                resized.save(stream, format="JPEG", quality=quality, optimize=True)
                jpeg = stream.getvalue()
            if len(jpeg) <= MAX_TRANSFER_BYTES:
                return jpeg, resized.size
    raise ValueError("JPEG lässt sich nicht auf die Übertragungsgröße verkleinern")


def atomic_write(destination, content, mode):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        temp_path = Path(handle.name)
        try:
            handle.write(content)
            handle.close()
            os.chmod(temp_path, mode)
            temp_path.replace(destination)
        finally:
            temp_path.unlink(missing_ok=True)


def publish(data, jpeg, size, history, now, token, review_after=REVIEW_AFTER):
    digest = hashlib.sha256(jpeg).hexdigest()
    payload = {
        "state": data["esp_timestamp"],
        "attributes": {
            "friendly_name": "Meter OCR Kontrollbild" + LABEL_SUFFIX,
            **data,
            **rolling_summary(history, now, review_after),
            "decimal_places": history.get("comparison_decimals", 0),
            "ocr_display": history.get("ocr_value"),
            "ocr_status": history["status"],
            "ocr_value": history.get("ocr_value"),
            "width": size[0],
            "height": size[1],
            "jpeg_sha256": digest,
            "jpeg_base64": base64.b64encode(jpeg).decode("ascii"),
        },
    }
    publish_state(CORE_URL, payload, token)


def publish_check(history, now, token, review_after=REVIEW_AFTER):
    summary = rolling_summary(history, now, review_after)
    payload = {
        "state": "review_due" if summary["review_due"] else history["check_status"],
        "attributes": {"friendly_name": "Meter OCR Prüfstatus" + LABEL_SUFFIX,
                       **summary, **history.get("slfork_diagnostics", {})},
    }
    publish_state(f"http://supervisor/core/api/states/{CHECK_ENTITY}", payload, token)


def standalone_reading(camera, sample, ocr, decimals, previous, integer_digits=5):
    """Keep a majority reading only if it does not go backwards at shared precision."""
    latest = {"camera": camera, "reading": ocr, "decimals": decimals,
              "integer_digits": integer_digits, "image_time": sample["esp_timestamp"]}
    if (previous and previous["camera"] == camera
            and previous.get("integer_digits", integer_digits) == integer_digits):
        common = min(decimals, previous["decimals"])
        if meter_prefix(ocr, common, integer_digits) < meter_prefix(previous["reading"], common, integer_digits):
            return None
    return latest


def publish_standalone(history, camera, token):
    last = history.get("standalone_reading")
    value = "unavailable"
    captured = None
    if last and last["camera"] == camera:
        if history.get("check_status") in ("ocr_only", STANDALONE_PENDING):
            digits = last.get("integer_digits", 5)
            value = last["reading"][:digits + (last["decimals"] + 1 if last["decimals"] else 0)]
        captured = last["image_time"]
    payload = {
        "state": value,
        "attributes": {"friendly_name": "Meter OCR Zählerstand" + LABEL_SUFFIX, "unit_of_measurement": "m³",
                       "device_class": "gas", "source_camera": camera, "last_successful_image": captured},
    }
    publish_state(f"http://supervisor/core/api/states/{OCR_ENTITY}", payload, token)


def publish_consumption(history, token):
    consumption = history.get("consumption")
    if consumption is not None:
        payload = {
            "state": format_cubic_metres(consumption["total_litres"]),
            "attributes": {
                "friendly_name": "Meter OCR Gasverbrauch gesamt" + LABEL_SUFFIX,
                "unit_of_measurement": "m³",
                "device_class": "gas",
                "state_class": "total_increasing",
            },
        }
        publish_state(f"http://supervisor/core/api/states/{CONSUMPTION_ENTITY}", payload, token)


def publish_state(url, payload, token):
    request = Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with open_core(request, timeout=10) as response:
        if response.status not in (200, 201):
            raise OSError(f"Home Assistant meldet HTTP {response.status}")


def check_reminder(reminder, history, now, review_after=REVIEW_AFTER):
    before = json.dumps(history)
    try:
        reminder.sync(history, rolling_summary(history, now, review_after), now.timestamp())
    except (OSError, ValueError, WebSocketException) as error:
        print(f"Meter-OCR-Erinnerung konnte nicht aktualisiert werden: {type(error).__name__}")
    after = json.dumps(history)
    if after != before:
        try:
            atomic_write(HISTORY, after.encode("utf-8"), 0o600)
        except OSError as error:
            print(f"Meter-OCR-Erinnerung konnte nicht gespeichert werden: {type(error).__name__}")


def main():
    raw_options = json.loads(OPTIONS.read_text(encoding="utf-8"))
    # The Supervisor remains the source of truth for values edited in its UI.
    # It regenerates options.json. Record a versioned, normalized copy separately.
    snapshot = json.loads(EFFECTIVE_OPTIONS.read_text(encoding="utf-8")) if EFFECTIVE_OPTIONS.exists() else {}
    options = load_options(raw_options, snapshot)
    configured = bool(options.get("kamera_entitaet")) or options["esp_url"] != DEFAULTS["esp_url"]
    setup_pending = not configured and snapshot.get(
        "setup_pending", not EFFECTIVE_OPTIONS.exists() and not HISTORY.exists())
    atomic_write(EFFECTIVE_OPTIONS, json.dumps({
        "schema_version": SCHEMA_VERSION, "options": options, "setup_pending": setup_pending,
    }, indent=2).encode("utf-8"), 0o600)
    zone = ZoneInfo(options["zeitzone"])
    crop = tuple(int(part.strip()) for part in options["ausschnitt"].split(","))
    if len(crop) != 4:
        raise ValueError("ausschnitt erwartet links, oben, rechts, unten")
    token = os.environ["SUPERVISOR_TOKEN"]
    history = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else {}
    source_selected = configured or bool(history.get("last_epoch"))
    camera = (options.get("kamera_entitaet") or "").strip()
    reference = (options.get("referenz_entitaet") or "").strip()
    if camera and not CAMERA.fullmatch(camera):
        raise ValueError("kamera_entitaet muss eine Home-Assistant-Kamera sein")
    if reference and not REFERENCE.fullmatch(reference):
        raise ValueError("referenz_entitaet muss ein Home-Assistant-Sensor sein")
    configured_source = dict(mode="camera" if camera else "slfork", url=options["esp_url"],
                  camera=camera, reference=reference)
    default_source = dict(configured_source)
    initial_setup_pending = setup_pending
    initial_source_key = [configured_source["mode"], camera or configured_source["url"].rstrip("/"), reference if camera else ""]
    try:
        configured_source = source_rules(json.loads(SOURCE_SETTINGS.read_text(encoding="utf-8")))
        source_selected = True
        setup_pending = False
    except FileNotFoundError:
        pass
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"Bildquelle konnte nicht geladen werden: {type(error).__name__}")

    def get_source():
        return {**configured_source, "selected": source_selected}, setup_pending

    def save_source(values):
        nonlocal configured_source, setup_pending, source_selected
        validated = source_rules(values)
        atomic_write(SOURCE_SETTINGS, json.dumps(validated).encode("utf-8"), 0o600)
        configured_source, setup_pending = validated, False
        source_selected = True

    default_decimals = options["vergleich_nachkommastellen"]
    default_attempts = options["ocr_versuche"]
    wake_worker = Event()
    automatic_request = handled_automatic_request = None

    def request_automatic_check():
        nonlocal automatic_request
        automatic_request = object()
        wake_worker.set()

    auto_rules = {"decimals": default_decimals, "attempts": default_attempts, "polarity": "auto",
                  "precision_mode": False, "fine_alignment_enabled": False, "adaptive_interval_enabled": False, "self_repair_enabled": False,
                  "reflection_estimate_enabled": False, "reflection_suggestion_hidden": False,
                  "reflection_confirmed_id": "",
                  "crop_mode": "auto", "crop": options["ausschnitt"],
                  "width": options["vorkomma_breite"], "rotation": 0, "crop_revision": "", "digit_boxes": [],
                  "max_flow_lph": DEFAULT_FLOW_LPH, "interval_minutes": DEFAULT_INTERVAL_MINUTES,
                  "integer_digits": 5, "fraction_digits": 3, "meter_display": "rollers",
                  "fallback_value": "", "fallback_time": ""}
    default_auto_rules = dict(auto_rules)
    try:
        saved_rules = json.loads(AUTO_RULES.read_text(encoding="utf-8"))
        if (type(saved_rules.get("decimals")) is int and 0 <= saved_rules["decimals"] <= 3
                and type(saved_rules.get("attempts")) is int and 1 <= saved_rules["attempts"] <= 10):
            polarity = saved_rules.get("polarity", "auto")
            if polarity not in ("auto", "light", "dark"):
                polarity = "auto"
            crop_mode = saved_rules.get("crop_mode", "auto")
            crop_text = saved_rules.get("crop", options["ausschnitt"])
            width = saved_rules.get("width", options["vorkomma_breite"])
            rotation = saved_rules.get("rotation", 0)
            try:
                crop_coordinates(crop_text, width, rotation)
                if crop_mode not in ("auto", "manual"):
                    raise ValueError("Ungültiger Ausschnittmodus")
            except ValueError:
                crop_mode, crop_text, width, rotation = (
                    "auto", options["ausschnitt"], options["vorkomma_breite"], 0
                )
            max_flow = saved_rules.get("max_flow_lph", DEFAULT_FLOW_LPH)
            if type(max_flow) is not int or not 1 <= max_flow <= MAX_FLOW_LPH:
                max_flow = DEFAULT_FLOW_LPH
            interval_minutes = saved_rules.get("interval_minutes", DEFAULT_INTERVAL_MINUTES)
            if not valid_interval_minutes(interval_minutes):
                interval_minutes = DEFAULT_INTERVAL_MINUTES
            integer_digits = saved_rules.get("integer_digits", 5)
            if type(integer_digits) is not int or not 1 <= integer_digits <= 9:
                integer_digits = 5
            fraction_digits = saved_rules.get("fraction_digits", 3)
            if type(fraction_digits) is not int or not 0 <= fraction_digits <= 3:
                fraction_digits = 3
            meter_display = saved_rules.get("meter_display", "rollers")
            if meter_display not in ("rollers", "digital", "mixed"):
                meter_display = "rollers"
            decimals = min(saved_rules["decimals"], fraction_digits)
            fallback_value = saved_rules.get("fallback_value", "")
            fallback_time = saved_rules.get("fallback_time", "")
            if not isinstance(fallback_value, str) or not isinstance(fallback_time, str):
                fallback_value, fallback_time = "", ""
            if fallback_value:
                try:
                    if (not re.fullmatch(r"[0-9]{1,9}(?:[.,][0-9]{1,3})?", fallback_value)
                            or meter_prefix(fallback_value, decimals, integer_digits) is None):
                        raise ValueError("Ungültiger Fallback")
                    datetime.fromisoformat(fallback_time)
                except ValueError:
                    fallback_value, fallback_time = "", ""
            else:
                fallback_time = ""
            try:
                digit_boxes = digit_box_settings(saved_rules.get("digit_boxes"), integer_digits + fraction_digits)
            except ValueError:
                digit_boxes = []
            auto_rules = {"decimals": saved_rules["decimals"],
                          "attempts": saved_rules["attempts"], "polarity": polarity,
                          "crop_mode": crop_mode, "crop": crop_text, "width": width, "rotation": rotation,
                          "digit_boxes": digit_boxes if crop_mode == "manual" else [],
                          "crop_revision": (str(saved_rules.get("crop_revision", ""))[:30]
                                            if crop_mode == "manual" else ""),
                          "max_flow_lph": max_flow, "interval_minutes": interval_minutes,
                          "integer_digits": integer_digits, "fraction_digits": fraction_digits,
                          "meter_display": meter_display, "fallback_value": fallback_value,
                          "precision_mode": saved_rules.get("precision_mode") is True,
                          "fine_alignment_enabled": saved_rules.get("fine_alignment_enabled") is True,
                          "self_repair_enabled": saved_rules.get("self_repair_enabled") is True,
                          "adaptive_interval_enabled": saved_rules.get("adaptive_interval_enabled") is True,
                          "reflection_estimate_enabled": saved_rules.get("reflection_estimate_enabled") is True,
                          "reflection_suggestion_hidden": saved_rules.get("reflection_suggestion_hidden") is True,
                          "reflection_confirmed_id": str(saved_rules.get("reflection_confirmed_id", ""))[:80],
                          "fallback_time": fallback_time, "decimals": decimals}
        else:
            print("Ungültige gespeicherte Automatikregeln; verwende die App-Konfiguration.")
    except FileNotFoundError:
        pass
    except (OSError, ValueError, AttributeError) as error:
        print(f"Automatikregeln konnten nicht geladen werden: {type(error).__name__}")

    def get_auto_rules():
        return dict(auto_rules)

    def save_auto_rules(values):
        nonlocal auto_rules
        integer_digits = values.get("integer_digits", auto_rules["integer_digits"])
        fraction_digits = values.get("fraction_digits", auto_rules["fraction_digits"])
        meter_display = values.get("meter_display", auto_rules["meter_display"])
        fallback_value = values.get("fallback_value", auto_rules["fallback_value"])
        fallback_time = values.get("fallback_time", auto_rules["fallback_time"])
        precision_mode = values.get("precision_mode", auto_rules["precision_mode"])
        self_repair = values.get("self_repair_enabled", auto_rules["self_repair_enabled"])
        fine_alignment = values.get("fine_alignment_enabled", auto_rules["fine_alignment_enabled"])
        adaptive_interval = values.get("adaptive_interval_enabled", auto_rules["adaptive_interval_enabled"])
        reflection_estimate_enabled = values.get("reflection_estimate_enabled", auto_rules["reflection_estimate_enabled"])
        reflection_suggestion_hidden = values.get("reflection_suggestion_hidden", auto_rules["reflection_suggestion_hidden"])
        reflection_confirmed_id = values.get("reflection_confirmed_id", auto_rules["reflection_confirmed_id"])
        if (type(values.get("decimals")) is not int or not 0 <= values["decimals"] <= fraction_digits
                or type(values.get("attempts")) is not int or not 1 <= values["attempts"] <= 10
                or values.get("polarity") not in ("auto", "light", "dark")
                or values.get("crop_mode") not in ("auto", "manual")
                or type(integer_digits) is not int or not 1 <= integer_digits <= 9
                or type(fraction_digits) is not int or not 0 <= fraction_digits <= 3
                or meter_display not in ("rollers", "digital", "mixed")
                or type(precision_mode) is not bool or type(fine_alignment) is not bool or type(adaptive_interval) is not bool or type(self_repair) is not bool
                or type(reflection_estimate_enabled) is not bool or type(reflection_suggestion_hidden) is not bool
                or not isinstance(reflection_confirmed_id, str) or len(reflection_confirmed_id) > 80
                or not isinstance(fallback_value, str) or not isinstance(fallback_time, str)):
            raise ValueError("Ungültige Einstellungen für die automatische Kontrolle")
        if fallback_value:
            if (not re.fullmatch(r"[0-9]{1,9}(?:[.,][0-9]{1,3})?", fallback_value)
                    or meter_prefix(fallback_value, values["decimals"], integer_digits) is None):
                raise ValueError("Ungültiger Fallback-Zählerstand")
            try:
                datetime.fromisoformat(fallback_time)
            except ValueError as error:
                raise ValueError("Ungültige Ablesezeit für den Fallback") from error
        else:
            fallback_time = ""
        rotation = values.get("rotation", 0)
        coords = crop_coordinates(values["crop"], values["width"], rotation)
        max_flow = values.get("max_flow_lph", DEFAULT_FLOW_LPH)
        if type(max_flow) is not int or not 1 <= max_flow <= MAX_FLOW_LPH:
            raise ValueError("Ungültiger maximaler Durchfluss")
        interval_minutes = values.get("interval_minutes", auto_rules["interval_minutes"])
        if not valid_interval_minutes(interval_minutes):
            raise ValueError("Ungültiges Prüfintervall")
        updated_rules = {**auto_rules, **values, "rotation": rotation, "max_flow_lph": max_flow,
                         "interval_minutes": interval_minutes, "integer_digits": integer_digits,
                         "fraction_digits": fraction_digits, "meter_display": meter_display,
                         "precision_mode": precision_mode, "fine_alignment_enabled": fine_alignment,
                         "adaptive_interval_enabled": adaptive_interval, "self_repair_enabled": self_repair,
                         "reflection_estimate_enabled": reflection_estimate_enabled,
                         "reflection_suggestion_hidden": reflection_suggestion_hidden,
                         "reflection_confirmed_id": reflection_confirmed_id,
                         "fallback_value": fallback_value, "fallback_time": fallback_time}
        updated_rules["crop"] = ",".join(str(part) for part in coords)
        updated_rules["digit_boxes"] = (digit_box_settings(updated_rules.get("digit_boxes"), integer_digits + fraction_digits)
                                        if updated_rules["crop_mode"] == "manual" else [])
        if (updated_rules["crop_revision"] == auto_rules["crop_revision"]
                and any(updated_rules[key] != auto_rules[key] for key in ("crop_mode", "crop", "rotation", "width", "digit_boxes"))):
            updated_rules["crop_revision"] = ""
        atomic_write(AUTO_RULES, json.dumps(updated_rules, indent=2).encode("utf-8"), 0o600)
        view_preferences = ("reflection_suggestion_hidden", "reflection_confirmed_id")
        needs_check = any(updated_rules[key] != auto_rules.get(key) for key in updated_rules
                          if key not in view_preferences)
        view_changed = any(updated_rules[key] != auto_rules.get(key) for key in view_preferences)
        auto_rules = updated_rules
        if needs_check or not view_changed:
            request_automatic_check()

    requested = Queue(maxsize=1)
    try:
        pause_state = json.loads(AUTO_PAUSED.read_text(encoding="utf-8"))
        auto_paused = {"value": isinstance(pause_state, dict) and pause_state.get("paused") is True}
    except (OSError, ValueError, AttributeError):
        auto_paused = {"value": False}

    def get_auto_paused():
        return auto_paused["value"]

    def save_auto_paused(value):
        if type(value) is not bool:
            raise ValueError("Pausenzustand muss wahr oder falsch sein")
        atomic_write(AUTO_PAUSED, json.dumps({"paused": value}).encode("utf-8"), 0o600)
        auto_paused["value"] = value
        if value:
            wake_worker.set()
        else:
            request_automatic_check()
    def save_language_modes(modes):
        atomic_write(LANGUAGE_MODES, json.dumps(modes).encode("utf-8"), 0o600)

    legacy_push = (options.get("push_dienst") or "").strip()
    if legacy_push and not PUSH_SERVICE.fullmatch(legacy_push):
        print("Handy-Push ist deaktiviert. Bitte den Dienst im Bereich Benachrichtigungen prüfen.")
        legacy_push = ""
    delivery = dict(enabled=bool(legacy_push), review_minutes=DEFAULT_REVIEW_MINUTES, delivery_hours=DEFAULT_DELIVERY_HOURS,
                    push=legacy_push, target="")
    default_delivery = dict(delivery)
    try:
        delivery = notification_rules(json.loads(NOTIFICATIONS.read_text(encoding="utf-8")))
    except FileNotFoundError:
        pass
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"Benachrichtigungseinstellungen konnten nicht geladen werden: {type(error).__name__}")

    def get_delivery():
        return dict(delivery)

    def save_delivery(values):
        nonlocal delivery
        validated = notification_rules(values)
        atomic_write(NOTIFICATIONS, json.dumps(validated).encode("utf-8"), 0o600)
        delivery = validated

    reset_requested = Event()
    reset_lock = Lock()
    reset_result = {"value": "idle"}

    def request_factory_reset():
        with reset_lock:
            if reset_result["value"] != "pending":
                reset_result["value"] = "pending"
                reset_requested.set()
                wake_worker.set()
        return "pending"

    def skip_setup():
        nonlocal setup_pending
        setup_pending = False
        snapshot["setup_pending"] = False
        atomic_write(EFFECTIVE_OPTIONS, json.dumps(snapshot, indent=2).encode("utf-8"), 0o600)
        wake_worker.set()

    activity = {"state": "paused" if auto_paused["value"] else "waiting",
                "detail": ("Automatik pausiert. Manuelle Tests bleiben verfügbar." if auto_paused["value"] else
                           "Einrichtung erforderlich. Bitte Bildquelle festlegen." if setup_pending else
                           "App läuft. Wartet auf die nächste automatische Prüfung.")}

    def set_activity(state, detail, *, completed=None, total=None):
        activity.update(state=state, detail=detail, updated_at=time.time(), completed=completed, total=total)

    def get_automatic_activity():
        if not get_auto_paused() and automatic_request is not handled_automatic_request:
            return {"state": "queued", "detail": "Einstellungen gespeichert. Prüfung startet gleich."}
        return dict(activity)

    settings_lock = RLock()
    calibration = None
    calibration_configuration = None
    calibration_next = 0.0
    calibration_worker = None
    calibration_preview = {}
    calibration_images = {}
    calibration_preview_version = 0
    geometry_backup = HISTORY.with_name("geometry-backup.json")

    def read_geometry_backup():
        try:
            backup = json.loads(geometry_backup.read_text(encoding="utf-8"))
            return backup["rules"] if backup["source"] == get_source()[0] else None
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def calibration_configuration_now():
        return get_auto_rules(), get_source()

    def control_calibration(action, limit, region=None):
        nonlocal calibration, calibration_configuration, calibration_next
        with settings_lock:
            running = calibration is not None and calibration.state in ("waiting", "testing") and not calibration.expired(time.monotonic())
            if action == "cancel":
                if running:
                    calibration.state = "cancelled"
            elif action == "restore":
                backup = read_geometry_backup()
                if running or not backup:
                    raise ValueError("No available geometry backup")
                keys = ("crop_mode", "crop", "width", "rotation", "digit_boxes")
                save_auto_rules({**get_auto_rules(), **{key: backup[key] for key in keys},
                                 "crop_revision": str(time.time_ns()) if backup["crop_mode"] == "manual" else ""})
                calibration = None
                calibration_preview.clear()
                calibration_images.clear()
            else:
                source, pending = get_source()
                if pending or not source["selected"] or get_auto_paused():
                    raise ValueError("Choose a source and resume automatic checks first.")
                if not MIN_IMAGE_LIMIT <= limit <= MAX_IMAGES:
                    raise ValueError("Invalid calibration image limit")
                now = time.monotonic()
                configuration = calibration_configuration_now()
                if running and (action == "repair" or (
                        calibration.limit == limit and calibration.region == region and configuration == calibration_configuration)):
                    return
                repair = action == "repair"
                previous = (calibration.best if calibration and calibration_configuration[1][0] == source else None)
                if repair:
                    atomic_write(geometry_backup, json.dumps({"source": source, "rules": get_auto_rules()}).encode(),
                                 0o600)
                calibration = Calibration(limit=limit, started=now, automatic=repair,
                                          duration=GEOMETRY_REPAIR_SECONDS if repair else TIME_LIMIT,
                                          attempt_limit=GEOMETRY_REPAIR_LIMIT if repair else MAX_ATTEMPTS,
                                          previous_layout=previous, region=region)
                calibration_preview.clear()
                calibration_images.clear()
                calibration_configuration = configuration
                calibration_next = now
            wake_worker.set()

    def calibration_status():
        with settings_lock:
            if calibration is None:
                return None
            status = calibration.status(time.monotonic())
            status["preview"] = dict(calibration_preview)
            if not status["seconds"] and status["state"] in ("waiting", "testing"):
                status["state"] = "timeout"
            elif status["state"] == "waiting" and calibration.image_wait_expired(time.monotonic()):
                status["state"] = "image_timeout"
            if status["state"] == "saved":
                status["settings"] = {**calibration.candidate.settings(), "crop_revision": auto_rules["crop_revision"]}
            elif status["state"] in ("failed", "timeout", "image_timeout") and calibration.best:
                status["proposal"] = calibration.best.settings()
            return status

    def calibration_image(kind, version):
        with settings_lock:
            return next((content for revision, content in calibration_images.get(kind, ())
                         if str(revision) == version), None)

    def run_calibration(active_rules, active_source, mode, base, camera, reference, source_key):
        nonlocal calibration, calibration_next, calibration_preview_version
        with settings_lock:
            now = time.monotonic()
            job = calibration
            if job is None or job.state not in ("waiting", "testing"):
                return False
            if job.expired(now):
                job.state = "timeout"
                return False
            if job.image_wait_expired(now):
                job.state = "image_timeout"
                return False
            if calibration_configuration_now() != calibration_configuration or get_auto_paused():
                job.state = "cancelled"
                return False
            configured_rules, (configured_camera, _) = calibration_configuration
            if now < calibration_next or (active_rules, active_source) != (configured_rules, configured_camera):
                return True
            job.state = "testing"
            job.stage = "capture"
            attempt = deepcopy(job)
        deadline = time.monotonic() + 30

        def stopped():
            return time.monotonic() >= deadline or calibration is not job or job.state == "cancelled" or get_auto_paused()

        def fetch(url, token=None, timeout=8):
            if stopped():
                raise TimeoutError("Calibration stopped")
            return get_bytes(url, token, timeout=min(timeout, max(0.01, deadline - time.monotonic())))

        def report_calibration(stage, variant=None, rotation=None, positions=None):
            with settings_lock:
                if calibration is job and job.state == "testing":
                    job.stage, job.variant, job.rotation = stage, variant, rotation
                    job.attempts = attempt.attempts
                    calibration_preview["weak_positions"] = positions or []

        def report_image(kind, content, **details):
            nonlocal calibration_preview_version
            with settings_lock:
                if calibration is not job or job.state != "testing":
                    return
                calibration_preview_version += 1
                recent = calibration_images.setdefault(kind, [])
                recent.append((calibration_preview_version, content))
                del recent[:-2]
                if kind == "frame":
                    calibration_preview.clear()
                calibration_preview.update(details, **{kind: calibration_preview_version})

        result = None
        selected = None
        try:
            if mode == "slfork":
                result = capture(base, {}, fetch=fetch)
            elif mode == "slfork_camera":
                result = capture_edge_camera(base, zone, fetch=fetch)
            elif camera:
                result = capture_camera(camera, reference, token, zone, fetch=fetch)
            if result is not None and not stopped():
                picture, drawn, sample = result
                captured = sample_epoch(sample, zone, datetime.now(zone))
                if captured is not None:
                    if mode == "slfork":
                        sample.update(slfork_reference(sample, captured, zone, history.get("last_slfork_match", {})))
                    baseline = history.get("consumption", {})
                    if baseline.get("source") == source_key and baseline.get("timestamp", 0) < captured:
                        baseline = {**baseline, "source": "calibration"}
                    else:
                        baseline = None
                    if baseline is None and active_rules["fallback_value"] and active_rules["fallback_time"]:
                        stamp = timestamp_epoch(active_rules["fallback_time"], zone)
                        if stamp < captured:
                            baseline = accumulate_consumption(
                                {}, "calibration", stamp, active_rules["fallback_value"], active_rules["decimals"],
                                active_rules["max_flow_lph"], active_rules["integer_digits"],
                            )
                    with Image.open(io.BytesIO(picture)) as frame:
                        if frame.width * frame.height > MAX_IMAGE_PIXELS:
                            raise ValueError("Kamerabild hat zu viele Pixel")
                        frame.load()
                        overlay = None
                        if drawn:
                            try:
                                with Image.open(io.BytesIO(drawn)) as marked:
                                    if marked.size == frame.size:
                                        overlay = marked.convert("RGB")
                            except (OSError, ValueError, Image.DecompressionBombError):
                                pass

                        previous_layout = None
                        frame_ready = False
                        readings = []
                        whole = active_rules["integer_digits"]
                        fraction = active_rules["fraction_digits"]
                        digit_cache = {}
                        digit_cache_lock = Lock()
                        calibration_ocr_env = {**os.environ, "OMP_THREAD_LIMIT": "1"}

                        def cached_digit(picture, light, digits, *, profile, **kwargs):
                            key = (picture.mode, picture.size, hashlib.sha256(picture.tobytes()).digest(),
                                   digits, profile)
                            with digit_cache_lock:
                                pending = digit_cache.get(key)
                                if pending is None:
                                    digit_cache[key] = future = Future()
                            if pending is not None:
                                return pending.result()
                            try:
                                value = read_register(picture, light, digits, profile=profile,
                                                      process_env=calibration_ocr_env, **kwargs)
                            except Exception as error:
                                future.set_exception(error)
                                raise
                            future.set_result(value)
                            return value

                        def on_image():
                            nonlocal frame_ready, deadline
                            now = time.monotonic()
                            deadline = now + attempt.remaining(now)
                            attempt.last_image_at = attempt.searching_since = now
                            with settings_lock:
                                job.searching_since = now
                                job.seen = attempt.seen.copy()
                            try:
                                report_image("frame", calibration_jpeg(frame, (720, 540)))
                                frame_ready = True
                            except (OSError, ValueError):
                                pass

                        def report_crop(layout, register, reading):
                            if not frame_ready:
                                return
                            box = layout.box
                            region = [box[0] / frame.width, box[1] / frame.height,
                                      (box[2] - box[0]) / frame.width, (box[3] - box[1]) / frame.height]
                            try:
                                preview = draw_test_preview(
                                    *register[:4], reading, whole, fraction, readings=readings, pending=reading is None,
                                )
                                report_image("crop", calibration_jpeg(preview, (820, 300)),
                                             region=region, reading=reading, angle=layout.rotation,
                                             approximate=not bool(layout.digit_boxes), method=layout.method, reason=None)
                            except (OSError, ValueError):
                                pass

                        def report_decision(reason):
                            with settings_lock:
                                if frame_ready and calibration is job and job.state == "testing":
                                    calibration_preview["reason"] = reason

                        def report_regions(boxes):
                            regions = [[round(1000 * value / size) for value, size in
                                        zip(box, frame.size * 2)] for box in boxes]
                            with settings_lock:
                                if frame_ready and calibration is job and job.state == "testing":
                                    calibration_preview["regions"] = regions

                        def show_selected(layout, values):
                            nonlocal previous_layout
                            previous_layout = layout
                            readings[:] = values
                            report_crop(layout, register_for(layout), values[-1])

                        def register_for(layout):
                            return select_register(
                                frame, None, layout.box, layout.width, layout.rotation, whole, fraction,
                                digit_boxes=layout.digit_boxes,
                            )

                        def recognize(layout, profile, register, ocr_deadline=None):
                            return read_visible_digits(
                                *register[:4], options["helle_ziffern"], active_rules["polarity"], profile=profile,
                                whole_digits=whole, fraction_digits=fraction,
                                deadline=deadline if ocr_deadline is None else ocr_deadline,
                                prefer_boxes=bool(layout.digit_boxes), recognize=cached_digit,
                            )

                        def read(layout, profile):
                            nonlocal previous_layout
                            register = register_for(layout)
                            if layout != previous_layout:
                                readings.clear()
                                previous_layout = layout
                                report_crop(layout, register, None)
                            reading = recognize(layout, profile, register)
                            readings.append(reading)
                            report_crop(layout, register, reading)
                            return reading

                        fine_deadline = None

                        def report_fine(variant, rotation, positions):
                            nonlocal fine_deadline
                            if fine_deadline is None:
                                fine_deadline = min(deadline, time.monotonic() + 12)
                            report_calibration("refine", variant, rotation, positions)

                        if attempt.verification_pending:
                            report_calibration("verify", rotation=attempt.candidate.rotation)
                            selected = attempt.verify(frame, sample, captured, active_rules, read, stopped,
                                                      on_image=on_image, on_decision=report_decision)
                        else:
                            report_calibration("search")
                            candidate = attempt.examine(
                                frame, overlay, sample, captured, active_rules, read, stopped, baseline,
                                on_attempt=lambda variant, rotation: report_calibration("ocr", variant, rotation),
                                on_image=on_image, on_decision=report_decision,
                                refine_read=lambda layout, profile: recognize(
                                    layout, profile, register_for(layout), fine_deadline),
                                on_refine=report_fine,
                                on_regions=report_regions,
                                on_selected=show_selected,
                                angle_read=read,
                                on_angle=lambda variant, rotation: report_calibration("angle", variant, rotation),
                            )
                            attempt.verification_pending = candidate is not None
        except (OSError, ValueError, TypeError, Image.DecompressionBombError) as error:
            print(f"Selbsteinrichtung konnte die Aufnahme nicht prüfen: {type(error).__name__}")
        with settings_lock:
            now = time.monotonic()
            if attempt.searching_since is not None:
                attempt.spent += now - attempt.searching_since
                attempt.searching_since = None
                attempt.last_image_at = now
            if calibration is not job or job.state == "cancelled":
                return True
            if attempt.expired(now):
                attempt.state = "timeout"
            elif calibration_configuration_now() != calibration_configuration or get_auto_paused():
                attempt.state = "cancelled"
            elif selected:
                try:
                    save_auto_rules({**get_auto_rules(), **selected.settings(), "crop_revision": str(time.time_ns())})
                    attempt.state = "saved"
                except (OSError, ValueError):
                    attempt.state = "save_failed"
            elif len(attempt.seen) >= attempt.limit or attempt.attempts >= attempt.attempt_limit:
                attempt.state = "failed"
            else:
                attempt.state = "waiting"
                attempt.stage = "verify_wait" if attempt.verification_pending else "waiting"
            calibration = attempt
            calibration_next = now + CAPTURE_INTERVAL
            wake_worker.set()
        return True

    _, update_progress, reset_manual_progress = start_panel(
        HISTORY, DESTINATION, GOOD_IMAGE, requested, default_decimals, default_attempts,
        get_auto_rules, save_auto_rules, options["ausschnitt"], options["vorkomma_breite"], TEST_IMAGE,
        partial(load_preferences, LANGUAGE_MODES), save_language_modes, get_delivery, save_delivery, get_source, save_source,
        wake_worker.set, test_source_image=TEST_SOURCE_IMAGE, automatic_preview=AUTOMATIC_PREVIEW,
        request_factory_reset=request_factory_reset, get_reset_status=lambda: reset_result["value"],
        skip_setup=skip_setup,
        discover_sources=partial(discover_ha_sources, token),
        get_activity=get_automatic_activity,
        get_auto_paused=get_auto_paused, save_auto_paused=save_auto_paused,
        settings_lock=settings_lock, get_calibration=calibration_status, control_calibration=control_calibration,
        get_calibration_image=calibration_image, has_calibration_backup=lambda: read_geometry_backup() is not None,
    )
    reminder = Reminder(token)
    pending_image = None
    startup = True
    published_standalone = bool(history.get("standalone_reading"))
    print(f"{APP_NAME} gestartet")

    def perform_factory_reset():
        nonlocal history, configured_source, setup_pending, auto_rules, delivery, source_selected
        nonlocal pending_image, startup, published_standalone, snapshot
        nonlocal handled_automatic_request, calibration
        try:
            reminder.clear_for_reset(history)
            paths = (
                HISTORY, AUTO_RULES, SOURCE_SETTINGS, NOTIFICATIONS, LANGUAGE_MODES,
                HISTORY.with_name("manual-test-settings.json"), DESTINATION, GOOD_IMAGE,
                TEST_IMAGE, TEST_SOURCE_IMAGE, AUTOMATIC_PREVIEW, AUTO_PAUSED, geometry_backup,
            )
            for path in paths:
                path.unlink(missing_ok=True)
            history = {}
            auto_paused["value"] = False
            configured_source = dict(default_source)
            setup_pending = True
            source_selected = configured
            auto_rules = dict(default_auto_rules)
            delivery = dict(default_delivery)
            pending_image = None
            startup = True
            published_standalone = False
            snapshot = {**snapshot, "setup_pending": True}
            atomic_write(EFFECTIVE_OPTIONS, json.dumps(snapshot, indent=2).encode("utf-8"), 0o600)
            handled_automatic_request = automatic_request
            reset_manual_progress()
            with settings_lock:
                calibration = None
                calibration_preview.clear()
                calibration_images.clear()
            reset_result["value"] = "done"
        except (OSError, ValueError, TypeError) as error:
            print(f"Werkreset konnte nicht abgeschlossen werden: {type(error).__name__}")
            reset_result["value"] = "failed"

    while True:
        wake_worker.clear()
        if reset_requested.is_set():
            reset_requested.clear()
            perform_factory_reset()
            continue
        requested_automatic_check = automatic_request
        run_automatic_now = requested_automatic_check is not handled_automatic_request
        active_rules = get_auto_rules()
        active_source, waiting_for_setup = get_source()
        mode = active_source["mode"]
        interval_minutes = automatic_interval_minutes(active_rules["interval_minutes"], mode)
        esp_camera_only = mode == "slfork_camera"
        standalone = mode in ("esphome", "slfork_camera") or mode == "camera" and not active_source["reference"]
        base = active_source["url"].rstrip("/")
        camera = active_source["camera"] if mode not in ESP_ADDRESS_MODES else ""
        reference = active_source["reference"] if mode == "camera" else ""
        source_key = [mode, camera or base, reference]
        now = datetime.now(zone)
        adaptive = mode == "slfork" and active_rules["adaptive_interval_enabled"]
        if adaptive:
            interval_minutes = suggested_interval(interval_minutes, history.get("adaptive_flow", {}), source_key, now.month)
        if not run_automatic_now and reschedule_next_check(history, interval_minutes):
            try:
                atomic_write(HISTORY, json.dumps(history).encode("utf-8"), 0o600)
            except OSError as error:
                print(f"Prüfintervall konnte nicht in der Historie gespeichert werden: {type(error).__name__}")
        standalone_source = source_key[1] if standalone else ""
        source_changed = history.get("check_source", initial_source_key) != source_key
        if source_changed:
            pending_image = None
        active_delivery = get_delivery()
        review_after = active_delivery["review_minutes"] * 60
        reminder.configure(enabled=active_delivery["enabled"], push=active_delivery["push"], target=active_delivery["target"],
                           delay=active_delivery["delivery_hours"] * 60 * 60)
        decimals = active_rules["decimals"]
        precision_mode = active_rules["precision_mode"]
        integer_digits = active_rules["integer_digits"]
        fraction_digits = active_rules["fraction_digits"]
        max_attempts = active_rules["attempts"]
        remaining = history.get("next_check_at", 0) - now.timestamp()
        try:
            manual_options = requested.get_nowait()
        except Empty:
            manual_options = None
        manual = manual_options is not None
        request_id = manual_options["request_id"] if manual else None
        if manual:
            update_progress(request_id, "running", "Lade Zählerbild und Referenzdaten …")
        if (not manual and calibration is not None and calibration.state in ("waiting", "testing")
                and time.monotonic() >= calibration_next
                and (calibration_worker is None or not calibration_worker.is_alive())):
            calibration_worker = Thread(target=run_calibration,
                                        args=(active_rules, active_source, mode, base, camera, reference, source_key),
                                        daemon=True, name="meter-calibration")
            calibration_worker.start()
        if get_auto_paused() and not manual:
            set_activity("paused", "Automatik pausiert. Manuelle Tests bleiben verfügbar.")
            wake_worker.wait(timeout=15)
            continue
        if (waiting_for_setup or not active_source["selected"]) and not manual:
            set_activity("waiting", "Einrichtung erforderlich. Bitte Bildquelle festlegen.")
            wake_worker.wait(timeout=2)
            continue
        if remaining > 0 and not startup and not manual and not source_changed and not run_automatic_now:
            set_activity("waiting", STANDALONE_PENDING_NOTICE if history.get("check_status") == STANDALONE_PENDING
                         else "App läuft. Wartet auf die nächste automatische Prüfung.")
            # Refresh status after a Home Assistant restart, even between checks.
            if "check_status" in history:
                try:
                    publish_check(history, now, token, review_after)
                    if pending_image is not None:
                        publish(*pending_image, history, now, token, review_after)
                        pending_image = None
                    if standalone or published_standalone:
                        publish_standalone(history, standalone_source, token)
                        published_standalone = standalone
                    publish_consumption(history, token)
                except OSError as error:
                    print(f"Prüfstatus konnte nicht übertragen werden: {error}")
                check_reminder(reminder, history, now, review_after)
            wake_worker.wait(timeout=min(remaining, RETRY_INTERVAL,
                                         CAPTURE_INTERVAL if calibration is not None
                                         and calibration.state in ("waiting", "testing") else RETRY_INTERVAL))
            continue

        keep_schedule = startup and remaining > 0 and not source_changed and not run_automatic_now
        startup = startup and manual
        if not manual:
            set_activity("working", "Automatische Prüfung startet …")
            handled_automatic_request = requested_automatic_check
        data = None
        outcome = "capture_unavailable"
        source_history = dict(history)
        if source_changed:
            source_history["confirmations"] = []
            for field in ("last_epoch", "last_match_at", "failure_since", "failure_attempts", "retry_suppressed", "capture_failure_since",
                          "source_connection_status", "source_connection_detail",
                          "last_digit_failures",
                          "standalone_candidate",
                          "learned_rotation", "geometry_recovery",
                          "reflection_anchor", "reflection_pending", "reflection_estimate", "reflection_streak", "reflection_live_estimate",
                          "last_slfork_match", "last_reference", "last_reference_time",
                          "last_reference_is_fallback", "ocr_value", "ocr_readings"):
                source_history.pop(field, None)
        source_history["check_source"] = source_key
        updated = dict(source_history)
        validation_detail = None
        new_consumption = None
        new_standalone = None
        standalone_reference = None
        fine_update = None
        recover_geometry = False
        geometry_warning = False
        # Confirmations obtained with another precision are not valid evidence
        # for the newly chosen automatic comparison rules.
        format_changed = any(history.get(key, default) != value for key, default, value in (
            ("comparison_decimals", decimals, decimals),
            ("comparison_integer_digits", integer_digits, integer_digits),
            ("comparison_fraction_digits", fraction_digits, fraction_digits),
            ("precision_mode", False, precision_mode),
        ))
        if format_changed:
            updated["confirmations"] = []
            updated.pop("last_match_at", None)
            updated.pop("last_digit_failures", None)
            for field in ("reflection_anchor", "reflection_pending", "reflection_estimate", "reflection_streak", "reflection_live_estimate"):
                updated.pop(field, None)
            if history.get("comparison_integer_digits", integer_digits) != integer_digits:
                updated.pop("standalone_reading", None)
        if format_changed or run_automatic_now:
            updated.pop("standalone_candidate", None)
        updated["comparison_decimals"] = decimals
        updated["comparison_integer_digits"] = integer_digits
        updated["comparison_fraction_digits"] = fraction_digits
        updated["precision_mode"] = precision_mode
        updated["check_detail"] = "Bild oder Messwert fehlt. Verbindung prüfen."
        manual_result = {"status": "capture_unavailable", "detail": updated["check_detail"]}
        diagnostics = {}
        sample = None
        raw_fallback = False
        duplicate_cycle = False
        automatic_preview_ready = False
        live_deadline = (time.monotonic() + LIVE_CAPTURE_WINDOW_SECONDS
                         if active_source["mode"] == "camera" else None)
        try:
            manual_upload = manual and bool(manual_options.get("image"))
            if manual_upload:
                update_progress(request_id, "running", "Testbild geladen – prüfe Ausschnitt und Ziffern …")
                result = (manual_options["image"], None, {
                    "esp_timestamp": datetime.now(zone).isoformat(),
                    "reference_required": False,
                    "image_source": "manual_upload",
                    "raw_value": None,
                    "actual_value": None,
                })
            else:
                if not manual:
                    set_activity("working", "Warte auf ein Kamerabild …" if camera or esp_camera_only else
                                 "Warte auf Bild und Messwerte vom ESP …")
                if camera:
                    result = capture_camera(
                        camera, reference, token, zone,
                        timeout=min(8, max(0.2, live_deadline - time.monotonic())) if live_deadline else 8,
                    )
                elif esp_camera_only:
                    result = capture_edge_camera(base, zone)
                else:
                    result = capture(base, diagnostics)
            if mode == "slfork" and result is None and not slfork_cycle_failed(diagnostics):
                print("Noch kein ausgerichtetes SLFork-Bild verfügbar. Neuer Versuch in 10 Sekunden.")
                if not manual:
                    set_activity("working", "Warte auf ein aktuelles Bild vom ESP …")
                time.sleep(10)
                result = capture(base, diagnostics)
            if mode == "slfork" and not manual_upload and (
                result is None or slfork_cycle_failed(diagnostics)
                or sample_epoch(result[2], zone, datetime.now(zone)) is None
            ):
                raw_fallback = True
                if manual:
                    update_progress(request_id, "running", SLFORK_RAW_NOTICE)
                else:
                    set_activity("working", SLFORK_RAW_NOTICE)
                result = capture_slfork_raw(base, zone)
            if result is not None:
                if not manual:
                    set_activity("working", "Bild wird vorbereitet.")
                    updated["source_connection_status"] = "stale" if raw_fallback else "connected"
                    updated["source_connection_detail"] = (
                        "Aufbereitetes ESP-Bild nicht nutzbar. Rohbild ohne ESP-Referenz geprüft." if raw_fallback else
                        "Kamera erreichbar. Frisches Bild empfangen." if camera or esp_camera_only else
                        "ESP erreichbar. Bild und Messwerte empfangen."
                    )
                if manual:
                    update_progress(request_id, "running", "Bild geladen – überprüfe Zeitstempel und Ziffernbereich …")
                picture, overlay, sample = result
                now = datetime.now(zone)
                captured = sample_epoch(sample, zone, now)
                if not manual and (captured is None or captured <= updated.get("last_epoch", 0)):
                    updated["source_connection_status"] = "stale"
                    if captured is None:
                        updated["source_connection_detail"] = (
                            "ESP erreichbar, aber Bild ist älter als 15 Minuten oder hat einen ungültigen Zeitstempel."
                            if not camera else "Kamera erreichbar, aber das Bild hat einen ungültigen Zeitstempel."
                        )
                    else:
                        updated["source_connection_detail"] = (
                            "ESP erreichbar. Seit der letzten Prüfung kam kein neues Bild; das vorhandene Bild ist noch nicht veraltet."
                            if not camera else "Home-Assistant-Kamera erreichbar; dieses Bild wurde bereits geprüft."
                        )
                    if (captured is not None and captured == updated.get("last_epoch")
                            and history.get("check_status") and not format_changed):
                        outcome = history["check_status"]
                        updated["check_detail"] = history["check_detail"]
                        duplicate_cycle = mode == "slfork" and not raw_fallback
                    else:
                        outcome = "stale_sample"
                        updated["check_detail"] = "Bild zu alt oder schon geprüft."
                    result = None
            if result is not None:
                image_time = captured if captured is not None else sample_timestamp(sample, zone)
                if mode == "slfork" and not manual_upload and not raw_fallback:
                    sample.update(slfork_reference(sample, image_time, zone, updated.get("last_slfork_match", {})))
                manual_reference = manual_options.get("manual_reference", "") if manual else ""
                apply_manual_reference(sample, manual_reference,
                                       manual_options["decimals"] if manual else decimals,
                                       integer_digits)
                with Image.open(io.BytesIO(picture)) as frame:
                    if frame.width * frame.height > MAX_IMAGE_PIXELS:
                        raise ValueError("Kamerabild hat zu viele Pixel")
                    if frame.format != "JPEG":
                        if not (camera or manual and manual_options.get("image")) or frame.format != "PNG":
                            raise ValueError("Das Kameraformat wird nicht unterstützt")
                        with io.BytesIO() as normalized:
                            frame.convert("RGB").save(normalized, "JPEG", quality=95)
                            picture = normalized.getvalue()
                    frame.load()
                    if manual:
                        atomic_write(TEST_SOURCE_IMAGE, picture, 0o600)
                    ocr_readings = []
                    ocr_error = None
                    detect_raw = False
                    rotation_adjustment = 0
                    rotation_key = None
                    try:
                        crop_rules = manual_options if manual else active_rules
                        manual_crop = crop
                        manual_width = options["vorkomma_breite"]
                        selected_overlay = overlay
                        rotation = 0
                        detect_raw = crop_rules["crop_mode"] == "auto"
                        custom_boxes = crop_rules.get("digit_boxes") if not detect_raw else None
                        if crop_rules["crop_mode"] == "manual":
                            rotation = crop_rules.get("rotation", 0)
                            manual_width = crop_rules["width"]
                            manual_crop = crop_coordinates(crop_rules["crop"], manual_width, rotation)
                            selected_overlay = None
                        if not manual and selected_overlay is None and not custom_boxes:
                            rotation_key = [
                                *manual_crop, manual_width, rotation, detect_raw, integer_digits, fraction_digits,
                                raw_fallback,
                            ]
                            if active_rules["crop_revision"]:
                                rotation_key.append(active_rules["crop_revision"])
                            learned = updated.get("learned_rotation", {})
                            if isinstance(learned, dict) and learned.get("crop") == rotation_key:
                                rotation_adjustment = learned.get("adjustment", 0)
                            pending = updated.get("standalone_candidate", {})
                            if standalone and pending.get("crop") == rotation_key:
                                rotation_adjustment = pending.get("rotation_adjustment", rotation_adjustment)
                            if type(rotation_adjustment) is not int or abs(rotation_adjustment) > MAX_LEARNED_ROTATION:
                                rotation_adjustment = 0
                        base_adjustment = rotation_adjustment

                        def prepare_register(original, current_overlay):
                            if base_adjustment:
                                return select_tilted_register(
                                    original, manual_crop, manual_width, rotation, base_adjustment,
                                    integer_digits, fraction_digits, detect_raw,
                                )
                            return select_register(
                                original, current_overlay, manual_crop, manual_width, rotation,
                                integer_digits, fraction_digits, detect_raw=detect_raw, digit_boxes=custom_boxes,
                            )

                        register, integer_width, whole_boxes, fraction_boxes, source = prepare_register(
                            frame, selected_overlay
                        )
                        read_state = {"register": register, "integer_width": integer_width,
                                      "whole_boxes": whole_boxes, "fraction_boxes": fraction_boxes,
                                      "source": source, "picture": picture, "captured": captured,
                                      "attempts": 0}
                        live_source = live_deadline is not None

                        def read_layout(layout, profile):
                            return read_visible_digits(
                                *layout[:4], options["helle_ziffern"],
                                manual_options["polarity"] if manual else active_rules["polarity"],
                                profile=profile, whole_digits=integer_digits, fraction_digits=fraction_digits,
                                **({"prefer_boxes": True} if custom_boxes else {}),
                            )

                        def read(profile):
                            if live_source and (manual or not standalone) and read_state["attempts"]:
                                remaining = live_deadline - time.monotonic()
                                if remaining <= 0:
                                    return "?"
                                latest = capture_camera(
                                    camera, reference, token, zone,
                                    timeout=min(8, max(0.2, remaining)),
                                )
                                if latest is None:
                                    return "?"
                                latest_picture, latest_overlay, latest_sample = latest
                                latest_time = sample_epoch(latest_sample, zone, datetime.now(zone))
                                apply_manual_reference(latest_sample, manual_reference,
                                                       manual_options["decimals"] if manual else decimals,
                                                       integer_digits)
                                with Image.open(io.BytesIO(latest_picture)) as latest_frame:
                                    if latest_frame.width * latest_frame.height > MAX_IMAGE_PIXELS:
                                        raise ValueError("Kamerabild hat zu viele Pixel")
                                    if latest_frame.format != "JPEG":
                                        if latest_frame.format != "PNG":
                                            raise ValueError("Das Kameraformat wird nicht unterstützt")
                                        with io.BytesIO() as normalized:
                                            latest_frame.convert("RGB").save(normalized, "JPEG", quality=95)
                                            latest_picture = normalized.getvalue()
                                    latest_frame.load()
                                    if manual:
                                        atomic_write(TEST_SOURCE_IMAGE, latest_picture, 0o600)
                                    latest_register, latest_integer_width, latest_whole, latest_fraction, latest_source = prepare_register(
                                        latest_frame, latest_overlay,
                                    )
                                sample.clear()
                                sample.update(latest_sample)
                                read_state.update(register=latest_register,
                                                  integer_width=latest_integer_width,
                                                  whole_boxes=latest_whole, fraction_boxes=latest_fraction,
                                                  source=latest_source, picture=latest_picture,
                                                  captured=latest_time)
                            read_state["attempts"] += 1
                            return read_layout((
                                read_state["register"], read_state["integer_width"],
                                read_state["whole_boxes"], read_state["fraction_boxes"],
                            ), profile)
                        if manual:
                            update_progress(request_id, "ocr", f"OCR-Prüfung gestartet (max. {manual_options['attempts']} Versuche).", 0)
                        def report_ocr(attempts, message):
                            if manual:
                                update_progress(request_id, "ocr", message, attempts)
                            else:
                                running = "läuft" in message
                                current_attempt = attempts + 1 if running else attempts
                                state = "läuft." if running else "abgeschlossen."
                                set_activity("working", f"Lese Zählerbild: OCR-Versuch {current_attempt} von {ocr_limit} {state}",
                                             completed=attempts, total=ocr_limit)
                        require_consensus = (raw_fallback and not manual_reference) or (standalone and not manual)
                        configured_attempts = manual_options["attempts"] if manual else max_attempts
                        if require_consensus:
                            configured_attempts = max(2, configured_attempts)
                        extra_attempts = (10 if not manual and history.get("failure_attempts", 0) == 0
                                          and not history.get("retry_suppressed") else 0)
                        ocr_limit = min(15, configured_attempts + extra_attempts)
                        if live_source:
                            ocr_limit = min(ocr_limit, LIVE_CAPTURE_MAX_ATTEMPTS)
                        reserve_for_rotation = (2 * len(INTENSIVE_ROTATIONS)
                                                if extra_attempts and source != "auto" and not custom_boxes else 0)
                        regular_limit = ocr_limit - reserve_for_rotation
                        regular_attempts = min(configured_attempts, regular_limit)
                        comparison_decimals = manual_options["decimals"] if manual else decimals

                        def stop_ocr():
                            return (not manual and get_auto_paused()) or (live_source and time.monotonic() >= live_deadline)

                        ocr, ocr_confirmed, ocr_attempts = read_with_retries(
                            read, sample, comparison_decimals,
                            progress=report_ocr,
                            max_attempts=regular_attempts,
                            trace=ocr_readings, standalone=require_consensus,
                            integer_digits=integer_digits,
                            extra_attempts=regular_limit - regular_attempts,
                            stop_before_attempt=stop_ocr,
                            force_all_attempts=manual,
                        )
                        regular_status, _ = compare_sample(sample, ocr, comparison_decimals,
                                                           ocr_confirmed=ocr_confirmed, integer_digits=integer_digits)
                        if reserve_for_rotation and regular_status in ("difference", "ocr_unclear") and not stop_ocr():
                            with Image.open(io.BytesIO(read_state["picture"])) as original:
                                for delta in INTENSIVE_ROTATIONS:
                                    if stop_ocr():
                                        break
                                    adjustment = base_adjustment + delta
                                    if abs(adjustment) > MAX_LEARNED_ROTATION:
                                        continue
                                    try:
                                        tilted = select_tilted_register(
                                            original, manual_crop, manual_width, rotation, adjustment,
                                            integer_digits, fraction_digits, detect_raw,
                                        )
                                    except ValueError:
                                        continue
                                    tilted_readings = []

                                    def report_rotation(attempts, _):
                                        set_activity("working", INTENSIVE_ROTATION_STATUS,
                                                     completed=ocr_attempts + attempts, total=ocr_limit)

                                    value, confirmed, attempts = read_with_retries(
                                        lambda profile: read_layout(tilted, profile), sample, comparison_decimals,
                                        max_attempts=2, progress=report_rotation, trace=tilted_readings,
                                        standalone=require_consensus, integer_digits=integer_digits,
                                        stop_before_attempt=stop_ocr,
                                    )
                                    ocr_attempts += attempts
                                    rotated_status, _ = compare_sample(
                                        sample, value, comparison_decimals, ocr_confirmed=confirmed,
                                        integer_digits=integer_digits,
                                    )
                                    if rotated_status in ("match", "ocr_only"):
                                        ocr, ocr_confirmed = value, confirmed
                                        ocr_readings = tilted_readings
                                        reg, width, whole, fractions, kind = tilted
                                        read_state.update(register=reg, integer_width=width, whole_boxes=whole,
                                                          fraction_boxes=fractions, source=kind)
                                        rotation_adjustment = adjustment
                                        break
                        register = read_state["register"]
                        integer_width = read_state["integer_width"]
                        whole_boxes = read_state["whole_boxes"]
                        fraction_boxes = read_state["fraction_boxes"]
                        source = read_state["source"]
                        picture = read_state["picture"]
                        captured = read_state["captured"]
                        image_time = captured if captured is not None else sample_timestamp(sample, zone)
                    except (OSError, ValueError, subprocess.SubprocessError) as error:
                        print(f"OCR-Bildprüfung fehlgeschlagen: {error}")
                        ocr_error = ("Ausschnitt ungültig. Koordinaten prüfen." if isinstance(error, ValueError)
                                     else "OCR fehlgeschlagen. Ziffernbereich prüfen.")
                        register, ocr, source = frame, None, "unavailable"
                        ocr_confirmed, ocr_attempts = True, 0
                    if not manual:
                        reading_status, _ = compare_sample(sample, ocr, decimals, ocr_confirmed=ocr_confirmed,
                                                           integer_digits=integer_digits)
                        accept_reference = (
                            decimals == 3 and reading_status in ("difference", "ocr_unclear")
                            and last_digit_can_pass(updated, precision_mode)
                            and differs_only_at_last_digit(sample, ocr, ocr_readings, integer_digits)
                        )
                        if (reading_status == "match" or accept_reference
                                or ((standalone or raw_fallback) and reading_status == "ocr_only")):
                            try:
                                if standalone:
                                    new_standalone = standalone_reading(
                                        standalone_source, sample, ocr, decimals, history.get("standalone_reading"),
                                        integer_digits,
                                    )
                                    if new_standalone is None:
                                        raise ImplausibleReading(LOWER_READING)
                                previous_consumption = history.get("consumption", {})
                                if not previous_consumption and active_rules["fallback_value"]:
                                    fallback_prefix = meter_prefix(active_rules["fallback_value"], decimals,
                                                                   integer_digits)
                                    fallback_time = active_rules["fallback_time"]
                                    if fallback_prefix is None or not fallback_time:
                                        raise ImplausibleReading("Fallback-Wert passt nicht zur Zähleranzeige.")
                                    fallback_stamp = datetime.fromisoformat(fallback_time).replace(tzinfo=zone).timestamp()
                                    fallback_step = 10 ** (3 - decimals)
                                    fallback_litres = fallback_prefix * fallback_step
                                    previous_consumption = {
                                        "source": source_key, "timestamp": fallback_stamp,
                                        "reading_litres": fallback_litres, "anchor_litres": fallback_litres,
                                        "step_litres": fallback_step, "total_litres": 0,
                                    }
                                new_consumption = accumulate_consumption(
                                    previous_consumption, source_key, captured,
                                    sample["actual_value"] if accept_reference else ocr, decimals,
                                    active_rules["max_flow_lph"], integer_digits,
                                )
                                if standalone:
                                    candidate = updated.get("standalone_candidate")
                                    if (candidate and candidate.get("crop") == (rotation_key or custom_boxes)
                                            and 0 < captured - candidate["counter"]["timestamp"] <= FRESH_SAMPLE_AGE):
                                        accumulate_consumption(
                                            candidate["counter"], source_key, captured, ocr, decimals,
                                            active_rules["max_flow_lph"], integer_digits,
                                        )
                                        standalone_reference = candidate
                                        updated.pop("standalone_candidate", None)
                                    else:
                                        updated["standalone_candidate"] = {
                                            "counter": new_consumption, "reading": ocr, "crop": rotation_key or custom_boxes,
                                            "rotation_adjustment": rotation_adjustment,
                                        }
                                        new_standalone = new_consumption = None
                            except ImplausibleReading as error:
                                ocr_confirmed = False
                                rejected = standalone and updated.pop("standalone_candidate", None)
                                validation_detail = (f"{STANDALONE_REJECTED_NOTICE} {error}" if rejected else str(error))
                                new_standalone = new_consumption = None
                        jpeg, size = transfer_jpeg(register)
                if sample.get("reference_is_fallback"):
                    validation_detail = fallback_detail(
                        sample, image_time, ocr, ocr_readings, history.get("consumption", {}),
                        source_key, active_rules["max_flow_lph"], integer_digits,
                    )
                if not manual and ocr_attempts and source != "unavailable":
                    try:
                        preview = draw_test_preview(
                            register, integer_width, whole_boxes, fraction_boxes, ocr,
                            integer_digits, fraction_digits, readings=ocr_readings,
                            composed=bool(ocr_readings and ocr not in ocr_readings),
                        )
                        with io.BytesIO() as buffer:
                            preview.save(buffer, "JPEG", quality=88, optimize=True)
                            atomic_write(AUTOMATIC_PREVIEW, buffer.getvalue(), 0o600)
                            automatic_preview_ready = True
                    except (OSError, ValueError) as error:
                        print(f"Automatische OCR-Vorschau konnte nicht erstellt werden: {error}")
                if source == "manual":
                    unclear_detail = RAW_ROW_UNCLEAR if detect_raw else MANUAL_ROW_UNCLEAR
                else:
                    unclear_detail = None
                if manual:
                    already_checked = (image_time == history.get("last_epoch")
                                       or image_time in history.get("confirmations", ()))
                    status, detail = compare_sample(sample, ocr, manual_options["decimals"],
                                                    ocr_confirmed=ocr_confirmed,
                                                    integer_digits=integer_digits)
                    if ocr_error:
                        detail = ocr_error
                    elif validation_detail:
                        detail = validation_detail
                    elif (manual_options["decimals"] == 3 and captured is not None
                          and status in ("difference", "ocr_unclear")
                          and differs_only_at_last_digit(sample, ocr, ocr_readings, integer_digits)):
                        detail = LAST_DIGIT_NOTICE
                        if ocr_attempts >= LAST_DIGIT_RETRIES and not precision_mode:
                            status, detail = "match_with_warning", LAST_DIGIT_PASS
                    elif status == "match" and not manual_reference:
                        precise = common_exact_precision(
                            ocr, sample.get("reference", sample.get("actual_value")),
                            fraction_digits, integer_digits,
                        )
                        if precise is not None and precise > manual_options["decimals"]:
                            detail = (f"Bestätigt: Zählerstand und Referenzwert stimmen bis einschließlich "
                                      f"der {precise}. Nachkommastelle überein.")
                    elif status == "ocr_unclear":
                        detail = unclear_detail or explain_uncertain_positions(
                            ocr_readings, manual_options["decimals"], integer_digits)
                    if (ocr_attempts == len(ocr_readings) and ocr not in ocr_readings
                            and status in ("match", "ocr_only")):
                        detail = "Ziffern aus mehreren OCR-Versuchen zusammengesetzt. " + detail
                    if raw_fallback and status in ("match", "ocr_only"):
                        detail = SLFORK_RAW_SUCCESS + " " + detail
                    if status in SUCCESSFUL_CHECKS and not ocr_error and not validation_detail:
                        updated["next_check_at"] = datetime.now(zone).timestamp() + (
                            interval_minutes * 60
                        )
                    if not raw_fallback and manual_confirms_failed_auto(
                            history, sample, ocr, status=status, uploaded_image=manual_upload,
                            image_time=image_time,
                            reference_time=sample.get("reference_time"), source_key=source_key,
                            manual_decimals=manual_options["decimals"], auto_decimals=decimals,
                            ocr_confirmed=ocr_confirmed, integer_digits=integer_digits,
                            reference_overridden=bool(manual_reference)):
                        updated["check_status"] = "match"
                        updated["status"] = "match"
                        updated["check_detail"] = detail
                        updated["failure_since"] = None
                        updated.pop("failure_attempts", None)
                        updated.pop("retry_suppressed", None)
                        updated.pop("capture_failure_since", None)
                        updated["next_check_at"] = datetime.now(zone).timestamp() + interval_minutes * 60
                    preview_available = False
                    if ocr_attempts and source != "unavailable":
                        try:
                            preview = draw_test_preview(
                                register, integer_width, whole_boxes, fraction_boxes, ocr,
                                integer_digits, fraction_digits, readings=ocr_readings,
                                composed=bool(ocr_readings and ocr not in ocr_readings),
                            )
                            with io.BytesIO() as buffer:
                                preview.save(buffer, "JPEG", quality=88, optimize=True)
                                atomic_write(TEST_IMAGE, buffer.getvalue(), 0o600)
                            preview_available = True
                        except (OSError, ValueError) as error:
                            print(f"OCR-Testvorschau konnte nicht erstellt werden: {error}")
                    manual_result = {
                        "preview": preview_available,
                        "readings": ocr_readings,
                        "status": status,
                        "ocr_attempts": ocr_attempts,
                        "ocr": ocr,
                        "reference": sample.get("reference", sample["actual_value"]),
                        "reference_time": sample.get("reference_time"),
                        "reference_is_fallback": sample.get("reference_is_fallback", False),
                        "detail": detail,
                        "image_time": image_time,
                        "already_checked": already_checked,
                        "outside_window": captured is None,
                        "can_apply_crop": (manual_options["crop_mode"] == "manual"
                                           and ocr_attempts > 0 and preview_available),
                    }
                elif record_sample(updated, sample, ocr, zone, datetime.now(zone), decimals,
                                   ocr_confirmed=ocr_confirmed, integer_digits=integer_digits,
                                   readings=ocr_readings if not validation_detail else (),
                                   precision_mode=precision_mode):
                    atomic_write(DESTINATION, picture, 0o644)
                    if not automatic_preview_ready:
                        AUTOMATIC_PREVIEW.unlink(missing_ok=True)
                    outcome = updated["status"]
                    if standalone and outcome == "ocr_only":
                        if standalone_reference is None:
                            outcome = updated["status"] = STANDALONE_PENDING
                            updated["check_detail"] = STANDALONE_PENDING_NOTICE
                        else:
                            updated["check_detail"] = STANDALONE_VERIFIED_NOTICE
                    if new_consumption is not None and not raw_fallback:
                        updated["consumption"] = new_consumption
                    if raw_fallback and outcome == "ocr_only":
                        updated["source_connection_detail"] = SLFORK_RAW_SUCCESS
                    if new_standalone is not None:
                        updated["standalone_reading"] = new_standalone
                    updated["ocr_readings"] = ocr_readings if outcome == "ocr_unclear" else []
                    if outcome == "ocr_unclear" and updated["check_detail"] != LAST_DIGIT_NOTICE:
                        updated["check_detail"] = (validation_detail or ocr_error or unclear_detail
                                                   or explain_uncertain_positions(ocr_readings, decimals, integer_digits))
                    elif validation_detail:
                        updated["check_detail"] = validation_detail
                    if outcome == "match":
                        if ocr_attempts == len(ocr_readings) and ocr not in ocr_readings:
                            updated["check_detail"] = "Ziffern aus mehreren OCR-Versuchen zusammengesetzt."
                        atomic_write(GOOD_IMAGE, picture, 0o644)
                        if mode == "slfork":
                            updated["last_slfork_match"] = {"reading": sample["actual_value"], "time": image_time}
                    data = {**sample, "crop_source": source, "ocr_attempts": ocr_attempts}
                    updated["ocr_rotation_adjustment"] = rotation_adjustment
                    if (rotation_key is not None and not raw_fallback
                            and (outcome == "match" or standalone_reference is not None and outcome == "ocr_only")):
                        updated["learned_rotation"] = {"crop": rotation_key, "adjustment": rotation_adjustment}
                    if rotation_adjustment:
                        data["ocr_rotation_adjustment"] = rotation_adjustment
                    manual_anchor = None
                    if active_rules["reflection_estimate_enabled"] and active_rules["fallback_value"]:
                        prefix = meter_prefix(active_rules["fallback_value"], decimals, integer_digits)
                        if prefix is not None and active_rules["fallback_time"]:
                            manual_anchor = {
                                "time": timestamp_epoch(active_rules["fallback_time"], zone),
                                "value": prefix * 10 ** (3 - decimals),
                            }
                    track_reflection(
                        updated, ocr, ocr_readings, image_time,
                        verified=outcome == "match" or standalone_reference is not None and outcome == "ocr_only",
                        unclear=outcome == "ocr_unclear" and not validation_detail and not ocr_error,
                        decimals=decimals, integer_digits=integer_digits, max_flow_lph=active_rules["max_flow_lph"],
                        enabled=active_rules["reflection_estimate_enabled"], manual_anchor=manual_anchor,
                    )
                    verified = outcome == "match" or standalone_reference is not None and outcome == "ocr_only"
                    if adaptive and outcome == "match" and not raw_fallback:
                        flow = updated.setdefault("adaptive_flow", {})
                        reference_value = sample["actual_value"]
                        if compare_sample(sample, reference_value, fraction_digits, integer_digits=integer_digits)[0] == "match":
                            observe_flow(flow, source_key, image_time, reference_value, fraction_digits,
                                         integer_digits, now.month, active_rules["max_flow_lph"])
                        interval_minutes = suggested_interval(
                            automatic_interval_minutes(active_rules["interval_minutes"], mode), flow, source_key, now.month,
                        )
                    if active_rules["fine_alignment_enabled"] and active_rules["crop_mode"] == "manual" and not raw_fallback:
                        learning = updated.setdefault("fine_alignment", {})
                        key = [source_key, active_rules["crop"], active_rules["rotation"], active_rules["width"],
                               integer_digits, fraction_digits, active_rules["polarity"]]
                        previous_boxes = active_rules["digit_boxes"]
                        if outcome in ("ocr_unclear", "difference"):
                            fine_update = alignment_rollback(learning, key, previous_boxes, True)
                        if verified:
                            alignment_rollback(learning, key, previous_boxes, False)
                            trusted = sample.get("actual_value")
                            known = fraction_digits if compare_sample(
                                sample, trusted, fraction_digits, integer_digits=integer_digits
                            )[0] == "match" else decimals
                            expected = trusted if known == fraction_digits and sample.get("reference_required") is not False else ocr
                            prefix = meter_prefix(expected, known, integer_digits)
                            if prefix is not None and (known == fraction_digits or previous_boxes):
                                digits = str(prefix).zfill(integer_digits + known)
                                if known:
                                    digits = digits[:integer_digits] + "." + digits[integer_digits:]
                                candidate_boxes = (learning.get("candidate") if learning.get("key") == key else None)
                                if not candidate_boxes:
                                    candidate_boxes = propose_digit_boxes(
                                        register, previous_boxes, integer_width, integer_digits, fraction_digits,
                                    )
                                trial = ""
                                if candidate_boxes and candidate_boxes != previous_boxes:
                                    boxes = scale_digit_boxes(candidate_boxes, register.size)
                                    try:
                                        trial = read_visible_digits(
                                            register, integer_width, boxes[:integer_digits], boxes[integer_digits:],
                                            options["helle_ziffern"], active_rules["polarity"],
                                            profile=OCR_PROFILES[0], whole_digits=integer_digits,
                                            fraction_digits=fraction_digits, prefer_boxes=True,
                                            deadline=time.monotonic() + 5,
                                        )
                                    except (OSError, ValueError, subprocess.SubprocessError):
                                        pass
                                fine_update = observe_alignment(
                                    learning, key, image_time, digits, ocr or "", previous_boxes, candidate_boxes, trial,
                                )
                    if not raw_fallback:
                        geometry_key = [source_key, active_rules["crop_mode"], active_rules["crop"],
                                        active_rules["rotation"], active_rules["width"], integer_digits,
                                        fraction_digits, active_rules["crop_revision"]]
                        recovery = updated.setdefault("geometry_recovery", {})
                        geometry_warning = observe_geometry_failures(
                            recovery, geometry_key, image_time, outcome,
                            reading_problem=not validation_detail and not ocr_error and ocr_attempts > 0,
                        )
                        recover_geometry = geometry_warning and active_rules["self_repair_enabled"] and fine_update is None
                    updated.update(
                        last_reference=(standalone_reference["reading"] if standalone_reference else
                                        sample.get("reference", sample["actual_value"])),
                        last_reference_time=(standalone_reference["counter"]["timestamp"] if standalone_reference else
                                             sample.get("reference_time")),
                        last_reference_is_fallback=sample.get("reference_is_fallback", False),
                    )
                else:
                    outcome = "stale_sample"
                    updated["check_detail"] = "Bild zu alt oder schon geprüft."
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            print(f"Bildabruf fehlgeschlagen: {type(error).__name__}")
            if raw_fallback:
                manual_result["detail"] = SLFORK_RAW_FAILED
            if not manual and data is None:
                detail = manual_result["detail"]
                updated = {**source_history, "check_detail": detail}
                updated["source_connection_status"] = "error"
                updated["source_connection_detail"] = (
                    SLFORK_RAW_FAILED if raw_fallback else
                    "Home-Assistant-Kamera nicht erreichbar oder Bild unlesbar. Kamera und Zugriff prüfen."
                    if camera else "ESP nicht erreichbar oder Antwort unvollständig. Adresse und Verbindung prüfen."
                )
                outcome = "capture_unavailable"

        now = datetime.now(zone)
        if manual:
            update_progress(request_id, "running", "Ergebnis wird gespeichert …",
                            manual_result.get("ocr_attempts", 0))
            manual_result.update(checked_at=now.timestamp(),
                                 settings={key: value for key, value in manual_options.items() if key != "image"},
                                 slfork_diagnostics=diagnostics)
            try:
                next_history = {**history, "manual_result": manual_result}
                # A manual image that cannot clear an automatic incident must not
                # postpone its short retry or change its one-hour cooldown.
                if (manual_result.get("status") in SUCCESSFUL_CHECKS
                        and not history.get("failure_attempts") and not history.get("standalone_candidate")):
                    next_history["next_check_at"] = updated.get("next_check_at", history.get("next_check_at"))
                if (sample is not None and updated.get("check_status") == "match"
                        and history.get("check_status") != "match"):
                    for key in ("check_status", "status", "check_detail", "failure_since", "failure_attempts",
                                "retry_suppressed", "capture_failure_since", "next_check_at"):
                        if key in updated:
                            next_history[key] = updated[key]
                atomic_write(HISTORY, json.dumps(next_history).encode("utf-8"), 0o600)
                history = next_history
            except OSError as error:
                print(f"Manueller Test konnte nicht gespeichert werden: {type(error).__name__}")
                manual_result.update(status="storage_error", can_apply_crop=False, preview=False,
                                     detail="Das Prüfergebnis konnte nicht gespeichert werden.")
            update_progress(request_id, "done", "Prüfung beendet.",
                            manual_result.get("ocr_attempts", 0), now.timestamp(),
                            outcome=manual_result["status"], detail=manual_result["detail"],
                            preview=manual_result.get("preview", False),
                            can_apply_crop=manual_result.get("can_apply_crop", False),
                            readings=manual_result.get("readings", []),
                            ocr=manual_result.get("ocr"), reference=manual_result.get("reference"),
                            reference_time=manual_result.get("reference_time"),
                            reference_is_fallback=manual_result.get("reference_is_fallback", False),
                            image_time=manual_result.get("image_time"))
            continue
        if keep_schedule and data is None and history.get("next_check_at", 0) > now.timestamp():
            continue
        updated["slfork_diagnostics"] = diagnostics
        if duplicate_cycle:
            defer_duplicate_cycle(updated, now.timestamp(), interval_minutes)
        else:
            schedule_next_check(updated, outcome, now.timestamp(), interval_minutes)
        try:
            atomic_write(HISTORY, json.dumps(updated).encode("utf-8"), 0o600)
        except OSError as error:
            print(f"Automatik konnte die Prüfhistorie nicht speichern: {type(error).__name__}")
            startup = False
            wake_worker.wait(timeout=RETRY_INTERVAL)
            continue
        history = updated
        if fine_update is not None:
            with settings_lock:
                if get_auto_rules() == active_rules and get_source()[0] == active_source:
                    try:
                        save_auto_rules({**active_rules, "digit_boxes": fine_update, "crop_revision": str(time.time_ns())})
                    except (OSError, ValueError):
                        print("Feinjustierung konnte nicht gespeichert werden.")
        set_activity("waiting", "Warte auf einen neuen Messzyklus vom ESP …" if duplicate_cycle else
                     STANDALONE_PENDING_NOTICE if outcome == STANDALONE_PENDING else
                     "Letzte Prüfung beendet. Nächster Versuch nach kurzer Wartezeit."
                     if not updated.get("retry_suppressed") and outcome not in SUCCESSFUL_CHECKS else
                     "Letzte Prüfung beendet. Wartet auf das eingestellte Prüfintervall.")
        if data is not None:
            pending_image = (data, jpeg, size)
            print(f"Kontrollbild bereit: {data['esp_timestamp']} | Ausschnitt: {source} | "
                  f"OCR: {ocr or '?'} ({data['ocr_attempts']} Durchläufe) | "
                  f"SLFork: {data['actual_value']} | Ergebnis: {outcome}")
        try:
            publish_check(history, now, token, review_after)
            if pending_image is not None:
                publish(*pending_image, history, now, token, review_after)
                pending_image = None
            if standalone or published_standalone:
                publish_standalone(history, standalone_source, token)
                published_standalone = standalone
            publish_consumption(history, token)
        except OSError as error:
            print(f"Home Assistant konnte nicht aktualisiert werden: {error}")
        check_reminder(reminder, history, now, review_after)
        repair_started = False
        if recover_geometry:
            with settings_lock:
                if get_auto_rules() == active_rules and get_source()[0] == active_source and not get_auto_paused():
                    try:
                        control_calibration("repair", GEOMETRY_REPAIR_LIMIT)
                        repair_started = True
                    except (OSError, ValueError) as error:
                        print(f"Automatische Nachjustierung nicht gestartet: {type(error).__name__}")
        if geometry_warning and reminder.enabled:
            message = ("Nach zehn Fehlmessungen sucht die App einmal nach einem besseren Ziffernrahmen. "
                       "Die bisherigen Einstellungen sind gesichert. Das Ergebnis steht in der App."
                       if repair_started else "Zehn unterschiedliche Prüfungen waren erfolglos. "
                                              "Bitte prüfe den Bildausschnitt in der App.")
            try:
                reminder.call_service("persistent_notification.create", {
                    "notification_id": f"{NAMESPACE}_geometry_repair",
                    "title": f"{APP_NAME}: Bildausschnitt prüfen",
                    "message": message,
                })
            except OSError as error:
                print(f"Nachjustierungs-Hinweis konnte nicht gesendet werden: {type(error).__name__}")



if __name__ == "__main__":
    main()
