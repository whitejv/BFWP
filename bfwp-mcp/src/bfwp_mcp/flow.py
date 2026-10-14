"""Gallons per day, split into zone runs and everything else."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from bfwp_mcp.clock import LOCAL_TZ, format_local, format_utc, parse_ms
from bfwp_mcp.db import connect_readonly, database_path


def get_flow_totals(
    start: str,
    end: str,
    bucket: str = "day",
    dev: str = "",
    source: str = "real",
    db_path: Path | None = None,
    tz_name: str = LOCAL_TZ,
) -> dict:
    """Metered gallons in each local day, split into scheduled and unscheduled.

    Scheduled gallons are the meter increase during zone runs. Unscheduled gallons
    are the rest of that day's increase. A day is clipped to [start, end).
    """
    if source not in ("real", "sim"):
        raise ValueError(f"source must be real or sim, not {source}")
    if bucket != "day":
        raise ValueError("bucket must be day")
    device = dev or ("twin1" if source == "sim" else "well1")
    start_ms = parse_ms(start, tz_name)
    end_ms = parse_ms(end, tz_name)
    if end_ms <= start_ms:
        raise ValueError("end must be after start")

    conn = connect_readonly(db_path or database_path(source))
    try:
        zones = conn.execute(
            """
            SELECT start_ts, end_ts FROM zone_runs
            WHERE start_ts < ? AND end_ts > ?
            ORDER BY start_ts
            """,
            (end_ms, start_ms),
        ).fetchall()
        buckets = []
        for day, bucket_start, bucket_end in _days(start_ms, end_ms, tz_name):
            total = _gallons(conn, device, bucket_start, bucket_end)
            scheduled = 0
            for zone in zones:
                overlap_start = max(zone["start_ts"], bucket_start)
                overlap_end = min(zone["end_ts"], bucket_end)
                if overlap_start < overlap_end:
                    scheduled += _gallons(conn, device, overlap_start, overlap_end)
            buckets.append(
                {
                    "date": day,
                    "start": format_local(bucket_start, tz_name),
                    "end": format_local(bucket_end, tz_name),
                    "scheduled": scheduled,
                    "unscheduled": total - scheduled,
                    "gallons": total,
                }
            )
    finally:
        conn.close()

    return {
        "start_utc": format_utc(start_ms),
        "end_utc": format_utc(end_ms),
        "tz": tz_name,
        "source": source,
        "dev": device,
        "bucket": bucket,
        "buckets": buckets,
    }


def _days(start_ms: int, end_ms: int, tz_name: str):
    tz = ZoneInfo(tz_name)
    day = datetime.fromtimestamp(start_ms / 1000, tz).replace(hour=0, minute=0, second=0, microsecond=0)
    while True:
        next_day = day + timedelta(days=1)
        bucket_start = max(start_ms, int(day.timestamp() * 1000))
        bucket_end = min(end_ms, int(next_day.timestamp() * 1000))
        if bucket_start < bucket_end:
            yield day.date().isoformat(), bucket_start, bucket_end
        if int(next_day.timestamp() * 1000) >= end_ms:
            return
        day = next_day


def _gallons(conn, dev: str, start_ms: int, end_ms: int) -> int:
    """Meter increase from the last reading before `start_ms` to the last before `end_ms`."""
    after = _level(conn, dev, end_ms)
    if after is None:
        return 0
    before = _level(conn, dev, start_ms)
    return after - (0 if before is None else before)


def _level(conn, dev: str, ts: int) -> int | None:
    row = conn.execute(
        """
        SELECT gal_total FROM readings
        WHERE dev = ? AND ts < ?
        ORDER BY ts DESC, seq DESC LIMIT 1
        """,
        (dev, ts),
    ).fetchone()
    return None if row is None else int(row["gal_total"])
