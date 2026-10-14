"""Whether a device is online, and what its latest health report says."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bfwp_mcp.clock import LOCAL_TZ, format_local, format_utc, parse_ms
from bfwp_mcp.coverage import _format_seq_gap, _seq_gaps
from bfwp_mcp.db import connect_readonly, database_path

DAY_MS = 86_400_000


def get_device_status(
    dev: str = "",
    source: str = "real",
    db_path: Path | None = None,
    tz_name: str = LOCAL_TZ,
    now: str | None = None,
) -> dict:
    """Latest online flag, firmware, health, and sequence gaps in the last 24 hours.

    `now` is an ISO-8601 clock for tests. The server uses the current local time.
    """
    if source not in ("real", "sim"):
        raise ValueError(f"source must be real or sim, not {source}")
    device = dev or ("twin1" if source == "sim" else "well1")
    now_ms = parse_ms(now, tz_name) if now is not None else _now_ms(tz_name)
    start_ms = now_ms - DAY_MS

    conn = connect_readonly(db_path or database_path(source))
    try:
        status = conn.execute(
            """
            SELECT received_ts, online, fw, rssi FROM status_log
            WHERE dev = ? AND received_ts < ?
            ORDER BY received_ts DESC LIMIT 1
            """,
            (device, now_ms),
        ).fetchone()
        last = conn.execute(
            """
            SELECT MAX(ts) FROM (
              SELECT ts FROM readings WHERE dev = ? AND ts < ?
              UNION ALL
              SELECT ts FROM events WHERE dev = ? AND ts < ?
              UNION ALL
              SELECT ts FROM health WHERE dev = ? AND ts < ?
              UNION ALL
              SELECT received_ts AS ts FROM status_log WHERE dev = ? AND received_ts < ?
            )
            """,
            (device, now_ms) * 4,
        ).fetchone()
        health = conn.execute(
            """
            SELECT ts, uptime_s, rssi, buffer_used, buffer_capacity, watchdog_timeouts, enclosure_f
            FROM health
            WHERE dev = ? AND ts < ?
            ORDER BY ts DESC, seq DESC LIMIT 1
            """,
            (device, now_ms),
        ).fetchone()
        numbered = conn.execute(
            """
            SELECT seq, ts FROM readings WHERE dev = ? AND ts >= ? AND ts < ?
            UNION ALL
            SELECT seq, ts FROM events WHERE dev = ? AND ts >= ? AND ts < ?
            UNION ALL
            SELECT seq, ts FROM health WHERE dev = ? AND ts >= ? AND ts < ?
            ORDER BY seq, ts
            """,
            (device, start_ms, now_ms) * 3,
        ).fetchall()
    finally:
        conn.close()

    last_ms = last[0] if last is not None else None
    return {
        "start_utc": format_utc(start_ms),
        "end_utc": format_utc(now_ms),
        "tz": tz_name,
        "source": source,
        "dev": device,
        "online": None if status is None else bool(status["online"]),
        "status_time": None if status is None else format_local(status["received_ts"], tz_name),
        "fw": None if status is None else status["fw"],
        "last_message": None if last_ms is None else format_local(last_ms, tz_name),
        "health": None if health is None else _health(health, tz_name),
        "seq_gaps": [_format_seq_gap(gap, tz_name) for gap in _seq_gaps(numbered)],
    }


def _now_ms(tz_name: str) -> int:
    return int(datetime.now(ZoneInfo(tz_name)).timestamp() * 1000)


def _health(row, tz_name: str) -> dict:
    capacity = row["buffer_capacity"]
    used = row["buffer_used"]
    return {
        "time": format_local(row["ts"], tz_name),
        "uptime_s": row["uptime_s"],
        "rssi": row["rssi"],
        "buffer_used": used,
        "buffer_capacity": capacity,
        "buffer_fill": None if not capacity else round(used / capacity, 3),
        "watchdog_timeouts": row["watchdog_timeouts"],
        "enclosure_f": row["enclosure_f"],
    }
