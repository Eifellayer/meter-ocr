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
import time
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw
from websocket import WebSocketException

from checks import (
    RETRY_INTERVAL, compare_sample, crop_register, read_register, read_with_retries, record_sample,
    explain_uncertain_positions,
    rolling_summary, sample_epoch, sample_timestamp, schedule_next_check,
)
from layout import find_digit_row
from reminder import Reminder
from settings import SCHEMA_VERSION, load_options
from panel import start_panel

MAX_RESPONSE_BYTES = 3_000_000
MAX_TRANSFER_BYTES = 11_000
DESTINATION = Path("/media/rf1/kontrollbild.jpg")
GOOD_IMAGE = Path("/media/rf1/letzter_treffer.jpg")
TEST_IMAGE = Path("/data/ocr-testvorschau.jpg")
HISTORY = Path("/data/kontrollmessung.json")
OPTIONS = Path("/data/options.json")
EFFECTIVE_OPTIONS = Path("/data/rf1-settings.json")
AUTO_RULES = Path("/data/auto-pruefregeln.json")
ENTITY = "sensor.rf1_kontrollbild"
CORE_URL = f"http://supervisor/core/api/states/{ENTITY}"
CHECK_ENTITY = "sensor.rf1_pruefstatus"
Image.MAX_IMAGE_PIXELS = 4_000_000


