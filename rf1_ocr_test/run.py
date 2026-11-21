"""Bridge the latest matched SLFork picture and reading to Home Assistant."""

import base64
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from email.parser import BytesHeaderParser
from functools import partial
import hashlib
import io
from itertools import chain
import json
import os
from pathlib import Path
import re
from statistics import median
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
    STANDALONE_CACHED_CAPTURE_DELAY, MAX_OCR_ATTEMPTS, DEFAULT_FAILURE_PAUSE_MINUTES, MAX_FAILURE_PAUSE_MINUTES, MIN_FAILURE_PAUSE_MINUTES, SHIFTED_DIGIT_POSITIONS, ROW_SHIFT_READS, ROW_SHIFT_TRIALS, plausible_integer_digits, note_skew, skew_offset, SHIFTED_DIGIT_READS, missing_digit_pattern, single_missing_digit, disputed_digit_pattern, resolve_ocr_readings,
    compare_sample, crop_register, lighting_ocr_profiles, read_register, read_with_retries, record_sample,
    anchored_leading_digits, anchored_hidden_digits, within_anchor_bounds, anchor_bounds,
    learned_flow_limit, slow_roller_digit,
    automatic_interval_minutes, defer_duplicate_cycle,
    LAST_DIGIT_NOTICE, LAST_DIGIT_PASS, LAST_DIGIT_RETRIES, SUCCESSFUL_CHECKS,
    SEVENTH_DIGIT_WAIT_NOTICE,
    differs_only_at_last_digit, last_digit_can_pass, explain_uncertain_positions,
    meter_prefix, common_exact_precision, manual_confirms_failed_auto,
    reschedule_next_check, rolling_summary, sample_epoch, sample_timestamp, schedule_next_check, slfork_reference,
    timestamp_epoch, track_reflection, system_idle,
    resume_optional_eighth_digit, relocate_last_digit_due, EIGHTH_DIGIT_RETRY_SECONDS,
    setup_deadlines, setup_source_id, stabilization_interval, stationary_partial_active, valid_interval_minutes,
)
from calibration import (Calibration, Layout, CAPTURE_INTERVAL, PERFECT_CONFIRMATION_INTERVAL, DEFAULT_LIMIT, MIN_IMAGES, MIN_IMAGE_LIMIT, MAX_IMAGES, MAX_ATTEMPTS,
                         DEFAULT_INTENSIVE_AGREEMENT, SHORTLIST_LIMIT, TIME_LIMIT, LAST_DIGIT_CAPTURE_INTERVAL,
                         image_quality_hints, two_decimal_reading, uncertain_slots, valid_intensive_agreement)
from consumption import (DEFAULT_FLOW_LPH, LOWER_READING, LOWER_PENDING, LOWER_RECOVERED, MAX_FLOW_LPH,
                         CALORIFIC_RANGE, CONVERSION_RANGE, STATE_FACTOR_RANGE, ImplausibleReading, energy_kwh, plausible_lower_drop, track_lower_series,
                         valid_energy_factor,
                         accumulate_consumption, fallback_detail, format_cubic_metres, record_consumption_sample)
from checks import (without_light, unclear_trailing_decimals, setup_tilt, initial_skew_state, FRAME_OFF_NOTICE, FRAME_OFF_STREAK, FRAME_OFF_WAIT_NOTICE, MOVING_DIGIT_NOTICE,
                    REDUCED_PRECISION_NOTICE, REDUCED_PRECISION2_NOTICE, MOVING_DIGITS_NOTICE, only_last_compared_unclear)
import debug_log
import experiments
import glyph_match
from layout import (MANUAL_ROW_UNCLEAR, PARTLY_UNCLEAR, RAW_ROW_UNCLEAR, digit_row_tilt, fine_rotation as valid_fine_rotation, crop_coordinates, find_digit_row,
                    digit_box_settings, find_raw_digit_row, normalize_digit_boxes, glyph_clipped, glare_slots, roll_center, rotated_width, scale_digit_boxes, turn_crop)
import digit_library
import optimizer
from meter_learning import (GEOMETRY_REPAIR_LIMIT, GEOMETRY_REPAIR_SECONDS, alignment_rollback, observe_flow,
                            observe_geometry_failures, local_geometry_trials, note_local_issue, note_local_improvement,
                            plan_reflection_recheck, REFLECTION_RECHECK_NOTICE, suggested_interval)
from reminder import Reminder
from notification_settings import (DEFAULT_DELIVERY_HOURS, DEFAULT_REVIEW_MINUTES, PUSH_SERVICE,
                                   notification_rules)
from settings import DEFAULTS, SCHEMA_VERSION, load_options
from auto_rules import changed_rules, default_rules, stored_rules, valid_experiments
from source_settings import (LIGHT, CAMERA, DISCOVERY_TEMPLATE, ESP_ADDRESS_MODES, REFERENCE,
                             discovered_sources, source_check_key, source_rules)
from panel import start_panel
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
ENERGY_ENTITY = f"sensor.{NAMESPACE}_verbrauch_gesamt_kwh"
MAX_IMAGE_PIXELS = 4_000_000
LIVE_CAPTURE_WINDOW_SECONDS = 20
LIVE_CAPTURE_MAX_ATTEMPTS = 10
# Frame nudging re-reads the image already taken, so the capture window above does not apply.
DIGIT_RECOVERY_SECONDS = 25
INTENSIVE_ROTATIONS = (-6, 6)
MAX_LEARNED_ROTATION = 18
FRESH_OCR_NOTICE = "Der Zählerstand konnte nicht bestätigt werden. Ein frisches Kamerabild folgt in Kürze."
OPTIMIZER_STATUS = "Automatik-Nachprüfung: {trial} ({done} von {total}, wird beim nächsten Bild fortgesetzt)."
SINGLE_DIGIT_RECHECK = "Automatik-Nachprüfung: Die App prüft die fehlende Ziffer mit leicht verschobenem Rahmen."
INTENSIVE_ROTATION_STATUS = "Intensivtest: Die App prüft das Bild leicht gedreht."


def learnable_shift(enabled, key, rotation, boxes, size, prefix):
    """Candidate for the local learning from frames that rescued a check, or None."""
    if not enabled or prefix is None or not boxes:
        return None
    try:
        relative = digit_box_settings([list(box) for box in normalize_digit_boxes(boxes, size)], len(boxes))
    except ValueError:
        return None
    return key, [rotation, [list(box) for box in relative]], prefix


SETUP_READ_LOG_LIMIT = 24


def setup_round_log(attempt, round_log, started, now):
    """Count one setup capture round; return a debug entry once a new image was evaluated."""
    stats = attempt.image_stats
    stats["requests"] = stats.get("requests", 0) + 1
    fetch_seconds = round_log.get("fetch_seconds")
    if fetch_seconds is not None:
        stats["fetch_seconds"] = stats.get("fetch_seconds", 0.0) + fetch_seconds
    if round_log.get("error"):
        errors = stats.setdefault("errors", {})
        errors[round_log["error"]] = errors.get(round_log["error"], 0) + 1
    accepted = round_log.get("accepted_at")
    if accepted is None:
        if round_log.get("captured") and not round_log.get("error"):
            # The camera answered, but the picture was identical or not newer.
            stats["discarded"] = stats.get("discarded", 0) + 1
        return []
    entry = {
        "kind": "setup_image",
        "purpose": attempt.purpose or ("background" if attempt.background else "setup"),
        "requests": stats.get("requests", 0),
        "discarded": stats.get("discarded", 0),
        "errors": stats.get("errors") or None,
        "fetch_s": round(stats.get("fetch_seconds", 0.0), 1),
        "eval_s": round(now - accepted, 1),
        "round_s": round(now - started, 1),
        "images": len(attempt.seen),
        "confirmations": attempt.confirmations,
        "partial_hits": attempt.partial_hits,
        "attempts": attempt.attempts,
        "simplified": attempt.simplified,
        "reads": round_log.get("reads") or None,
    }
    attempt.image_stats = {}
    return [entry]


def setup_end_log(attempt, now):
    return {"kind": "setup_end", "state": attempt.state, "images": len(attempt.seen),
            "confirmations": attempt.confirmations, "attempts": attempt.attempts,
            "minutes": round((now - attempt.started) / 60, 1),
            "purpose": attempt.purpose or ("background" if attempt.background else "setup")}


def write_setup_log(entries):
    for entry in entries:
        debug_log.record(**entry)


def failed_angle_requires_fresh_image(trials, outcome):
    """Retry on a fresh image if tested angle variants still give an uncertain or wrong reading."""
    return trials > 0 and outcome in ("ocr_unclear", "difference")

SLFORK_RAW_SOURCE = "slfork_raw"
SLFORK_RAW_NOTICE = "Aufbereitetes ESP-Bild fehlt oder ist zu alt. Die App prüft ein frisches Rohbild."
SLFORK_RAW_SUCCESS = "Rohbild gelesen. Das aufbereitete ESP-Bild war nicht nutzbar – prüfe in AI on the Edge die Bildausrichtung und die Referenzmarken."
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
        suggestions = discovered_sources(data)
        if suggestions:
            return suggestions
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


LIGHT_DELAY = 1.5


def post_json(url, token, payload, timeout=8):
    request = Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with open_core(request, timeout=timeout) as response:
        return response.read(MAX_RESPONSE_BYTES)


# Median brightness of recent pictures taken with the capture light, per light (adaptive,
# in memory). A picture far darker than that was taken without (or with a fading) light.
LIT_BRIGHTNESS = {}
DARK_PICTURE_RATIO = 0.75


def picture_brightness(picture):
    """Median grey value of a small copy of the picture, or None if it cannot be decoded."""
    try:
        with Image.open(io.BytesIO(picture)) as image:
            histogram = image.convert("L").resize((80, 60)).histogram()
        seen = 0
        for value, count in enumerate(histogram):
            seen += count
            if seen * 2 > 80 * 60:
                return value
        return None
    except (OSError, ValueError, TypeError, Image.DecompressionBombError):
        return None


def dark_picture(light, brightness):
    reference = LIT_BRIGHTNESS.get(light)
    return brightness is not None and reference is not None and brightness < reference * DARK_PICTURE_RATIO


def remember_lit_brightness(light, brightness):
    if brightness is None:
        return
    reference = LIT_BRIGHTNESS.get(light)
    LIT_BRIGHTNESS[light] = brightness if reference is None else 0.8 * reference + 0.2 * brightness


GAIN_ADJUST_SECONDS = 5 * 60
GAIN_ADJUST_MAX_STEP = 8
GAIN_ADJUST_CEILING = 20
GAIN_ADJUSTED = {}
GAIN_ENTITY = re.compile(r"number\.[a-z0-9_]+")


def raise_camera_gain(light, brightness, token, *, fetch, post, now=time.monotonic):
    """Pictures stay dark even with the light on: raise the camera's gain a little (ESPHome).

    The gain control is a number entity on the same Home Assistant device as the light
    (e.g. number.esp_gaszaehler_verstarkung). Steps are small, bounded and at most every
    few minutes, so a manual setting is corrected gently, never overshot. Returns the new
    value or None.
    """
    expected = LIT_BRIGHTNESS.get(light)
    if not light or not brightness or not expected:
        return None
    last = GAIN_ADJUSTED.get(light)
    if last is not None and now() - last < GAIN_ADJUST_SECONDS:
        return None
    GAIN_ADJUSTED[light] = now()
    base = "http://supervisor/core/api"
    template = ("{%% set d = device_id('%s') %%}{{ (device_entities(d) if d else []) "
                "| select('match', '^number\\..*(verst|gain)') | list | first | default('') }}" % light)
    try:
        answer = post(f"{base}/template", token, {"template": template})
        entity = (answer.decode("utf-8") if isinstance(answer, bytes) else str(answer or "")).strip()
        if not GAIN_ENTITY.fullmatch(entity):
            return None
        state = json.loads(fetch(f"{base}/states/{entity}", token, timeout=4))
        current = float(state["state"])
        attributes = state.get("attributes") or {}
        ceiling = min(float(attributes.get("max", GAIN_ADJUST_CEILING)), GAIN_ADJUST_CEILING)
        if current >= ceiling:
            return None
        wanted = current * expected / max(brightness, 1)
        target = min(ceiling, current + GAIN_ADJUST_MAX_STEP, max(current + 1, round(wanted)))
        post(f"{base}/services/number/set_value", token, {"entity_id": entity, "value": target})
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeDecodeError) as error:
        print(f"Verstärkung der Kamera konnte nicht angepasst werden: {type(error).__name__}")
        return None
    print(f"Bilder bleiben trotz Licht dunkel – Verstärkung {current:g} -> {target:g}")
    debug_log.record(kind="exposure_adjust", entity=entity, old=current, new=target,
                     brightness=brightness, expected=round(expected))
    return target


