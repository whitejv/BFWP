"""Pump cycles with the zone runs that overlap them, and gallons per zone."""

from __future__ import annotations

from pathlib import Path

from bfwp_mcp.clock import LOCAL_TZ, format_local, format_utc, parse_ms
from bfwp_mcp.db import connect_readonly, database_path
from bfwp_mcp.readings import meter_delta


def get_pump_cycles(
    start: str,
    end: str,
    dev: str = "",
    source: str = "real",
    db_path: Path | None = None,
    tz_name: str = LOCAL_TZ,
) -> dict:
    """Cycles in [start, end), each with overlapping zone runs. Zone gallons are the meter delta."""
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
        zones = conn.execute(
            """
            SELECT zone_id, start_ts, end_ts, source
            FROM zone_runs
            WHERE start_ts < ? AND end_ts > ?
            ORDER BY start_ts, zone_id
            """,
            (end_ms, start_ms),
        ).fetchall()
        zone_rows = []
        for zone in zones:
            zone_rows.append(
                {
                    "zone_id": zone["zone_id"],
                    "start": format_local(zone["start_ts"], tz_name),
                    "end": format_local(zone["end_ts"], tz_name),
                    "source": zone["source"],
                    "gallons": meter_delta(conn, device, zone["start_ts"], zone["end_ts"]),
                    "_start_ms": zone["start_ts"],
                    "_end_ms": zone["end_ts"],
                }
            )
        cycle_rows = []
        for cycle in cycles:
            cycle_end = cycle["end_ts"]
            overlapping = [
                {key: value for key, value in zone.items() if not key.startswith("_")}
                for zone in zone_rows
                if zone["_start_ms"] < (cycle_end if cycle_end is not None else end_ms)
                and zone["_end_ms"] > cycle["start_ts"]
            ]
            cycle_rows.append(
                {
                    "start": format_local(cycle["start_ts"], tz_name),
                    "end": None if cycle_end is None else format_local(cycle_end, tz_name),
                    "duration_s": cycle["duration_s"],
                    "gallons": cycle["gallons"],
                    "psi_avg": cycle["psi_avg"],
                    "psi_min": cycle["psi_min"],
                    "psi_max": cycle["psi_max"],
                    "amps_avg": cycle["amps_avg"],
                    "amps_max": cycle["amps_max"],
                    "zones": overlapping,
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
        "cycles": cycle_rows,
        "zone_runs": [{key: value for key, value in zone.items() if not key.startswith("_")} for zone in zone_rows],
    }
