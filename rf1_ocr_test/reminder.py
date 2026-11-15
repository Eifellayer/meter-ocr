"""Track a Home Assistant notice and send at most one reminder per RF1 incident."""

import json
from threading import Thread
from time import sleep
from urllib.request import Request

from websocket import create_connection

from transport import open_core
from notification_settings import PUSH_SERVICE

class Reminder:
    def __init__(self, token):
        self.token = token
        self.enabled = False
        self.push = ""
        self.target = ""
        self.delay = 0
        self.skipped_id = None
        self.listening = False

    def configure(self, *, enabled, push, target, delay):
        self.enabled, self.push, self.target, self.delay = enabled, push, target, delay
        if enabled and push and not self.listening:
            self.listening = True
            Thread(target=self.listen_for_skip, daemon=True).start()

    def listen_for_skip(self):
        request = Request(
            "http://supervisor/core/api/stream?restrict=mobile_app_notification_action",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        while True:
            try:
                with open_core(request, timeout=90) as stream:
                    for line in stream:
                        if not line.startswith(b"data:"):
                            continue
                        action = json.loads(line[5:]).get("data", {}).get("action")
                        if isinstance(action, str) and action.startswith("RF1_SKIP_"):
                            self.skipped_id = action.removeprefix("RF1_SKIP_")
            except (OSError, ValueError):
                sleep(10)

    def call_service(self, service, data):
        domain, action = service.split(".")
        request = Request(
            f"http://supervisor/core/api/services/{domain}/{action}",
            data=json.dumps(data).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method="POST",
        )
        with open_core(request, timeout=10):
            pass

    def notifications(self):
        socket = create_connection(
            "ws://supervisor/core/websocket", timeout=6, suppress_origin=True, redirect_limit=0,
            header={"Authorization": f"Bearer {self.token}"},
        )
        try:
            if json.loads(socket.recv()).get("type") != "auth_required":
                raise ValueError("Unerwartete WebSocket-Anmeldung")
            socket.send(json.dumps({"type": "auth", "access_token": self.token}))
            if json.loads(socket.recv()).get("type") != "auth_ok":
                raise ValueError("Home Assistant hat die WebSocket-Anmeldung abgelehnt")
            socket.send(json.dumps({"id": 1, "type": "persistent_notification/get"}))
            reply = json.loads(socket.recv())
            if reply.get("id") != 1 or not reply.get("success"):
                raise ValueError("Home Assistant hat die Abfrage der Hinweise abgelehnt")
            return reply["result"]
        finally:
            socket.close()

    def sync(self, history, summary, now):
        incident = summary["failure_since_epoch"] if summary["review_due"] else None
        reminder = history.get("reminder")
        if reminder is None and (incident is None or not self.enabled):
            return
        if reminder is not None and reminder["incident"] == incident and not self.enabled:
            return
        notices = {notice["notification_id"] for notice in self.notifications()}
        if reminder is not None and reminder["incident"] != incident:
            if reminder["id"] in notices:
                self.call_service("persistent_notification.dismiss", {"notification_id": reminder["id"]})
            self.clear_push(reminder)
            history.pop("reminder", None)
            reminder = None

        if incident is None or not self.enabled:
            return
        if reminder is None:
            notification_id = f"rf1_review_{round(incident * 1_000_000)}"
            if notification_id not in notices:
                self.call_service("persistent_notification.create", {
                    "notification_id": notification_id,
                    "title": "Gaszähler bitte prüfen",
                    "message": "Die automatische Kontrolle konnte den Zählerstand wiederholt nicht bestätigen. "
                               "Das Kontrollbild findest du unter Medien → Lokale Medien → rf1. "
                               "Wenn du den Stand geprüft hast, kannst du diesen Hinweis schließen.",
                })
                notices.add(notification_id)
            reminder = {"id": notification_id, "incident": incident, "shown_at": now}
            history["reminder"] = reminder

        if reminder.get("skipped") or reminder["id"] == self.skipped_id or reminder["id"] not in notices:
            if reminder["id"] in notices:
                self.call_service("persistent_notification.dismiss", {"notification_id": reminder["id"]})
            self.clear_push(reminder)
            reminder["skipped"] = True
            return
        if now - reminder["shown_at"] < self.delay:
            return

        payload = {
            "title": "Gaszähler bitte prüfen",
            "message": "Die automatische Kontrolle konnte den Zählerstand wiederholt nicht bestätigen. "
                       "Bitte prüfe den Stand am Zähler oder öffne das Kontrollbild in Home Assistant.",
        }
        if self.push and not reminder.get("pushed"):
            try:
                self.call_service(self.push, {**payload, "data": {"tag": reminder["id"], "actions": [
                    {"action": "URI", "title": "Prüfstatus öffnen", "uri": "entityId:sensor.rf1_pruefstatus"},
                    {"action": f"RF1_SKIP_{reminder['id']}", "title": "Überspringen"},
                ]}})
            except OSError as error:
                print(f"RF1-Handy-Push konnte nicht gesendet werden: {type(error).__name__}")
            else:
                reminder.update(pushed=True, push_service=self.push)
        if self.target and not reminder.get("target_sent"):
            try:
                self.call_service("notify.send_message", {**payload, "entity_id": self.target})
            except OSError as error:
                print(f"RF1-Benachrichtigung konnte nicht gesendet werden: {type(error).__name__}")
            else:
                reminder["target_sent"] = True

    def clear_push(self, reminder):
        push = reminder.get("push_service") or self.push
        if reminder.get("pushed") and not reminder.get("push_cleared") and PUSH_SERVICE.fullmatch(push):
            self.call_service(push, {"message": "clear_notification", "data": {"tag": reminder["id"]}})
            reminder["push_cleared"] = True