def lit_picture(light, take, token, *, fetch, post, delay=LIGHT_DELAY, sleep=time.sleep):
    """Switch a Home Assistant light on for one picture, like AI on the Edge's flash.

    A light that was already on is left on; a light the app switched on is always
    switched off again, also when taking the picture fails.
    """
    if not light:
        return take()
    base = "http://supervisor/core/api"
    try:
        already_on = json.loads(fetch(f"{base}/states/{light}", token, timeout=4)).get("state") == "on"
    except (OSError, ValueError, TypeError, AttributeError):
        already_on = False
    switched = False
    try:
        if not already_on:
            try:
                post(f"{base}/services/light/turn_on", token, {"entity_id": light})
                switched = True
                sleep(delay)
            except OSError as error:
                print(f"Licht für die Aufnahme konnte nicht eingeschaltet werden: {type(error).__name__}")
        picture = take()
        brightness = picture_brightness(picture)
        if dark_picture(light, brightness):
            # Light not (yet) on, or switched off externally just before the picture
            # (e.g. by a "keep the flash on" switch on the ESP): switch on, wait, take again.
            debug_log.record(kind="dark_picture", brightness=brightness,
                             expected=round(LIT_BRIGHTNESS.get(light, 0)), already_on=already_on)
            print("Bild ohne Licht erkannt – Licht an und neues Bild.")
            try:
                if already_on and not switched:
                    try:
                        still_on = json.loads(fetch(f"{base}/states/{light}", token, timeout=4)).get("state") == "on"
                    except (OSError, ValueError, TypeError, AttributeError):
                        still_on = True
                    # Switched off by someone else in the meantime: now the app owns it.
                    switched = not still_on
                post(f"{base}/services/light/turn_on", token, {"entity_id": light})
                switched = switched or not already_on
                sleep(delay)
                retry = take()
                retry_brightness = picture_brightness(retry)
                if retry_brightness is not None and (brightness is None or retry_brightness > brightness):
                    picture, brightness = retry, retry_brightness
                if dark_picture(light, brightness):
                    # The ESP may still be busy switching: one more, longer wait before giving up.
                    sleep(2 * delay)
                    retry = take()
                    retry_brightness = picture_brightness(retry)
                    if retry_brightness is not None and (brightness is None or retry_brightness > brightness):
                        picture, brightness = retry, retry_brightness
                if dark_picture(light, brightness):
                    # Still dark with the light on: the camera itself is set too dark.
                    raise_camera_gain(light, brightness, token, fetch=fetch, post=post)
            except OSError as error:
                print(f"Neues Bild mit Licht nicht möglich: {type(error).__name__}")
        if not dark_picture(light, brightness):
            remember_lit_brightness(light, brightness)
        return picture
    finally:
        if switched:
            switch_light_off(light, token, fetch=fetch, post=post, sleep=sleep)


LIGHT_OFF_ATTEMPTS = 4


def switch_light_off(light, token, *, fetch, post, sleep=time.sleep):
    """Switch the capture light off and make sure it stays off.

    A busy camera ESP may miss or delay a command, so the state is read back and the
    command repeated a few times instead of leaving the LED on.
    """
    base = "http://supervisor/core/api"
    for attempt in range(LIGHT_OFF_ATTEMPTS):
        try:
            post(f"{base}/services/light/turn_off", token, {"entity_id": light})
        except OSError as error:
            print(f"Licht für die Aufnahme konnte nicht ausgeschaltet werden: {type(error).__name__}")
        sleep(1 + attempt)
        try:
            if json.loads(fetch(f"{base}/states/{light}", token, timeout=4)).get("state") == "off":
                return True
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    print("Licht für die Aufnahme meldet nach mehreren Versuchen nicht „aus“.")
    return False


CAMERA_LIGHT_CACHE = {}
CAMERA_LIGHT_SECONDS = 10 * 60


def camera_light(camera, token, *, post=None, now=time.monotonic):
    """The light that belongs to the same Home Assistant device as the camera (its own flash LED).

    Looked up through the device registry by template and cached for a few minutes.
    Returns "" when the camera has no light of its own.
    """
    cached = CAMERA_LIGHT_CACHE.get(camera)
    if cached and now() - cached[1] < CAMERA_LIGHT_SECONDS:
        return cached[0]
    template = ("{%% set d = device_id('%s') %%}{{ (device_entities(d) if d else []) "
                "| select('match', '^light\\.') | list | first | default('') }}" % camera)
    light = ""
    try:
        answer = (post or post_json)("http://supervisor/core/api/template", token, {"template": template})
        value = (answer.decode("utf-8") if isinstance(answer, bytes) else str(answer or "")).strip()
        light = value if LIGHT.fullmatch(value) else ""
    except (OSError, ValueError, UnicodeDecodeError) as error:
        print(f"Licht der Kamera konnte nicht ermittelt werden: {type(error).__name__}")
        return cached[0] if cached else ""
    CAMERA_LIGHT_CACHE[camera] = (light, now())
    return light


def capture_light(source, camera, token, *, post=None):
    """External light if one is set, otherwise the camera's own light unless switched off."""
    external = (source or {}).get("light") or ""
    if external:
        return external
    if (source or {}).get("camera_light", True) is False or not camera:
        return ""
    return camera_light(camera, token, post=post)


def capture_camera(camera, reference, token, zone, timeout=8, *, fetch=None, light="", post=None):
    fetch = fetch or get_bytes
    base = "http://supervisor/core/api"
    picture = lit_picture(light, lambda: fetch(f"{base}/camera_proxy/{camera}", token, timeout=timeout), token,
                          fetch=fetch, post=post or post_json)
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


def hidden_reflection_slots(rules, source):
    """Slots permanently hidden by a reflection (marked by the user or found by the setup)."""
    marked = rules.get("setup_reflection")
    if (not rules.get("reflection_estimate_enabled") or not isinstance(marked, dict)
            or marked.get("source") != setup_source_id(source)):
        return []
    positions = marked.get("positions")
    if not isinstance(positions, list) or not all(type(slot) is int and slot >= 0 for slot in positions):
        return []
    return positions[:2]


def manual_reading_anchor(rules, zone):
    """The reading entered by hand (fallback value with time) as an anchor, if any."""
    value, stamp = str(rules.get("fallback_value") or ""), rules.get("fallback_time")
    match = re.fullmatch(r"([0-9]{1,9})(?:[.,]([0-9]{1,3}))?", value)
    if not match or not stamp:
        return None
    try:
        return {"time": timestamp_epoch(stamp, zone),
                "value": int(match[1]) * 1000 + int((match[2] or "").ljust(3, "0"))}
    except (TypeError, ValueError):
        return None


def newest_anchor(first, second, before):
    candidates = [item for item in (first, second)
                  if isinstance(item, dict) and type(item.get("time")) in (int, float) and item["time"] < before]
    return max(candidates, key=lambda item: item["time"], default=None)


def shadow_experiments(rules, manual, register, boxes, stable, light, forced):
    """Read the same register with each ticked experiment, only with spare CPU capacity."""
    names = experiments.enabled_experiments(rules)
    if not names or manual or register is None or len(boxes) < 3:
        return None
    load = experiments.host_load()
    if not system_idle():
        return {"skipped": "busy", "load": load}
    record = {"stable": stable, "load": load}

    def read_box(image, box):
        return read_digit(image, box, lambda picture, digits: read_register(
            picture, light, digits, profile=OCR_PROFILES[0], force_polarity=forced, isolated_digit=True))

    for name in names:
        try:
            if name == "perspective":
                record[name] = experiments.shadow_perspective(register, boxes, read_box)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            record[name] = {"error": type(error).__name__}
    return record


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


TEMPLATE_VETO_GAP = .02


def template_veto(register, box, digit, polarity, light_digits):
    """True when the digit templates clearly prefer another digit than the one Tesseract agreed on.

    Blurred 6 and 5 look alike for Tesseract; on the meter both profiles read a clear 6 as 5
    (20.11.), while the templates still ranked the 6 first. Such a frame is not trusted.
    """
    scores = glyph_scores(register, box, polarity, light_digits)
    if not scores or digit not in scores:
        return False
    best = glyph_match.ranked(scores)[0]
    if best == digit or {best, digit} in glyph_match.CONFUSABLE:
        # The templates themselves mix up 1 and 7 on this meter; they cannot veto there.
        return False
    return scores[best] - scores[digit] >= TEMPLATE_VETO_GAP


