"""Bridge the latest matched SLFork picture and reading to Home Assistant."""

import base64
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
from threading import Event
import time
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw
from websocket import WebSocketException

from app_channel import APP_NAME, CHECK_ENTITY, LABEL_SUFFIX, NAMESPACE

from checks import (
    DEFAULT_INTERVAL_MINUTES, RETRY_INTERVAL, REVIEW_AFTER, compare_sample, crop_register, read_register, read_with_retries, record_sample,
    explain_uncertain_positions, meter_prefix,
    reschedule_next_check, rolling_summary, sample_epoch, sample_timestamp, schedule_next_check, slfork_reference,
    valid_interval_minutes,
)
from consumption import (DEFAULT_FLOW_LPH, LOWER_READING, MAX_FLOW_LPH, ImplausibleReading,
                         accumulate_consumption, fallback_detail, format_cubic_metres)
from layout import crop_coordinates, find_digit_row, turn_crop
from reminder import Reminder
from notification_settings import (DEFAULT_DELIVERY_HOURS, DEFAULT_REVIEW_MINUTES, PUSH_SERVICE,
                                   notification_rules)
from settings import DEFAULTS, SCHEMA_VERSION, load_options
from source_settings import CAMERA, REFERENCE, source_rules
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
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def get_bytes(url, token=None, timeout=8):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
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


def capture(base, diagnostics):
    def process_data():
        payload = json.loads(get_bytes(base + "/process_data"))
        if not isinstance(payload, dict):
            raise ValueError("Ungültige SLFork-Messdaten")
        return payload

    before = process_data()
    diagnostics.update(slfork_diagnostics(before))
    picture = get_bytes(base + "/img_tmp/alg.jpg")
    try:
        overlay = get_bytes(base + "/img_tmp/alg_roi.jpg")
    except (OSError, ValueError):
        overlay = None
    after = process_data()
    diagnostics.update(slfork_diagnostics(after))
    timestamp = sequence_value(after, "timestamp_processed")
    if not isinstance(timestamp, str) or not timestamp:
        raise ValueError("Kein Zeitstempel vom ESP")
    if sequence_value(before, "timestamp_processed") != timestamp:
        return None
    return picture, overlay, {
        "esp_timestamp": timestamp,
        "raw_value": sequence_value(after, "raw_value"),
        "actual_value": sequence_value(after, "actual_value"),
        "slfork_fallback_value": sequence_value(after, "fallback_value"),
        **diagnostics,
    }


def capture_camera(camera, reference, token, zone, timeout=8):
    base = "http://supervisor/core/api"
    picture = get_bytes(f"{base}/camera_proxy/{camera}", token, timeout=timeout)
    captured = datetime.now(zone)
    value = None
    reference_time = None
    if reference:
        try:
            state = json.loads(get_bytes(f"{base}/states/{reference}", token, timeout=timeout))
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


def select_register(frame, overlay, manual_crop, manual_width, rotation=0, whole_digits=5, fraction_digits=3):
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
    register = turn_crop(crop_register(frame, manual_crop), rotation)
    if not 0 < manual_width <= register.width:
        raise ValueError("vorkomma_breite liegt außerhalb des Ausschnitts")
    # Ohne Rahmen teilt der konfigurierte Ausschnitt den Rest in drei Rollen.
    right_width = register.width - manual_width
    boundaries = [manual_width + right_width * i // max(1, fraction_digits)
                  for i in range(max(1, fraction_digits) + 1)]
    boxes = [(left, 0, right, register.height)
             for left, right in zip(boundaries, boundaries[1:]) if right - left >= 8]
    return register, manual_width, [], boxes, "manual"


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
                        whole_digits=5, fraction_digits=3):
    if polarity != "auto":
        light_digits = polarity == "light"

    def read(picture, digits=whole_digits):
        return read_register(picture, light_digits, digits, force_polarity=polarity != "auto", profile=profile)

    whole = read(register.crop((0, 0, integer_width, register.height)))
    if whole is None:
        whole = "".join(read_digit(register, box, read, trim_vertical=True)
                        for box in whole_boxes).ljust(whole_digits, "?")
    fraction = "".join(read_digit(register, box, read) for box in fraction_boxes[:fraction_digits])
    return f"{whole}.{fraction.ljust(fraction_digits, '?')}" if fraction_digits else whole


