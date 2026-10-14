"""Pressure, current, flow, and pump series, plus the meter change over a window."""

from __future__ import annotations

from pathlib import Path

from bfwp_mcp.clock import LOCAL_TZ, format_local, format_utc, parse_ms
from bfwp_mcp.db import connect_readonly, database_path

MAX_POINTS = 2000
SIX_H_MS = 6 * 3_600_000
MINUTE_MS = 60_000
FIELD_ORDER = ("psi", "amps", "gpm", "pump")
# Coarser than one minute when a rollup would still exceed MAX_POINTS.
LADDER_MIN = (1, 5, 15, 60, 180, 1440)


def meter_delta(conn, dev: str, start_ms: int, end_ms: int) -> int:
    """Last `gal_total` minus first `gal_total` for readings in [start_ms, end_ms)."""
    rows = conn.execute(
        """
        SELECT gal_total FROM readings
        WHERE dev = ? AND ts >= ? AND ts < ?
        ORDER BY ts, seq
        """,
        (dev, start_ms, end_ms),
    ).fetchall()
    if len(rows) < 2:
        return 0
    return int(rows[-1]["gal_total"]) - int(rows[0]["gal_total"])


def get_readings(
    start: str,
    end: str,
    resolution: str = "auto",
    fields: list[str] | None = None,
    dev: str = "",
    source: str = "real",
    db_path: Path | None = None,
    tz_name: str = LOCAL_TZ,
) -> dict:
    """psi, amps, gpm, and pump from [start, end).

    `resolution="auto"` uses raw readings for a span of six hours or less when
    that is at most about 2,000 points. Longer spans, and raw series that would
    be longer than that, use the one-minute rollup or a coarser bucket.
    On a rollup, `psi` is the average and `psi_min` / `psi_max` are included,
    `gpm` is the gallon change per minute of the bucket, and `pump` is seconds on.
    """
    if source not in ("real", "sim"):
        raise ValueError(f"source must be real or sim, not {source}")
    chosen = _fields(fields)
    device = dev or ("twin1" if source == "sim" else "well1")
    start_ms = parse_ms(start, tz_name)
    end_ms = parse_ms(end, tz_name)
    if end_ms <= start_ms:
        raise ValueError("end must be after start")

    conn = connect_readonly(db_path or database_path(source))
    try:
        raw_count = conn.execute(
            "SELECT COUNT(*) FROM readings WHERE dev = ? AND ts >= ? AND ts < ?",
            (device, start_ms, end_ms),
        ).fetchone()[0]
        use_raw = _use_raw(resolution, end_ms - start_ms, raw_count)
        if use_raw:
            rows = conn.execute(
                f"""
                SELECT ts, {", ".join(chosen)} FROM readings
                WHERE dev = ? AND ts >= ? AND ts < ?
                ORDER BY ts, seq
                """,
                (device, start_ms, end_ms),
            ).fetchall()
            points = [_raw_point(row, chosen, tz_name) for row in rows]
            served = "raw"
        else:
            minutes = conn.execute(
                """
                SELECT minute_ts, n, psi_avg, psi_min, psi_max, amps_avg, pump_secs, gallons
                FROM readings_1min
                WHERE dev = ? AND minute_ts >= ? AND minute_ts < ?
                ORDER BY minute_ts
                """,
                (device, start_ms, end_ms),
            ).fetchall()
            step = _step_minutes(resolution, len(minutes))
            buckets = _buckets(minutes, step)
            points = [_bucket_point(bucket, chosen, tz_name) for bucket in buckets]
            served = f"{step}min"
    finally:
        conn.close()

    return {
        "start_utc": format_utc(start_ms),
        "end_utc": format_utc(end_ms),
        "tz": tz_name,
        "source": source,
        "dev": device,
        "resolution": served,
        "points": points,
    }


def _fields(fields: list[str] | None) -> tuple[str, ...]:
    if not fields:
        return FIELD_ORDER
    unknown = [field for field in fields if field not in FIELD_ORDER]
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(unknown)}")
    return tuple(field for field in fields if field in FIELD_ORDER)