def single_digit_frames(boxes, index, size, *, last_roller=False):
    normalized = list(map(list, normalize_digit_boxes(boxes, size)))
    left, top, right, bottom = boxes[index]
    if last_roller and top == 0 and bottom == size[1]:
        # Full-height frames cannot move vertically. Try exposing more of either half of the wheel.
        margin = max(1, (bottom - top) // 14)
        yield left, top, right, bottom - margin
        yield left, top + margin, right, bottom
    # The last roller only turns; moving its frame sideways shows half a digit (a cut-off 9
    # reads as 4). It is centred on the roller beforehand and only moved up and down here.
    axes = (1,) if last_roller else (0,)
    for angle, shifted in local_geometry_trials(normalized, [index], axes=axes):
        if angle:
            break
        dx, dy = (round((moved - old) * length / 1000)
                  for moved, old, length in zip(shifted[index][:2], normalized[index][:2], size))
        dx = max(-left, min(dx, size[0] - right))
        dy = max(-top, min(dy, size[1] - bottom))
        yield left + dx, top + dy, right + dx, bottom + dy
    if not last_roller:
        # Then wider steps up to a quarter of the frame: on a slanted camera the frames of the
        # decimal rollers can sit that far beside the glyph (red border inside, digit cut off).
        width = right - left
        for fraction in (9, 6, 4):
            step = max(2, width // fraction)
            for dx in (-step, step):
                dx = max(-left, min(dx, size[0] - right))
                if dx:
                    yield left + dx, top, right + dx, bottom


def recover_single_digit(layout, pattern, current, whole_digits, fraction_digits, read, available, report, stop, accept,
                         veto=None):
    """Probe each missing slot on this register with nudged frames and two agreeing OCR profiles.

    Only the unclear positions are re-read; every other digit stays as read. All slots have to
    be filled, and the completed value still has to pass ``accept`` (reference, flow and
    previous reading), otherwise nothing changes.
    """
    register, width, whole_boxes, fraction_boxes = layout
    whole = whole_boxes or approximate_whole_boxes(width, register.height, whole_digits)
    boxes = [*whole, *fraction_boxes]
    if len(boxes) != whole_digits + fraction_digits:
        return None, 0
    attempted = 0
    filled = pattern
    moved = boxes.copy()
    positions = [position for position, char in enumerate(pattern) if char == "?"]
    for number, position in enumerate(positions):
        index = position - (position > whole_digits)
        seen = {boxes[index]}
        last_roller = fraction_digits > 0 and index == len(boxes) - 1
        final = number == len(positions) - 1
        found = False
        search = boxes
        if last_roller:
            centre = roll_center(register, boxes)
            left, top, right, bottom = boxes[index]
            if centre is not None and abs(centre - (left + right) / 2) > (right - left) / 8:
                dx = round(centre - (left + right) / 2)
                dx = max(-left, min(dx, register.width - right))
                search = [*boxes[:index], (left + dx, top, right + dx, bottom), *boxes[index + 1:]]
        frames = single_digit_frames(search, index, register.size, last_roller=last_roller)
        if search is not boxes:
            frames = chain([search[index]], frames)
        for box in frames:
            if attempted + 2 > available or stop():
                return None, attempted
            if box in seen or box[2] - box[0] < 8 or box[3] - box[1] < 12:
                continue
            seen.add(box)
            if glyph_clipped(register, box):
                # Part of a digit only: never read it, it would look like another digit.
                report(attempted, box, "unclear", position=position)
                continue
            report(attempted, position=position)
            first = read(box, OCR_PROFILES[0])
            attempted += 1
            if first not in "0123456789" or len(first) != 1 or stop():
                report(attempted, box, "unclear", position=position)
                continue
            report(attempted, position=position)
            second = read(box, OCR_PROFILES[1])
            attempted += 1
            if first != second or (veto is not None and veto(box, first)):
                report(attempted, box, "disagreement", position=position)
                continue
            candidate = filled[:position] + first + filled[position + 1:]
            if final and not accept(candidate + current[len(pattern):]):
                report(attempted, box, "agreement", position=position)
                continue
            report(attempted, box, "accepted" if final else "agreement", position=position)
            filled = candidate
            moved[index] = box
            found = True
            break
        if not found:
            return None, attempted
    return (filled + current[len(pattern):], moved[:whole_digits], moved[whole_digits:]), attempted


def glyph_scores(register, box, polarity, light_digits):
    """Template scores for one digit frame (second opinion next to Tesseract), {} on failure."""
    try:
        return glyph_match.digit_scores(register.crop(box), None if polarity == "auto" else light_digits)
    except (OSError, ValueError, ZeroDivisionError):
        return {}


_digit_pool = None
_digit_pool_lock = Lock()


def digit_workers():
    """Parallel single-digit reads: one per usable CPU core, at most four."""
    cores = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count() or 1
    try:
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if quota != "max":
            cores = min(cores, max(1, int(quota) // int(period)))
    except (OSError, ValueError):
        pass
    return max(1, min(4, cores))


def read_digits_parallel(tasks):
    """Run the single-digit reads of one row side by side and keep their order.

    Every digit costs several Tesseract starts; on a small machine a row took ten seconds and
    more. The reads are independent processes, so the cores can share them (0.5.0).
    ``tasks`` holds callables, or a ready result for a skipped digit.
    """
    global _digit_pool
    pending = [task for task in tasks if callable(task)]
    workers = digit_workers()
    if workers < 2 or len(pending) < 2:
        return [task() if callable(task) else task for task in tasks]
    with _digit_pool_lock:
        if _digit_pool is None:
            _digit_pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="digit")
        pool = _digit_pool
    futures = [pool.submit(task) if callable(task) else task for task in tasks]
    return [item.result() if isinstance(item, Future) else item for item in futures]


def read_visible_digits(register, integer_width, whole_boxes, fraction_boxes, light_digits, polarity, *, profile,
                        whole_digits=5, fraction_digits=3, deadline=None, prefer_boxes=False, recognize=None,
                        whole_range=None, glyphs=True, parallel=None):
    # Real OCR calls are independent processes and may run side by side; a supplied reader
    # only when the caller says it is safe for threads.
    side_by_side = recognize is None if parallel is None else parallel
    recognize = recognize or read_register
    gather = read_digits_parallel if side_by_side else (
        lambda tasks: [task() if callable(task) else task for task in tasks])
    if polarity != "auto":
        light_digits = polarity == "light"

    def read(picture, digits=whole_digits):
        kwargs = {"deadline": deadline} if deadline is not None else {}
        return recognize(picture, light_digits, digits, force_polarity=polarity != "auto", profile=profile, **kwargs)

    glared = set()
    if glyphs and len(whole_boxes) == whole_digits:
        try:
            # A flash reflection makes Tesseract invent digits (e.g. a 7) in the washed-out frame.
            frames = [*whole_boxes, *fraction_boxes[:fraction_digits]]
            glared = set(glare_slots(register, frames)) | set(glyph_match.washed_out(register, frames))
        except (OSError, ValueError, ZeroDivisionError):
            glared = set()
    whole = None if prefer_boxes else read(register.crop((0, 0, integer_width, register.height)))
    if whole is not None and glared & set(range(whole_digits)):
        whole = None
    if whole is None:
        cells = gather([
            "?" if index in glared else partial(read_digit, register, box, read, trim_vertical=not prefer_boxes)
            for index, box in enumerate(whole_boxes)])
        scores = []
        if glyphs and len(whole_boxes) == whole_digits:
            scores = [glyph_scores(register, box, polarity, light_digits) for box in whole_boxes]
            cells = ["?" if index in glared else glyph_match.combine(cell, score)
                     for index, (cell, score) in enumerate(zip(cells, scores))]
        whole = "".join(cells).ljust(whole_digits, "?")
        if scores and whole_range is not None:
            whole = glyph_match.anchored_whole(whole, scores, *whole_range)
        if (prefer_boxes and whole_digits >= 4 and whole.count("?") == 1 and len(whole_boxes) == whole_digits
                and not glared & set(range(whole_digits))):
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
    fraction_cells = gather([
        "?" if whole_digits + index in glared else partial(read_digit, register, box, read)
        for index, box in enumerate(fraction_boxes[:fraction_digits])])
    if glyphs:
        fraction_cells = ["?" if whole_digits + index in glared
                          else glyph_match.combine(cell, glyph_scores(register, box, polarity, light_digits))
                          for index, (cell, box) in enumerate(zip(fraction_cells, fraction_boxes))]
    if glyphs and "?" in whole + "".join(fraction_cells) and digit_library.LIBRARY.digits:
        # 0.4.0: unclear cells compared with this meter's own learned digit shapes.
        bright = bool(light_digits)
        whole_cells = list(whole)
        if len(whole_cells) == whole_digits and len(whole_boxes) == whole_digits:
            for index, box in enumerate(whole_boxes):
                if whole_cells[index] == "?" and index not in glared:
                    learned = learned_digit(register, box, bright, polarity, light_digits)
                    if learned:
                        whole_cells[index] = learned
            whole = "".join(whole_cells)
        for index, box in enumerate(fraction_boxes[:fraction_digits]):
            if index < len(fraction_cells) and fraction_cells[index] == "?" and whole_digits + index not in glared:
                learned = learned_digit(register, box, bright, polarity, light_digits)
                if learned:
                    fraction_cells[index] = learned
    fraction = "".join(fraction_cells)
    return f"{whole}.{fraction.ljust(fraction_digits, '?')}" if fraction_digits else whole


def learned_digit(register, box, bright, polarity, light_digits):
    try:
        cell = register.crop(box)
        return digit_library.LIBRARY.fill(cell, bright, glyph_scores(register, box, polarity, light_digits))
    except (OSError, ValueError, ZeroDivisionError):
        return None


def learn_confirmed_digits(register, boxes, readings, value, light_digits, *, skip_last=False):
    """Teach the digit library from a confirmed check: cells all readings agree on."""
    rows = [str(item).replace(".", "").replace(",", "") for item in readings]
    target = str(value).replace(".", "").replace(",", "")
    if not rows or len(boxes) < len(target) - (1 if skip_last else 0):
        return 0
    cells = []
    for index, digit in enumerate(target):
        if index >= len(boxes) or (skip_last and index == len(target) - 1):
            break
        if digit.isdigit() and all(len(row) > index and row[index] == digit for row in rows):
            try:
                cells.append((register.crop(boxes[index]), digit))
            except (OSError, ValueError):
                continue
    return digit_library.LIBRARY.learn(cells, bool(light_digits)) if cells else 0


def glyph_whole_range(history, rules, zone, captured):
    """Whole cubic metres the meter can show at ``captured`` after the newest known reading.

    Used only as a hint to fill unclear whole digits; the reading itself is checked as before.
    """
    if type(captured) not in (int, float):
        return None
    consumption = history.get("consumption") or {}
    counted = ({"value": consumption["reading_litres"], "time": consumption["timestamp"]}
               if type(consumption.get("reading_litres")) is int
               and type(consumption.get("timestamp")) in (int, float) else None)
    anchor = newest_anchor(history.get("reflection_anchor"), counted, captured)
    anchor = newest_anchor(anchor, manual_reading_anchor(rules, zone), captured)
    bounds = anchor_bounds(anchor, captured, 3, rules.get("max_flow_lph"))
    return (bounds[0] // 1000, bounds[1] // 1000) if bounds else None


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
        picture, _, _ = capture_camera(source["camera"], "", token, zone, timeout=5,
                                       light=capture_light(source, source["camera"], token))
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


def usable_known_good_geometry(saved, scopes, digits):
    """The remembered frame if it fits this camera and digit count, else None.

    A file from 0.2.9 or older ("camera" missing) was keyed on settings that do not move
    the digits (source mode, reference sensor, display style). It is still offered as the
    starting point when the digit count matches; the setup checks it on fresh images
    before anything is saved (20.11.).
    """
    if not isinstance(saved, dict) or not isinstance(saved.get("geometry"), dict):
        return None
    if saved.get("scope") in scopes:
        return saved["geometry"]
    if "camera" not in saved and len(saved["geometry"].get("digit_boxes") or ()) == digits:
        return saved["geometry"]
    return None


def calibration_source_id(source):
    return hashlib.sha256(json.dumps(without_light(source), sort_keys=True).encode()).hexdigest()


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
    else:
        # No reading yet after a new setup or reset: keep showing the last booked value
        # instead of "unavailable" (dashboards and statistics would show a gap).
        counter = history.get("consumption")
        if (isinstance(counter, dict) and isinstance(counter.get("source"), list)
                and camera in counter["source"] and type(counter.get("anchor_litres")) is int):
            step = counter.get("anchor_step") or counter.get("step_litres") or 1
            decimals = {1: 3, 10: 2, 100: 1}.get(step, 0)
            value = f"{counter['anchor_litres'] / 1000:.{decimals}f}"
            captured = counter.get("anchor_time")
            is_fallback = True
    payload = {
        "state": value,
        "attributes": {"friendly_name": "Meter OCR Zählerstand" + LABEL_SUFFIX, "unit_of_measurement": "m³",
                       "device_class": "gas", "source_camera": camera, "last_successful_image": captured,
                       "is_fallback": is_fallback},
    }
    publish_state(f"http://supervisor/core/api/states/{OCR_ENTITY}", payload, token)


def factory_reset_history(history, keep_statistics=False):
    """Discard setup and checks while optionally retaining the verified consumption ledger."""
    if not keep_statistics:
        return {}
    retained = {key: deepcopy(history[key]) for key in ("consumption", "consumption_statistics")
                if key in history}
    retained["statistics_preserved_after_reset"] = True
    return retained


def publish_energy(history, token, rules):
    """Consumption in kWh, only once both billing factors are set."""
    consumption = history.get("consumption")
    if isinstance(consumption, dict) and isinstance(rules, dict):
        kwh = energy_kwh(consumption.get("total_litres"),
                         valid_energy_factor(rules.get("gas_state_factor"), STATE_FACTOR_RANGE),
                         valid_energy_factor(rules.get("calorific_value"), CALORIFIC_RANGE),
                         valid_energy_factor(rules.get("kwh_conversion_factor"), CONVERSION_RANGE))
        if kwh is not None:
            publish_state(f"http://supervisor/core/api/states/{ENERGY_ENTITY}", {
                "state": f"{kwh:.2f}",
                "attributes": {
                    "friendly_name": "Meter OCR Gasverbrauch gesamt (kWh)" + LABEL_SUFFIX,
                    "unit_of_measurement": "kWh", "device_class": "energy", "state_class": "total_increasing",
                    "zustandszahl": rules.get("gas_state_factor"), "brennwert_kwh_m3": rules.get("calorific_value"),
                    "umrechnungsfaktor": rules.get("kwh_conversion_factor"),
                },
            }, token)


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
SETUP_RETRY_NOTICE = ("Die Einrichtung hat noch keinen sicheren Rahmen gefunden. "
                      "Die App startet sie in wenigen Minuten automatisch neu.")
SETUP_RETRY_LONG_NOTICE = ("Die Einrichtung hat noch keinen sicheren Rahmen gefunden. "
                           "Die App versucht es stündlich von selbst erneut. Häufige Ursachen: "
                           "unscharfes Bild (Objektiv scharfstellen) oder eine Spiegelung des Blitzes auf den Ziffern.")
# A user-started setup that ended without result is restarted, so the app does not wait forever.
SETUP_RETRY_STATES = ("timeout", "image_timeout", "failed")
SETUP_RETRY_SECONDS = 300
SETUP_RETRY_LIMIT = 3
# After the quick retries the setup keeps trying hourly, so a later fix at the camera
# (focus, glare) is picked up without anyone tapping a button.
SETUP_RETRY_LONG_SECONDS = 3600


def setup_retry_delay(count):
    """Seconds until the next automatic setup restart after `count` earlier restarts."""
    return SETUP_RETRY_SECONDS if count < SETUP_RETRY_LIMIT else SETUP_RETRY_LONG_SECONDS


def app_build():
    """Identify the installed app version; changes with every update."""
    version = os.environ.get("BUILD_VERSION", "").strip()
    if version:
        return version
    try:
        return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def plain_setup(rules, action):
    """Does this job confirm the frames with two decimals (the plain setup)?

    The comparison precision is a rule for the routine checks. A setup must not ask for more
    than they do: with "whole cubic metres" (0) and no reference it demanded all three decimals,
    including the fast last roller, and never confirmed (0.4.4).
    """
    return action in ("setup", "start", "repair") and (
        rules["fraction_digits"] == 3 or rules["decimals"] in (2, 3))


def setup_autostart_due(history, build, job, attempted):
    """Restart an unfinished setup once per installed version, without user interaction.

    Only after a setup was started before; choosing a source alone does not start one.
    """
    return job is None and bool(build) and history.get("setup_autostart_build") != build and attempted()


def setup_attempted_before():
    try:
        return '"kind": "setup_' in debug_log.read_text(debug_log.MAX_ENTRIES)
    except (OSError, ValueError):
        return False


def last_setup_unfinished(text=None):
    """True if the newest user/update setup ran out of time or failed and nothing read since.

    Then a new version restarts the setup on its own after the update, even though an older
    frame is still stored (Stefan 20.11.2026: setup timed out, automatic read only "?????.9??").
    """
    try:
        lines = (debug_log.read_text(debug_log.MAX_ENTRIES) if text is None else text).splitlines()
    except (OSError, ValueError):
        return False
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        kind = entry.get("kind")
        if kind == "automatic" and entry.get("outcome") in SUCCESSFUL_CHECKS:
            return False
        if kind == "setup_start" and entry.get("trigger") in ("user", "update", "retry"):
            return False
        if kind == "setup_end" and entry.get("purpose") == "setup":
            return entry.get("state") in ("timeout", "failed")
    return False


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

    # Two decimals by default (config.yaml); 3 means precision mode is on.
    default_decimals = options["vergleich_nachkommastellen"]
    default_attempts = options["ocr_versuche"]
    wake_worker = Event()
    automatic_request = handled_automatic_request = None

    def request_automatic_check(*, on_demand=False):
        nonlocal automatic_request
        automatic_request = (on_demand,)
        wake_worker.set()

    auto_rules = default_rules(options)
    default_auto_rules = dict(auto_rules)
    try:
        auto_rules = stored_rules(json.loads(AUTO_RULES.read_text(encoding="utf-8")), options)
        if auto_rules is None:
            auto_rules = dict(default_auto_rules)
            print("Ungültige gespeicherte Automatikregeln; verwende die App-Konfiguration.")
    except FileNotFoundError:
        pass
    except (OSError, ValueError, AttributeError) as error:
        print(f"Automatikregeln konnten nicht geladen werden: {type(error).__name__}")

    def get_auto_rules():
        return dict(auto_rules)

    def save_auto_rules(values, *, request_check=True):
        nonlocal auto_rules
        updated_rules = changed_rules(auto_rules, values)
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
    reset_mode = {"keep_statistics": False}

    def request_factory_reset(*, keep_statistics=False):
        if type(keep_statistics) is not bool:
            raise ValueError("Ungültige Werkreset-Variante")
        with reset_lock:
            if reset_result["value"] != "pending":
                reset_mode["keep_statistics"] = keep_statistics
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
                           "Einrichtung erforderlich: Lege zuerst die Bildquelle fest." if setup_pending else
                           "App läuft. Wartet auf die nächste automatische Prüfung.")}

    def set_activity(state, detail, *, completed=None, total=None, reading=None, candidates=None, readings=None):
        # readings: every attempt of the running check, for the per-digit table under "Prüfdetails".
        activity.update(state=state, detail=detail, updated_at=time.time(), completed=completed, total=total,
                        reading=reading, candidates=candidates,
                        readings=[str(value) for value in readings][-12:] if readings else None)

    def ready_for_automatic(rules, source):
        if setup_pending and history.get("statistics_preserved_after_reset"):
            return False
        explicit_crop = options["ausschnitt"] != DEFAULTS["ausschnitt"]
        return automatic_inputs_ready(rules, source, history, legacy_crop=explicit_crop and not setup_pending)

    def get_automatic_activity():
        if not get_auto_paused() and not ready_for_automatic(get_auto_rules(), get_source()[0]):
            return {"state": "setup_wait",
                    "detail": SETUP_RETRY_NOTICE if setup_retry["job"] is not None else SETUP_WAIT_NOTICE}
        if not get_auto_paused() and automatic_request is not handled_automatic_request:
            detail = ("Automatische Prüfung angefordert." if automatic_request[0] else
                      "Einstellungen gespeichert. Prüfung startet gleich.")
            return {"state": "queued", "detail": detail}
        return dict(activity)

    settings_lock = RLock()
    calibration = None
    calibration_configuration = None
    # Tilt of each candidate layout, measured on the setup images: the coarse search finds the
    # digits in whole degrees, this gives the remaining fine angle to save with the layout.
    calibration_tilts = {}
    calibration_next = 0.0
    calibration_worker = None
    setup_retry = {"job": None, "at": 0.0, "count": 0}
    # Checked once after each start of the app: restart an unfinished setup after an update.
    setup_autostart = {"pending": True, "build": app_build()}
    calibration_preview = {}
    calibration_images = {}
    # The newest picture of an automatic check. Background searches (eighth digit, frame
    # relocation, fine adjustment after the setup) only evaluate these pictures and never
    # request extra ones from the camera.
    automatic_capture = {"seq": 0, "result": None}
    calibration_preview_version = 0
    geometry_backup = HISTORY.with_name("geometry-backup.json")
    calibration_candidates_path = HISTORY.with_name("calibration-candidates.json")
    known_good_geometry_path = HISTORY.with_name("known-good-geometry.json")
    digit_library.LIBRARY = digit_library.DigitLibrary(HISTORY.with_name("digit-library.json"))

    def automatic_check_available():
        source, _ = get_source()
        calibrating = (calibration is not None and not calibration.background
                       and calibration.state in ("waiting", "testing"))
        return (not get_auto_paused() and not calibrating and activity["state"] != "working"
                and automatic_request is handled_automatic_request and ready_for_automatic(get_auto_rules(), source))

    def start_automatic_now():
        with settings_lock:
            if not automatic_check_available():
                return False
            request_automatic_check(on_demand=True)
            return True

    def known_good_scope(rules, source):
        # Only what moves the digits in the picture: which camera and how many digits.
        # Source mode, reference sensor, light, polarity or display style do not, and a
        # changed setting there must not throw away a frame that read for hours (20.11.).
        camera = source.get("camera") or str(source.get("url") or "").rstrip("/")
        return calibration_source_id(["known-good", camera, rules["integer_digits"], rules["fraction_digits"]])

    def legacy_known_good_scope(rules, source):
        format_keys = ("integer_digits", "fraction_digits", "meter_display", "polarity")
        return calibration_source_id([source, [rules[key] for key in format_keys]])

    def geometry_layout(geometry, rules):
        box = crop_coordinates(geometry["crop"], geometry["width"], geometry["rotation"])
        boxes = digit_box_settings(geometry["digit_boxes"], rules["integer_digits"] + rules["fraction_digits"])
        return Layout(box, geometry["rotation"], geometry["width"], tuple(map(tuple, boxes)))

    def load_known_good_layout(rules, source):
        try:
            saved = json.loads(known_good_geometry_path.read_text(encoding="utf-8"))
            geometry = usable_known_good_geometry(
                saved, (known_good_scope(rules, source), legacy_known_good_scope(rules, source)),
                rules["integer_digits"] + rules["fraction_digits"])
            if geometry is not None:
                return geometry_layout(geometry, rules)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            pass
        return None

    def remember_known_good_layout(rules, source, layout):
        if layout == load_known_good_layout(rules, source):
            return
        camera = source.get("camera") or str(source.get("url") or "").rstrip("/")
        saved = {"scope": known_good_scope(rules, source), "camera": camera, "geometry": layout.settings()}
        try:
            atomic_write(known_good_geometry_path, json.dumps(saved).encode(), 0o600)
        except OSError:
            print("Der bestätigte Rahmen konnte nicht als Ausgangspunkt gespeichert werden.")

    def candidate_scope(configuration, region, simplified, intensive):
        rules, source = configuration
        relevant = ("integer_digits", "fraction_digits", "decimals", "polarity", "meter_display")
        # The app version belongs to the scope: frames found by an older version are not reused.
        key = [without_light(source), [rules[name] for name in relevant], region, simplified, intensive, app_build()]
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
            return backup["rules"] if without_light(backup["source"]) == without_light(get_source()[0]) else None
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def calibration_configuration_now():
        return get_auto_rules(), get_source()

    def calibration_tilt_key(layout):
        return (tuple(layout.box), layout.rotation, layout.width, tuple(map(tuple, layout.digit_boxes)))

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
        if verified and (not attempt.intensive or attempt.setup_last_digit) and not attempt.automatic and reference:
            success = {"source": setup_source_id(source), "time": finished, "duration_seconds": elapsed, **metrics}
            if not previous_completion:
                completed = success
        revision = str(time.time_ns())
        partial = (provisional and not reflected) or verified and attempt.simplified
        partial_scope = calibration_source_id([source, revision]) if partial else None
        pending_source = setup_source_id(source) if provisional else rules.get("setup_pending_source")
        pending_started = finished - elapsed if provisional else rules.get("setup_pending_started")
        pending_metrics = metrics if provisional else rules.get("setup_pending_metrics")
        tilts = calibration_tilts.get(calibration_tilt_key(layout), [])
        fine = rules.get("rotation_fine", 0.0) if layout.settings().get("rotation") == rules.get("rotation") else 0.0
        # Fine angle within ±0.5°; the rest of the measured tilt seeds the routine correction.
        fine, seed = setup_tilt(tilts, fine)
        saved_geometry = layout.settings()
        skew_seed = {"key": [saved_geometry["crop"], saved_geometry["width"], saved_geometry["rotation"],
                             valid_fine_rotation(fine)], "offset": seed}
        relocated = {"last_frame_relocated_at": time.time()} if attempt.purpose == "relocate" and not provisional else {}
        save_auto_rules({**rules, **layout.settings(), **relocated, "rotation_fine": valid_fine_rotation(fine),
                         "crop_revision": revision, "skew_seed": skew_seed,
                         "setup_input_source": setup_source_id(source),
                         "calibration_reference": reference, "stationary_partial_scope": partial_scope,
                         "setup_completed": completed, "setup_success": success,
                         "setup_pending_source": None if completed else pending_source,
                         "setup_pending_started": None if completed else pending_started,
                         "setup_pending_metrics": None if completed else pending_metrics})

    def control_calibration(action, limit, region=None, *, verification_id=None, trigger="user"):
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
                # A repair confirms the frames with two decimals like a plain setup: the third
                # roller (glare, always turning) must not keep a moved camera from being found again.
                # 0.4.3: a setup that compares two decimals is the same plain setup. Before, only
                # three compared decimals got it; with two (the default after a factory reset) the
                # setup ran the strict path without the 0.4.2 corrections and never confirmed.
                # 0.4.4: and so is every setup of a meter with three decimal rollers, whatever
                # precision the routine checks compare (0 demanded all three decimals here).
                simplified = plain_setup(rules, action)
                intensive = action in ("intensive", "relocate_last")
                if intensive and (rules["fraction_digits"] != 3 or rules["decimals"] != 3):
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
                # A new setup starts without the frames of earlier runs: after the camera was
                # moved they only read rubbish first and were even chosen again (Stefan 21.11.).
                shortlist = {} if repair or action == "setup" else load_calibration_candidates(scope, rules)
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
                background = intensive and (action == "relocate_last" or stationary_partial_active(rules, source))
                calibration = Calibration(limit=limit, started=now, automatic=repair,
                                          rank_candidates=not (repair or intensive), shortlist=shortlist,
                                          simplified=simplified, intensive=intensive,
                                          background=background, followup=background,
                                          purpose="relocate" if action == "relocate_last" else "",
                                          duration=GEOMETRY_REPAIR_SECONDS if repair else TIME_LIMIT,
                                          attempt_limit=GEOMETRY_REPAIR_LIMIT if repair else MAX_ATTEMPTS,
                                          previous_layout=previous, region=region,
                                          known_good_layout=reflected_layout or known_good,
                                          reflected_layout=reflected_layout, reflected_positions=reflected_positions)
                calibration_preview.clear()
                calibration_images.clear()
                calibration_configuration = configuration
                calibration_next = now
                # Who started which search: a setup must never start unnoticed.
                debug_log.record(kind="setup_start", action=action, trigger=trigger,
                                 region=bool(region), known_good=known_good is not None,
                                 decimals=rules["decimals"], simplified=simplified)
            wake_worker.set()
            return True

    def calibration_status():
        with settings_lock:
            if calibration is None:
                return None
            status = calibration.status(time.monotonic())
            status["preview"] = dict(calibration_preview)
            relocated_at = auto_rules.get("last_frame_relocated_at")
            if calibration.purpose == "relocate" and type(relocated_at) in (int, float):
                status["relocated_at"] = relocated_at
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
            if job.image_wait_expired(now) and not job.background:
                job.state = "image_timeout"
                return False
            if calibration_configuration_now() != calibration_configuration or get_auto_paused():
                job.state = "cancelled"
                return False
            configured_rules, (configured_camera, _) = calibration_configuration
            if now < calibration_next or (active_rules, active_source) != (configured_rules, configured_camera):
                return True
            shared_result = None
            if job.background:
                if automatic_capture["seq"] <= job.automatic_seq or automatic_capture["result"] is None:
                    return True
                job.automatic_seq = automatic_capture["seq"]
                picture, drawn, sample = automatic_capture["result"]
                shared_result = (picture, drawn, dict(sample))
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
        round_started = time.monotonic()
        round_log = {"fetch_seconds": None, "accepted_at": None, "error": None, "captured": False, "reads": []}
        try:
            if shared_result is not None:
                result = shared_result
            elif attempt.intensive and not attempt.stream_unavailable:
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
            if shared_result is not None:
                pass
            elif stream_pictures:
                result = capture_esp_snapshot(base, zone, "camera_stream", fetch=lambda _: stream_pictures[-1])
            elif mode == "slfork":
                result = capture(base, {}, fetch=fetch)
            elif mode == "slfork_camera":
                result = capture_edge_camera(base, zone, fetch=fetch)
            elif camera:
                result = capture_camera(camera, reference, token, zone, fetch=fetch,
                                        light=capture_light(get_source()[0], camera, token))
            round_log["fetch_seconds"] = time.monotonic() - round_started
            if result is not None and not stopped():
                round_log["captured"] = True
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
                                active_rules["max_flow_lph"], active_rules["integer_digits"], confirmed=True,
                            )
                    glyph_range = glyph_whole_range(history, active_rules, zone, captured)
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
                            round_log["accepted_at"] = now
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
                            reduced = (attempt.simplified or active_rules["decimals"] == 2) and not full_precision
                            value = read_visible_digits(
                                *register[:4], options["helle_ziffern"], active_rules["polarity"], profile=profile,
                                whole_digits=whole, fraction_digits=2 if reduced else fraction,
                                deadline=deadline if ocr_deadline is None else ocr_deadline,
                                prefer_boxes=bool(layout.digit_boxes), recognize=cached_digit,
                                whole_range=glyph_range, parallel=True,
                            )
                            return two_decimal_reading(value) if reduced else value

                        def read(layout, profile):
                            nonlocal previous_layout
                            register = register_for(layout)
                            if layout != previous_layout:
                                readings.clear()
                                previous_layout = layout
                                report_crop(layout, register, None)
                                if layout.digit_boxes and register[2]:
                                    try:
                                        tilt = digit_row_tilt(register[0], register[2])
                                    except (OSError, ValueError, ZeroDivisionError):
                                        tilt = None
                                    if tilt is not None and abs(tilt) <= 4:
                                        key = calibration_tilt_key(layout)
                                        calibration_tilts[key] = (calibration_tilts.get(key, []) + [tilt])[-9:]
                                        if len(calibration_tilts) > 40:
                                            calibration_tilts.pop(next(iter(calibration_tilts)))
                            reading = recognize(layout, profile, register)
                            readings.append(reading)
                            if len(round_log["reads"]) < SETUP_READ_LOG_LIMIT:
                                # Which frame read what: without this a failed setup could not be explained.
                                box = layout.box
                                round_log["reads"].append(
                                    f"{layout.method or 'frame'} {box[0]},{box[1]},{box[2]},{box[3]} "
                                    f"{layout.rotation}° P{OCR_PROFILES.index(profile) if profile in OCR_PROFILES else '?'} {reading}")
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
                                    if trial != layout and glyph_clipped(register[0], digit_box):
                                        # A moved frame that cuts the digit would read another digit.
                                        return "?"
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
                                if attempt.setup_last_digit and attempt.verification_pending:
                                    report_calibration("verify", rotation=layout.rotation)
                                    result_layout = attempt.verify(
                                        frame, sample, captured, active_rules, read, stopped,
                                        on_image=on_image, on_decision=report_decision,
                                    )
                                else:
                                    centre = None
                                    try:
                                        image, _, whole_px, fraction_px = register_for(layout)[:4]
                                        found = roll_center(image, [*whole_px, *fraction_px])
                                        if found is not None and image.width:
                                            centre = found * 1000 / image.width
                                    except (OSError, ValueError, TypeError, IndexError):
                                        centre = None
                                    result_layout = attempt.check_last_digit(
                                        frame, sample, captured, layout, whole, read_last,
                                        lambda: stopped() or transition is not None, on_image, report_decision,
                                        roll_center=centre,
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
                            elif attempt.stationary_crop_ready():
                                selected = attempt.candidate
                                provisional = True
                            elif attempt.reflection_crop_ready():
                                selected = attempt.reflected_layout
                                provisional = reflected = True
                        if attempt.reference_reading is not None and attempt.counter.get("timestamp") == captured:
                            attempt.reference_image_id = hashlib.sha256(picture).hexdigest()
        except (OSError, ValueError, TypeError, Image.DecompressionBombError) as error:
            round_log["error"] = type(error).__name__
            print(f"Selbsteinrichtung konnte die Aufnahme nicht prüfen: {type(error).__name__}")
        setup_entries = []
        with settings_lock:
            now = time.monotonic()
            setup_entries = setup_round_log(attempt, round_log, round_started, now)
            for entry in setup_entries:
                entry["reason"] = calibration_preview.get("reason")
                entry["reading"] = calibration_preview.get("reading")
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
                    # A verified seven-digit setup is committed BEFORE any
                    # optional eighth-digit check. The fine check is independent
                    # of normal automatic consumption readings.
                    save_calibration_layout(attempt, selected, provisional=provisional,
                                            verified=not provisional, reflected=reflected)
                    if reflected and attempt.auto_reflection:
                        # Fire and Forget: a reflection found by the app is remembered like a marked one.
                        save_auto_rules({**get_auto_rules(), "reflection_estimate_enabled": True,
                                         "setup_reflection": {
                                             "source": setup_source_id(active_source),
                                             "positions": list(attempt.reflected_positions),
                                             **selected.settings(), "automatic": True}},
                                        request_check=False)
                        debug_log.record(kind="setup_glare", positions=list(attempt.reflected_positions),
                                         visible=(attempt.auto_glare or {}).get("visible"))
                    if not provisional and not attempt.automatic:
                        remember_known_good_layout(get_auto_rules(), active_source, selected)
                        history["setup_first_check_revision"] = get_auto_rules()["crop_revision"]
                        # The setup itself confirmed the reading three times.
                        history["last_match_at"] = time.time()
                    attempt.state = "saved_reflection" if reflected else "saved_stationary" if provisional else "saved"
                    if (attempt.simplified and not provisional and not reflected and not attempt.automatic
                            and get_auto_rules()["decimals"] == 3):
                        calibration = Calibration(
                            limit=attempt.limit, started=now, intensive=True,
                            background=True, followup=True, previous_layout=selected,
                            duration=TIME_LIMIT, attempt_limit=MAX_ATTEMPTS,
                        )
                        calibration_configuration = calibration_configuration_now()
                        calibration_next = now + LAST_DIGIT_CAPTURE_INTERVAL
                        wake_worker.set()
                        setup_entries.append(setup_end_log(attempt, now))
                        write_setup_log(setup_entries)
                        return True
                except (OSError, ValueError):
                    attempt.state = "save_failed"
            elif len(attempt.seen) >= attempt.limit or attempt.search_exhausted():
                attempt.state = "failed"
            else:
                attempt.state = "waiting"
                attempt.stage = "verify_wait" if attempt.verification_pending else "waiting"
            if attempt.state not in ("waiting", "testing"):
                setup_entries.append(setup_end_log(attempt, now))
            calibration = attempt
            capture_interval = LAST_DIGIT_CAPTURE_INTERVAL if attempt.intensive else (
                PERFECT_CONFIRMATION_INTERVAL if attempt.full_hits else CAPTURE_INTERVAL)
            calibration_next = now + capture_interval
            wake_worker.set()
        write_setup_log(setup_entries)
        return True

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
        statistics_zone=zone,
        can_start_automatic=automatic_check_available, start_automatic_check=start_automatic_now,
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
        keep_statistics = reset_mode["keep_statistics"]
        retained_history = factory_reset_history(history, keep_statistics)
        try:
            if keep_statistics:
                # Persist the counter and samples before deleting any setup files.
                atomic_write(HISTORY, json.dumps(retained_history).encode("utf-8"), 0o600)
            reminder.clear_for_reset(history)
            paths = (
                HISTORY, AUTO_RULES, SOURCE_SETTINGS, NOTIFICATIONS, LANGUAGE_MODES,
                HISTORY.with_name("manual-test-settings.json"), DESTINATION, GOOD_IMAGE,
                TEST_IMAGE, TEST_SOURCE_IMAGE, AUTOMATIC_PREVIEW, AUTO_PAUSED, geometry_backup,
                calibration_candidates_path, known_good_geometry_path,
                HISTORY.with_name("digit-library.json"),
            )
            for path in paths:
                if keep_statistics and path == HISTORY:
                    continue
                path.unlink(missing_ok=True)
            digit_library.LIBRARY.clear()
            # Left over from the removed "Experimentell · Mehrere Zähler" field (≤ 0.3.2).
            HISTORY.with_name("experimental-meters.json").unlink(missing_ok=True)
            history = retained_history
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
            # Support rounds need to see a deliberate reset (setups start without a known frame).
            debug_log.record(kind="factory_reset", keep_statistics=keep_statistics)
        except (OSError, ValueError, TypeError) as error:
            print(f"Werkreset konnte nicht abgeschlossen werden: {type(error).__name__}")
            reset_result["value"] = "failed"

    while True:
        wake_worker.clear()
        if reset_requested.is_set():
            reset_requested.clear()
            perform_factory_reset()
            continue
        with settings_lock:
            requested_automatic_check = automatic_request
            run_automatic_now = requested_automatic_check is not handled_automatic_request
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
        adaptive = active_rules["adaptive_interval_enabled"]
        if adaptive:
            interval_minutes = suggested_interval(interval_minutes, history.get("adaptive_flow", {}), source_key, now.month)
        interval_minutes = stabilization_interval(interval_minutes, stabilizing_until, now.timestamp())
        history["failure_pause_minutes"] = active_rules.get("failure_pause_minutes", DEFAULT_FAILURE_PAUSE_MINUTES)
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
        # The initial seven-digit setup is persistent, but the optional fine
        # search itself is in memory. Resume it after restarts and after failed
        # or timed-out searches, without suspending normal seven-digit checks.
        if (not manual and not get_auto_paused()
                and (calibration is None or calibration.state not in ("waiting", "testing")
                     or calibration.expired(time.monotonic()))):
            with settings_lock:
                if (get_auto_rules() == active_rules and get_source()[0] == active_source
                        and not get_auto_paused()):
                    try:
                        if resume_optional_eighth_digit(
                                history, active_rules, active_source, now.timestamp(),
                                lambda: control_calibration("intensive", DEFAULT_LIMIT, trigger="eighth_digit")):
                            atomic_write(HISTORY, json.dumps(history).encode("utf-8"), 0o600)
                    except (OSError, ValueError, TypeError) as error:
                        print(f"Hintergrundprüfung der achten Ziffer konnte nicht erneut starten: {type(error).__name__}")
                    try:
                        if relocate_last_digit_due(history, active_rules, now.timestamp()):
                            history["last_digit_relocate_at"] = now.timestamp() + EIGHTH_DIGIT_RETRY_SECONDS
                            history.pop("last_digit_relocate_due", None)
                            if control_calibration("relocate_last", DEFAULT_LIMIT, trigger="relocate"):
                                print("Rahmen der letzten Stelle sitzt vermutlich daneben – suche ihn im Hintergrund neu")
                            atomic_write(HISTORY, json.dumps(history).encode("utf-8"), 0o600)
                    except (OSError, ValueError, TypeError) as error:
                        print(f"Neue Suche der letzten Stelle konnte nicht starten: {type(error).__name__}")
        if (not manual and calibration is not None and calibration.state in ("waiting", "testing")
                and time.monotonic() >= calibration_next
                and (not calibration.background
                     or (not startup and remaining > LAST_DIGIT_CAPTURE_INTERVAL
                         and not run_automatic_now))
                and (calibration_worker is None or not calibration_worker.is_alive())):
            calibration_worker = Thread(target=run_calibration,
                                        args=(active_rules, active_source, mode, base, camera, reference, source_key),
                                        daemon=True, name="meter-calibration")
            calibration_worker.start()
        if (not manual and calibration is not None and not calibration.automatic
                and not calibration.background
                and calibration.state in ("waiting", "testing")):
            wake_worker.wait(timeout=LAST_DIGIT_CAPTURE_INTERVAL if calibration.intensive else CAPTURE_INTERVAL)
            continue
        if get_auto_paused() and not manual:
            set_activity("paused", "Automatik pausiert. Manuelle Tests bleiben verfügbar.")
            wake_worker.wait(timeout=15)
            continue
        if not manual and not ready_for_automatic(active_rules, active_source):
            job = calibration
            build = setup_autostart["build"] if setup_autostart["pending"] else ""
            setup_autostart["pending"] = False
            if setup_autostart_due(history, build, job, setup_attempted_before):
                # After an update the setup restarts on its own (Fire and Forget), once per version.
                history["setup_autostart_build"] = build
                setup_retry.update(job=None, count=0)
                try:
                    atomic_write(HISTORY, json.dumps(history).encode("utf-8"), 0o600)
                    if control_calibration("setup", DEFAULT_LIMIT, trigger="update"):
                        print("Neue App-Version: Selbsteinrichtung startet automatisch neu.")
                        debug_log.record(kind="setup_autostart", build=build)
                        continue
                except (OSError, ValueError):
                    print("Selbsteinrichtung konnte nach dem Update nicht automatisch starten.")
            if (job is not None and job.simplified and not job.automatic and not job.background
                    and not job.intensive and job.state in SETUP_RETRY_STATES):
                if setup_retry["job"] is not job:
                    setup_retry.update(job=job, at=time.monotonic() + setup_retry_delay(setup_retry["count"]))
                if time.monotonic() >= setup_retry["at"]:
                    setup_retry.update(job=None, count=setup_retry["count"] + 1)
                    try:
                        control_calibration("setup", job.limit, trigger="retry")
                    except (OSError, ValueError):
                        print("Selbsteinrichtung konnte nicht automatisch neu gestartet werden.")
                    continue
                set_activity("setup_wait", SETUP_RETRY_NOTICE if setup_retry["count"] < SETUP_RETRY_LIMIT
                             else SETUP_RETRY_LONG_NOTICE)
            else:
                setup_retry["job"] = None
                set_activity("setup_wait", SETUP_WAIT_NOTICE)
            wake_worker.wait(timeout=2)
            continue
        setup_retry.update(job=None, count=0)
        if setup_autostart["pending"] and not manual:
            setup_autostart["pending"] = False
            build = setup_autostart["build"]
            if setup_autostart_due(history, build, calibration, last_setup_unfinished):
                # The last setup did not finish: a new version tries again on its own.
                history["setup_autostart_build"] = build
                try:
                    atomic_write(HISTORY, json.dumps(history).encode("utf-8"), 0o600)
                    if control_calibration("setup", DEFAULT_LIMIT, trigger="update"):
                        print("Neue App-Version: unterbrochene Selbsteinrichtung startet automatisch neu.")
                        debug_log.record(kind="setup_autostart", build=build, reason="unfinished")
                        continue
                except (OSError, ValueError):
                    print("Selbsteinrichtung konnte nach dem Update nicht automatisch starten.")
        setup_autostart["pending"] = False
        if remaining > 0 and not startup and not manual and not source_changed and not run_automatic_now:
            set_activity("waiting", SEVENTH_DIGIT_WAIT_NOTICE if history.get("seventh_digit_wait") else
                         FRESH_OCR_NOTICE if history.get("fresh_ocr_retry_at") else
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
                    publish_energy(history, token, get_auto_rules())
                except OSError as error:
                    print(f"Prüfstatus konnte nicht übertragen werden: {error}")
                check_reminder(reminder, history, now, review_after)
            wake_worker.wait(timeout=min(remaining, RETRY_INTERVAL,
                                         CAPTURE_INTERVAL if calibration is not None
                                         and calibration.state in ("waiting", "testing") else RETRY_INTERVAL))
            continue

        if not manual:
            with settings_lock:
                requested_automatic_check = automatic_request
                run_automatic_now = requested_automatic_check is not handled_automatic_request
                set_activity("working", "Automatische Prüfung startet …")
                handled_automatic_request = requested_automatic_check
        keep_schedule = startup and remaining > 0 and not source_changed and not run_automatic_now
        startup = startup and manual
        on_demand = run_automatic_now and requested_automatic_check[0]
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
                          "hidden_digit_prompt", "flow_peaks", "flow_peak_samples",
                          "reflection_rechecks", "reflection_retry_at", "fresh_ocr_retry_at", "ocr_candidates", "ocr_method",
                          "last_slfork_match", "last_reference", "last_reference_time",
                          "last_reference_is_fallback", "ocr_value", "ocr_readings"):
                source_history.pop(field, None)
        source_history["check_source"] = source_key
        updated = dict(source_history)
        validation_detail = None
        lower_recovered = False
        new_consumption = None
        new_standalone = None
        standalone_reference = None
        fine_update = None
        fine_rotation = None
        optimizer_saved = False
        local_trial = None
        shifted_trial = None
        recovery_log = None
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
            if history.get("comparison_integer_digits", integer_digits) != integer_digits:
                # A temporary precision change keeps the time of the last confirmed reading.
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
        rotation_trials = 0
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
                    set_activity("working", "Kamerabild wird angefordert …" if camera or esp_camera_only else
                                 "Die App wartet auf Bild und Messwerte vom ESP …")
                if camera:
                    result = capture_camera(
                        camera, reference, token, zone,
                        timeout=min(8, max(0.2, live_deadline - time.monotonic())) if live_deadline else 8,
                        light=capture_light(active_source, camera, token),
                    )
                elif esp_camera_only:
                    result = capture_edge_camera(base, zone)
                else:
                    result = capture(base, diagnostics)
            if mode == "slfork" and result is None and not slfork_cycle_failed(diagnostics):
                print("Noch kein ausgerichtetes SLFork-Bild verfügbar. Neuer Versuch in 10 Sekunden.")
                if not manual:
                    set_activity("working", "Die App wartet auf ein aktuelles Bild vom ESP …")
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
            if result is not None and not manual and not manual_upload and not raw_fallback:
                with settings_lock:
                    automatic_capture.update(seq=automatic_capture["seq"] + 1, result=result)
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
                            "ESP erreichbar, aber das Bild ist älter als 15 Minuten oder hat einen ungültigen Zeitstempel."
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
                        # SLFork's raw camera image can have completely different
                        # coordinates from its processed alg.jpg. Try detecting
                        # the digit strip on the full raw image first, even if
                        # the normal processed-image crop is saved manually.
                        detect_raw = crop_rules["crop_mode"] == "auto" or (raw_fallback and not manual)
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
                        # Whole degrees stay in ``rotation`` (saved geometry); the image itself is turned
                        # by the set 0.1° remainder plus the tilt the app measured over recent checks.
                        skew_key = None
                        skew_state = {}
                        view_rotation = rotation
                        if crop_rules["crop_mode"] == "manual" and not detect_raw:
                            view_rotation = rotation + valid_fine_rotation(crop_rules.get("rotation_fine", 0))
                            if not manual and custom_boxes:
                                # Not tied to the frame revision: re-placing a single frame (e.g. the
                                # last digit) keeps the learned tilt instead of starting from zero.
                                skew_key = [crop_rules["crop"], manual_width, rotation,
                                            valid_fine_rotation(crop_rules.get("rotation_fine", 0))]
                                skew_state = updated.get("skew")
                                if not isinstance(skew_state, dict) or skew_state.get("key") != skew_key:
                                    # New geometry: start from the tilt the setup measured.
                                    skew_state = initial_skew_state(skew_key, crop_rules.get("skew_seed"))
                                view_rotation += skew_offset(skew_state)

                        def prepare_register(original, current_overlay):
                            if base_adjustment:
                                return select_tilted_register(
                                    original, manual_crop, manual_width, view_rotation, base_adjustment,
                                    integer_digits, fraction_digits, detect_raw,
                                )
                            return select_register(
                                original, current_overlay, manual_crop, manual_width, view_rotation,
                                integer_digits, fraction_digits, detect_raw=detect_raw, digit_boxes=custom_boxes,
                            )

                        register, integer_width, whole_boxes, fraction_boxes, source = prepare_register(
                            frame, selected_overlay
                        )
                        tilt_measured, tilt_skip = None, None
                        if skew_key is None:
                            tilt_skip = "no_frames" if crop_rules["crop_mode"] == "manual" else "auto_crop"
                        elif base_adjustment:
                            tilt_skip = "learned_rotation"
                        else:
                            try:
                                # All digits except the turning last roller. A digit whose right
                                # neighbour shows 8 or 9 is already lifted by the carry, so it is left out.
                                tilt_boxes = [*whole_boxes, *fraction_boxes][:max(0, integer_digits + fraction_digits - 1)]
                                counter_now = (source_history.get("consumption") or {}).get("reading_litres")
                                shown = (str(counter_now).zfill(integer_digits + 3)[:integer_digits + fraction_digits]
                                         if type(counter_now) is int else "")
                                lifted = {index for index in range(len(tilt_boxes))
                                          if index + 1 < len(shown) and shown[index + 1] in "89"}
                                tilt_measured = digit_row_tilt(register, tilt_boxes, skip=lifted)
                                tilt_skip = None if tilt_measured is not None else f"unmeasured:{len(whole_boxes)}"
                                updated["skew"] = note_skew(skew_state, tilt_measured)
                            except (OSError, ValueError, ZeroDivisionError) as error:
                                tilt_skip = type(error).__name__
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
                                whole_range=None if manual else glyph_whole_range(
                                    history, active_rules, zone, read_state["captured"]),
                            )

                        def read(profile):
                            if live_source and (manual or not standalone) and read_state["attempts"]:
                                remaining = live_deadline - time.monotonic()
                                if remaining <= 0:
                                    return "?"
                                latest = capture_camera(
                                    camera, reference, token, zone,
                                    timeout=min(8, max(0.2, remaining)),
                                    light=capture_light(active_source, camera, token),
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
                                             reading=ocr_readings[-1] if ocr_readings else None,
                                             readings=ocr_readings)
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
                        exact_partial = stationary_partial and not manual

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
                            exact_prefix=exact_partial,
                        )
                        regular_status, _ = compare_sample(sample, ocr, comparison_decimals,
                                                           ocr_confirmed=ocr_confirmed, integer_digits=integer_digits,
                                                           exact_prefix=exact_partial)
                        same_frame = read_state["frame_reads"]
                        observed = same_frame[-1] if same_frame else ""
                        pattern = disputed_digit_pattern(same_frame, comparison_decimals, integer_digits,
                                                         SHIFTED_DIGIT_POSITIONS)
                        paused_now = not manual and get_auto_paused()
                        near_hit = (digit_probe_enabled and regular_status != "match"
                                    and read_state["captured"] is not None and not sample.get("reference_is_fallback")
                                    and (pattern or not ocr_confirmed
                                         and missing_digit_pattern(observed, comparison_decimals, integer_digits,
                                                                   SHIFTED_DIGIT_POSITIONS))
                                    and not paused_now)
                        recovery_log = {"tried": near_hit}
                        if not near_hit:
                            recovery_log["reason"] = (
                                "matched" if regular_status == "match" else
                                "confirmed" if ocr_confirmed else
                                "disabled" if not digit_probe_enabled else
                                "paused" if paused_now else
                                "no_capture_time" if read_state["captured"] is None else
                                "fallback_reference" if sample.get("reference_is_fallback") else
                                "too_many_unclear")
                        if near_hit:
                            layout = tuple(read_state[key] for key in (
                                "register", "integer_width", "whole_boxes", "fraction_boxes",
                            ))
                            # Only digits that are really missing get extra reads, up to SHIFTED_DIGIT_READS.
                            budget = ocr_attempts + SHIFTED_DIGIT_READS
                            recovery_started = time.monotonic()
                            recovery_reads = ocr_attempts
                            # Own budget on the image already taken: the live capture window (fresh
                            # pictures for a moving meter) is usually used up by the regular reads.
                            # 0.4.0: planned from the measured seconds per read on this machine.
                            optimizer_state = updated.setdefault("optimizer", {})
                            if not isinstance(optimizer_state, dict):
                                optimizer_state = updated["optimizer"] = {}
                            recovery_seconds = max(DIGIT_RECOVERY_SECONDS, optimizer.recheck_seconds(optimizer_state))
                            digit_deadline = recovery_started + recovery_seconds

                            def stop_recovery():
                                return (not manual and get_auto_paused()) or time.monotonic() >= digit_deadline

                            def report_digit(attempts, box=None, evidence=None, position=None):
                                if box is not None and pattern:
                                    if position is None:
                                        position = pattern.index("?")
                                    candidate = {
                                        "position": position + (position < integer_digits), "box": box,
                                        "angle": view_rotation + base_adjustment, "evidence": evidence,
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
                            pattern = (disputed_digit_pattern(same_frame, comparison_decimals, integer_digits,
                                                              SHIFTED_DIGIT_POSITIONS)
                                       or single_missing_digit(observed, same_frame, comparison_decimals, integer_digits,
                                                               SHIFTED_DIGIT_POSITIONS))
                            optimizable = (bool(custom_boxes) and crop_rules["crop_mode"] == "manual" and not detect_raw
                                           and not base_adjustment and not raw_fallback
                                           and read_state["picture"] is not None and len(same_frame) >= 2)
                            if optimizable and not stop_recovery():
                                # (1) angle ±1°/±2°, (2) decimal frames up/down – resumed on the next picture.
                                optimizer.plan(optimizer_state, geometry_check_key(active_rules, source_key))
                                planned = optimizer.next_trials(optimizer_state, optimizer.trials_per_image(optimizer_state))
                                required_slots = integer_digits + comparison_decimals
                                base_rows = list(same_frame[:2])
                                done = 0
                                trial_log = []
                                left, top, right, bottom = manual_crop
                                try:
                                    with Image.open(io.BytesIO(read_state["picture"])) as original:
                                        for trial in planned:
                                            if stop_recovery():
                                                break
                                            geometry = optimizer.trial_geometry(
                                                trial, view_rotation, custom_boxes, layout[0].height, integer_digits)
                                            done += 1
                                            if geometry is None:
                                                continue
                                            angle, boxes = geometry
                                            width = manual_width if angle == view_rotation else min(
                                                manual_width, rotated_width(right - left, bottom - top, angle))
                                            done_now, total = optimizer.progress(optimizer_state)
                                            set_activity("working", OPTIMIZER_STATUS.format(
                                                done=done_now + done, total=total, trial=optimizer.describe(trial)),
                                                completed=ocr_attempts, total=budget, reading=observed)
                                            try:
                                                trial_register = select_register(
                                                    original, None, manual_crop, width, angle,
                                                    integer_digits, fraction_digits, digit_boxes=boxes,
                                                )
                                                values = [read_layout(trial_register[:4], profile)
                                                          for profile in OCR_PROFILES[:2]]
                                            except (OSError, ValueError, subprocess.SubprocessError):
                                                continue
                                            ocr_attempts += 2
                                            trial_sure, base_sure, contradiction = optimizer.note_result(
                                                optimizer_state, trial, values, base_rows, required_slots)
                                            trial_log.append([trial, trial_sure, base_sure, contradiction])
                                            optimizer_state["height"] = layout[0].height
                                            prefix = meter_prefix(values[0], comparison_decimals, integer_digits)
                                            if (not contradiction and prefix is not None
                                                    and prefix == meter_prefix(values[1], comparison_decimals, integer_digits)
                                                    and compare_sample(sample, values[0], comparison_decimals,
                                                                       integer_digits=integer_digits,
                                                                       exact_prefix=exact_partial)[0] in ("match", "ocr_only")):
                                                ocr, ocr_confirmed, ocr_readings = values[0], True, values
                                                ocr_method = "optimizer"
                                                reg, width_now, whole_now, fraction_now, kind = trial_register
                                                read_state.update(register=reg, integer_width=width_now,
                                                                  whole_boxes=whole_now, fraction_boxes=fraction_now,
                                                                  source=kind)
                                                regular_status = compare_sample(
                                                    sample, ocr, comparison_decimals, integer_digits=integer_digits,
                                                    exact_prefix=exact_partial,
                                                )[0]
                                                break
                                except (OSError, ValueError, Image.DecompressionBombError):
                                    pass
                                optimizer.advance(optimizer_state, done)
                                done_now, total = optimizer.progress(optimizer_state)
                                recovery_log["plan"] = {"trials": trial_log, "done": done_now, "total": total,
                                                        "rounds": optimizer_state.get("rounds", 0),
                                                        "resume": done_now > 0 and done_now < total}
                                ocr_limit = max(ocr_limit, ocr_attempts)
                            if pattern and not ocr_confirmed:
                                register_for_digit = layout[0]
                                polarity = active_rules["polarity"]

                                def read_shifted(box, profile):
                                    return read_digit(register_for_digit, box, lambda picture, digits: read_register(
                                        picture, options["helle_ziffern"] if polarity == "auto" else polarity == "light",
                                        digits, profile=profile, force_polarity=polarity != "auto", deadline=digit_deadline,
                                        isolated_digit=True,
                                    ))

                                recovery, used = recover_single_digit(
                                    layout, pattern, observed, integer_digits, fraction_digits, read_shifted,
                                    budget - ocr_attempts, report_digit, stop_recovery,
                                    lambda candidate: compare_sample(
                                        sample, candidate, comparison_decimals, integer_digits=integer_digits,
                                        exact_prefix=exact_partial,
                                    )[0] in ("match", "ocr_only"),
                                    veto=lambda box, digit: template_veto(
                                        register_for_digit, box, digit, polarity,
                                        options["helle_ziffern"] if polarity == "auto" else polarity == "light"),
                                )
                                ocr_attempts += used
                                ocr_limit = budget
                                if recovery:
                                    ocr, whole, fraction = recovery
                                    ocr_confirmed, ocr_readings = True, [ocr, ocr]
                                    ocr_method = "shifted"
                                    read_state.update(whole_boxes=whole, fraction_boxes=fraction)
                                    shifted_trial = learnable_shift(
                                        local_enabled and bool(custom_boxes) and read_state["captured"] is not None,
                                        geometry_check_key(active_rules, source_key), rotation + rotation_adjustment,
                                        [*whole, *fraction], read_state["register"].size,
                                        meter_prefix(ocr, comparison_decimals, integer_digits))
                                    regular_status = compare_sample(
                                        sample, ocr, comparison_decimals, integer_digits=integer_digits,
                                        exact_prefix=exact_partial,
                                    )[0]
                            if not ocr_confirmed and custom_boxes and not stop_recovery():
                                # Still unclear: move the whole row of frames a little (the camera
                                # image shifts slightly between captures) and read again. Accept only
                                # two agreeing profiles, no cut-off digits and a plausible value.
                                register_now, width_now, whole_now, fraction_now = layout
                                boxes_now = [*whole_now, *fraction_now]
                                if boxes_now:
                                    box_width = boxes_now[0][2] - boxes_now[0][0]
                                    box_height = boxes_now[0][3] - boxes_now[0][1]
                                    shifts = [(0, -max(1, box_height // 8)), (0, max(1, box_height // 8)),
                                              (-max(1, box_width // 10), 0), (max(1, box_width // 10), 0)]
                                    for dx, dy in shifts[:ROW_SHIFT_TRIALS]:
                                        if ocr_attempts + 2 > budget + ROW_SHIFT_READS or stop_recovery():
                                            break
                                        moved = [(left + dx, top + dy, right + dx, bottom + dy)
                                                 for left, top, right, bottom in boxes_now]
                                        if any(box[0] < 0 or box[1] < 0 or box[2] > register_now.width
                                               or box[3] > register_now.height for box in moved):
                                            continue
                                        # The last roller is allowed to be cut (it turns); the others not.
                                        if any(glyph_clipped(register_now, box) for box in moved[:-1]):
                                            continue
                                        moved_whole, moved_fraction = moved[:len(whole_now)], moved[len(whole_now):]
                                        try:
                                            values = [read_visible_digits(
                                                register_now, width_now, moved_whole, moved_fraction,
                                                options["helle_ziffern"], active_rules["polarity"], profile=profile,
                                                whole_digits=integer_digits, fraction_digits=fraction_digits,
                                                prefer_boxes=True, deadline=digit_deadline,
                                            ) for profile in OCR_PROFILES[:2]]
                                        except (OSError, subprocess.SubprocessError):
                                            continue
                                        ocr_attempts += 2
                                        if (values[0] != values[1]
                                                or meter_prefix(values[0], comparison_decimals, integer_digits) is None
                                                or compare_sample(sample, values[0], comparison_decimals,
                                                                  integer_digits=integer_digits,
                                                                  exact_prefix=exact_partial)[0] not in ("match", "ocr_only")):
                                            continue
                                        ocr, ocr_confirmed, ocr_readings = values[0], True, values
                                        ocr_method = "row_shifted"
                                        read_state.update(whole_boxes=moved_whole, fraction_boxes=moved_fraction)
                                        shifted_trial = learnable_shift(
                                            local_enabled and read_state["captured"] is not None,
                                            geometry_check_key(active_rules, source_key), rotation + rotation_adjustment,
                                            moved, register_now.size,
                                            meter_prefix(ocr, comparison_decimals, integer_digits))
                                        regular_status = compare_sample(
                                            sample, ocr, comparison_decimals, integer_digits=integer_digits,
                                            exact_prefix=exact_partial,
                                        )[0]
                                        break
                                ocr_limit = max(ocr_limit, ocr_attempts)
                            recovery_spent = time.monotonic() - recovery_started
                            optimizer.note_read_time(optimizer_state, recovery_spent, ocr_attempts - recovery_reads)
                            recovery_log.update(
                                pattern=pattern or None, reads=ocr_attempts - recovery_reads,
                                seconds=round(recovery_spent, 1), budget=recovery_seconds,
                                read_s=optimizer_state.get("read_s"),
                                result=ocr_method if ocr_method in ("shifted", "row_shifted", "optimizer") else (
                                    "timeout" if time.monotonic() >= digit_deadline else "unclear"))
                        if digit_probe_enabled and not ocr_confirmed:
                            # A moving meter can show different digits on separate photographs.
                            ocr_readings = same_frame
                            counter = source_history.get("consumption")
                            counter = counter if isinstance(counter, dict) else {}
                            # The last confirmed reading rules out impossible whole digits (an 8 read as 6).
                            allowed = plausible_integer_digits(
                                counter.get("anchor_litres"), counter.get("anchor_time"), time.time(),
                                active_rules["max_flow_lph"], integer_digits,
                            )
                            ocr, ocr_confirmed = resolve_ocr_readings(
                                ocr_readings, comparison_decimals, integer_digits, standalone=require_consensus,
                                standalone_composition=True, allowed=allowed,
                            )
                            if allowed and not ocr_confirmed:
                                # The anchor itself may be a misread (20.11.: 10491.4 booked while the
                                # meter showed 10490.6). Readings that agree on a LOWER value must still
                                # reach the misread correction (lower_series) instead of being blanked.
                                plain, plain_confirmed = resolve_ocr_readings(
                                    ocr_readings, comparison_decimals, integer_digits,
                                    standalone=require_consensus, standalone_composition=True,
                                )
                                whole = (int(plain[:integer_digits]) if plain[:integer_digits].isdigit()
                                         and len(plain) >= integer_digits else None)
                                if whole is not None and whole < counter["anchor_litres"] // 1000:
                                    # Whole digits agree on a lower value; unclear trailing decimals are
                                    # handled by the coarser check below as usual.
                                    print(f"Lesung {plain} liegt unter dem gespeicherten Stand – zur Prüfung auf Lesefehler")
                                    ocr, ocr_confirmed = plain, plain_confirmed
                            if ocr_confirmed and ocr not in ocr_readings:
                                ocr_method = "composed"
                            regular_status = compare_sample(
                                sample, ocr, comparison_decimals, ocr_confirmed=ocr_confirmed, integer_digits=integer_digits,
                                exact_prefix=exact_partial,
                            )[0]
                        if local_enabled:
                            required = integer_digits + comparison_decimals
                            rows = [str(value).replace(".", "").replace(",", "")[:required] for value in ocr_readings]
                            weak = uncertain_slots(rows, required) if len(rows) >= 2 else []
                            if comparison_decimals == 3:
                                # Never move the last roller sideways (half digits); it has its own search.
                                weak = [slot for slot in weak if slot != required - 1]
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
                                        angle = view_rotation + base_adjustment + adjustment
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
                                                     reading=ocr_readings[-1] if ocr_readings else None,
                                                     readings=ocr_readings)
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
                                                          integer_digits=integer_digits,
                                                          exact_prefix=exact_partial)[0] not in ("match", "ocr_only"):
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
                                            original, manual_crop, manual_width, view_rotation, adjustment,
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
                                        exact_prefix=exact_partial,
                                    )
                                    ocr_attempts += attempts
                                    if attempts:
                                        rotation_trials += 1
                                    rotated_status, _ = compare_sample(
                                        sample, value, comparison_decimals, ocr_confirmed=confirmed,
                                        integer_digits=integer_digits, exact_prefix=exact_partial,
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
                        if (not manual and not ocr_confirmed and not raw_fallback and ocr_readings
                                and not sample.get("reference_is_fallback") and read_state["captured"] is not None):
                            anchor = history.get("reflection_anchor")
                            anchored = anchored_leading_digits(
                                ocr_readings, anchor, read_state["captured"], comparison_decimals,
                                integer_digits, active_rules["max_flow_lph"],
                            )
                            hidden_slots = hidden_reflection_slots(active_rules, active_source)
                            if not anchored and hidden_slots:
                                anchor = newest_anchor(anchor, manual_reading_anchor(active_rules, zone),
                                                       read_state["captured"])
                                anchored = anchored_hidden_digits(
                                    ocr_readings, anchor, read_state["captured"], comparison_decimals,
                                    integer_digits, active_rules["max_flow_lph"], hidden_slots,
                                )
                                if anchored:
                                    updated.pop("hidden_digit_prompt", None)
                                elif anchor is None:
                                    # No verified or entered reading to fill the hidden digit from: ask once.
                                    updated["hidden_digit_prompt"] = {
                                        "positions": [slot + 1 for slot in hidden_slots], "time": time.time()}
                            if anchored:
                                anchored_readings, filled_positions = anchored
                                value, confirmed = resolve_ocr_readings(
                                    anchored_readings, comparison_decimals, integer_digits,
                                    standalone=require_consensus, standalone_composition=True,
                                )
                                if confirmed and within_anchor_bounds(
                                        value, anchor, read_state["captured"], comparison_decimals,
                                        integer_digits, active_rules["max_flow_lph"]):
                                    print(f"Führende Stelle(n) {', '.join(str(p + 1) for p in filled_positions)} "
                                          f"aus bestätigtem Stand ergänzt: {ocr} -> {value}")
                                    ocr, ocr_confirmed, ocr_readings = value, True, anchored_readings
                                    ocr_method = "anchored"
                            flow_limit = learned_flow_limit(history, active_rules["max_flow_lph"])
                            slow_anchor = history.get("reflection_anchor")
                            slow = (None if ocr_confirmed else slow_roller_digit(
                                ocr_readings, slow_anchor, read_state["captured"], comparison_decimals,
                                integer_digits, flow_limit))
                            if slow:
                                slow_readings, _ = slow
                                value, confirmed = resolve_ocr_readings(
                                    slow_readings, comparison_decimals, integer_digits,
                                    standalone=require_consensus, standalone_composition=True,
                                )
                                if confirmed and within_anchor_bounds(
                                        value, slow_anchor, read_state["captured"], comparison_decimals,
                                        integer_digits, flow_limit):
                                    print(f"Erste Nachkommastelle aus bestätigtem Stand und Durchfluss "
                                          f"(≤ {flow_limit} l/h) ergänzt: {ocr} -> {value}")
                                    ocr, ocr_confirmed, ocr_readings = value, True, slow_readings
                                    ocr_method = "slow_roller"
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
                                                           integer_digits=integer_digits, exact_prefix=stationary_partial)
                        reduced_precision = False
                        reduced_by = 0
                        drop = (unclear_trailing_decimals(ocr, decimals, integer_digits)
                                if reading_status == "ocr_unclear" and decimals > 0 and not ocr_error else 0)
                        if drop:
                            # The last one or two compared rollers are unreadable (typically turning
                            # while gas flows): accept this one check that much coarser instead of
                            # failing. The truncated value is a safe lower bound for booking.
                            coarse, coarse_confirmed = resolve_ocr_readings(
                                ocr_readings or [ocr, ocr], decimals - drop, integer_digits,
                                standalone=require_consensus, standalone_composition=True,
                            )
                            coarse_status, _ = compare_sample(sample, ocr, decimals - drop, ocr_confirmed=coarse_confirmed,
                                                              integer_digits=integer_digits, exact_prefix=True)
                            if coarse_confirmed and coarse_status in ("match", "ocr_only"):
                                print(f"Hintere {drop} Stelle(n) unklar ({ocr}), prüfe diesmal mit "
                                      f"{decimals - drop} Nachkommastelle(n)")
                                decimals -= drop
                                reduced_by = drop
                                reading_status, ocr_confirmed, reduced_precision = coarse_status, True, True
                        accept_reference = (
                            decimals == 3 and reading_status in ("difference", "ocr_unclear")
                            and last_digit_can_pass(updated, precision_mode)
                            and differs_only_at_last_digit(sample, ocr, ocr_readings, integer_digits)
                        )
                        if (reading_status == "match" or accept_reference
                                or ((standalone or raw_fallback) and reading_status == "ocr_only")):
                            for allow_lower in (False, True):
                                try:
                                    if standalone:
                                        # Plausibility against the last *confirmed* value lives in
                                        # accumulate_consumption; an unconfirmed misread must not block.
                                        new_standalone = standalone_reading(
                                            standalone_source, sample, ocr, decimals, None, integer_digits,
                                        )
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
                                            if history.get("statistics_preserved_after_reset"):
                                                # A new image source establishes a fresh meter-reading baseline,
                                                # but must not reset the preserved cumulative consumption total.
                                                setup_counter["total_litres"] = previous_consumption.get("total_litres", 0)
                                            previous_consumption = setup_counter
                                    new_consumption = accumulate_consumption(
                                        previous_consumption, source_key, captured,
                                        sample["actual_value"] if accept_reference else ocr, decimals,
                                        active_rules["max_flow_lph"], integer_digits, allow_lower=allow_lower,
                                        confirmed=reading_status == "match" or accept_reference,
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
                                                active_rules["max_flow_lph"], integer_digits, allow_lower=allow_lower,
                                                require_consistent=True,
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
                                    if (str(error) == LOWER_READING and not allow_lower and not raw_fallback
                                            and not accept_reference and captured is not None
                                            and plausible_lower_drop(history.get("consumption"), captured, ocr,
                                                                     decimals, active_rules["max_flow_lph"],
                                                                     integer_digits)):
                                        lower_series, lower_confirmed = track_lower_series(
                                            history.get("lower_series"), captured, ocr, decimals,
                                            active_rules["max_flow_lph"], integer_digits,
                                        )
                                        updated["lower_series"] = lower_series
                                        if lower_confirmed:
                                            print(f"Lesefehler-Korrektur: {len(lower_series)} stimmige niedrigere "
                                                  f"Ablesungen, übernehme {ocr}")
                                            debug_log.record(kind="correction", ocr=ocr, lower_series=len(lower_series))
                                            continue
                                        error = ImplausibleReading(LOWER_PENDING)
                                    ocr_confirmed = False
                                    rejected = standalone and updated.pop("standalone_candidate", None)
                                    validation_detail = (f"{STANDALONE_REJECTED_NOTICE} {error}" if rejected else str(error))
                                    new_standalone = new_consumption = None
                                else:
                                    if allow_lower:
                                        lower_recovered = True
                                    if new_consumption is not None:
                                        # Only a committed reading ends the series; with
                                        # standalone checks the second image commits.
                                        updated.pop("lower_series", None)
                                break
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
                        if active_rules.get("experiments_enabled"):
                            # Plain digit strip (window only, no labels) for /testbild-streifen.
                            with io.BytesIO() as buffer:
                                register.convert("RGB").save(buffer, "PNG")
                                atomic_write(HISTORY.with_name("ocr-ziffernstreifen.png"), buffer.getvalue(), 0o600)
                    except (OSError, ValueError) as error:
                        print(f"Automatische OCR-Vorschau konnte nicht erstellt werden: {error}")
                if source == "manual":
                    unclear_detail = RAW_ROW_UNCLEAR if detect_raw else MANUAL_ROW_UNCLEAR
                    shown = str(ocr or "").replace(".", "")[:integer_digits + max(0, decimals)]
                    if not detect_raw and shown and shown.count("?") <= 3 and sum(ch.isdigit() for ch in shown) >= 4:
                        unclear_detail = PARTLY_UNCLEAR
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
                        if ocr_attempts >= LAST_DIGIT_RETRIES:
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
                                   precision_mode=precision_mode, exact_prefix=stationary_partial):
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
                            preserve_on_source_change=bool(history.get("statistics_preserved_after_reset")),
                        )
                        updated.pop("statistics_preserved_after_reset", None)
                    if raw_fallback and outcome == "ocr_only":
                        updated["source_connection_detail"] = SLFORK_RAW_SUCCESS
                    if new_standalone is not None:
                        updated["standalone_reading"] = new_standalone
                    if lower_recovered and new_consumption is not None and outcome in SUCCESSFUL_CHECKS:
                        updated["check_detail"] = LOWER_RECOVERED
                    if (locals().get("reduced_precision") and outcome in SUCCESSFUL_CHECKS
                            and not validation_detail and not lower_recovered):
                        updated["check_detail"] = (REDUCED_PRECISION2_NOTICE if locals().get("reduced_by") == 2
                                                   else REDUCED_PRECISION_NOTICE)
                    updated["ocr_readings"] = ocr_readings if outcome == "ocr_unclear" else []
                    if outcome == "ocr_unclear" and updated["check_detail"] != LAST_DIGIT_NOTICE:
                        if not validation_detail and not ocr_error and only_last_compared_unclear(
                                ocr, comparison_decimals if "comparison_decimals" in locals() else decimals,
                                integer_digits):
                            unclear_detail = MOVING_DIGIT_NOTICE
                        elif (not validation_detail and not ocr_error and unclear_trailing_decimals(
                                ocr, comparison_decimals if "comparison_decimals" in locals() else decimals,
                                integer_digits) == 2):
                            unclear_detail = MOVING_DIGITS_NOTICE
                        updated["check_detail"] = (validation_detail or ocr_error or unclear_detail
                                                   or explain_uncertain_positions(ocr_readings, decimals, integer_digits))
                    elif validation_detail:
                        updated["check_detail"] = validation_detail
                    if ((locals().get("reduced_precision") and locals().get("reduced_by") == 1
                            and outcome in SUCCESSFUL_CHECKS)
                            or updated.get("check_detail") == MOVING_DIGIT_NOTICE):
                        streak = updated.get("last_position_unclear_streak", 0)
                        streak = (streak if type(streak) is int else 0) + 1
                        updated["last_position_unclear_streak"] = streak
                        if streak >= FRAME_OFF_STREAK and not validation_detail and not lower_recovered:
                            relocatable = active_rules["decimals"] == 3 and active_rules["fraction_digits"] == 3
                            updated["check_detail"] = FRAME_OFF_NOTICE if relocatable else FRAME_OFF_WAIT_NOTICE
                            if relocatable:
                                updated["last_digit_relocate_due"] = True
                    elif outcome in SUCCESSFUL_CHECKS:
                        updated.pop("last_position_unclear_streak", None)
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
                    if (outcome == "ocr_only" and standalone_reference is not None
                            and type(image_time) in (int, float)):
                        # A reading confirmed with a second image counts as a confirmed comparison.
                        updated["last_match_at"] = image_time
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
                    exhausted_ocr = (outcome in ("ocr_unclear", "difference") and not validation_detail
                                     and not ocr_error and ocr_attempts > 0 and not raw_fallback
                                     and ((outcome == "ocr_unclear" and not ocr_confirmed)
                                          or failed_angle_requires_fresh_image(rotation_trials, outcome)))
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
                    # A frame that reads a value confirmed by a second picture is the starting point
                    # for any later setup (also when the setup wizard is run again).
                    if ((verified or outcome == "ocr_only") and not stationary_partial and source == "manual"
                            and active_rules["crop_mode"] == "manual" and not raw_fallback):
                        with settings_lock:
                            if get_auto_rules() == active_rules and get_source()[0] == active_source:
                                remember_known_good_layout(active_rules, active_source,
                                                           geometry_layout(active_rules, active_rules))
                        try:
                            # 0.4.0: learn this meter's digit shapes from cells both profiles agreed on.
                            library_learned = learn_confirmed_digits(
                                read_state["register"], [*read_state["whole_boxes"], *read_state["fraction_boxes"]],
                                ocr_readings or [], ocr,
                                options["helle_ziffern"] if active_rules["polarity"] == "auto"
                                else active_rules["polarity"] == "light",
                                skip_last=fraction_digits == 3)
                        except (OSError, ValueError, KeyError, TypeError, NameError):
                            library_learned = 0
                    if (adaptive and not optimization_paused and outcome in ("match", "ocr_only") and not raw_fallback
                            and not locals().get("reduced_precision") and decimals == fraction_digits):
                        # Learn the flow from the ESP value or, for camera sources, from the reading
                        # confirmed with a second image. Coarser partial checks are not used.
                        flow = updated.setdefault("adaptive_flow", {})
                        reference_value = sample.get("actual_value") if outcome == "match" else ocr
                        if (reference_value is not None and compare_sample(
                                sample, reference_value, fraction_digits, integer_digits=integer_digits)[0] in ("match", "ocr_only")):
                            observe_flow(flow, source_key, image_time, reference_value, fraction_digits,
                                         integer_digits, now.month, active_rules["max_flow_lph"])
                        interval_minutes = suggested_interval(
                            automatic_interval_minutes(active_rules["interval_minutes"], mode), flow, source_key, now.month,
                        )
                    local_backup = updated.get("local_geometry_backup", {})
                    if (not optimization_paused and (active_rules["fine_alignment_enabled"] or local_backup.get("optimizer"))
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
                                if local_backup.get("optimizer"):
                                    debug_log.record(kind="optimize_rollback", rotation=local_backup["rotation"],
                                                     reason="zwei Fehlprüfungen nach der Übernahme")
                    optimizer_state = updated.get("optimizer")
                    winner = (optimizer.best_trial(optimizer_state) if isinstance(optimizer_state, dict)
                              and optimizer_state.get("key") == geometry_check_key(active_rules, source_key) else None)
                    if (winner and fine_update is None and not optimization_paused and not raw_fallback
                            and active_rules.get("digit_boxes") and active_rules["crop_mode"] == "manual"):
                        geometry = optimizer.trial_geometry(
                            winner, active_rules["rotation"], active_rules["digit_boxes"],
                            optimizer_state.get("height") or 1000, integer_digits)
                        if geometry is not None:
                            fine_rotation, fine_update = geometry
                            optimizer_saved = True
                            debug_log.record(kind="optimize_saved", trial=winner, reason=optimizer.describe(winner),
                                             stats=optimizer_state["stats"].get(winner),
                                             old={"rotation": active_rules["rotation"],
                                                  "digit_boxes": active_rules["digit_boxes"]},
                                             new={"rotation": fine_rotation, "digit_boxes": fine_update})
                            updated["optimizer"] = {"read_s": optimizer_state.get("read_s")}
                    if local_trial is None and shifted_trial is not None:
                        # A frame shift that rescued this check is learned under the same rules as the
                        # local fine alignment: three fresh images, two meter readings, rollback on errors.
                        local_trial = shifted_trial
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
                    "Home-Assistant-Kamera nicht erreichbar oder Bild unlesbar. Prüfe Kamera und Zugriff."
                    if camera else "ESP nicht erreichbar oder Antwort unvollständig. Prüfe Adresse und Verbindung."
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
            if on_demand and not source_changed and history.get("next_check_at", 0) > now.timestamp():
                updated["next_check_at"] = history["next_check_at"]
        else:
            updated.pop("reflection_retry_at", None)
            updated.pop("fresh_ocr_retry_at", None)
            updated["failure_pause_minutes"] = active_rules.get("failure_pause_minutes", DEFAULT_FAILURE_PAUSE_MINUTES)
            schedule_next_check(updated, outcome, now.timestamp(), interval_minutes)
            if (on_demand and not source_changed and outcome in SUCCESSFUL_CHECKS
                    and not updated.get("seventh_digit_wait")
                    and history.get("check_status") in SUCCESSFUL_CHECKS
                    and history.get("next_check_at", 0) > now.timestamp()):
                updated["next_check_at"] = history["next_check_at"]
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
                                "optimizer": optimizer_saved,
                            }
                        if fine_rotation is not None:
                            atomic_write(HISTORY, json.dumps(updated).encode("utf-8"), 0o600)
                    except (OSError, ValueError):
                        print("Feinjustierung konnte nicht gespeichert werden.")
        set_activity("waiting", FRESH_OCR_NOTICE if updated.get("fresh_ocr_retry_at") else
                     REFLECTION_RECHECK_NOTICE if updated.get("reflection_retry_at") else
                     "Die App wartet auf den nächsten Messzyklus des ESP …" if duplicate_cycle else
                     STANDALONE_PENDING_NOTICE if outcome == STANDALONE_PENDING else
                     "Letzte Prüfung beendet. Nächster Versuch nach kurzer Wartezeit."
                     if not updated.get("retry_suppressed") and outcome not in SUCCESSFUL_CHECKS else
                     "Letzte Prüfung beendet. Wartet auf das eingestellte Prüfintervall.")
        if data is not None:
            pending_image = (data, jpeg, size)
            print(f"Kontrollbild bereit: {data['esp_timestamp']} | Ausschnitt: {source} | "
                  f"OCR: {ocr or '?'} ({data['ocr_attempts']} Durchläufe) | "
                  f"SLFork: {data['actual_value']} | Ergebnis: {outcome}")
            local = locals()
            experiment = shadow_experiments(
                active_rules, manual, local.get("register"),
                [*(local.get("whole_boxes") or []), *(local.get("fraction_boxes") or [])], ocr,
                options["helle_ziffern"] if active_rules["polarity"] == "auto" else active_rules["polarity"] == "light",
                active_rules["polarity"] != "auto")
            library_filled = digit_library.LIBRARY.take_filled()
            debug_log.record(
                library={"filled": library_filled, "learned": local.get("library_learned", 0),
                         "samples": digit_library.LIBRARY.samples()}
                if (library_filled or local.get("library_learned")) else None,
                experiment=experiment, recovery=local.get("recovery_log"),
                kind="manual" if manual else "automatic", image=data.get("esp_timestamp"), crop=source,
                ocr=ocr, readings=local.get("ocr_readings"), attempts=data.get("ocr_attempts"),
                method=local.get("ocr_method"), outcome=outcome, detail=updated.get("check_detail"),
                compared_decimals=local.get("comparison_decimals"), reference=data.get("actual_value"),
                consumption=updated.get("consumption"), failures=updated.get("failure_attempts"),
                lower_series=len(updated.get("lower_series") or []) or None,
                tilt={"offset": skew_offset(updated.get("skew")),
                      "samples": len((updated.get("skew") or {}).get("samples", [])),
                      "measured": (round(local["tilt_measured"], 2)
                                   if type(local.get("tilt_measured")) is float else None),
                      "skip": local.get("tilt_skip"),
                      "angle": local.get("view_rotation")} if "view_rotation" in local else None,
            )
        try:
            publish_check(history, now, token, review_after)
            if pending_image is not None:
                publish(*pending_image, history, now, token, review_after)
                pending_image = None
            if standalone or published_standalone:
                publish_standalone(history, standalone_source, token)
                published_standalone = standalone
            publish_consumption(history, token)
            publish_energy(history, token, get_auto_rules())
        except OSError as error:
            print(f"Home Assistant konnte nicht aktualisiert werden: {error}")
        check_reminder(reminder, history, now, review_after)
        repair_started = False
        if recover_geometry:
            with settings_lock:
                if get_auto_rules() == active_rules and get_source()[0] == active_source and not get_auto_paused():
                    try:
                        repair_started = bool(control_calibration("repair", GEOMETRY_REPAIR_LIMIT, trigger="repair"))
                    except (OSError, ValueError) as error:
                        print(f"Automatische Nachjustierung nicht gestartet: {type(error).__name__}")
        if geometry_warning and reminder.enabled:
            message = ("Seit zwei Stunden schlagen die Prüfungen fehl. Die App sucht deshalb einmal selbst nach einem besseren Ziffernrahmen. "
                       "Die bisherigen Einstellungen sind gesichert. Das Ergebnis siehst du in der App."
                       if repair_started else "Die Ziffern werden seit mindestens zwei Stunden nicht sicher erkannt. "
                                              "Prüfe in der App Bildausschnitt, Fokus und Beleuchtung.")
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
