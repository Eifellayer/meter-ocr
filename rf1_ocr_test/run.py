"""Bridge the latest matched SLFork picture and reading to Home Assistant."""

import base64
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
from tempfile import NamedTemporaryFile
import time
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from PIL import Image
from websocket import WebSocketException

from checks import RETRY_INTERVAL, crop_register, read_register, record_sample, rolling_summary, schedule_next_check
from layout import find_digit_row
from reminder import Reminder
from settings import SCHEMA_VERSION, load_options

MAX_RESPONSE_BYTES = 3_000_000
MAX_TRANSFER_BYTES = 11_000
DESTINATION = Path("/media/rf1/kontrollbild.jpg")
HISTORY = Path("/data/kontrollmessung.json")
OPTIONS = Path("/data/options.json")
EFFECTIVE_OPTIONS = Path("/data/rf1-settings.json")
ENTITY = "sensor.rf1_kontrollbild"
CORE_URL = f"http://supervisor/core/api/states/{ENTITY}"
CHECK_ENTITY = "sensor.rf1_pruefstatus"
Image.MAX_IMAGE_PIXELS = 4_000_000


def get_bytes(url):
    with urlopen(url, timeout=8) as response:
        data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("Antwort zu groß")
    return data


def sequence_value(data, key):
    value = data.get(key, {})
    return value.get("main") if isinstance(value, dict) else None


def capture(base):
    before = json.loads(get_bytes(base + "/process_data"))
    picture = get_bytes(base + "/img_tmp/alg.jpg")
    try:
        overlay = get_bytes(base + "/img_tmp/alg_roi.jpg")
    except (OSError, ValueError):
        overlay = None
    after = json.loads(get_bytes(base + "/process_data"))
    timestamp = sequence_value(after, "timestamp_processed")
    if not timestamp:
        raise ValueError("Kein Zeitstempel vom ESP")
    if sequence_value(before, "timestamp_processed") != timestamp:
        return None
    return picture, overlay, {
        "esp_timestamp": timestamp,
        "raw_value": sequence_value(after, "raw_value"),
        "actual_value": sequence_value(after, "actual_value"),
    }


def select_register(frame, overlay, manual_crop, manual_width):
    if overlay is not None:
        try:
            with Image.open(io.BytesIO(overlay)) as annotated:
                if annotated.size == frame.size:
                    layout = find_digit_row(annotated)
                    if layout is not None:
                        crop, width = layout
                        return crop_register(frame, crop), width, "auto"
        except (OSError, ValueError, Image.DecompressionBombError):
            pass
    register = crop_register(frame, manual_crop)
    if not 0 < manual_width <= register.width:
        raise ValueError("vorkomma_breite liegt außerhalb des Ausschnitts")
    return register, manual_width, "manual"


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
            "decimal_places": 0,
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
        "attributes": {"friendly_name": "RF1 Prüfstatus", **summary},
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
    push_service = (options.get("push_dienst") or "").strip()
    reminder = None
    if push_service:
        try:
            reminder = Reminder(push_service, token)
        except ValueError as error:
            print(f"RF1-Erinnerung deaktiviert: {error}")
    pending_image = None
    print("RF1 Kontrollmessung gestartet")
    while True:
        now = datetime.now(zone)
        remaining = history.get("next_check_at", 0) - now.timestamp()
        if remaining > 0:
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
            time.sleep(min(remaining, RETRY_INTERVAL))
            continue

        data = None
        outcome = "capture_unavailable"
        updated = dict(history)
        try:
            result = capture(base)
            if result is None:
                print("SLFork hat während des Abrufs gemessen. Neuer Versuch in 10 Sekunden.")
                time.sleep(10)
                result = capture(base)
            if result is not None:
                picture, overlay, sample = result
                with Image.open(io.BytesIO(picture)) as frame:
                    if frame.format != "JPEG":
                        raise ValueError("Der ESP hat kein JPEG geliefert")
                    frame.load()
                    try:
                        register, integer_width, source = select_register(
                            frame, overlay, crop, options["vorkomma_breite"]
                        )
                        whole = register.crop((0, 0, integer_width, register.height))
                        ocr = read_register(whole, options["helle_ziffern"])
                    except (OSError, ValueError, subprocess.SubprocessError) as error:
                        print(f"Lokale OCR nicht verfügbar: {error}")
                        register, ocr, source = frame, None, "unavailable"
                    jpeg, size = transfer_jpeg(register)
                now = datetime.now(zone)
                if record_sample(updated, sample, ocr, zone, now):
                    atomic_write(DESTINATION, picture, 0o644)
                    outcome = updated["status"]
                    data = {**sample, "crop_source": source}
                else:
                    outcome = "stale_sample"
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            print(f"Bildabruf fehlgeschlagen: {error}")

        now = datetime.now(zone)
        schedule_next_check(updated, outcome, now.timestamp())
        atomic_write(HISTORY, json.dumps(updated).encode("utf-8"), 0o600)
        history = updated
        if data is not None:
            pending_image = (data, jpeg, size)
            print(f"Kontrollbild bereit: {data['esp_timestamp']} | Ausschnitt: {source} | "
                  f"OCR: {ocr or '?'} | SLFork: {data['actual_value']} | Ergebnis: {outcome}")
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
