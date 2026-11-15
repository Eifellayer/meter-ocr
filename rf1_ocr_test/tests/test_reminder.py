"""Notification rules use Home Assistant without sending real messages in tests."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks import rolling_summary
from notification_settings import notification_rules
from reminder import Reminder


class ReminderTests(TestCase):
    def setUp(self):
        self.history = {"failure_since": 100}
        self.notices = set()
        self.sent = []
        self.reminder = Reminder("stub")
        self.enterContext(patch("reminder.Thread"))
        self.enterContext(patch.object(self.reminder, "call_service", self.call_service))
        self.enterContext(patch.object(self.reminder, "notifications", lambda: [
            {"notification_id": notice} for notice in self.notices
        ]))

    def call_service(self, service, payload):
        self.sent.append((service, payload))
        if service == "persistent_notification.create":
            self.notices.add(payload["notification_id"])
        if service == "persistent_notification.dismiss":
            self.notices.discard(payload["notification_id"])

    def sync(self, now, review_after=60):
        summary = rolling_summary(self.history, datetime.fromtimestamp(now, timezone.utc), review_after)
        self.reminder.sync(self.history, summary, now)

    def test_notice_and_both_channels_are_sent_once_after_the_configured_delays(self):
        self.reminder.configure(enabled=True, push="notify.mobile_app_phone", target="notify.mail", delay=3600)
        self.sync(159)
        self.assertEqual([], self.sent)
        self.sync(160)
        self.assertEqual(["persistent_notification.create"], [name for name, _ in self.sent])
        self.sync(3759)
        self.assertEqual(1, len(self.sent))
        self.sync(3760)
        self.history = json.loads(json.dumps(self.history))
        self.sync(4000)
        self.assertEqual(["persistent_notification.create", "notify.mobile_app_phone", "notify.send_message"],
                         [name for name, _ in self.sent])
        self.assertEqual("notify.mail", self.sent[-1][1]["entity_id"])
        self.assertEqual("Überspringen", self.sent[1][1]["data"]["actions"][1]["title"])

    def test_zero_delay_and_independent_channels(self):
        self.reminder.configure(enabled=True, push="notify.mobile_app_phone", target="notify.mail", delay=0)

        def fail_push(service, payload):
            if service == "notify.mobile_app_phone":
                raise OSError("unavailable")
            self.call_service(service, payload)

        with patch.object(self.reminder, "call_service", fail_push):
            self.sync(160)
        self.assertTrue(self.history["reminder"]["target_sent"])
        self.assertNotIn("pushed", self.history["reminder"])
        self.sync(170)
        self.assertEqual("notify.mobile_app_phone", self.sent[-1][0])
        self.assertEqual(1, sum(service == "notify.send_message" for service, _ in self.sent))

    def test_dismissal_and_recovery_cancel_pending_delivery(self):
        self.reminder.configure(enabled=True, push="", target="notify.mail", delay=3600)
        self.sync(160)
        self.notices.clear()
        self.sync(3900)
        self.assertTrue(self.history["reminder"]["skipped"])
        self.assertEqual(1, len(self.sent))
        self.history.pop("failure_since")
        self.sync(3920)
        self.assertNotIn("reminder", self.history)

    def test_home_assistant_only_and_disabled_no_delivery(self):
        self.reminder.configure(enabled=False, push="", target="notify.mail", delay=0)
        self.sync(160)
        self.assertEqual([], self.sent)
        self.reminder.configure(enabled=True, push="", target="", delay=0)
        self.sync(160)
        self.assertEqual(["persistent_notification.create"], [name for name, _ in self.sent])

    def test_validation_rejects_non_notification_destinations(self):
        defaults = dict(enabled=True, review_minutes=240, delivery_hours=24, push="", target="")
        self.assertEqual(defaults, notification_rules(defaults))
        for change in ({"target": "script.test"}, {"push": "notify.generic"}, {"delivery_hours": 169}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                notification_rules({**defaults, **change})
