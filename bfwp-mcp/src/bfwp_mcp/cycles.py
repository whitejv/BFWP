"""Pump cycles from the well monitor."""

from __future__ import annotations

from pathlib import Path

from bfwp_mcp.clock import LOCAL_TZ, format_local, format_utc, parse_ms
from bfwp_mcp.db import connect_readonly, database_path


def get_pump_cycles(
    start: str,
    end: str,
    dev: str = "",
    source: str = "real",
    db_path: Path | None = None,
    tz_name: str = LOCAL_TZ,
) -> dict:
    """Cycles in [start, end). Gallons are the meter increase stored for that cycle."""
    if source not in ("real", "sim"):
        raise ValueError(f"source must be real or sim, not {source}")
    device = dev or ("twin1" if source == "sim" else "well1")
    start_ms = parse_ms(start, tz_name)
    end_ms = parse_ms(end, tz_name)
    if end_ms <= start_ms:
        raise ValueError("end must be after start")

    conn = connect_readonly(db_path or database_path(source))
    try:
        cycles = conn.execute(
            """
            SELECT start_ts, end_ts, duration_s, gallons, psi_avg, psi_min, psi_max, amps_avg, amps_max
            FROM pump_cycles
            WHERE dev = ? AND start_ts < ? AND (end_ts IS NULL OR end_ts > ?)
            ORDER BY start_ts
            """,
            (device, end_ms, start_ms),
        ).fetchall()
        cycle_rows = [
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
        ]
    finally:
        conn.close()

    return {
        "start_utc": format_utc(start_ms),
        "end_utc": format_utc(end_ms),
        "tz": tz_name,
        "source": source,
        "dev": device,
        "cycles": cycle_rows,
    }
