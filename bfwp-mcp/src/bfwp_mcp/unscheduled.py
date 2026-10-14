"""Pump runs and metered flow that do not overlap a zone run."""

from __future__ import annotations

from pathlib import Path

from bfwp_mcp.clock import LOCAL_TZ, format_local, format_utc, parse_ms
from bfwp_mcp.db import connect_readonly, database_path
from bfwp_mcp.readings import meter_delta

# A downstream leak near 0.4 gpm pulses about every few minutes. A longer quiet
# stretch is a separate draw, not part of the same flow.
GAP_MS = 10 * 60_000
MINUTE_MS = 60_000


def get_unscheduled_pump_runs(
    start: str,
    end: str,
    dev: str = "",
    source: str = "real",
    db_path: Path | None = None,
    tz_name: str = LOCAL_TZ,
) -> dict:
    """Cycles and metered flow in [start, end) with no overlapping zone run.

    Flow gallons are the meter change outside zone runs. A pump cycle's own
    gallons count only while the pump is on, so a slow leak shows up in `flow`.
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
            SELECT start_ts, end_ts FROM zone_runs
            WHERE start_ts < ? AND end_ts > ?
            ORDER BY start_ts
            """,
            (end_ms, start_ms),
        ).fetchall()
        cycle_rows = []
        for cycle in cycles:
            cycle_end = cycle["end_ts"] if cycle["end_ts"] is not None else end_ms
            if any(zone["start_ts"] < cycle_end and zone["end_ts"] > cycle["start_ts"] for zone in zones):
                continue
            cycle_rows.append(
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
            )
        flow = [
            {
                "start": format_local(span_start, tz_name),
                "end": format_local(span_end, tz_name),
                "gallons": gallons,
                "gpm": round(gallons / ((span_end - span_start) / MINUTE_MS), 3),
            }
            for span_start, span_end, gallons in _flow_spans(conn, device, start_ms, end_ms, zones)
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
        "flow": flow,
    }


def _flow_spans(conn, dev: str, start_ms: int, end_ms: int, zones) -> list[tuple[int, int, int]]:
    rows = conn.execute(
        """
        SELECT minute_ts FROM readings_1min
        WHERE dev = ? AND minute_ts >= ? AND minute_ts < ? AND gallons > 0
        ORDER BY minute_ts
        """,
        (dev, start_ms, end_ms),
    ).fetchall()
    minutes = [row["minute_ts"] for row in rows if not _in_zone(row["minute_ts"], zones)]
    spans = []
    if not minutes:
        return spans
    span_start = previous = minutes[0]
    for minute in minutes[1:]:
        if minute - previous > GAP_MS:
            spans.append(_span(conn, dev, span_start, previous, end_ms))
            span_start = minute
        previous = minute
    spans.append(_span(conn, dev, span_start, previous, end_ms))
    return [span for span in spans if span[2] > 0]


def _in_zone(minute: int, zones) -> bool:
    return any(minute < zone["end_ts"] and minute + MINUTE_MS > zone["start_ts"] for zone in zones)


def _span(conn, dev: str, first_minute: int, last_minute: int, end_ms: int) -> tuple[int, int, int]:
    span_end = min(last_minute + MINUTE_MS, end_ms)
    return first_minute, span_end, meter_delta(conn, dev, first_minute, span_end)
