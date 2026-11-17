"""Bridge the latest matched SLFork picture and reading to Home Assistant."""

import base64
from concurrent.futures import Future
from copy import deepcopy
from datetime import datetime
from email.parser import BytesHeaderParser
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
    STANDALONE_CACHED_CAPTURE_DELAY, MAX_OCR_ATTEMPTS, missing_digit_pattern, single_missing_digit, disputed_digit_pattern, resolve_ocr_readings,
    compare_sample, crop_register, lighting_ocr_profiles, read_register, read_with_retries, record_sample,
    automatic_interval_minutes, defer_duplicate_cycle,
    LAST_DIGIT_NOTICE, LAST_DIGIT_PASS, LAST_DIGIT_RETRIES, SUCCESSFUL_CHECKS,
    differs_only_at_last_digit, last_digit_can_pass, explain_uncertain_positions,
    meter_prefix, common_exact_precision, manual_confirms_failed_auto,
    reschedule_next_check, rolling_summary, sample_epoch, sample_timestamp, schedule_next_check, slfork_reference,
    timestamp_epoch, track_reflection,
    setup_deadlines, setup_source_id, stabilization_interval, stationary_partial_active, valid_interval_minutes,
)
from calibration import (Calibration, Layout, CAPTURE_INTERVAL, PERFECT_CONFIRMATION_INTERVAL, MIN_IMAGES, MIN_IMAGE_LIMIT, MAX_IMAGES, MAX_ATTEMPTS,
                         DEFAULT_INTENSIVE_AGREEMENT, SHORTLIST_LIMIT, TIME_LIMIT, LAST_DIGIT_CAPTURE_INTERVAL,
                         image_quality_hints, two_decimal_reading, uncertain_slots, valid_intensive_agreement)
from consumption import (DEFAULT_FLOW_LPH, LOWER_READING, MAX_FLOW_LPH, ImplausibleReading,
                         accumulate_consumption, fallback_detail, format_cubic_metres, record_consumption_sample)
from layout import (MANUAL_ROW_UNCLEAR, RAW_ROW_UNCLEAR, crop_coordinates, find_digit_row,
                    digit_box_settings, find_raw_digit_row, normalize_digit_boxes, rotated_width, scale_digit_boxes, turn_crop)
from meter_learning import (GEOMETRY_REPAIR_LIMIT, GEOMETRY_REPAIR_SECONDS, alignment_rollback, observe_flow,
                            observe_geometry_failures, local_geometry_trials, note_local_issue, note_local_improvement,
                            plan_reflection_recheck, REFLECTION_RECHECK_NOTICE, suggested_interval)
from reminder import Reminder
from notification_settings import (DEFAULT_DELIVERY_HOURS, DEFAULT_REVIEW_MINUTES, PUSH_SERVICE,
                                   notification_rules)
from settings import DEFAULTS, SCHEMA_VERSION, load_options
from source_settings import (CAMERA, DISCOVERY_TEMPLATE, ESP_ADDRESS_MODES, REFERENCE,
                             discovered_sources, source_check_key, source_rules)
from panel import start_panel
from experimental_meters import ExperimentalMeters
from language import load_preferences
from transport import open_core

MAX_RESPONSE_BYTES = 3_000_000
LAST_WHEEL_STREAM_FRAMES = 3
LAST_WHEEL_STREAM_SECONDS = 2
LAST_WHEEL_STREAM_SPACING = .35
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
FRESH_OCR_NOTICE = "Die bisherigen OCR-Versuche reichen nicht aus. Ein frisches Kamerabild folgt in Kürze."
SINGLE_DIGIT_RECHECK = "Automatik-Nachprüfung: Die App prüft die fehlende Ziffer mit leicht verschobenem Rahmen."
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


