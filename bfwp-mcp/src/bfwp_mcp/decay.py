"""Overnight pressure change and the gallons metered while it happens."""

from __future__ import annotations

from pathlib import Path

from bfwp_mcp.clock import LOCAL_TZ, format_local, format_utc, parse_ms
from bfwp_mcp.db import connect_readonly, database_path
from bfwp_mcp.readings import meter_delta

HOUR_MS = 3_600_000


def get_overnight_decay(
    date: str,
    window: str = "00:00-05:00",
    dev: str = "",
    source: str = "real",
    db_path: Path | None = None,
    tz_name: str = LOCAL_TZ,
) -> dict:
    """Pressure and metered gallons for the local overnight window on `date`.

    `date` is YYYY-MM-DD. `window` is HH:MM-HH:MM in America/Chicago when the
    times have no offset. `rate_psi_h` is the change from the first reading to
    the last. `psi_min` and `psi_max` keep a drop visible when the pump refills
    before the window ends.
    """
    if source not in ("real", "sim"):
        raise ValueError(f"source must be real or sim, not {source}")
    device = dev or ("twin1" if source == "sim" else "well1")
    start_ms, end_ms = _window_bounds(date, window, tz_name)

    conn = connect_readonly(db_path or database_path(source))
    try:
        readings = conn.execute(
            """
            SELECT ts, psi, pump FROM readings
            WHERE dev = ? AND ts >= ? AND ts < ? AND psi IS NOT NULL
            ORDER BY ts, seq
            """,
            (device, start_ms, end_ms),
        ).fetchall()
        cycles = conn.execute(
            """
            SELECT start_ts, end_ts, duration_s, gallons, psi_avg, psi_min, psi_max, amps_avg, amps_max
            FROM pump_cycles
            WHERE dev = ? AND start_ts < ? AND (end_ts IS NULL OR end_ts > ?)
            ORDER BY start_ts
            """,
            (device, end_ms, start_ms),
        ).fetchall()
        gallons = meter_delta(conn, device, start_ms, end_ms)
    finally:
        conn.close()

    psis = [row["psi"] for row in readings]
    psi_start = psis[0] if psis else None
    psi_end = psis[-1] if psis else None
    hours = (end_ms - start_ms) / HOUR_MS
    rate = None if psi_start is None else round((psi_end - psi_start) / hours, 3)
    night = {
        "date": date,
        "start": format_local(start_ms, tz_name),
        "end": format_local(end_ms, tz_name),
        "psi_start": psi_start,
        "psi_end": psi_end,
        "psi_min": min(psis) if psis else None,
        "psi_max": max(psis) if psis else None,
        "rate_psi_h": rate,
        "gallons": gallons,
        "cycles": [
            {
                "start": format_local(cycle["start_ts"], tz_name),
                "end": None if cycle["end_ts"] is None else format_local(cycle["end_ts"], tz_name),
                "duration_s": cycle["duration_s"],
                "gallons": cycle["gallons"],
                "psi_avg": cycle["psi_avg"],
                "psi_min": cycle["psi_min"],
                "psi_max": cycle["psi_max"],
                "amps_avg": cycle["amps_avg"],
                "amps_max": cycle["amps_max"],
            }
            for cycle in cycles
        ],
    }
    return {
        "start_utc": format_utc(start_ms),
        "end_utc": format_utc(end_ms),
        "tz": tz_name,
        "source": source,
        "dev": device,
        "nights": [night],
    }


def _window_bounds(date: str, window: str, tz_name: str) -> tuple[int, int]:
    start_clock, end_clock = (part.strip() for part in window.split("-", 1))
    if start_clock.count(":") == 1:
        start_clock += ":00"
    if end_clock.count(":") == 1:
        end_clock += ":00"
    start_ms = parse_ms(f"{date}T{start_clock}", tz_name)
    end_ms = parse_ms(f"{date}T{end_clock}", tz_name)
    if end_ms <= start_ms:
        end_ms += 24 * HOUR_MS
    return start_ms, end_ms
