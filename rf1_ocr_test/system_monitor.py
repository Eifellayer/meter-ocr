"""Load of the machine and of this app: processor, memory, temperature (0.5.0).

Reads the Linux ``/proc`` and ``/sys`` files directly, so it needs no extra package and also
works on a Raspberry Pi. Every value that cannot be read is ``None``; nothing here raises.
"""

import os
from pathlib import Path
from threading import Lock
import time

PROC = Path("/proc")
THERMAL = Path("/sys/class/thermal")
_lock = Lock()
_last = {}


def _cpu_times(text):
    """(busy, total) jiffies from the first line of /proc/stat."""
    fields = [int(value) for value in text.split("\n", 1)[0].split()[1:]]
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
    return sum(fields) - idle, sum(fields)


def _memory(text):
    """(total, available) in megabytes from /proc/meminfo."""
    values = {}
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        if name in ("MemTotal", "MemAvailable"):
            values[name] = int(rest.split()[0]) / 1024
    return values.get("MemTotal"), values.get("MemAvailable")


def _temperature(folder):
    """Hottest thermal zone in °C, or None (containers often see none)."""
    readings = []
    try:
        zones = sorted(folder.glob("thermal_zone*/temp"))
    except OSError:
        return None
    for zone in zones:
        try:
            value = int(zone.read_text().strip()) / 1000
        except (OSError, ValueError):
            continue
        if 0 < value < 150:
            readings.append(value)
    return round(max(readings), 1) if readings else None


def _own_memory(text):
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    return None


def _read(path):
    try:
        return path.read_text()
    except (OSError, ValueError):
        return None


def snapshot(now=None, *, proc=PROC, thermal=THERMAL, times=os.times, cores=os.cpu_count):
    """Current load. Percentages compare with the previous call and are None on the first one."""
    now = time.monotonic() if now is None else now
    result = {"cpu_percent": None, "app_cpu_percent": None, "load": None, "cores": cores() or 1,
              "memory_total_mb": None, "memory_available_mb": None, "memory_used_percent": None,
              "app_memory_mb": None, "temperature_c": _temperature(thermal)}
    stat, meminfo = _read(proc / "stat"), _read(proc / "meminfo")
    status, load = _read(proc / "self" / "status"), _read(proc / "loadavg")
    try:
        if meminfo:
            total, available = _memory(meminfo)
            if total and available is not None:
                result.update(memory_total_mb=round(total), memory_available_mb=round(available),
                              memory_used_percent=round(100 * (total - available) / total))
        if status:
            own = _own_memory(status)
            result["app_memory_mb"] = round(own) if own is not None else None
        if load:
            result["load"] = float(load.split()[0])
        used = times()
        # The OCR engine runs as child processes: their time belongs to the app.
        own_seconds = used.user + used.system + used.children_user + used.children_system
        busy_total = _cpu_times(stat) if stat else None
        with _lock:
            previous = dict(_last)
            _last.update(stamp=now, own=own_seconds, cpu=busy_total)
        if previous and now > previous["stamp"]:
            # Percent of the whole machine, so both numbers can be compared.
            share = (own_seconds - previous["own"]) / (now - previous["stamp"]) / result["cores"]
            result["app_cpu_percent"] = max(0, min(100, round(100 * share)))
            if busy_total and previous.get("cpu") and busy_total[1] > previous["cpu"][1]:
                busy = (busy_total[0] - previous["cpu"][0]) / (busy_total[1] - previous["cpu"][1])
                result["cpu_percent"] = max(0, min(100, round(100 * busy)))
    except (ValueError, IndexError, TypeError, AttributeError):
        pass
    return result


def busy(sample, limit=85):
    """Is the machine so loaded that work without a deadline should wait?"""
    cpu, memory = sample.get("cpu_percent"), sample.get("memory_used_percent")
    return bool((cpu is not None and cpu >= limit) or (memory is not None and memory >= 92))