def draw_test_preview(register, integer_width, whole_boxes, fraction_boxes, reading,
                      whole_digits=5, fraction_digits=3):
    """Mark OCR digit regions and the actual read characters for manual diagnostics.

    Green: OCR returned a digit at this position, red: it returned '?'.
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
    stroke = max(2, min(6, w // 240))
    for idx, box in enumerate(boxes + fraction):
        if idx >= 8:
            break
        l, t, r, b = [int(coord) for coord in box]
        if not (0 <= l < r <= w and 0 <= t < b <= h):
            continue
        color = (36, 170, 92) if chars[idx].isdigit() else (203, 65, 77)
        draw.rectangle((l, t, r - 1, b - 1), outline=color, width=stroke)
        # The label is drawn on a filled patch for contrast against the counter.
        label = chars[idx]
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
        if history.get("check_status") == "ocr_only":
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
        setup_pending = False
    except FileNotFoundError:
        pass
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"Bildquelle konnte nicht geladen werden: {type(error).__name__}")

    def get_source():
        return dict(configured_source), setup_pending

    def save_source(values):
        nonlocal configured_source, setup_pending
        validated = source_rules(values)
        atomic_write(SOURCE_SETTINGS, json.dumps(validated).encode("utf-8"), 0o600)
        configured_source, setup_pending = validated, False

    default_decimals = options["vergleich_nachkommastellen"]
    default_attempts = options["ocr_versuche"]
    wake_worker = Event()
    auto_rules = {"decimals": default_decimals, "attempts": default_attempts, "polarity": "auto",
                  "crop_mode": "auto", "crop": options["ausschnitt"],
                  "width": options["vorkomma_breite"], "rotation": 0,
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
            auto_rules = {"decimals": saved_rules["decimals"],
                          "attempts": saved_rules["attempts"], "polarity": polarity,
                          "crop_mode": crop_mode, "crop": crop_text, "width": width, "rotation": rotation,
                          "max_flow_lph": max_flow, "interval_minutes": interval_minutes,
                          "integer_digits": integer_digits, "fraction_digits": fraction_digits,
                          "meter_display": meter_display, "fallback_value": fallback_value,
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
        if (type(values.get("decimals")) is not int or not 0 <= values["decimals"] <= fraction_digits
                or type(values.get("attempts")) is not int or not 1 <= values["attempts"] <= 10
                or values.get("polarity") not in ("auto", "light", "dark")
                or values.get("crop_mode") not in ("auto", "manual")
                or type(integer_digits) is not int or not 1 <= integer_digits <= 9
                or type(fraction_digits) is not int or not 0 <= fraction_digits <= 3
                or meter_display not in ("rollers", "digital", "mixed")
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
        interval_changed = interval_minutes != auto_rules["interval_minutes"]
        updated_rules = {**auto_rules, **values, "rotation": rotation, "max_flow_lph": max_flow,
                         "interval_minutes": interval_minutes, "integer_digits": integer_digits,
                         "fraction_digits": fraction_digits, "meter_display": meter_display,
                         "fallback_value": fallback_value, "fallback_time": fallback_time}
        updated_rules["crop"] = ",".join(str(part) for part in coords)
        atomic_write(AUTO_RULES, json.dumps(updated_rules, indent=2).encode("utf-8"), 0o600)
        auto_rules = updated_rules
        # Saving automatic settings schedules a fresh run immediately.
        history["next_check_at"] = time.time()
        atomic_write(HISTORY, json.dumps(history).encode("utf-8"), 0o600)
        wake_worker.set()

    requested = Queue(maxsize=1)
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
    reset_finished = Event()
    reset_result = {"value": "pending"}

    def request_factory_reset():
        if reset_requested.is_set():
            return "pending"
        reset_finished.clear()
        reset_result["value"] = "pending"
        reset_requested.set()
        wake_worker.set()
        if reset_finished.wait(timeout=60):
            return reset_result["value"]
        return "pending"

    def skip_setup():
        nonlocal setup_pending
        setup_pending = False
        snapshot["setup_pending"] = False
        atomic_write(EFFECTIVE_OPTIONS, json.dumps(snapshot, indent=2).encode("utf-8"), 0o600)
        wake_worker.set()

    _, update_progress = start_panel(
        HISTORY, DESTINATION, GOOD_IMAGE, requested, default_decimals, default_attempts,
        get_auto_rules, save_auto_rules, options["ausschnitt"], options["vorkomma_breite"], TEST_IMAGE,
        partial(load_preferences, LANGUAGE_MODES), save_language_modes, get_delivery, save_delivery, get_source, save_source,
        wake_worker.set, test_source_image=TEST_SOURCE_IMAGE, automatic_preview=AUTOMATIC_PREVIEW,
        request_factory_reset=request_factory_reset, skip_setup=skip_setup,
    )
    reminder = Reminder(token)
    pending_image = None
    startup = True
    published_standalone = bool(history.get("standalone_reading"))
    print(f"{APP_NAME} gestartet")

    def perform_factory_reset():
        nonlocal history, configured_source, setup_pending, auto_rules, delivery
        nonlocal pending_image, startup, published_standalone, snapshot
        try:
            reminder.clear_for_reset(history)
            paths = (
                HISTORY, AUTO_RULES, SOURCE_SETTINGS, NOTIFICATIONS, LANGUAGE_MODES,
                HISTORY.with_name("manual-test-settings.json"), DESTINATION, GOOD_IMAGE,
                TEST_IMAGE, TEST_SOURCE_IMAGE, AUTOMATIC_PREVIEW,
            )
            for path in paths:
                path.unlink(missing_ok=True)
            history = {}
            configured_source = dict(default_source)
            setup_pending = True
            auto_rules = dict(default_auto_rules)
            delivery = dict(default_delivery)
            pending_image = None
            startup = True
            published_standalone = False
            snapshot = {**snapshot, "setup_pending": True}
            atomic_write(EFFECTIVE_OPTIONS, json.dumps(snapshot, indent=2).encode("utf-8"), 0o600)
            reset_result["value"] = "done"
        except (OSError, ValueError, TypeError) as error:
            print(f"Werkreset konnte nicht abgeschlossen werden: {type(error).__name__}")
            reset_result["value"] = "failed"

    while True:
        wake_worker.clear()
        if reset_requested.is_set():
            reset_requested.clear()
            perform_factory_reset()
            reset_finished.set()
            continue
        active_rules = get_auto_rules()
        interval_minutes = active_rules["interval_minutes"]
        if reschedule_next_check(history, interval_minutes):
            try:
                atomic_write(HISTORY, json.dumps(history).encode("utf-8"), 0o600)
            except OSError as error:
                print(f"Prüfintervall konnte nicht in der Historie gespeichert werden: {type(error).__name__}")
        active_source, waiting_for_setup = get_source()
        standalone = (active_source["mode"] == "esphome"
                      or active_source["mode"] == "camera" and not active_source["reference"])
        base = active_source["url"].rstrip("/")
        camera = active_source["camera"] if active_source["mode"] != "slfork" else ""
        reference = active_source["reference"] if active_source["mode"] == "camera" else ""
        source_key = [active_source["mode"], camera or base, reference]
        source_changed = history.get("check_source", initial_source_key) != source_key
        if source_changed:
            pending_image = None
        active_delivery = get_delivery()
        review_after = active_delivery["review_minutes"] * 60
        reminder.configure(enabled=active_delivery["enabled"], push=active_delivery["push"], target=active_delivery["target"],
                           delay=active_delivery["delivery_hours"] * 60 * 60)
        decimals = active_rules["decimals"]
        integer_digits = active_rules["integer_digits"]
        fraction_digits = active_rules["fraction_digits"]
        max_attempts = active_rules["attempts"]
        now = datetime.now(zone)
        remaining = history.get("next_check_at", 0) - now.timestamp()
        try:
            manual_options = requested.get_nowait()
        except Empty:
            manual_options = None
        manual = manual_options is not None
        request_id = manual_options["request_id"] if manual else None
        if manual:
            update_progress(request_id, "running", "Lade Zählerbild und Referenzdaten …")
        if waiting_for_setup and not manual:
            wake_worker.wait(timeout=2)
            continue
        if remaining > 0 and not startup and not manual and not source_changed:
            # Refresh status after a Home Assistant restart, even between checks.
            if "check_status" in history:
                try:
                    publish_check(history, now, token, review_after)
                    if pending_image is not None:
                        publish(*pending_image, history, now, token, review_after)
                        pending_image = None
                    if standalone or published_standalone:
                        publish_standalone(history, camera if standalone else "", token)
                        published_standalone = standalone
                    publish_consumption(history, token)
                except OSError as error:
                    print(f"Prüfstatus konnte nicht übertragen werden: {error}")
                check_reminder(reminder, history, now, review_after)
            wake_worker.wait(timeout=min(remaining, RETRY_INTERVAL))
            continue

        keep_schedule = startup and remaining > 0 and not source_changed
        startup = startup and manual
        data = None
        outcome = "capture_unavailable"
        source_history = dict(history)
        if source_changed:
            source_history["confirmations"] = []
            for field in ("last_epoch", "last_match_at", "failure_since", "capture_failure_since",
                          "last_slfork_match", "last_reference", "last_reference_time",
                          "last_reference_is_fallback", "ocr_value", "ocr_readings"):
                source_history.pop(field, None)
        source_history["check_source"] = source_key
        updated = dict(source_history)
        validation_detail = None
        new_consumption = None
        new_standalone = None
        # Confirmations obtained with another precision are not valid evidence
        # for the newly chosen automatic comparison rules.
        format_changed = any(history.get(key, default) != value for key, default, value in (
            ("comparison_decimals", decimals, decimals),
            ("comparison_integer_digits", integer_digits, integer_digits),
            ("comparison_fraction_digits", fraction_digits, fraction_digits),
        ))
        if format_changed:
            updated["confirmations"] = []
            updated.pop("last_match_at", None)
            if history.get("comparison_integer_digits", integer_digits) != integer_digits:
                updated.pop("standalone_reading", None)
        updated["comparison_decimals"] = decimals
        updated["comparison_integer_digits"] = integer_digits
        updated["comparison_fraction_digits"] = fraction_digits
        updated["check_detail"] = "Bild oder Messwert fehlt. Verbindung prüfen."
        manual_result = {"status": "capture_unavailable", "detail": updated["check_detail"]}
        diagnostics = {}
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
                result = capture_camera(
                    camera, reference, token, zone,
                    timeout=min(8, max(0.2, live_deadline - time.monotonic())) if live_deadline else 8,
                ) if camera else capture(base, diagnostics)
            if result is None:
                print("SLFork hat während des Abrufs gemessen. Neuer Versuch in 10 Sekunden.")
                time.sleep(10)
                result = capture(base, diagnostics)
            if result is not None:
                if manual:
                    update_progress(request_id, "running", "Bild geladen – überprüfe Zeitstempel und Ziffernbereich …")
                picture, overlay, sample = result
                now = datetime.now(zone)
                captured = sample_epoch(sample, zone, now)
                if not manual and (captured is None or captured <= updated.get("last_epoch", 0)):
                    if (captured is not None and captured == updated.get("last_epoch")
                            and history.get("check_status") and not format_changed):
                        outcome = history["check_status"]
                        updated["check_detail"] = history["check_detail"]
                    else:
                        outcome = "stale_sample"
                        updated["check_detail"] = "Bild zu alt oder schon geprüft."
                    result = None
            if result is not None:
                image_time = captured if captured is not None else sample_timestamp(sample, zone)
                if not camera and not (manual and manual_options.get("image")):
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
                    try:
                        crop_rules = manual_options if manual else active_rules
                        manual_crop = crop
                        manual_width = options["vorkomma_breite"]
                        selected_overlay = overlay
                        rotation = 0
                        if crop_rules["crop_mode"] == "manual":
                            rotation = crop_rules.get("rotation", 0)
                            manual_width = crop_rules["width"]
                            manual_crop = crop_coordinates(crop_rules["crop"], manual_width, rotation)
                            selected_overlay = None
                        register, integer_width, whole_boxes, fraction_boxes, source = select_register(
                            frame, selected_overlay, manual_crop, manual_width, rotation,
                            integer_digits, fraction_digits,
                        )
                        read_state = {"register": register, "integer_width": integer_width,
                                      "whole_boxes": whole_boxes, "fraction_boxes": fraction_boxes,
                                      "source": source, "picture": picture, "captured": captured,
                                      "attempts": 0}
                        live_source = live_deadline is not None

                        def read(profile):
                            if live_source and read_state["attempts"]:
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
                                    latest_register, latest_integer_width, latest_whole, latest_fraction, latest_source = select_register(
                                        latest_frame, latest_overlay, manual_crop, manual_width, rotation,
                                        integer_digits, fraction_digits,
                                    )
                                sample.clear()
                                sample.update(latest_sample)
                                read_state.update(register=latest_register,
                                                  integer_width=latest_integer_width,
                                                  whole_boxes=latest_whole, fraction_boxes=latest_fraction,
                                                  source=latest_source, picture=latest_picture,
                                                  captured=latest_time)
                            read_state["attempts"] += 1
                            return read_visible_digits(
                                read_state["register"], read_state["integer_width"],
                                read_state["whole_boxes"], read_state["fraction_boxes"],
                                options["helle_ziffern"],
                                manual_options["polarity"] if manual else active_rules["polarity"],
                                profile=profile, whole_digits=integer_digits,
                                fraction_digits=fraction_digits,
                            )
                        if manual:
                            update_progress(request_id, "ocr", f"OCR-Prüfung gestartet (max. {manual_options['attempts']} Versuche).", 0)
                        def report_ocr(attempts, message):
                            if manual:
                                update_progress(request_id, "ocr", message, attempts)
                        ocr, ocr_confirmed, ocr_attempts = read_with_retries(
                            read, sample,
                            manual_options["decimals"] if manual else decimals,
                            progress=report_ocr if manual else None,
                            max_attempts=(manual_options["attempts"] if manual else
                                          max(2, max_attempts) if standalone else max_attempts),
                            trace=ocr_readings, standalone=standalone and not manual,
                            integer_digits=integer_digits,
                            stop_before_attempt=(lambda: live_source and (
                                time.monotonic() >= live_deadline
                                or read_state["attempts"] >= LIVE_CAPTURE_MAX_ATTEMPTS
                            )),
                            force_all_attempts=manual,
                        )
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
                        if reading_status == "match" or (standalone and reading_status == "ocr_only"):
                            try:
                                if standalone:
                                    new_standalone = standalone_reading(
                                        camera, sample, ocr, decimals, history.get("standalone_reading"),
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
                                    previous_consumption, source_key, captured, ocr, decimals,
                                    active_rules["max_flow_lph"], integer_digits,
                                )
                            except ImplausibleReading as error:
                                ocr_confirmed = False
                                validation_detail = str(error)
                                new_standalone = None
                        jpeg, size = transfer_jpeg(register)
                if sample.get("reference_is_fallback"):
                    validation_detail = fallback_detail(
                        sample, image_time, ocr, ocr_readings, history.get("consumption", {}),
                        source_key, active_rules["max_flow_lph"], integer_digits,
                    )
                if not manual and ocr_attempts and source != "unavailable":
                    try:
                        preview = draw_test_preview(register, integer_width, whole_boxes,
                                                    fraction_boxes, ocr, integer_digits, fraction_digits)
                        with io.BytesIO() as buffer:
                            preview.save(buffer, "JPEG", quality=88, optimize=True)
                            atomic_write(AUTOMATIC_PREVIEW, buffer.getvalue(), 0o600)
                    except (OSError, ValueError) as error:
                        print(f"Automatische OCR-Vorschau konnte nicht erstellt werden: {error}")
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
                    elif status == "ocr_unclear":
                        detail = explain_uncertain_positions(ocr_readings, manual_options["decimals"],
                                                             integer_digits)
                    if (ocr_attempts == len(ocr_readings) and ocr not in ocr_readings
                            and status in ("match", "ocr_only")):
                        detail = "Ziffern aus mehreren OCR-Versuchen zusammengesetzt. " + detail
                    if status in ("match", "ocr_only") and not ocr_error and not validation_detail:
                        updated["next_check_at"] = datetime.now(zone).timestamp() + (
                            active_rules["interval_minutes"] * 60
                        )
                    preview_available = False
                    if ocr_attempts and source != "unavailable":
                        try:
                            preview = draw_test_preview(register, integer_width, whole_boxes,
                                                        fraction_boxes, ocr, integer_digits, fraction_digits)
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
                                   ocr_confirmed=ocr_confirmed, integer_digits=integer_digits):
                    atomic_write(DESTINATION, picture, 0o644)
                    outcome = updated["status"]
                    if new_consumption is not None:
                        updated["consumption"] = new_consumption
                    if new_standalone is not None:
                        updated["standalone_reading"] = new_standalone
                    updated["ocr_readings"] = ocr_readings if outcome == "ocr_unclear" else []
                    if outcome == "ocr_unclear":
                        updated["check_detail"] = validation_detail or ocr_error or explain_uncertain_positions(ocr_readings, decimals)
                    elif validation_detail:
                        updated["check_detail"] = validation_detail
                    if outcome == "match":
                        if ocr_attempts == len(ocr_readings) and ocr not in ocr_readings:
                            updated["check_detail"] = "Ziffern aus mehreren OCR-Versuchen zusammengesetzt."
                        atomic_write(GOOD_IMAGE, picture, 0o644)
                        if not camera:
                            updated["last_slfork_match"] = {"reading": sample["actual_value"], "time": image_time}
                    data = {**sample, "crop_source": source, "ocr_attempts": ocr_attempts}
                    updated.update(
                        last_reference=sample.get("reference", sample["actual_value"]),
                        last_reference_time=sample.get("reference_time"),
                        last_reference_is_fallback=sample.get("reference_is_fallback", False),
                    )
                else:
                    outcome = "stale_sample"
                    updated["check_detail"] = "Bild zu alt oder schon geprüft."
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            print(f"Bildabruf fehlgeschlagen: {type(error).__name__}")
            if not manual and data is None:
                detail = manual_result["detail"]
                updated = {**source_history, "check_detail": detail}
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
        schedule_next_check(updated, outcome, now.timestamp(), interval_minutes)
        try:
            atomic_write(HISTORY, json.dumps(updated).encode("utf-8"), 0o600)
        except OSError as error:
            print(f"Automatik konnte die Prüfhistorie nicht speichern: {type(error).__name__}")
            startup = False
            wake_worker.wait(timeout=RETRY_INTERVAL)
            continue
        history = updated
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
                publish_standalone(history, camera if standalone else "", token)
                published_standalone = standalone
            publish_consumption(history, token)
        except OSError as error:
            print(f"Home Assistant konnte nicht aktualisiert werden: {error}")
        check_reminder(reminder, history, now, review_after)


if __name__ == "__main__":
    main()
