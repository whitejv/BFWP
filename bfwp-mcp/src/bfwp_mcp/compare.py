"""Which zone changed: each zone's latest run against the median of its runs."""

from __future__ import annotations

from pathlib import Path

from bfwp_mcp.clock import LOCAL_TZ, format_utc, parse_ms
from bfwp_mcp.db import connect_readonly, database_path
from bfwp_mcp.signature import get_zone_signature

_FIELDS = ("psi", "amps", "gpm", "gallons")


def compare_zone_signatures(
    start: str,
    end: str,
    dev: str = "",
    source: str = "real",
    db_path: Path | None = None,
    tz_name: str = LOCAL_TZ,
) -> dict:
    """Latest run of every zone in [start, end), against the median of that zone's runs.

    The median matches `get_zone_signature`. A zone with one run has deltas of zero.
    """
    if source not in ("real", "sim"):
        raise ValueError(f"source must be real or sim, not {source}")
    device = dev or ("twin1" if source == "sim" else "well1")
    start_ms = parse_ms(start, tz_name)
    end_ms = parse_ms(end, tz_name)
    if end_ms <= start_ms:
        raise ValueError("end must be after start")

    path = db_path or database_path(source)
    conn = connect_readonly(path)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT zone_id FROM zone_runs
            WHERE start_ts < ? AND end_ts > ?
            """,
            (end_ms, start_ms),
        ).fetchall()
    finally:
        conn.close()

    zones = []
    for row in sorted(rows, key=lambda item: _zone_key(item["zone_id"])):
        signature = get_zone_signature(
            row["zone_id"],
            start,
            end,
            dev=device,
            source=source,
            db_path=path,
            tz_name=tz_name,
        )
        current = signature["runs"][-1]
        zones.append(
            {
                "zone": signature["zone"],
                "current": {field: current[field] for field in ("start", "end", *_FIELDS)},
                "baseline": signature["baseline"],
                **{f"{field}_delta": current[f"{field}_delta"] for field in _FIELDS},
            }
        )
    return {
        "start_utc": format_utc(start_ms),
        "end_utc": format_utc(end_ms),
        "tz": tz_name,
        "source": source,
        "dev": device,
        "zones": zones,
    }


def _zone_key(zone_id: str) -> tuple:
    text = str(zone_id)
    return (0, int(text)) if text.isdigit() else (1, text)
