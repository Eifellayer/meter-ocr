"""Separate, opt-in monitoring of Home Assistant cumulative meter entities."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import re
from threading import Event, Lock, Thread
import time

from consumption import consumption_statistics, record_consumption_sample

METER_LIMIT = 6
METER_UNITS = ("m³", "kWh")


def meter_config(text):
    meters = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        entity, _, minutes = map(str.strip, line.partition(","))
        if (not re.fullmatch(r"sensor\.[a-z0-9_]{1,80}", entity) or entity in ("sensor.rf1_verbrauch_gesamt", "sensor.rf1_ocr_zaehlerstand")
                or entity in meters or len(meters) >= METER_LIMIT):
            raise ValueError("Invalid meter entity")
        interval = int(minutes or "30")
        if not 5 <= interval <= 1440:
            raise ValueError("Invalid meter interval")
        meters[entity] = interval
    return meters


def read_meter(previous, state, now):
    attrs = state["attributes"]
    unit = attrs.get("unit_of_measurement")
    if unit not in METER_UNITS or attrs.get("state_class") != "total_increasing":
        raise ValueError("Meter needs a supported cumulative state")
    reported = datetime.fromisoformat(state.get("last_reported") or state["last_updated"])
    if reported.tzinfo is None or reported.timestamp() > now + 60:
        raise ValueError("Invalid report time")
    raw = Decimal(state["state"])
    if not raw.is_finite() or not 0 <= raw < 10 ** 12:
        raise ValueError("Invalid meter value")
    value = int((raw * 1000).to_integral_value())
    stamp = reported.timestamp()
    if previous.get("unit") != unit:
        previous = {}
    if stamp <= max(previous.get("timestamp", 0), previous.get("reset_time", 0)):
        return {**previous, "status": "reset_pending" if previous.get("reset_time") else "stale"}
    total = previous.get("total", 0)
    last = previous.get("reading", value)
    reset = value < last
    if reset and not (previous.get("reset_time") and previous["reset_reading"] <= value):
        return {**previous, "status": "reset_pending", "reset_time": stamp, "reset_reading": value}
    if not reset:
        total += value - last
    # A reset is a new baseline. Keep the accumulated total but leave the interval unallocated.
    series = previous.get("series", {})
    scope = unit
    previous_step = series.get("samples", [[0, 0, 1]])[-1][2]
    step = 3 - previous_step if reset else previous_step
    series = record_consumption_sample(series, scope, {
        "timestamp": stamp, "total_litres": total, "step_litres": step,
    })
    return {"label": str(attrs.get("friendly_name") or "")[:100], "unit": unit, "reading": value,
            "total": total, "timestamp": stamp, "series": series, "status": "reset" if reset else "ok"}


class ExperimentalMeters:
    def __init__(self, path, fetch, write, zone):
        self.path, self.fetch, self.write, self.zone = path, fetch, write, zone
        self.lock = Lock()
        self.wake = Event()
        self.thread = None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.settings, self.states = data["settings"], data["states"]
        except (OSError, ValueError, KeyError, TypeError):
            self.settings, self.states = {}, {}

    def _save(self, settings, states):
        self.write(self.path, json.dumps({"settings": settings, "states": states}).encode(), 0o600)
        self.settings, self.states = settings, states

    def configure(self, text):
        settings = meter_config(text)
        with self.lock:
            states = {entity: {**self.states.get(entity, {}), "next": 0} for entity in settings}
            self._save(settings, states)
        self.start()
        self.wake.set()

    def reset(self):
        with self.lock:
            self.path.unlink(missing_ok=True)
            self.settings, self.states = {}, {}
        self.wake.set()

    def start(self):
        with self.lock:
            if self.settings and self.thread is None:
                self.thread = Thread(target=self._monitor, name="experimental-meters", daemon=True)
                self.thread.start()

    def snapshot(self):
        with self.lock:
            rows = [(entity, minutes, self.states.get(entity, {})) for entity, minutes in self.settings.items()]
        now = time.time()
        return [{
            "id": entity, "minutes": minutes, "label": state.get("label") or entity,
            "status": state.get("status", "waiting"), "unit": state.get("unit"),
            "reading": state.get("reading"), "timestamp": state.get("timestamp"), "next": state.get("next"),
            "usage": consumption_statistics(state.get("series", {}), state.get("unit"), now, self.zone),
        } for entity, minutes, state in rows]

    def _monitor(self):
        while True:
            self.wake.clear()
            with self.lock:
                settings = self.settings
                entity = min(settings, key=lambda key: self.states.get(key, {}).get("next", 0), default=None)
                previous = self.states.get(entity, {})
            wait = previous.get("next", 0) - time.time() if entity else 3600
            if wait > 0:
                self.wake.wait(wait)
                continue
            try:
                current = read_meter(previous, self.fetch(entity), time.time())
            except (OSError, ValueError, TypeError, KeyError, InvalidOperation):
                current = {**previous, "status": "unavailable"}
            with self.lock:
                if settings is not self.settings:
                    continue
                current["next"] = time.time() + settings[entity] * 60
                try:
                    self._save(settings, {**self.states, entity: current})
                except OSError:
                    current = None
            if current is None:
                self.wake.wait(30)
