"""Steady-state signature of a zone, and how each run sits against the median."""

from __future__ import annotations

from pathlib import Path

from bfwp_mcp.clock import LOCAL_TZ, format_local, format_utc, parse_ms
from bfwp_mcp.db import connect_readonly, database_path
from bfwp_mcp.flow import _gallons

# The first half-minute of a run is the valve opening, not the steady draw.
STEADY_SKIP_MS = 30_000


def get_zone_signature(
    zone: str,
    start: str,
    end: str,
    dev: str = "",
    source: str = "real",
    db_path: Path | None = None,
    tz_name: str = LOCAL_TZ,
) -> dict:
    """Each run of `zone` in [start, end): mean psi, amps, and gpm after the first 30 s, plus gallons.

    The baseline is the median of those runs. Each delta is the run minus that median.
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
        zones = conn.execute(
            """
            SELECT start_ts, end_ts FROM zone_runs
            WHERE zone_id = ? AND start_ts < ? AND end_ts > ?
            ORDER BY start_ts
            """,
            (str(zone), end_ms, start_ms),
        ).fetchall()
        runs = [_run(conn, device, zone_row["start_ts"], zone_row["end_ts"], tz_name) for zone_row in zones]
    finally:
        conn.close()

    baseline = _baseline(runs)
    for run in runs:
        for field in ("psi", "amps", "gpm", "gallons"):
            run[f"{field}_delta"] = None if run[field] is None or baseline[field] is None else run[field] - baseline[field]
    return {
        "start_utc": format_utc(start_ms),
        "end_utc": format_utc(end_ms),
        "tz": tz_name,
        "source": source,
        "dev": device,
        "zone": str(zone),
        "baseline": baseline,
        "runs": runs,
    }


def _run(conn, dev: str, start_ms: int, end_ms: int, tz_name: str) -> dict:
    steady_start = start_ms + STEADY_SKIP_MS
    rows = []
    if steady_start < end_ms:
        rows = conn.execute(
            """
            SELECT psi, amps, gpm FROM readings
            WHERE dev = ? AND ts >= ? AND ts < ?
            ORDER BY ts, seq
            """,
            (dev, steady_start, end_ms),
        ).fetchall()
    return {
        "start": format_local(start_ms, tz_name),
        "end": format_local(end_ms, tz_name),
        "psi": _mean(row["psi"] for row in rows),
        "amps": _mean(row["amps"] for row in rows),
        "gpm": _mean(row["gpm"] for row in rows),
        "gallons": _gallons(conn, dev, start_ms, end_ms),
    }


def _mean(values) -> float | None:
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _baseline(runs: list[dict]) -> dict:
    baseline = {"runs": len(runs)}
    for field in ("psi", "amps", "gpm", "gallons"):
        baseline[field] = _median([run[field] for run in runs if run[field] is not None])
    return baseline


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2