def get_bytes(url, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with urlopen(Request(url, headers=headers), timeout=8) as response:
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
    before = json.loads(get_bytes(base + "/process_data"))
    diagnostics.update(slfork_diagnostics(before))
    picture = get_bytes(base + "/img_tmp/alg.jpg")
    try:
        overlay = get_bytes(base + "/img_tmp/alg_roi.jpg")
    except (OSError, ValueError):
        overlay = None
    after = json.loads(get_bytes(base + "/process_data"))
    diagnostics.update(slfork_diagnostics(after))
    timestamp = sequence_value(after, "timestamp_processed")
    if not timestamp:
        raise ValueError("Kein Zeitstempel vom ESP")
    if sequence_value(before, "timestamp_processed") != timestamp:
        return None
    return picture, overlay, {
        "esp_timestamp": timestamp,
        "raw_value": sequence_value(after, "raw_value"),
        "actual_value": sequence_value(after, "actual_value"),
        **diagnostics,
    }


def capture_camera(camera, reference, token, zone):
    base = "http://supervisor/core/api"
    picture = get_bytes(f"{base}/camera_proxy/{camera}", token)
    captured = datetime.now(zone)
    value = None
    if reference:
        try:
            state = json.loads(get_bytes(f"{base}/states/{reference}", token))
            reported = datetime.fromisoformat(state.get("last_reported") or state["last_updated"])
            if (state.get("attributes", {}).get("unit_of_measurement") == "m³"
                    and abs((captured - reported).total_seconds()) <= 5 * 60):
                value = state["state"]
        except (OSError, ValueError, KeyError) as error:
            print(f"Referenzsensor konnte nicht gelesen werden: {type(error).__name__}")
    return picture, None, {
        "esp_timestamp": captured.isoformat(),
        "raw_value": value,
        "actual_value": value,
        "reference_required": bool(reference),
        "image_source": "home_assistant_camera",
    }


def select_register(frame, overlay, manual_crop, manual_width):
    if overlay is not None:
        try:
            with Image.open(io.BytesIO(overlay)) as annotated:
                if annotated.size == frame.size:
                    layout = find_digit_row(annotated)
                    if layout is not None:
                        crop, width, boxes = layout
                        return crop_register(frame, crop), width, boxes[:5], boxes[5:], "auto"
        except (OSError, ValueError, Image.DecompressionBombError):
            pass
    register = crop_register(frame, manual_crop)
    if not 0 < manual_width <= register.width:
        raise ValueError("vorkomma_breite liegt außerhalb des Ausschnitts")
    # Ohne Rahmen teilt der konfigurierte Ausschnitt den Rest in drei Rollen.
    right_width = register.width - manual_width
    boundaries = [manual_width + right_width * i // 3 for i in range(4)]
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


def read_visible_digits(register, integer_width, whole_boxes, fraction_boxes, light_digits, polarity, *, profile):
    if polarity != "auto":
        light_digits = polarity == "light"

    def read(picture, digits=5):
        return read_register(picture, light_digits, digits, force_polarity=polarity != "auto", profile=profile)

    whole = read(register.crop((0, 0, integer_width, register.height)))
    if whole is None:
        whole = "".join(read_digit(register, box, read, trim_vertical=True)
                        for box in whole_boxes).ljust(5, "?")
    fraction = "".join(read_digit(register, box, read) for box in fraction_boxes[:3])
    return f"{whole}.{fraction.ljust(3, '?')}"


def draw_test_preview(register, integer_width, whole_boxes, fraction_boxes, reading):
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
    boxes = list(whole_boxes[:5]) if len(whole_boxes) >= 5 else [
        (whole_width * i // 5, 0, whole_width * (i + 1) // 5, h)
        for i in range(5)
    ]
    fraction = list(fraction_boxes[:3])
    if not fraction and whole_width < w:
        fraction = [
            (whole_width + (w - whole_width) * i // 3, 0,
             whole_width + (w - whole_width) * (i + 1) // 3, h)
            for i in range(3)
        ]
    chars = (str(reading or "").split(".", 1)[0].ljust(5, "?")[:5]
             + str(reading or "").split(".", 1)[-1].ljust(3, "?")[:3]
             if "." in str(reading or "") else str(reading or "").ljust(8, "?")[:8])
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


def publish(data, jpeg, size, history, now, token):
    digest = hashlib.sha256(jpeg).hexdigest()
    payload = {
        "state": data["esp_timestamp"],
        "attributes": {
            "friendly_name": "RF1 Kontrollbild",
            **data,
            **rolling_summary(history, now),
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


def publish_check(history, now, token):
    summary = rolling_summary(history, now)
    payload = {
        "state": "review_due" if summary["review_due"] else history["check_status"],
        "attributes": {"friendly_name": "RF1 Prüfstatus", **summary, **history.get("slfork_diagnostics", {})},
    }
    publish_state(f"http://supervisor/core/api/states/{CHECK_ENTITY}", payload, token)


def publish_state(url, payload, token):
    request = Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=10) as response:
        if response.status not in (200, 201):
            raise OSError(f"Home Assistant meldet HTTP {response.status}")


def check_reminder(reminder, history, now):
    if reminder is None:
        return
    before = json.dumps(history)
    try:
        reminder.sync(history, rolling_summary(history, now), now.timestamp())
    except (OSError, ValueError, WebSocketException) as error:
        print(f"RF1-Erinnerung konnte nicht aktualisiert werden: {type(error).__name__}")
    after = json.dumps(history)
    if after != before:
        atomic_write(HISTORY, after.encode("utf-8"), 0o600)


def main():
    raw_options = json.loads(OPTIONS.read_text(encoding="utf-8"))
    # The Supervisor remains the source of truth for values edited in its UI.
    # It regenerates options.json. Record a versioned, normalized copy separately.
    snapshot = json.loads(EFFECTIVE_OPTIONS.read_text(encoding="utf-8")) if EFFECTIVE_OPTIONS.exists() else {}
    options = load_options(raw_options, snapshot)
    atomic_write(EFFECTIVE_OPTIONS, json.dumps({
        "schema_version": SCHEMA_VERSION, "options": options,
    }, indent=2).encode("utf-8"), 0o600)
    base = options["esp_url"].rstrip("/")
    zone = ZoneInfo(options["zeitzone"])
    crop = tuple(int(part.strip()) for part in options["ausschnitt"].split(","))
    if len(crop) != 4:
        raise ValueError("ausschnitt erwartet links, oben, rechts, unten")
    token = os.environ["SUPERVISOR_TOKEN"]
    history = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else {}
    camera = (options.get("kamera_entitaet") or "").strip()
    reference = (options.get("referenz_entitaet") or "").strip()
    if camera and not re.fullmatch(r"camera\.[a-z0-9_]+", camera):
        raise ValueError("kamera_entitaet muss eine Home-Assistant-Kamera sein")
    if reference and not re.fullmatch(r"sensor\.[a-z0-9_]+", reference):
        raise ValueError("referenz_entitaet muss ein Home-Assistant-Sensor sein")
    default_decimals = options["vergleich_nachkommastellen"]
    default_attempts = options["ocr_versuche"]
    auto_rules = {"decimals": default_decimals, "attempts": default_attempts, "polarity": "auto",
                  "crop_mode": "auto", "crop": options["ausschnitt"],
                  "width": options["vorkomma_breite"]}
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
            crop_valid = (isinstance(crop_text, str) and
                          re.fullmatch(r"\d{1,4}\s*,\s*\d{1,4}\s*,\s*\d{1,4}\s*,\s*\d{1,4}", crop_text)
                          and type(width) is int and 1 <= width <= 1920)
            if crop_mode not in ("auto", "manual") or not crop_valid:
                crop_mode, crop_text, width = "auto", options["ausschnitt"], options["vorkomma_breite"]
            auto_rules = {"decimals": saved_rules["decimals"],
                          "attempts": saved_rules["attempts"], "polarity": polarity,
                          "crop_mode": crop_mode, "crop": crop_text, "width": width}
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
        if (type(values.get("decimals")) is not int or not 0 <= values["decimals"] <= 3
                or type(values.get("attempts")) is not int or not 1 <= values["attempts"] <= 10
                or values.get("polarity") not in ("auto", "light", "dark")
                or values.get("crop_mode") not in ("auto", "manual")
                or type(values.get("width")) is not int or not 1 <= values["width"] <= 1920
                or not isinstance(values.get("crop"), str)
                or not re.fullmatch(r"\d{1,4}\s*,\s*\d{1,4}\s*,\s*\d{1,4}\s*,\s*\d{1,4}", values["crop"])):
            raise ValueError("Ungültige Einstellungen für die automatische Kontrolle")
        coords = [int(part.strip()) for part in values["crop"].split(",")]
        if not (0 <= coords[0] < coords[2] <= 1920 and 0 <= coords[1] < coords[3] <= 1920
                and values["width"] <= coords[2] - coords[0]):
            raise ValueError("Ungültiger Ausschnitt oder zu große Vorkommabreite")
        updated_rules = dict(values)
        updated_rules["crop"] = ",".join(str(part) for part in coords)
        atomic_write(AUTO_RULES, json.dumps(updated_rules, indent=2).encode("utf-8"), 0o600)
        auto_rules = updated_rules

    requested = Queue(maxsize=1)
    update_progress = start_panel(
        HISTORY, DESTINATION, GOOD_IMAGE, requested, default_decimals, default_attempts,
        get_auto_rules, save_auto_rules, options["ausschnitt"], options["vorkomma_breite"], TEST_IMAGE,
    )
    push_service = (options.get("push_dienst") or "").strip()
    reminder = None
    if push_service:
        try:
            reminder = Reminder(push_service, token)
        except ValueError as error:
            print(f"RF1-Erinnerung deaktiviert: {error}")
    pending_image = None
    startup = True
    manual_options = None
    print("RF1 Kontrollmessung gestartet")
    while True:
        active_rules = get_auto_rules()
        decimals = active_rules["decimals"]
        max_attempts = active_rules["attempts"]
        now = datetime.now(zone)
        remaining = history.get("next_check_at", 0) - now.timestamp()
        if manual_options is None:
            try:
                manual_options = requested.get_nowait()
            except Empty:
                pass
        manual = manual_options is not None
        request_id = manual_options["request_id"] if manual else None
        if manual:
            update_progress(request_id, "running", "Lade Zählerbild und Referenzdaten …")
        if remaining > 0 and not startup and not manual:
            # Refresh status after a Home Assistant restart, even between checks.
            if "check_status" in history:
                try:
                    publish_check(history, now, token)
                    if pending_image is not None:
                        publish(*pending_image, history, now, token)
                        pending_image = None
                except OSError as error:
                    print(f"Prüfstatus konnte nicht übertragen werden: {error}")
                check_reminder(reminder, history, now)
            try:
                manual_options = requested.get(timeout=min(remaining, RETRY_INTERVAL))
            except Empty:
                pass
            continue

        keep_schedule = startup and remaining > 0
        startup = startup and manual
        data = None
        outcome = "capture_unavailable"
        updated = dict(history)
        # Confirmations obtained with another precision are not valid evidence
        # for the newly chosen automatic comparison rules.
        if history.get("comparison_decimals", decimals) != decimals:
            updated["confirmations"] = []
            updated.pop("last_match_at", None)
        updated["comparison_decimals"] = decimals
        updated["check_detail"] = "Das Zählerbild oder die Messwerte sind nicht verfügbar. Bitte die ESP- bzw. Kameraverbindung prüfen."
        manual_result = {"detail": updated["check_detail"]}
        diagnostics = {}
        try:
            result = capture_camera(camera, reference, token, zone) if camera else capture(base, diagnostics)
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
                if not manual and (captured is None or captured <= history.get("last_epoch", 0)):
                    outcome = "stale_sample"
                    updated["check_detail"] = "Das Bild ist zu alt oder wurde schon ausgewertet."
                    result = None
            if result is not None:
                with Image.open(io.BytesIO(picture)) as frame:
                    if frame.format != "JPEG":
                        raise ValueError("Der ESP hat kein JPEG geliefert")
                    frame.load()
                    ocr_readings = []
                    try:
                        # Manual crop is a diagnostic override for this test only.
                        manual_crop = crop
                        manual_width = options["vorkomma_breite"]
                        selected_overlay = overlay
                        if manual and manual_options.get("crop_mode") == "manual":
                            manual_crop = tuple(int(part.strip()) for part in manual_options["crop"].split(","))
                            manual_width = manual_options["width"]
                            selected_overlay = None
                        elif not manual and active_rules["crop_mode"] == "manual":
                            manual_crop = tuple(int(part.strip()) for part in active_rules["crop"].split(","))
                            manual_width = active_rules["width"]
                            selected_overlay = None
                        register, integer_width, whole_boxes, fraction_boxes, source = select_register(
                            frame, selected_overlay, manual_crop, manual_width
                        )
                        read = partial(
                            read_visible_digits,
                            register, integer_width, whole_boxes, fraction_boxes,
                            options["helle_ziffern"], manual_options["polarity"] if manual else active_rules["polarity"],
                        )
                        if manual:
                            update_progress(request_id, "ocr", f"OCR-Prüfung gestartet (max. {manual_options['attempts']} Versuche).", 0)
                        def report_ocr(attempts, message):
                            if manual:
                                update_progress(request_id, "ocr", message, attempts)
                        ocr, ocr_confirmed, ocr_attempts = read_with_retries(
                            lambda profile: read(profile=profile), sample,
                            manual_options["decimals"] if manual else decimals,
                            progress=report_ocr if manual else None,
                            max_attempts=manual_options["attempts"] if manual else max_attempts,
                            trace=ocr_readings,
                        )
                    except (OSError, ValueError, subprocess.SubprocessError) as error:
                        print(f"Lokale OCR nicht verfügbar: {error}")
                        register, ocr, source = frame, None, "unavailable"
                        ocr_confirmed, ocr_attempts = True, 0
                    if not manual:
                        jpeg, size = transfer_jpeg(register)
                if manual:
                    image_time = sample_timestamp(sample, zone)
                    already_checked = (image_time == history.get("last_epoch")
                                       or image_time in history.get("confirmations", ()))
                    status, detail = compare_sample(sample, ocr, manual_options["decimals"],
                                                    ocr_confirmed=ocr_confirmed)
                    if status == "ocr_unclear":
                        detail = explain_uncertain_positions(ocr_readings, manual_options["decimals"])
                    preview_available = False
                    if ocr_attempts and source != "unavailable":
                        try:
                            preview = draw_test_preview(register, integer_width, whole_boxes,
                                                        fraction_boxes, ocr)
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
                        "reference": sample["actual_value"],
                        "detail": detail,
                        "image_time": image_time,
                        "already_checked": already_checked,
                        "outside_window": captured is None,
                        "can_apply_crop": (manual_options["crop_mode"] == "manual"
                                           and ocr_attempts > 0 and preview_available),
                    }
                elif record_sample(updated, sample, ocr, zone, datetime.now(zone), decimals,
                                   ocr_confirmed=ocr_confirmed):
                    atomic_write(DESTINATION, picture, 0o644)
                    outcome = updated["status"]
                    if outcome == "ocr_unclear":
                        updated["check_detail"] = explain_uncertain_positions(ocr_readings, decimals)
                    if outcome == "match":
                        atomic_write(GOOD_IMAGE, picture, 0o644)
                    data = {**sample, "crop_source": source, "ocr_attempts": ocr_attempts}
                    updated["last_reference"] = sample["actual_value"]
                else:
                    outcome = "stale_sample"
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            print(f"Bildabruf fehlgeschlagen: {error}")

        now = datetime.now(zone)
        if manual:
            update_progress(request_id, "running", "Ergebnis wird gespeichert …",
                            manual_result.get("ocr_attempts", 0))
            manual_result.update(checked_at=now.timestamp(), settings=manual_options, slfork_diagnostics=diagnostics)
            manual_options = None
            history["manual_result"] = manual_result
            atomic_write(HISTORY, json.dumps(history).encode("utf-8"), 0o600)
            update_progress(request_id, "done", "Prüfung beendet.",
                            manual_result.get("ocr_attempts", 0), now.timestamp(),
                            outcome=manual_result.get("status", "capture_unavailable"),
                            detail=manual_result["detail"], preview=manual_result.get("preview", False),
                            can_apply_crop=manual_result.get("can_apply_crop", False),
                            readings=manual_result.get("readings", []))
            continue
        if keep_schedule and data is None and history.get("next_check_at", 0) > now.timestamp():
            continue
        updated["slfork_diagnostics"] = diagnostics
        schedule_next_check(updated, outcome, now.timestamp())
        atomic_write(HISTORY, json.dumps(updated).encode("utf-8"), 0o600)
        history = updated
        if data is not None:
            pending_image = (data, jpeg, size)
            print(f"Kontrollbild bereit: {data['esp_timestamp']} | Ausschnitt: {source} | "
                  f"OCR: {ocr or '?'} ({data['ocr_attempts']} Durchläufe) | "
                  f"SLFork: {data['actual_value']} | Ergebnis: {outcome}")
        try:
            publish_check(history, now, token)
            if pending_image is not None:
                publish(*pending_image, history, now, token)
                pending_image = None
        except OSError as error:
            print(f"Home Assistant konnte nicht aktualisiert werden: {error}")
        check_reminder(reminder, history, now)


if __name__ == "__main__":
    main()
