"""The one-click meter camera (esphome/ in the repository) in Home Assistant.

A freshly installed meter camera announces itself in the network. Home Assistant then lists it
as a discovered ESPHome device that still waits for "Add". The setup wizard shows that and adds
it with one click, so nobody has to look for it under Settings → Devices & services.
"""

import json
import re
import unicodedata

from websocket import WebSocketException, create_connection

CORE_WEBSOCKET = "ws://supervisor/core/websocket"
CORE_FLOW = "http://supervisor/core/api/config/config_entries/flow/{}"
# Device name "zaehlerkamera-a1b2c3", friendly name "Zählerkamera a1b2c3" (both from the firmware).
KIT_NAME = re.compile(r"z(?:ae|a|ä)hlerkamera(?:[\s_-]|$)")
FLOW_ID = re.compile(r"[0-9a-f]{32}")


def ha_command(token, message, *, connect=create_connection):
    """Send one command over Home Assistant's WebSocket API and return its result."""
    socket = connect(CORE_WEBSOCKET, timeout=6, suppress_origin=True, redirect_limit=0,
                     header={"Authorization": f"Bearer {token}"})
    try:
        if json.loads(socket.recv()).get("type") != "auth_required":
            raise ValueError("Unexpected WebSocket greeting")
        socket.send(json.dumps({"type": "auth", "access_token": token}))
        if json.loads(socket.recv()).get("type") != "auth_ok":
            raise ValueError("Home Assistant refused the WebSocket login")
        socket.send(json.dumps({"id": 1, **message}))
        reply = json.loads(socket.recv())
        if reply.get("id") != 1 or not reply.get("success"):
            raise ValueError("Home Assistant refused the command")
        return reply.get("result")
    finally:
        socket.close()


def kit_name(name):
    folded = unicodedata.normalize("NFC", str(name or "")).casefold()
    return bool(KIT_NAME.match(folded))


def pending_kit_cameras(token, *, command=ha_command):
    """Meter cameras Home Assistant has discovered but not added yet: [{flow_id, name}]."""
    found = []
    for flow in command(token, {"type": "config_entries/flow/progress"}) or []:
        if not isinstance(flow, dict) or flow.get("handler") != "esphome":
            continue
        context = flow.get("context") if isinstance(flow.get("context"), dict) else {}
        placeholders = context.get("title_placeholders") if isinstance(context.get("title_placeholders"), dict) else {}
        name = str(placeholders.get("name") or "")
        flow_id = str(flow.get("flow_id") or "")
        if kit_name(name) and FLOW_ID.fullmatch(flow_id) and context.get("source") in ("zeroconf", "dhcp", "mqtt"):
            found.append({"flow_id": flow_id, "name": name[:80]})
    return found[:10]


def add_kit_camera(token, flow_id, *, post, command=ha_command):
    """Confirm Home Assistant's discovery of one meter camera. Returns "added" or "needs_attention".

    Only a flow that pending_kit_cameras() lists right now is confirmed, never an arbitrary one.
    """
    if not FLOW_ID.fullmatch(str(flow_id)):
        raise ValueError("Invalid flow")
    if flow_id not in {camera["flow_id"] for camera in pending_kit_cameras(token, command=command)}:
        raise LookupError("This camera is not waiting in Home Assistant")
    answer = post(CORE_FLOW.format(flow_id), token, {})
    result = json.loads(answer.decode("utf-8") if isinstance(answer, bytes) else answer)
    # "create_entry": added. Anything else (a form, e.g. for an encryption key) needs the user.
    return "added" if isinstance(result, dict) and result.get("type") == "create_entry" else "needs_attention"


def safe_pending(token, *, command=ha_command):
    """pending_kit_cameras() for the web page: an empty list when Home Assistant cannot answer."""
    try:
        return pending_kit_cameras(token, command=command)
    except (OSError, ValueError, TypeError, WebSocketException) as error:
        print(f"Neue Zählerkameras konnten nicht abgefragt werden: {type(error).__name__}")
        return []


def safe_add(token, flow_id, *, post, command=ha_command):
    """add_kit_camera() for the web page: "added", "needs_attention", "gone" or "failed"."""
    try:
        return add_kit_camera(token, flow_id, post=post, command=command)
    except LookupError:
        return "gone"
    except (OSError, ValueError, TypeError, WebSocketException) as error:
        print(f"Zählerkamera konnte nicht hinzugefügt werden: {type(error).__name__}")
        return "failed"


# Extras of the firmware that are switched off by default (entities disabled in Home Assistant).
EXTRAS = {"wlan_kanal": "WLAN-Kanal", "wlan_zugangspunkt": "WLAN-Zugangspunkt"}


def kit_extras(token, camera, *, command=ha_command):
    """The extras of the meter camera behind `camera`: {key: {"entity_id": …, "enabled": bool}}."""
    entries = [entry for entry in command(token, {"type": "config/entity_registry/list"}) or []
               if isinstance(entry, dict) and isinstance(entry.get("entity_id"), str)]
    device = next((entry.get("device_id") for entry in entries if entry["entity_id"] == camera), None)
    if not device:
        return {}
    found = {}
    for entry in entries:
        if entry.get("device_id") != device or entry.get("platform") != "esphome":
            continue
        for key, name in EXTRAS.items():
            if entry.get("original_name") == name:
                found[key] = {"entity_id": entry["entity_id"], "enabled": entry.get("disabled_by") is None}
    return found


def set_kit_extra(token, camera, key, enabled, *, command=ha_command):
    """Switch one extra on or off. Only entities of the camera's own device are touched."""
    extras = kit_extras(token, camera, command=command)
    if key not in extras:
        raise LookupError("This camera has no such extra")
    command(token, {"type": "config/entity_registry/update", "entity_id": extras[key]["entity_id"],
                    "disabled_by": None if enabled else "user"})
    return True


def safe_extras(token, camera, *, command=ha_command):
    try:
        return {key: {"enabled": value["enabled"]} for key, value in kit_extras(token, camera, command=command).items()}
    except (OSError, ValueError, TypeError, KeyError, WebSocketException) as error:
        print(f"Zusätze der Zählerkamera konnten nicht gelesen werden: {type(error).__name__}")
        return {}


def safe_set_extra(token, camera, key, enabled, *, command=ha_command):
    """set_kit_extra() for the web page: "saved", "gone" or "failed"."""
    try:
        set_kit_extra(token, camera, key, enabled, command=command)
        return "saved"
    except LookupError:
        return "gone"
    except (OSError, ValueError, TypeError, KeyError, WebSocketException) as error:
        print(f"Zusatz der Zählerkamera konnte nicht geändert werden: {type(error).__name__}")
        return "failed"
