"""Clinic wall-clock timestamps match the approved DATETIME storage convention."""

from datetime import datetime
from zoneinfo import ZoneInfo


CLINIC_TIMEZONE = ZoneInfo('Africa/Casablanca')


def clinic_now() -> datetime:
    return datetime.now(CLINIC_TIMEZONE).replace(tzinfo=None)
