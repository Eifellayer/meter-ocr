"""Validate the independent settings for automatic failure notifications."""

import re

DEFAULT_REVIEW_MINUTES = 240
DEFAULT_DELIVERY_HOURS = 24
PUSH_SERVICE = re.compile(r"notify\.mobile_app_[a-z0-9_]+")
NOTIFY_ENTITY = re.compile(r"notify\.[a-z0-9_]+")


def notification_rules(values):
    enabled = values["enabled"]
    review = values["review_minutes"]
    delay = values["delivery_hours"]
    push = values["push"].strip()
    target = values["target"].strip()
    if (type(enabled) is not bool
            or type(review) is not int or not 1 <= review <= 2880
            or type(delay) is not int or not 0 <= delay <= 168
            or (push and not PUSH_SERVICE.fullmatch(push))
            or (target and not NOTIFY_ENTITY.fullmatch(target))):
        raise ValueError("Ungültige Benachrichtigungseinstellungen")
    return dict(enabled=enabled, review_minutes=review, delivery_hours=delay, push=push, target=target)
