"""ISO-8601 times. A value with no offset is America/Chicago."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

LOCAL_TZ = os.environ.get("LOCAL_TZ", "America/Chicago")


def parse_ms(value: str, tz_name: str = LOCAL_TZ) -> int:
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo(tz_name))
    return int(moment.timestamp() * 1000)


def format_local(ms: int, tz_name: str = LOCAL_TZ) -> str:
    moment = datetime.fromtimestamp(ms / 1000, ZoneInfo(tz_name))
    return moment.isoformat(timespec="milliseconds")


def format_utc(ms: int) -> str:
    moment = datetime.fromtimestamp(ms / 1000, timezone.utc)
    return moment.isoformat(timespec="milliseconds")
