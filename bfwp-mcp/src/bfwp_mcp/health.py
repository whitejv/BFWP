"""Health reports in a range, with the boots called out."""

from __future__ import annotations

from pathlib import Path

from bfwp_mcp.clock import LOCAL_TZ, format_local, format_utc, parse_ms
from bfwp_mcp.db import connect_readonly, database_path

MAX_REPORTS = 2000
MINUTE_MS = 60_000


def get_device_health(
    start: str,
    end: str,
    dev: str = "",
    source: str = "real",
    db_path: Path | None = None,
    tz_name: str = LOCAL_TZ,
) -> dict:
    """Health reports in [start, end). Reboots are the reports whose uptime is zero.

    A range with more than 2,000 reports is thinned. Reports with uptime zero stay.
    """
    if source not in ("real", "sim"):
        raise ValueError(f"source must be real or sim, not {source}")
    device = dev or ("twin1" if source == "sim" else "well1")
    start_ms = parse_ms(start, tz_name)
    end_ms = parse_ms(end, tz_name)
    if end_ms <= start_ms:
        raise ValueError("end must be after start")

    conn = connect_readonly(db_path or database_path(source))
    try:
        rows = conn.execute(
            """
            SELECT ts, reset_reason, uptime_s, rssi, heap_free, heap_min, enclosure_f
            FROM health
            WHERE dev = ? AND ts >= ? AND ts < ?
            ORDER BY ts, seq
            """,
            (device, start_ms, end_ms),
        ).fetchall()
    finally:
        conn.close()

    kept, resolution = _thin(rows)
    reports = [_report(row, tz_name) for row in kept]
    return {
        "start_utc": format_utc(start_ms),
        "end_utc": format_utc(end_ms),
        "tz": tz_name,
        "source": source,
        "dev": device,
        "resolution": resolution,
        "reports": reports,
        "reboots": [report for report in reports if report["uptime_s"] == 0],
    }


def _thin(rows) -> tuple[list, str | None]:
    if len(rows) <= MAX_REPORTS:
        return list(rows), None
    stride = (len(rows) + MAX_REPORTS - 1) // MAX_REPORTS
    kept = [row for index, row in enumerate(rows) if index % stride == 0 or row["uptime_s"] == 0]
    step_min = _step_minutes(rows) * stride
    return kept, f"{step_min}min"


def _step_minutes(rows) -> int:
    if len(rows) < 2:
        return 5
    gap = int(rows[1]["ts"]) - int(rows[0]["ts"])
    return max(1, round(gap / MINUTE_MS))


def _report(row, tz_name: str) -> dict:
    return {
        "time": format_local(row["ts"], tz_name),
        "reset_reason": row["reset_reason"],
        "uptime_s": row["uptime_s"],
        "rssi": row["rssi"],
        "heap_free": row["heap_free"],
        "heap_min": row["heap_min"],
        "enclosure_f": row["enclosure_f"],
    }