def read_last_wheel_stream(url, *, token=None, stop=lambda: False):
    """Read a short, bounded multipart JPEG sequence from a direct ESP camera."""
    sample_after = time.monotonic()
    deadline = sample_after + LAST_WHEEL_STREAM_SECONDS
    headers = {"Accept": "multipart/x-mixed-replace", "Cache-Control": "no-cache"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    open_request = open_core if token else urlopen
    pictures = []
    pending = bytearray()
    with open_request(request, timeout=1) as response:
        headers = response.headers
        boundary = headers.get_param("boundary")
        if headers.get_content_type() != "multipart/x-mixed-replace" or not boundary or len(boundary) > 70:
            return pictures
        delimiter = b"--" + boundary.encode("ascii")
        while len(pictures) < LAST_WHEEL_STREAM_FRAMES and not stop() and time.monotonic() < deadline:
            end = pending.find(b"\r\n\r\n")
            if end >= 0:
                section = pending[:end].lstrip(b"\r\n")
                marker, _, part = section.partition(b"\r\n")
                if marker != delimiter or end > 4096:
                    break
                fields = BytesHeaderParser().parsebytes(bytes(part))
                if fields.get_content_type() != "image/jpeg":
                    break
                start = end + 4
                length = fields.get("Content-Length")
                if length is None:
                    data_end = pending.find(b"\r\n" + delimiter, start)
                else:
                    length = int(length)
                    if not 0 < length <= MAX_RESPONSE_BYTES:
                        break
                    data_end = start + length
                if data_end >= 0 and len(pending) >= data_end:
                    if not 0 < data_end - start <= MAX_RESPONSE_BYTES:
                        break
                    picture = bytes(pending[start:data_end])
                    del pending[:data_end]
                    sampled_at = time.monotonic()
                    if (sampled_at >= sample_after and picture.startswith(b"\xff\xd8")
                            and picture.endswith(b"\xff\xd9") and picture not in pictures):
                        try:
                            with Image.open(io.BytesIO(picture)) as frame:
                                if frame.width * frame.height <= MAX_IMAGE_PIXELS:
                                    frame.load()
                                    pictures.append(picture)
                                    sample_after = sampled_at + LAST_WHEEL_STREAM_SPACING
                        except (OSError, ValueError, Image.DecompressionBombError):
                            pass
                    continue
                if len(pending) - start > MAX_RESPONSE_BYTES:
                    break
            elif len(pending) > 4096:
                break
            try:
                block = response.read1(16_384)
            except TimeoutError:
                break
            if not block:
                break
            pending.extend(block)
    return pictures


def last_wheel_transition(readings):
    """Report a forward one-position change between visible digits, including 9 → 0."""
    visible = []
    for value in readings:
        if value in tuple("0123456789") and (not visible or value != visible[-1]):
            visible.append(value)
    if len(visible) == 2 and (int(visible[0]) + 1) % 10 == int(visible[1]):
        return visible[0], visible[1]
    return None


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


def recover_single_digit(layout, pattern, current, whole_digits, fraction_digits, read, available, report, stop, accept):
    """Probe the missing slot on this register, with two agreeing OCR profiles."""
    register, width, whole_boxes, fraction_boxes = layout
    position = pattern.index("?")
    index = position - (position > whole_digits)
    whole = whole_boxes or approximate_whole_boxes(width, register.height, whole_digits)
    boxes = [*whole, *fraction_boxes]
    if len(boxes) != whole_digits + fraction_digits:
        return None, 0
    normalized = list(map(list, normalize_digit_boxes(boxes, register.size)))
    seen = {boxes[index]}
    attempted = 0
    for angle, shifted in local_geometry_trials(normalized, [index]):
        if angle or attempted + 2 > available or stop():
            break
        box = scale_digit_boxes([shifted[index]], register.size)[0]
        if box in seen:
            continue
        seen.add(box)
        report(attempted)
        first = read(box, OCR_PROFILES[0])
        attempted += 1
        if first not in "0123456789" or len(first) != 1 or stop():
            report(attempted, box, "unclear")
            continue
        report(attempted)
        second = read(box, OCR_PROFILES[1])
        attempted += 1
        candidate = pattern[:position] + first + pattern[position + 1:] + current[len(pattern):]
        accepted = first == second and accept(candidate)
        evidence = "accepted" if accepted else "agreement" if first == second else "disagreement"
        report(attempted, box, evidence)
        if accepted:
            moved = boxes.copy()
            moved[index] = box
            return (candidate, moved[:whole_digits], moved[whole_digits:]), attempted
    return None, attempted


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


def wizard_camera_preview(source, token, zone, *, full_size=False):
    mode = source["mode"]
    if mode == "slfork":
        base = source["url"].rstrip("/")
        try:
            picture = get_bytes(base + "/img_tmp/alg.jpg", timeout=5)
        except HTTPError as error:
            if error.code not in (404, 410):
                raise
            error.close()
            picture, _, _ = capture_edge_camera(base, zone)
    elif mode == "slfork_camera":
        picture, _, _ = capture_edge_camera(source["url"].rstrip("/"), zone)
    else:
        picture, _, _ = capture_camera(source["camera"], "", token, zone, timeout=5)
    try:
        with Image.open(io.BytesIO(picture)) as frame:
            if frame.width * frame.height > MAX_IMAGE_PIXELS:
                raise ValueError("Kamerabild hat zu viele Pixel")
            return calibration_jpeg(frame, frame.size if full_size else (960, 720))
    except Image.DecompressionBombError as error:
        raise ValueError("Kamerabild hat zu viele Pixel") from error


def calibration_jpeg(frame, max_size):
    image = frame.convert("RGB")
    image.thumbnail(max_size, Image.Resampling.LANCZOS)
    with io.BytesIO() as buffer:
        image.save(buffer, "JPEG", quality=84)
        return buffer.getvalue()


def approximate_whole_boxes(width, height, count):
    return [(width * index // count, 0, width * (index + 1) // count, height)
            for index in range(count)]


def draw_test_preview(register, integer_width, whole_boxes, fraction_boxes, reading,
                      whole_digits=5, fraction_digits=3, readings=None, composed=False, pending=False, suspected_slots=(), visible_slots=None):
    """Mark OCR digit regions and the actual read characters for manual diagnostics.

    Green: a digit was read without observed variation; yellow: attempts disagreed
    or a digit position is suspected; red: the position remains unclear.
    The coordinates are approximate for manually configured crops without digit frames.
    They do NOT assert a match against the reference value.
    """
    annotated = register.convert("RGB")
    draw = ImageDraw.Draw(annotated)
    h, w = annotated.height, annotated.width
    if w <= 0 or h <= 0:
        raise ValueError("Leerer OCR-Ausschnitt")
    whole_width = max(1, min(integer_width, w))
    boxes = (list(whole_boxes[:whole_digits]) if len(whole_boxes) >= whole_digits
             else approximate_whole_boxes(whole_width, h, whole_digits))
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
        if visible_slots is not None and idx not in visible_slots:
            continue
        l, t, r, b = [int(coord) for coord in box]
        if not (0 <= l < r <= w and 0 <= t < b <= h):
            continue
        if pending:
            color = (71, 157, 194)
        elif idx in uncertain or idx in suspected_slots:
            color = (241, 184, 54)
        else:
            color = (36, 170, 92) if chars[idx].isdigit() else (203, 65, 77)
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


def geometry_check_key(rules, source_key):
    return [source_key, rules["crop_mode"], rules["crop"], rules["rotation"], rules["width"],
            rules["integer_digits"], rules["fraction_digits"], rules["crop_revision"]]


def last_verified_configured_geometry(history, rules, source_key):
    """Recover an existing saved crop only when history corroborates its revision."""
    recorded = history.get("geometry_recovery", {})
    if (rules["crop_mode"] == "manual" and rules["crop_revision"]
            and history.get("check_status") in ("match", "ocr_only")
            and not history.get("ocr_rotation_adjustment")
            and recorded.get("key") == geometry_check_key(rules, source_key)
            and recorded.get("stamp") == history.get("last_epoch")
            and recorded.get("failures") == 0):
        return rules
    return None


def calibration_source_id(source):
    return hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()


def standalone_calibration_reference(rules, source, source_key, captured, previous):
    """Use a recent reading from this meter until a newer automatic reading takes over."""
    saved = rules.get("calibration_reference")
    if not isinstance(saved, dict) or saved.get("source") != calibration_source_id(source):
        return None
    stamp, precision = saved.get("time"), saved.get("precision")
    if (type(stamp) not in (int, float) or not 0 < captured - stamp <= FRESH_SAMPLE_AGE
            or type(precision) is not int or not rules["decimals"] <= precision <= rules["fraction_digits"]
            or saved.get("integer_digits") != rules["integer_digits"]
            or (previous.get("source") == source_key and previous.get("timestamp", 0) >= stamp)):
        return None
    reading = saved.get("reading")
    if meter_prefix(reading, precision, rules["integer_digits"]) is None:
        return None
    counter = accumulate_consumption({}, source_key, stamp, reading, precision,
                                     rules["max_flow_lph"], rules["integer_digits"])
    return {"counter": counter, "reading": reading, "image_id": saved.get("image_id")}


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
    is_fallback = False
    if last and last["camera"] == camera:
        digits = last.get("integer_digits", 5)
        value = last["reading"][:digits + (last["decimals"] + 1 if last["decimals"] else 0)]
        captured = last["image_time"]
        is_fallback = history.get("check_status") != "ocr_only"
    payload = {
        "state": value,
        "attributes": {"friendly_name": "Meter OCR Zählerstand" + LABEL_SUFFIX, "unit_of_measurement": "m³",
                       "device_class": "gas", "source_camera": camera, "last_successful_image": captured,
                       "is_fallback": is_fallback},
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


SETUP_WAIT_NOTICE = "Automatik wartet auf die Einrichtung. Du kannst sie automatisch oder manuell abschließen."


def automatic_inputs_ready(rules, source, history, *, legacy_crop=False):
    if not source["selected"]:
        return False
    scope = setup_source_id(source)
    key = source_check_key(source)
    if (setup_deadlines(rules, source)[0] or history.get("consumption", {}).get("source") == key
            or (history.get("check_source") == key and history.get("last_match_at"))
            or history.get("manual_setup_source") == scope):
        return True
    saved_scope = rules.get("setup_input_source")
    if saved_scope is not None:
        return saved_scope == scope and bool(
            rules["crop_mode"] == "manual" or rules.get("fallback_value") and rules.get("fallback_time")
        )
    return history.get("check_source", key) == key and bool(
        rules["crop_mode"] == "manual" or rules.get("fallback_value") and rules.get("fallback_time") or legacy_crop
    )


def main():
    raw_options = json.loads(OPTIONS.read_text(encoding="utf-8"))
    # The Supervisor remains the source of truth for values edited in its UI.
    # It regenerates options.json. Record a versioned, normalized copy separately.
    snapshot = json.loads(EFFECTIVE_OPTIONS.read_text(encoding="utf-8")) if EFFECTIVE_OPTIONS.exists() else {}
    options = load_options(raw_options, snapshot)
    configured = bool(options.get("kamera_entitaet")) or options["esp_url"] != DEFAULTS["esp_url"]
    setup_pending = snapshot.get(
        "setup_pending", not configured and not EFFECTIVE_OPTIONS.exists() and not HISTORY.exists())
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
    initial_source_key = source_check_key(configured_source)
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
        if source_check_key(validated) != source_check_key(configured_source) and not auto_rules.get("setup_input_source"):
            save_auto_rules({**auto_rules, "setup_input_source": setup_source_id(get_source()[0])}, request_check=False)
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
                  "intensive_agreement": DEFAULT_INTENSIVE_AGREEMENT,
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
            intensive_agreement = saved_rules.get("intensive_agreement", DEFAULT_INTENSIVE_AGREEMENT)
            if not valid_intensive_agreement(intensive_agreement):
                intensive_agreement = DEFAULT_INTENSIVE_AGREEMENT
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
                          "calibration_reference": saved_rules.get("calibration_reference"),
                          "setup_completed": saved_rules.get("setup_completed"),
                          "setup_success": saved_rules.get("setup_success"),
                          "setup_input_source": saved_rules.get("setup_input_source"),
                          "setup_pending_source": saved_rules.get("setup_pending_source"),
                          "setup_pending_started": saved_rules.get("setup_pending_started"),
                          "setup_pending_metrics": saved_rules.get("setup_pending_metrics"),
                          "setup_reflection": saved_rules.get("setup_reflection"),
                          "stationary_partial_scope": saved_rules.get("stationary_partial_scope"),
                          "intensive_agreement": intensive_agreement,
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

    def save_auto_rules(values, *, request_check=True):
        nonlocal auto_rules
        integer_digits = values.get("integer_digits", auto_rules["integer_digits"])
        fraction_digits = values.get("fraction_digits", auto_rules["fraction_digits"])
        meter_display = values.get("meter_display", auto_rules["meter_display"])
        fallback_value = values.get("fallback_value", auto_rules["fallback_value"])
        fallback_time = values.get("fallback_time", auto_rules["fallback_time"])
        precision_mode = values.get("precision_mode", auto_rules["precision_mode"])
        intensive_agreement = values.get("intensive_agreement", auto_rules["intensive_agreement"])
        if not valid_intensive_agreement(intensive_agreement):
            raise ValueError("Ungültige Übereinstimmung für die Intensivprüfung")
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
        if request_check and (needs_check or not view_changed):
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

    def set_activity(state, detail, *, completed=None, total=None, reading=None, candidates=None):
        activity.update(state=state, detail=detail, updated_at=time.time(), completed=completed, total=total,
                        reading=reading, candidates=candidates)

    def ready_for_automatic(rules, source):
        explicit_crop = options["ausschnitt"] != DEFAULTS["ausschnitt"]
        return automatic_inputs_ready(rules, source, history, legacy_crop=explicit_crop and not setup_pending)

    def get_automatic_activity():
        if not get_auto_paused() and not ready_for_automatic(get_auto_rules(), get_source()[0]):
            return {"state": "setup_wait", "detail": SETUP_WAIT_NOTICE}
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
    calibration_candidates_path = HISTORY.with_name("calibration-candidates.json")
    known_good_geometry_path = HISTORY.with_name("known-good-geometry.json")

    def known_good_scope(rules, source):
        format_keys = ("integer_digits", "fraction_digits", "meter_display", "polarity")
        return calibration_source_id([source, [rules[key] for key in format_keys]])

    def geometry_layout(geometry, rules):
        box = crop_coordinates(geometry["crop"], geometry["width"], geometry["rotation"])
        boxes = digit_box_settings(geometry["digit_boxes"], rules["integer_digits"] + rules["fraction_digits"])
        return Layout(box, geometry["rotation"], geometry["width"], tuple(map(tuple, boxes)))

    def load_known_good_layout(rules, source):
        try:
            saved = json.loads(known_good_geometry_path.read_text(encoding="utf-8"))
            if saved["scope"] == known_good_scope(rules, source):
                return geometry_layout(saved["geometry"], rules)
        except (OSError, ValueError, TypeError, KeyError):
            pass
        return None

    def remember_known_good_layout(rules, source, layout):
        if layout == load_known_good_layout(rules, source):
            return
        saved = {"scope": known_good_scope(rules, source), "geometry": layout.settings()}
        try:
            atomic_write(known_good_geometry_path, json.dumps(saved).encode(), 0o600)
        except OSError:
            print("Der bestätigte Rahmen konnte nicht als Ausgangspunkt gespeichert werden.")

    def candidate_scope(configuration, region, simplified, intensive):
        rules, source = configuration
        relevant = ("integer_digits", "fraction_digits", "decimals", "polarity", "meter_display")
        key = [source, [rules[name] for name in relevant], region, simplified, intensive]
        return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()

    def load_calibration_candidates(scope, rules):
        try:
            saved = json.loads(calibration_candidates_path.read_text(encoding="utf-8"))
            if saved["scope"] != scope:
                return {}
            result = {}
            for item in saved["candidates"][:SHORTLIST_LIMIT]:
                geometry, score = item["geometry"], item["score"]
                if (len(score) not in (2, 3) or type(score[0]) is not int or not 0 <= score[0] <= 100
                        or type(score[1]) not in (int, float) or not 0 <= score[1] <= 255
                        or (len(score) == 3 and (type(score[2]) is not int or not score[0] <= score[2] <= 100))):
                    continue
                result[geometry_layout(geometry, rules)] = tuple(score)
            return result
        except (OSError, ValueError, TypeError, KeyError):
            return {}

    def save_calibration_candidates(scope, shortlist):
        candidates = [{"geometry": layout.settings(), "score": score} for layout, score in shortlist.items()]
        atomic_write(calibration_candidates_path,
                     json.dumps({"scope": scope, "candidates": candidates}).encode(), 0o600)

    def read_geometry_backup():
        try:
            backup = json.loads(geometry_backup.read_text(encoding="utf-8"))
            return backup["rules"] if backup["source"] == get_source()[0] else None
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def calibration_configuration_now():
        return get_auto_rules(), get_source()

    def save_calibration_layout(attempt, layout, *, provisional=False, verified=False, reflected=False):
        rules = get_auto_rules()
        reference = rules.get("calibration_reference") if attempt.intensive else None
        if not provisional and attempt.reference_reading is not None:
            precision = {1: 3, 10: 2, 100: 1, 1000: 0}[attempt.counter["step_litres"]]
            head, _, fraction = attempt.reference_reading.replace(",", ".").partition(".")
            reading = f"{head}.{fraction[:precision]}" if precision else head
            reference = {
                "reading": reading, "time": attempt.counter["timestamp"], "precision": precision,
                "source": calibration_source_id(get_source()[0]), "integer_digits": rules["integer_digits"],
                "image_id": attempt.reference_image_id,
            }
        source, _ = get_source()
        completed = rules.get("setup_completed")
        previous_completion, _ = setup_deadlines(rules, source)
        finished = time.time()
        elapsed = max(0, round(time.monotonic() - attempt.started))
        metrics = {"frames_tested": attempt.attempts, "images_checked": len(attempt.seen)}
        success = rules.get("setup_success")
        if verified and not attempt.intensive and not attempt.automatic and reference:
            success = {"source": setup_source_id(source), "time": finished, "duration_seconds": elapsed, **metrics}
            if not previous_completion:
                completed = success
        revision = str(time.time_ns())
        partial = (provisional and not reflected) or verified and attempt.simplified
        partial_scope = calibration_source_id([source, revision]) if partial else None
        pending_source = setup_source_id(source) if provisional else rules.get("setup_pending_source")
        pending_started = finished - elapsed if provisional else rules.get("setup_pending_started")
        pending_metrics = metrics if provisional else rules.get("setup_pending_metrics")
        save_auto_rules({**rules, **layout.settings(), "crop_revision": revision,
                         "setup_input_source": setup_source_id(source),
                         "calibration_reference": reference, "stationary_partial_scope": partial_scope,
                         "setup_completed": completed, "setup_success": success,
                         "setup_pending_source": None if completed else pending_source,
                         "setup_pending_started": None if completed else pending_started,
                         "setup_pending_metrics": None if completed else pending_metrics})

    def control_calibration(action, limit, region=None, *, verification_id=None):
        nonlocal calibration, calibration_configuration, calibration_next
        with settings_lock:
            if action == "repair":
                _, optimization_until = setup_deadlines(get_auto_rules(), get_source()[0])
                if time.time() < optimization_until:
                    return False
            running = calibration is not None and calibration.state in ("waiting", "testing") and not calibration.expired(time.monotonic())
            if action == "cancel":
                if running:
                    calibration.state = "cancelled"
            elif action == "skip-verification":
                current_id = calibration.skippable_verification_id() if calibration else None
                if (not current_id or verification_id != current_id
                        or calibration_configuration_now() != calibration_configuration):
                    raise ValueError("No matching fine-check verification to skip")
                save_calibration_layout(calibration, calibration.candidate)
                calibration.state = "saved_without_verification"
                calibration.verification_pending = False
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
                rules = configuration[0]
                simplified = rules["decimals"] == 3 and (
                    action == "setup" or action == "start" and not rules["precision_mode"])
                intensive = action == "intensive"
                if intensive and rules["fraction_digits"] != 3:
                    raise ValueError("The meter must display three decimal digits")
                if running and (action == "repair" or (
                        calibration.limit == limit and calibration.region == region
                        and calibration.simplified == simplified and calibration.intensive == intensive
                        and configuration == calibration_configuration)):
                    return False
                repair = action == "repair"
                previous = (calibration.best if calibration and calibration_configuration[1][0] == source else None)
                if repair:
                    atomic_write(geometry_backup, json.dumps({"source": source, "rules": get_auto_rules()}).encode(),
                                 0o600)
                scope = candidate_scope(configuration, region, simplified, intensive)
                shortlist = {} if repair else load_calibration_candidates(scope, rules)
                known_good = load_known_good_layout(rules, source)
                if known_good is None:
                    source_key = source_check_key(source)
                    verified_geometry = last_verified_configured_geometry(history, rules, source_key)
                    if verified_geometry:
                        known_good = geometry_layout(verified_geometry, rules)
                if intensive:
                    previous = geometry_layout(rules, rules) if rules["crop_mode"] == "manual" else known_good
                    if previous is None:
                        raise ValueError("A saved crop is required for the last digit")
                reflected_layout = None
                reflected_positions = ()
                marked = rules.get("setup_reflection")
                if (not repair and not intensive and rules["reflection_estimate_enabled"]
                        and isinstance(marked, dict) and marked.get("source") == setup_source_id(source)):
                    try:
                        layout = geometry_layout(marked, rules)
                        positions = tuple(marked["positions"])
                        if (layout.digit_boxes and 1 <= len(positions) <= 2
                                and all(type(index) is int and 0 <= index < len(layout.digit_boxes)
                                        for index in positions)):
                            reflected_layout, reflected_positions = layout, positions
                    except (ValueError, TypeError, KeyError):
                        pass
                calibration = Calibration(limit=limit, started=now, automatic=repair,
                                          rank_candidates=not (repair or intensive), shortlist=shortlist,
                                          simplified=simplified, intensive=intensive,
                                          duration=GEOMETRY_REPAIR_SECONDS if repair else TIME_LIMIT,
                                          attempt_limit=GEOMETRY_REPAIR_LIMIT if repair else MAX_ATTEMPTS,
                                          previous_layout=previous, region=region,
                                          known_good_layout=reflected_layout or known_good,
                                          reflected_layout=reflected_layout, reflected_positions=reflected_positions)
                calibration_preview.clear()
                calibration_images.clear()
                calibration_configuration = configuration
                calibration_next = now
            wake_worker.set()
            return True

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
            same_configuration = calibration_configuration_now() == calibration_configuration
            saved = status["state"] in ("saved", "saved_without_verification", "saved_stationary", "saved_reflection")
            saved_layout = (calibration.reflected_layout if status["state"] == "saved_reflection"
                            else calibration.candidate if saved else calibration.previous_layout)
            if saved_layout and (saved or (calibration.followup and same_configuration)):
                status["settings"] = {**saved_layout.settings(), "crop_revision": auto_rules["crop_revision"]}
            if same_configuration:
                status["skip_verification_id"] = calibration.skippable_verification_id()
            if status["state"] in ("failed", "timeout", "image_timeout") and calibration.best:
                status["proposal"] = calibration.best.settings()
            if calibration.fine_evidence and status["state"] in (
                    "failed", "timeout", "image_timeout", "saved_without_verification"):
                status["preview"] = dict(calibration.fine_evidence[1])
            return status

    def calibration_image(kind, version):
        with settings_lock:
            recent = next((content for revision, content in calibration_images.get(kind, ())
                           if str(revision) == version), None)
            if recent is not None:
                return recent
            if calibration and calibration.fine_evidence:
                _, preview, images = calibration.fine_evidence
                if str(preview.get(kind)) == version:
                    return images.get(kind)
            return None

    def run_calibration(active_rules, active_source, mode, base, camera, reference, source_key):
        nonlocal calibration, calibration_configuration, calibration_next, calibration_preview_version
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
        if attempt.intensive:
            active_rules = {**active_rules, "decimals": 3}
        deadline = time.monotonic() + 30

        def stopped():
            return time.monotonic() >= deadline or calibration is not job or job.state != "testing" or get_auto_paused()

        def fetch(url, token=None, timeout=8):
            if stopped():
                raise TimeoutError("Calibration stopped")
            return get_bytes(url, token, timeout=min(timeout, max(0.01, deadline - time.monotonic())))

        def report_calibration(stage, variant=None, rotation=None, positions=None):
            with settings_lock:
                if calibration is job and job.state == "testing":
                    job.stage, job.variant, job.rotation = stage, variant, rotation
                    job.attempts = attempt.attempts
                    job.row_found = attempt.row_found
                    job.agreement_threshold = attempt.agreement_threshold
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
        provisional = False
        reflected = False
        stream_pictures = []
        try:
            if attempt.intensive and not attempt.stream_unavailable:
                stream_url = None
                stream_token = None
                if mode == "slfork_camera":
                    stream_url = base + "/camera?task=stream_flashlight"
                elif camera and not reference:
                    stream_url = f"http://supervisor/core/api/camera_proxy_stream/{camera}"
                    stream_token = token
                if stream_url:
                    try:
                        stream_pictures = read_last_wheel_stream(stream_url, token=stream_token, stop=stopped)
                    except (OSError, ValueError) as error:
                        if isinstance(error, HTTPError):
                            error.close()
                    if not stream_pictures and not stopped():
                        attempt.stream_unavailable = True
            if stream_pictures:
                result = capture_esp_snapshot(base, zone, "camera_stream", fetch=lambda _: stream_pictures[-1])
            elif mode == "slfork":
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
                    if attempt.simplified:
                        sample = {**sample, **{key: two_decimal_reading(sample[key])
                                              for key in ("raw_value", "actual_value") if key in sample}}
                    precision = attempt.precision(active_rules, sample.get("reference_required") is not False)
                    baseline = history.get("consumption", {})
                    if baseline.get("source") == source_key and baseline.get("timestamp", 0) < captured:
                        baseline = {**baseline, "source": "calibration"}
                    else:
                        baseline = None
                    if baseline is None and attempt.followup_baseline:
                        baseline = attempt.followup_baseline
                    if baseline is None and active_rules["fallback_value"] and active_rules["fallback_time"]:
                        stamp = timestamp_epoch(active_rules["fallback_time"], zone)
                        if stamp < captured:
                            baseline = accumulate_consumption(
                                {}, "calibration", stamp, active_rules["fallback_value"], min(precision, configured_rules["decimals"]),
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

                        def report_crop(layout, register, reading, *, last_only=False, tentative_last=False):
                            if not frame_ready:
                                return
                            box = layout.box
                            if attempt.image_hints is None:
                                try:
                                    hints = image_quality_hints(frame, layout)
                                except ValueError:
                                    hints = []
                                attempt.image_hints = hints
                                with settings_lock:
                                    if calibration is job and job.state == "testing":
                                        job.image_hints = hints
                            region = [box[0] / frame.width, box[1] / frame.height,
                                      (box[2] - box[0]) / frame.width, (box[3] - box[1]) / frame.height]
                            try:
                                digits = (reading or "").replace(".", "")
                                suspected = ()
                                if tentative_last:
                                    suspected = (whole + 2,)
                                elif len(digits) == whole + fraction and digits.count("?") == 1:
                                    # One open slot between or next to otherwise readable digits.
                                    suspected = (digits.index("?"),)
                                painted = "?" * whole + ".??" + (reading or "?") if last_only else reading
                                preview = draw_test_preview(
                                    *register[:4], painted, whole, fraction,
                                    readings=None if last_only else readings, pending=reading is None,
                                    suspected_slots=(whole + 2,) if last_only and reading == "?" else suspected,
                                    visible_slots=(whole + 2,) if last_only else None,
                                )
                                report_image("crop", calibration_jpeg(preview, (820, 300)),
                                             region=region, reading=reading, angle=layout.rotation, last_digit_only=last_only,
                                             approximate=not bool(layout.digit_boxes), method=layout.method, reason=None)
                            except (OSError, ValueError):
                                pass

                        def retain_preview(accepted=False):
                            if not (attempt.intensive and accepted and readings and readings[-1].isdigit()):
                                return
                            with settings_lock:
                                if calibration is not job or job.state != "testing":
                                    return
                                images = {}
                                for kind in ("frame", "crop"):
                                    version = calibration_preview.get(kind)
                                    content = calibration_image(kind, str(version)) if version else None
                                    if content is None:
                                        return
                                    images[kind] = content
                                attempt.retain_fine_evidence(100, True, calibration_preview, images)

                        def report_decision(reason):
                            with settings_lock:
                                if frame_ready and calibration is job and job.state == "testing":
                                    calibration_preview["reason"] = reason
                            retain_preview(accepted=reason in ("accepted", "verified"))

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
                            retain_preview()

                        def register_for(layout):
                            return select_register(
                                frame, None, layout.box, layout.width, layout.rotation, whole, fraction,
                                digit_boxes=layout.digit_boxes,
                            )

                        def recognize(layout, profile, register, ocr_deadline=None, *, full_precision=False):
                            reduced = attempt.simplified and not full_precision
                            value = read_visible_digits(
                                *register[:4], options["helle_ziffern"], active_rules["polarity"], profile=profile,
                                whole_digits=whole, fraction_digits=2 if reduced else fraction,
                                deadline=deadline if ocr_deadline is None else ocr_deadline,
                                prefer_boxes=bool(layout.digit_boxes), recognize=cached_digit,
                            )
                            return two_decimal_reading(value) if reduced else value

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

                        def read_calibration_slot(layout, index, profile):
                            register, width, whole_boxes, fraction_boxes, _ = register_for(layout)
                            if index < whole:
                                boxes = whole_boxes or approximate_whole_boxes(width, register.height, whole)
                            else:
                                boxes, index = fraction_boxes, index - whole
                            if index >= len(boxes):
                                return "?"
                            box = boxes[index]
                            if box[2] <= box[0]:
                                return "?"
                            polarity = active_rules["polarity"]
                            return read_digit(register, box, lambda picture, digits: cached_digit(
                                picture, options["helle_ziffern"] if polarity == "auto" else polarity == "light",
                                digits, profile=profile, force_polarity=polarity != "auto", deadline=fine_deadline))

                        def preview_optional_slot(layout):
                            nonlocal fine_deadline
                            fine_deadline = min(deadline, time.monotonic() + 3)
                            hint = attempt.probe_optional_last_slot(
                                layout, active_rules, read_calibration_slot,
                                lambda: stopped() or time.monotonic() >= fine_deadline, report_fine,
                            )
                            if hint is not None:
                                trial, values = hint
                                readings[:] = values
                                report_crop(trial, register_for(trial), values[-1], tentative_last=True)
                                report_decision("optional_last_slot")

                        if attempt.intensive:
                            earlier_frames = []
                            for stream_picture in stream_pictures[:-1]:
                                try:
                                    with Image.open(io.BytesIO(stream_picture)) as earlier:
                                        if earlier.size == frame.size:
                                            earlier_frames.append(earlier.convert("RGB"))
                                except (OSError, ValueError, Image.DecompressionBombError):
                                    continue
                            transition = None
                            layout = attempt.candidate or attempt.previous_layout
                            if layout and not layout.digit_boxes:
                                register, _, whole_boxes, fraction_boxes, _ = register_for(layout)
                                boxes = normalize_digit_boxes([*whole_boxes, *fraction_boxes], register.size)
                                if len(boxes) == whole + fraction:
                                    layout = Layout(layout.box, layout.rotation, layout.width, boxes)
                            if layout and len(layout.digit_boxes) == whole + fraction:
                                def read_last(trial, profile):
                                    nonlocal previous_layout, transition
                                    register = register_for(trial)
                                    if trial != previous_layout:
                                        readings.clear()
                                        previous_layout = trial
                                        report_crop(trial, register, None, last_only=True)
                                    polarity = active_rules["polarity"]
                                    def recognize_digit(picture, digits, *, active_profile=profile):
                                        return cached_digit(
                                            picture, options["helle_ziffern"] if polarity == "auto" else polarity == "light",
                                            digits, profile=active_profile, force_polarity=polarity != "auto",
                                            deadline=deadline)

                                    digit_box = register[3][-1]
                                    digit = read_digit(register[0], digit_box, recognize_digit)
                                    if trial == layout and earlier_frames:
                                        views = [turn_crop(crop_register(earlier, trial.box), trial.rotation)
                                                 for earlier in earlier_frames]
                                        previous = [read_digit(view, digit_box, recognize_digit) for view in views]
                                        observed = last_wheel_transition([*previous, digit])
                                        if observed:
                                            other = OCR_PROFILES[1] if profile == OCR_PROFILES[0] else OCR_PROFILES[0]
                                            cross_check = [read_digit(
                                                view, digit_box, partial(recognize_digit, active_profile=other)
                                            ) for view in [*views, register[0]]]
                                            if last_wheel_transition(cross_check) == observed:
                                                transition = observed
                                                digit = "?"
                                    readings.append(digit)
                                    report_crop(trial, register, digit, last_only=True)
                                    return digit

                                report_calibration("last_digit", rotation=layout.rotation)
                                result_layout = attempt.check_last_digit(
                                    frame, sample, captured, layout, whole, read_last,
                                    lambda: stopped() or transition is not None, on_image, report_decision,
                                )
                                if transition:
                                    with settings_lock:
                                        if calibration is job and job.state == "testing":
                                            calibration_preview["wheel_transition"] = transition
                                    report_decision("roll_transition")
                                if result_layout is not None:
                                    if attempt.verification_pending:
                                        selected = result_layout
                                    else:
                                        attempt.begin_verification(time.monotonic())
                        elif attempt.verification_pending:
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
                                read_slot=read_calibration_slot,
                                angle_read=read,
                                on_angle=lambda variant, rotation: report_calibration("angle", variant, rotation),
                                on_shortlist=lambda variant, rotation: report_calibration(
                                    "shortlist", variant, rotation),
                            )
                            if candidate is not None:
                                if attempt.automatic:
                                    attempt.begin_verification(time.monotonic())
                                else:
                                    selected = candidate
                                    preview_optional_slot(selected)
                            elif attempt.stationary_crop_ready():
                                selected = attempt.candidate
                                provisional = True
                            elif attempt.reflection_crop_ready():
                                selected = attempt.reflected_layout
                                provisional = reflected = True
                        if attempt.reference_reading is not None and attempt.counter.get("timestamp") == captured:
                            attempt.reference_image_id = hashlib.sha256(picture).hexdigest()
        except (OSError, ValueError, TypeError, Image.DecompressionBombError) as error:
            print(f"Selbsteinrichtung konnte die Aufnahme nicht prüfen: {type(error).__name__}")
        with settings_lock:
            now = time.monotonic()
            if attempt.searching_since is not None:
                attempt.spent += now - attempt.searching_since
                attempt.searching_since = None
                attempt.last_image_at = now
            if calibration is not job or job.state != "testing":
                return True
            if (attempt.shortlist != job.shortlist and attempt.shortlist
                    and calibration_configuration_now() == calibration_configuration):
                try:
                    scope = candidate_scope(calibration_configuration, attempt.region,
                                            attempt.simplified, attempt.intensive)
                    save_calibration_candidates(scope, attempt.shortlist)
                except OSError:
                    print("Zwischenkandidaten konnten nicht gespeichert werden.")
            if attempt.expired(now):
                attempt.state = "timeout"
            elif calibration_configuration_now() != calibration_configuration or get_auto_paused():
                attempt.state = "cancelled"
            elif selected:
                try:
                    save_calibration_layout(attempt, selected, provisional=provisional,
                                            verified=not provisional, reflected=reflected)
                    if not provisional and not attempt.intensive:
                        remember_known_good_layout(get_auto_rules(), active_source, selected)
                    if not attempt.intensive and not attempt.automatic:
                        history["setup_first_check_revision"] = get_auto_rules()["crop_revision"]
                    attempt.state = "saved_reflection" if reflected else "saved_stationary" if provisional else "saved"
                except (OSError, ValueError):
                    attempt.state = "save_failed"
            elif len(attempt.seen) >= attempt.limit or attempt.search_exhausted():
                attempt.state = "failed"
            else:
                attempt.state = "waiting"
                attempt.stage = "verify_wait" if attempt.verification_pending else "waiting"
            calibration = attempt
            capture_interval = LAST_DIGIT_CAPTURE_INTERVAL if attempt.intensive else (
                PERFECT_CONFIRMATION_INTERVAL if attempt.full_hits else CAPTURE_INTERVAL)
            calibration_next = now + capture_interval
            wake_worker.set()
        return True

    extra_meters = ExperimentalMeters(
        HISTORY.with_name("experimental-meters.json"),
        lambda entity: json.loads(get_bytes(f"http://supervisor/core/api/states/{entity}", token, timeout=5)),
        atomic_write, zone,
    )
    extra_meters.start()
    _, update_progress, reset_manual_progress = start_panel(
        HISTORY, DESTINATION, GOOD_IMAGE, requested, default_decimals, default_attempts,
        get_auto_rules, save_auto_rules, options["ausschnitt"], options["vorkomma_breite"], TEST_IMAGE,
        partial(load_preferences, LANGUAGE_MODES), save_language_modes, get_delivery, save_delivery, get_source, save_source,
        wake_worker.set, test_source_image=TEST_SOURCE_IMAGE, automatic_preview=AUTOMATIC_PREVIEW,
        request_factory_reset=request_factory_reset, get_reset_status=lambda: reset_result["value"],
        skip_setup=skip_setup,
        discover_sources=partial(discover_ha_sources, token),
        get_wizard_image=partial(wizard_camera_preview, token=token, zone=zone),
        get_activity=get_automatic_activity,
        get_auto_paused=get_auto_paused, save_auto_paused=save_auto_paused,
        settings_lock=settings_lock, get_calibration=calibration_status, control_calibration=control_calibration,
        get_calibration_image=calibration_image, has_calibration_backup=lambda: read_geometry_backup() is not None,
        statistics_zone=zone, experimental_meters=extra_meters,
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
                calibration_candidates_path, known_good_geometry_path,
            )
            for path in paths:
                path.unlink(missing_ok=True)
            extra_meters.reset()
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
        with settings_lock:
            active_rules = get_auto_rules()
            active_source, _ = get_source()
        mode = active_source["mode"]
        interval_minutes = automatic_interval_minutes(active_rules["interval_minutes"], mode)
        esp_camera_only = mode == "slfork_camera"
        standalone = mode in ("esphome", "slfork_camera") or mode == "camera" and not active_source["reference"]
        base = active_source["url"].rstrip("/")
        camera = active_source["camera"] if mode not in ESP_ADDRESS_MODES else ""
        reference = active_source["reference"] if mode == "camera" else ""
        source_key = source_check_key(active_source)
        now = datetime.now(zone)
        stabilizing_until, optimization_until = setup_deadlines(active_rules, active_source)
        optimization_paused = now.timestamp() < optimization_until
        adaptive = mode == "slfork" and active_rules["adaptive_interval_enabled"]
        if adaptive:
            interval_minutes = suggested_interval(interval_minutes, history.get("adaptive_flow", {}), source_key, now.month)
        interval_minutes = stabilization_interval(interval_minutes, stabilizing_until, now.timestamp())
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
        stationary_partial = stationary_partial_active(active_rules, active_source)
        decimals = 2 if stationary_partial else active_rules["decimals"]
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
        if (not manual and calibration is not None and not calibration.automatic
                and calibration.state in ("waiting", "testing")):
            wake_worker.wait(timeout=LAST_DIGIT_CAPTURE_INTERVAL if calibration.intensive else CAPTURE_INTERVAL)
            continue
        if get_auto_paused() and not manual:
            set_activity("paused", "Automatik pausiert. Manuelle Tests bleiben verfügbar.")
            wake_worker.wait(timeout=15)
            continue
        if not manual and not ready_for_automatic(active_rules, active_source):
            set_activity("setup_wait", SETUP_WAIT_NOTICE)
            wake_worker.wait(timeout=2)
            continue
        if remaining > 0 and not startup and not manual and not source_changed and not run_automatic_now:
            set_activity("waiting", FRESH_OCR_NOTICE if history.get("fresh_ocr_retry_at") else
                         REFLECTION_RECHECK_NOTICE if history.get("reflection_retry_at") else
                         STANDALONE_PENDING_NOTICE if history.get("check_status") == STANDALONE_PENDING
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
                          "reflection_rechecks", "reflection_retry_at", "fresh_ocr_retry_at", "ocr_candidates", "ocr_method",
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
        fine_rotation = None
        local_trial = None
        restoring_local = False
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
            for field in ("reflection_anchor", "reflection_pending", "reflection_estimate", "reflection_streak",
                          "reflection_live_estimate", "reflection_rechecks", "reflection_retry_at"):
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
        cached_standalone = False
        setup_finished_in_check = False
        reflection_recheck = None
        ocr_candidates = []
        ocr_method = None
        exhausted_ocr = False
        decoded_test_image = False
        image_id = None
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
                if not manual and standalone and captured is not None:
                    image_id = hashlib.sha256(picture).hexdigest()
                    pending = updated.get("standalone_candidate") or standalone_calibration_reference(
                        active_rules, active_source, source_key, captured, history.get("consumption", {}),
                    )
                    if (pending and pending.get("image_id") == image_id
                            and pending["counter"]["source"] == source_key
                            and 0 <= captured - pending["counter"]["timestamp"] <= FRESH_SAMPLE_AGE):
                        cached_standalone = True
                        outcome = updated["status"] = STANDALONE_PENDING
                        updated["source_connection_status"] = "stale"
                        updated["source_connection_detail"] = "Home-Assistant-Kamera erreichbar; dieses Bild wurde bereits geprüft."
                        updated["check_detail"] = STANDALONE_PENDING_NOTICE
                        result = None
                if result is not None and not manual and (captured is None or captured <= updated.get("last_epoch", 0)):
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
                    decoded_test_image = manual_upload
                    if manual:
                        atomic_write(TEST_SOURCE_IMAGE, picture, 0o600)
                    ocr_readings = []
                    ocr_error = None
                    local_enabled = False
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
                                      "image_id": image_id, "attempts": 0, "frame_reads": []}
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
                                                  captured=latest_time, frame_reads=[],
                                                  image_id=hashlib.sha256(latest_picture).hexdigest()
                                                  if standalone and not manual else None)
                            read_state["attempts"] += 1
                            observed = read_layout((
                                read_state["register"], read_state["integer_width"],
                                read_state["whole_boxes"], read_state["fraction_boxes"],
                            ), profile)
                            read_state["frame_reads"].append(str(observed))
                            return observed
                        if manual:
                            update_progress(request_id, "ocr", f"OCR-Prüfung gestartet (max. {manual_options['attempts']} Versuche).", 0)
                        def report_ocr(attempts, message):
                            if manual:
                                update_progress(request_id, "ocr", message, attempts)
                            else:
                                running = "läuft" in message
                                current_attempt = attempts + 1 if running else attempts
                                set_activity("working", f"Zählerbild wird gelesen · Versuch {current_attempt} von {ocr_limit}",
                                             completed=attempts, total=ocr_limit,
                                             reading=ocr_readings[-1] if ocr_readings else None)
                        require_consensus = (raw_fallback and not manual_reference) or (standalone and not manual)
                        configured_attempts = manual_options["attempts"] if manual else max_attempts
                        if require_consensus:
                            configured_attempts = max(2, configured_attempts)
                        local_enabled = (not manual and not optimization_paused and not raw_fallback
                                         and active_rules["fine_alignment_enabled"] and crop_rules["crop_mode"] == "manual")
                        extra_attempts = (10 if not manual and not local_enabled and not optimization_paused
                                          and history.get("failure_attempts", 0) == 0
                                          and not history.get("retry_suppressed") else 0)
                        ocr_limit = min(15, configured_attempts + (5 if local_enabled else extra_attempts))
                        if live_source:
                            ocr_limit = min(ocr_limit, LIVE_CAPTURE_MAX_ATTEMPTS)
                        reserve_for_rotation = (2 * len(INTENSIVE_ROTATIONS)
                                                if extra_attempts and source != "auto" and not custom_boxes
                                                and not stationary_partial else 0)
                        regular_limit = min(configured_attempts, ocr_limit) if local_enabled else ocr_limit - reserve_for_rotation
                        regular_attempts = min(configured_attempts, regular_limit)
                        comparison_decimals = manual_options["decimals"] if manual else decimals

                        def stop_ocr():
                            return (not manual and get_auto_paused()) or (live_source and time.monotonic() >= live_deadline)

                        digit_probe_enabled = not manual and not raw_fallback and not sample.get("reference_is_fallback")

                        def stop_before_extra_profile():
                            if stop_ocr():
                                return True
                            same_frame = read_state["frame_reads"]
                            if not digit_probe_enabled or not same_frame:
                                return False
                            if len(same_frame) == 1:
                                return live_source and missing_digit_pattern(same_frame[-1], comparison_decimals,
                                                                             integer_digits) is not None
                            return disputed_digit_pattern(same_frame, comparison_decimals, integer_digits) is not None

                        ocr, ocr_confirmed, ocr_attempts = read_with_retries(
                            read, sample, comparison_decimals,
                            progress=report_ocr,
                            max_attempts=regular_attempts,
                            trace=ocr_readings, standalone=require_consensus,
                            integer_digits=integer_digits,
                            extra_attempts=regular_limit - regular_attempts,
                            stop_before_attempt=stop_before_extra_profile,
                            force_all_attempts=manual,
                            profiles=lighting_ocr_profiles(register),
                            defer_composition=digit_probe_enabled,
                        )
                        regular_status, _ = compare_sample(sample, ocr, comparison_decimals,
                                                           ocr_confirmed=ocr_confirmed, integer_digits=integer_digits)
                        same_frame = read_state["frame_reads"]
                        observed = same_frame[-1] if same_frame else ""
                        pattern = disputed_digit_pattern(same_frame, comparison_decimals, integer_digits)
                        near_hit = (digit_probe_enabled and regular_status != "match"
                                    and read_state["captured"] is not None and not sample.get("reference_is_fallback")
                                    and (pattern or not ocr_confirmed
                                         and missing_digit_pattern(observed, comparison_decimals, integer_digits))
                                    and not stop_ocr())
                        if near_hit and ocr_attempts + 2 <= MAX_OCR_ATTEMPTS:
                            layout = tuple(read_state[key] for key in (
                                "register", "integer_width", "whole_boxes", "fraction_boxes",
                            ))
                            budget = MAX_OCR_ATTEMPTS
                            digit_deadline = time.monotonic() + 5
                            if live_source:
                                digit_deadline = min(digit_deadline, live_deadline)

                            def report_digit(attempts, box=None, evidence=None):
                                if box is not None and pattern:
                                    position = pattern.index("?")
                                    candidate = {
                                        "position": position + (position < integer_digits), "box": box,
                                        "angle": rotation + base_adjustment, "evidence": evidence,
                                    }
                                    rank = {"accepted": 3, "agreement": 2, "disagreement": 1, "unclear": 0}
                                    ocr_candidates.append(candidate)
                                    ocr_candidates.sort(key=lambda entry: rank[entry["evidence"]], reverse=True)
                                    del ocr_candidates[3:]
                                set_activity("working", SINGLE_DIGIT_RECHECK, completed=ocr_attempts + attempts,
                                             total=budget, reading=observed, candidates=list(ocr_candidates))

                            if len(same_frame) == 1:
                                report_digit(0)
                                try:
                                    same_frame.append(read_visible_digits(
                                        *layout, options["helle_ziffern"], active_rules["polarity"],
                                        profile=OCR_PROFILES[1], whole_digits=integer_digits,
                                        fraction_digits=fraction_digits, prefer_boxes=bool(custom_boxes),
                                        deadline=digit_deadline,
                                    ))
                                except (OSError, subprocess.SubprocessError):
                                    pass
                                ocr_attempts += 1
                            pattern = (disputed_digit_pattern(same_frame, comparison_decimals, integer_digits)
                                       or single_missing_digit(observed, same_frame, comparison_decimals, integer_digits))
                            if pattern:
                                register_for_digit = layout[0]
                                polarity = active_rules["polarity"]

                                def read_shifted(box, profile):
                                    return read_digit(register_for_digit, box, lambda picture, digits: read_register(
                                        picture, options["helle_ziffern"] if polarity == "auto" else polarity == "light",
                                        digits, profile=profile, force_polarity=polarity != "auto", deadline=digit_deadline,
                                    ))

                                recovery, used = recover_single_digit(
                                    layout, pattern, observed, integer_digits, fraction_digits, read_shifted,
                                    budget - ocr_attempts, report_digit,
                                    lambda: stop_ocr() or time.monotonic() >= digit_deadline,
                                    lambda candidate: compare_sample(
                                        sample, candidate, comparison_decimals, integer_digits=integer_digits,
                                    )[0] in ("match", "ocr_only"),
                                )
                                ocr_attempts += used
                                ocr_limit = budget
                                if recovery:
                                    ocr, whole, fraction = recovery
                                    ocr_confirmed, ocr_readings = True, [ocr, ocr]
                                    ocr_method = "shifted"
                                    read_state.update(whole_boxes=whole, fraction_boxes=fraction)
                                    regular_status = compare_sample(
                                        sample, ocr, comparison_decimals, integer_digits=integer_digits,
                                    )[0]
                        if digit_probe_enabled and not ocr_confirmed:
                            # A moving meter can show different digits on separate photographs.
                            ocr_readings = same_frame
                            ocr, ocr_confirmed = resolve_ocr_readings(
                                ocr_readings, comparison_decimals, integer_digits, standalone=require_consensus,
                                standalone_composition=True,
                            )
                            if ocr_confirmed and ocr not in ocr_readings:
                                ocr_method = "composed"
                            regular_status = compare_sample(
                                sample, ocr, comparison_decimals, ocr_confirmed=ocr_confirmed, integer_digits=integer_digits,
                            )[0]
                        if local_enabled:
                            required = integer_digits + comparison_decimals
                            rows = [str(value).replace(".", "").replace(",", "")[:required] for value in ocr_readings]
                            weak = uncertain_slots(rows, required) if len(rows) >= 2 else []
                            if (regular_status not in ("difference", "ocr_unclear") or not 1 <= len(weak) <= 2
                                    or required - len(weak) < 3
                                    or comparison_decimals == 3 and weak == [required - 1]):
                                weak = []
                            local_key = geometry_check_key(active_rules, source_key)
                            issue = updated.setdefault("local_issue", {})
                            stamp = read_state["captured"] or sample_timestamp(sample, zone)
                            if read_state["captured"] is not None and note_local_issue(issue, local_key, stamp, weak):
                                options_iter = list(local_geometry_trials(custom_boxes or [], weak))
                                start = ((issue["count"] - 3) * 2) % len(options_iter)
                                variants = (options_iter[start:] + options_iter[:start])[:2]
                                with Image.open(io.BytesIO(read_state["picture"])) as original:
                                    for adjustment, trial_boxes in variants:
                                        if stop_ocr() or ocr_attempts + 2 > ocr_limit:
                                            break
                                        angle = rotation + base_adjustment + adjustment
                                        if not -180 <= angle <= 180:
                                            continue
                                        if adjustment:
                                            left, top, right, bottom = manual_crop
                                            width = min(manual_width, rotated_width(
                                                right - left, bottom - top, angle))
                                        else:
                                            width = manual_width
                                        trial = select_register(
                                            original, None, manual_crop, width, angle,
                                            integer_digits, fraction_digits, digit_boxes=trial_boxes,
                                        )
                                        set_activity("working", "Nachprüfung: Dieselben Ziffern waren wiederholt unklar.",
                                                     completed=ocr_attempts, total=ocr_limit,
                                                     reading=ocr_readings[-1] if ocr_readings else None)
                                        values = [read_layout(trial, profile) for profile in OCR_PROFILES[:2]]
                                        ocr_attempts += len(values)
                                        prefix = meter_prefix(values[0], comparison_decimals, integer_digits)
                                        if prefix is None or prefix != meter_prefix(values[1], comparison_decimals, integer_digits):
                                            continue
                                        digits = str(prefix).zfill(required)
                                        if any(row[index] != digits[index] for index in range(required)
                                               if index not in weak for row in rows):
                                            continue
                                        if compare_sample(sample, values[0], comparison_decimals,
                                                          integer_digits=integer_digits)[0] not in ("match", "ocr_only"):
                                            continue
                                        ocr, ocr_confirmed, ocr_readings = values[0], True, values
                                        ocr_method = None
                                        reg, width, whole, fractions, kind = trial
                                        read_state.update(register=reg, integer_width=width, whole_boxes=whole,
                                                          fraction_boxes=fractions, source=kind)
                                        rotation_adjustment = base_adjustment + adjustment
                                        local_trial = (local_key, [rotation + rotation_adjustment, trial_boxes], prefix)
                                        break
                        if reserve_for_rotation and regular_status in ("difference", "ocr_unclear") and not stop_ocr():
                            with Image.open(io.BytesIO(read_state["picture"])) as original:
                                for delta in INTENSIVE_ROTATIONS:
                                    if stop_ocr() or ocr_attempts + 2 > ocr_limit:
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
                                                     completed=ocr_attempts + attempts, total=ocr_limit,
                                                     reading=(tilted_readings or ocr_readings or [None])[-1])

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
                                        ocr_method = "composed" if ocr not in tilted_readings else None
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
                        image_id = read_state["image_id"]
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
                                setup_reference = standalone_calibration_reference(
                                    active_rules, active_source, source_key, captured, previous_consumption,
                                ) if standalone else None
                                if setup_reference and setup_reference.get("image_id") == image_id:
                                    setup_reference = None
                                if setup_reference:
                                    setup_counter = setup_reference["counter"]
                                    accumulate_consumption(
                                        setup_counter, source_key, captured, ocr, decimals,
                                        active_rules["max_flow_lph"], integer_digits,
                                    )
                                    if previous_consumption.get("source") != source_key:
                                        previous_consumption = setup_counter
                                new_consumption = accumulate_consumption(
                                    previous_consumption, source_key, captured,
                                    sample["actual_value"] if accept_reference else ocr, decimals,
                                    active_rules["max_flow_lph"], integer_digits,
                                )
                                if setup_reference:
                                    standalone_reference = setup_reference
                                    updated.pop("standalone_candidate", None)
                                elif standalone:
                                    candidate = updated.get("standalone_candidate")
                                    if (candidate and candidate.get("crop") == (rotation_key or custom_boxes)
                                            and candidate.get("image_id") not in (None, image_id)
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
                                            "rotation_adjustment": rotation_adjustment, "image_id": image_id,
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
                    updated["ocr_candidates"] = ocr_candidates
                    updated["ocr_method"] = ocr_method if automatic_preview_ready else None
                    if standalone and outcome == "ocr_only":
                        if standalone_reference is None:
                            outcome = updated["status"] = STANDALONE_PENDING
                            updated["check_detail"] = STANDALONE_PENDING_NOTICE
                        else:
                            updated["check_detail"] = STANDALONE_VERIFIED_NOTICE
                    if new_consumption is not None and not raw_fallback:
                        updated["consumption"] = new_consumption
                        updated["consumption_statistics"] = record_consumption_sample(
                            history.get("consumption_statistics", {}), setup_source_id(active_source), new_consumption,
                        )
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
                    if (not optimization_paused and not stationary_partial and not local_enabled
                            and rotation_key is not None and not raw_fallback
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
                    setup_source = setup_source_id(active_source)
                    if (active_rules["reflection_estimate_enabled"] and mode != "slfork" and not raw_fallback
                            and outcome == "ocr_unclear" and not validation_detail and not ocr_error):
                        pattern = single_missing_digit(ocr, ocr_readings, decimals, integer_digits)
                        if pattern:
                            reflection_recheck = (setup_source, pattern, ocr, image_time,
                                                  integer_digits, fraction_digits)
                    if outcome in SUCCESSFUL_CHECKS or not active_rules["reflection_estimate_enabled"]:
                        updated.pop("reflection_rechecks", None)
                    verified = outcome == "match" or standalone_reference is not None and outcome == "ocr_only"
                    exhausted_ocr = (outcome == "ocr_unclear" and not ocr_confirmed and not validation_detail
                                     and not ocr_error and ocr_attempts > 0 and not raw_fallback)
                    if (verified and not raw_fallback and not stabilizing_until
                            and active_rules.get("setup_pending_source") == setup_source):
                        whole, _, fraction = ocr.replace(",", ".").partition(".")
                        reading = f"{whole}.{fraction[:decimals]}" if decimals else whole
                        with settings_lock:
                            if get_auto_rules() == active_rules and get_source()[0] == active_source:
                                try:
                                    started = active_rules.get("setup_pending_started")
                                    finished = now.timestamp()
                                    duration = (round(finished - started) if type(started) in (int, float)
                                                and 0 < started <= finished else None)
                                    metrics = active_rules.get("setup_pending_metrics")
                                    if not isinstance(metrics, dict):
                                        metrics = {}
                                    save_auto_rules({
                                        **active_rules,
                                        "setup_completed": {
                                            "source": setup_source, "time": finished, "duration_seconds": duration,
                                            "frames_tested": metrics.get("frames_tested"),
                                            "images_checked": metrics.get("images_checked"),
                                        },
                                        "setup_pending_source": None, "setup_pending_started": None,
                                        "setup_pending_metrics": None,
                                        "calibration_reference": {
                                            "reading": reading, "time": image_time, "precision": decimals,
                                            "source": setup_source, "integer_digits": integer_digits,
                                            "image_id": image_id,
                                        },
                                    }, request_check=False)
                                except OSError:
                                    print("Abschluss der Einrichtung konnte nicht gespeichert werden.")
                                else:
                                    setup_finished_in_check = True
                                    stabilizing_until, _ = setup_deadlines(get_auto_rules(), active_source)
                                    interval_minutes = stabilization_interval(interval_minutes, stabilizing_until, now.timestamp())
                                    optimization_paused = True
                    if (verified and not stationary_partial and source == "manual" and active_rules["crop_mode"] == "manual"
                            and not rotation_adjustment and not raw_fallback):
                        with settings_lock:
                            if get_auto_rules() == active_rules and get_source()[0] == active_source:
                                remember_known_good_layout(active_rules, active_source,
                                                           geometry_layout(active_rules, active_rules))
                    if adaptive and not optimization_paused and outcome == "match" and not raw_fallback:
                        flow = updated.setdefault("adaptive_flow", {})
                        reference_value = sample["actual_value"]
                        if compare_sample(sample, reference_value, fraction_digits, integer_digits=integer_digits)[0] == "match":
                            observe_flow(flow, source_key, image_time, reference_value, fraction_digits,
                                         integer_digits, now.month, active_rules["max_flow_lph"])
                        interval_minutes = suggested_interval(
                            automatic_interval_minutes(active_rules["interval_minutes"], mode), flow, source_key, now.month,
                        )
                    local_backup = updated.get("local_geometry_backup", {})
                    if (not optimization_paused and active_rules["fine_alignment_enabled"]
                            and local_backup.get("revision") == active_rules["crop_revision"]
                            and local_backup.get("source") == source_key and not raw_fallback):
                        if verified and local_trial is None:
                            local_backup["failures"] = 0
                        elif outcome in ("ocr_unclear", "difference") and not validation_detail and not ocr_error:
                            local_backup["failures"] = local_backup.get("failures", 0) + 1
                            if local_backup["failures"] >= 2:
                                fine_rotation = local_backup["rotation"]
                                fine_update = local_backup["digit_boxes"]
                                restoring_local = True
                    if (not optimization_paused and not raw_fallback and local_trial is not None and verified
                            and fine_update is None):
                        trial_key, geometry, prefix = local_trial
                        learning = updated.setdefault("local_improvement", {})
                        if note_local_improvement(learning, trial_key, image_time, geometry, prefix):
                            fine_rotation, fine_update = geometry
                    elif (fine_update is None and not optimization_paused
                          and active_rules["fine_alignment_enabled"] and not raw_fallback):
                        learning = updated.setdefault("fine_alignment", {})
                        key = [source_key, active_rules["crop"], active_rules["rotation"], active_rules["width"],
                               integer_digits, fraction_digits, active_rules["polarity"]]
                        failed = outcome in ("ocr_unclear", "difference")
                        if failed or verified:
                            fine_update = alignment_rollback(learning, key, active_rules["digit_boxes"], failed)
                    if not raw_fallback and not optimization_paused:
                        geometry_key = geometry_check_key(active_rules, source_key)
                        recovery = updated.setdefault("geometry_recovery", {})
                        geometry_warning = observe_geometry_failures(
                            recovery, geometry_key, image_time, outcome,
                            reading_problem=(not validation_detail and not ocr_error and ocr_attempts > 0
                                             and not updated.get("last_digit_failures")),
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
                unlock_automatic = (not ready_for_automatic(active_rules, active_source)
                                    and active_source.get("selected") and active_source == get_source()[0]
                                    and (decoded_test_image or manual_options.get("manual_reference")))
                if unlock_automatic:
                    next_history["manual_setup_source"] = setup_source_id(active_source)
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
                if unlock_automatic:
                    request_automatic_check()
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
        if keep_schedule and not cached_standalone and data is None and history.get("next_check_at", 0) > now.timestamp():
            continue
        updated["slfork_diagnostics"] = diagnostics
        if (not duplicate_cycle and not cached_standalone
                and updated.pop("setup_first_check_revision", None) == active_rules["crop_revision"]):
            updated["setup_first_check_unclear"] = outcome not in (*SUCCESSFUL_CHECKS, STANDALONE_PENDING)
            if updated["setup_first_check_unclear"]:
                updated.pop("failure_attempts", None)
                updated.pop("failure_since", None)
                updated.pop("retry_suppressed", None)
        else:
            if not cached_standalone and not duplicate_cycle:
                updated.pop("setup_first_check_unclear", None)
        if cached_standalone:
            updated["check_status"] = STANDALONE_PENDING
            defer_duplicate_cycle(updated, now.timestamp(), interval_minutes)
            updated["next_check_at"] = now.timestamp() + STANDALONE_CACHED_CAPTURE_DELAY
        elif duplicate_cycle:
            defer_duplicate_cycle(updated, now.timestamp(), interval_minutes)
        else:
            updated.pop("reflection_retry_at", None)
            updated.pop("fresh_ocr_retry_at", None)
            schedule_next_check(updated, outcome, now.timestamp(), interval_minutes)
            if outcome != STANDALONE_PENDING and not setup_finished_in_check:
                updated["automatic_completed_at"] = now.timestamp()
            if updated.get("setup_first_check_unclear") and mode != "slfork":
                updated["next_check_at"] = now.timestamp() + 15
            if (exhausted_ocr and mode != "slfork" and updated.get("failure_attempts", 0) == 1
                    and not history.get("fresh_ocr_retry_at")):
                deadline = now.timestamp() + 15
                if deadline < updated["next_check_at"]:
                    updated["next_check_at"] = updated["fresh_ocr_retry_at"] = deadline
            if reflection_recheck is not None:
                delay = plan_reflection_recheck(
                    updated, *reflection_recheck, updated["next_check_at"] - now.timestamp(),
                )
                if delay is not None:
                    updated["next_check_at"] = updated["reflection_retry_at"] = now.timestamp() + delay
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
                        revision = str(time.time_ns())
                        values = {**active_rules, "digit_boxes": fine_update, "crop_revision": revision}
                        if fine_rotation is not None:
                            values["rotation"] = fine_rotation
                            left, top, right, bottom = crop_coordinates(
                                active_rules["crop"], active_rules["width"], active_rules["rotation"])
                            values["width"] = min(active_rules["width"],
                                                  rotated_width(right - left, bottom - top, fine_rotation))
                        if stationary_partial:
                            values["stationary_partial_scope"] = setup_source_id([active_source, revision])
                        save_auto_rules(values, request_check=False)
                        if restoring_local:
                            updated.pop("local_geometry_backup", None)
                        elif fine_rotation is not None:
                            updated["local_geometry_backup"] = {
                                "revision": revision, "source": source_key, "rotation": active_rules["rotation"],
                                "digit_boxes": active_rules["digit_boxes"], "failures": 0,
                            }
                        if fine_rotation is not None:
                            atomic_write(HISTORY, json.dumps(updated).encode("utf-8"), 0o600)
                    except (OSError, ValueError):
                        print("Feinjustierung konnte nicht gespeichert werden.")
        set_activity("waiting", FRESH_OCR_NOTICE if updated.get("fresh_ocr_retry_at") else
                     REFLECTION_RECHECK_NOTICE if updated.get("reflection_retry_at") else
                     "Warte auf einen neuen Messzyklus vom ESP …" if duplicate_cycle else
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
                        repair_started = bool(control_calibration("repair", GEOMETRY_REPAIR_LIMIT))
                    except (OSError, ValueError) as error:
                        print(f"Automatische Nachjustierung nicht gestartet: {type(error).__name__}")
        if geometry_warning and reminder.enabled:
            message = ("Nach zwei Stunden mit anhaltenden Fehlmessungen sucht die App einmal nach einem besseren Ziffernrahmen. "
                       "Die bisherigen Einstellungen sind gesichert. Das Ergebnis steht in der App."
                       if repair_started else "Die Ziffernerkennung ist seit mindestens zwei Stunden gestört. "
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
