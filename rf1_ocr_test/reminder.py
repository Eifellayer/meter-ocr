"""Track a Home Assistant notice and send at most one reminder per RF1 incident."""

import json
import re
from threading import Thread
from time import sleep
from urllib.request import Request, urlopen

from websocket import create_connection

REMINDER_DELAY = 24 * 60 * 60


class Reminder:
    def __init__(self, service, token):
        if not re.fullmatch(r"notify\.mobile_app_[a-z0-9_]+", service):
            raise ValueError("push_dienst muss notify.mobile_app_… sein")
        self.service = service
        self.token = token
        self.skipped_id = None
        Thread(target=self.listen_for_skip, daemon=True).start()

    def listen_for_skip(self):
        request = Request(
            "http://supervisor/core/api/stream?restrict=mobile_app_notification_action",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        while True:
            try:
                with urlopen(request, timeout=90) as stream:
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
        with urlopen(request, timeout=10):
            pass

    def notifications(self):
        socket = create_connection(
            "ws://supervisor/core/websocket", timeout=6, suppress_origin=True,
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
        if reminder is None and incident is None:
            return
        notices = {notice["notification_id"] for notice in self.notifications()}
        if reminder is not None and reminder["incident"] != incident:
            if reminder["id"] in notices:
                self.call_service("persistent_notification.dismiss", {"notification_id": reminder["id"]})
            if reminder.get("pushed"):
                self.clear_push(reminder)
            history.pop("reminder", None)
            reminder = None

        if reminder is None and incident is not None:
            notification_id = f"rf1_review_{round(incident * 1_000_000)}"
            if notification_id not in notices:
                self.call_service("persistent_notification.create", {
                    "notification_id": notification_id,
                    "title": "RF1 braucht eine Sichtprüfung",
                    "message": "Die Gaszählerkontrolle konnte den Stand seit vier Stunden nicht bestätigen. "
                               "Prüfe das Kontrollbild unter Medien → Lokale Medien → rf1. "
                               "Schließe diesen Hinweis, wenn du ihn gesehen hast oder überspringen möchtest.",
                })
            history["reminder"] = {"id": notification_id, "incident": incident, "shown_at": now}
            return

        if reminder is None:
            return
        if reminder.get("skipped") or reminder["id"] == self.skipped_id or reminder["id"] not in notices:
            if reminder["id"] in notices:
                self.call_service("persistent_notification.dismiss", {"notification_id": reminder["id"]})
            if reminder.get("pushed") and not reminder.get("push_cleared"):
                self.clear_push(reminder)
                reminder["push_cleared"] = True
            reminder["skipped"] = True
        elif not reminder.get("pushed") and now - reminder["shown_at"] >= REMINDER_DELAY:
            self.call_service(self.service, {
                "title": "RF1-Hinweis noch offen",
                "message": "Die Gaszählerkontrolle wartet seit 24 Stunden auf eine Sichtprüfung.",
                "data": {"tag": reminder["id"], "actions": [
                    {"action": "URI", "title": "Prüfstatus öffnen", "uri": "entityId:sensor.rf1_pruefstatus"},
                    {"action": f"RF1_SKIP_{reminder['id']}", "title": "Überspringen"},
                ]},
            })
            reminder["pushed"] = True

    def clear_push(self, reminder):
        self.call_service(self.service, {"message": "clear_notification", "data": {"tag": reminder["id"]}})