def _use_raw(resolution: str, span_ms: int, raw_count: int) -> bool:
    if resolution == "raw":
        return raw_count <= MAX_POINTS
    if resolution == "auto":
        return span_ms <= SIX_H_MS and raw_count <= MAX_POINTS
    if resolution in {f"{step}min" for step in LADDER_MIN}:
        return False
    raise ValueError(f"resolution must be auto, raw, or one of {', '.join(f'{s}min' for s in LADDER_MIN)}")


def _step_minutes(resolution: str, minute_count: int) -> int:
    if resolution in {f"{step}min" for step in LADDER_MIN}:
        minimum = int(resolution.removesuffix("min"))
    else:
        minimum = 1
    choices = [step for step in LADDER_MIN if step >= minimum] or [LADDER_MIN[-1]]
    for step in choices:
        if _bucket_count(minute_count, step) <= MAX_POINTS:
            return step
    step = choices[-1]
    while _bucket_count(minute_count, step) > MAX_POINTS:
        step *= 2
    return step


def _bucket_count(minute_count: int, step: int) -> int:
    if minute_count <= 0:
        return 0
    return (minute_count + step - 1) // step


def _raw_point(row, fields: tuple[str, ...], tz_name: str) -> dict:
    point = {"time": format_local(row["ts"], tz_name)}
    for field in fields:
        point[field] = row[field]
    return point


def _buckets(rows, step: int) -> list[dict]:
    if step == 1:
        return [
            {
                "minute_ts": row["minute_ts"],
                "psi": row["psi_avg"],
                "psi_min": row["psi_min"],
                "psi_max": row["psi_max"],
                "amps": row["amps_avg"],
                "pump": row["pump_secs"],
                "gpm": row["gallons"],
            }
            for row in rows
        ]
    bucket_ms = step * MINUTE_MS
    groups: list[dict] = []
    current = None
    for row in rows:
        key = (row["minute_ts"] // bucket_ms) * bucket_ms
        if current is None or current["minute_ts"] != key:
            current = {
                "minute_ts": key,
                "psi_sum": 0.0,
                "psi_weight": 0,
                "psi_min": None,
                "psi_max": None,
                "amps_sum": 0.0,
                "amps_weight": 0,
                "pump": 0.0,
                "gallons": 0,
            }
            groups.append(current)
        weight = row["n"] or 0
        if row["psi_avg"] is not None and weight:
            current["psi_sum"] += row["psi_avg"] * weight
            current["psi_weight"] += weight
            current["psi_min"] = row["psi_min"] if current["psi_min"] is None else min(current["psi_min"], row["psi_min"])
            current["psi_max"] = row["psi_max"] if current["psi_max"] is None else max(current["psi_max"], row["psi_max"])
        if row["amps_avg"] is not None and weight:
            current["amps_sum"] += row["amps_avg"] * weight
            current["amps_weight"] += weight
        current["pump"] += row["pump_secs"]
        current["gallons"] += row["gallons"]
    for group in groups:
        group["psi"] = None if not group["psi_weight"] else group["psi_sum"] / group["psi_weight"]
        group["amps"] = None if not group["amps_weight"] else group["amps_sum"] / group["amps_weight"]
        group["gpm"] = group["gallons"] / step
    return groups


def _bucket_point(bucket: dict, fields: tuple[str, ...], tz_name: str) -> dict:
    point = {"time": format_local(bucket["minute_ts"], tz_name)}
    if "psi" in fields:
        point["psi"] = bucket["psi"]
        point["psi_min"] = bucket["psi_min"]
        point["psi_max"] = bucket["psi_max"]
    if "amps" in fields:
        point["amps"] = bucket["amps"]
    if "gpm" in fields:
        point["gpm"] = bucket["gpm"]
    if "pump" in fields:
        point["pump"] = bucket["pump"]
    return point
