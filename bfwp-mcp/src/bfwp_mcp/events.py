"""Device events in a time range."""

from __future__ import annotations

import json
from pathlib import Path

from bfwp_mcp.clock import LOCAL_TZ, format_local, format_utc, parse_ms
from bfwp_mcp.db import connect_readonly, database_path

MAX_EVENTS = 2000


def get_events(
    start: str,
    end: str,
    types: list[str] | None = None,
    dev: str = "",
    source: str = "real",
    db_path: Path | None = None,
    tz_name: str = LOCAL_TZ,
) -> dict:
    """Events in [start, end). `types` limits the list; omitted, every type is included.

    `counts` covers the whole range. When more than 2,000 events match, `events`
    keeps the latest 2,000 and `truncated` is true.
    """
    if source not in ("real", "sim"):
        raise ValueError(f"source must be real or sim, not {source}")
    device = dev or ("twin1" if source == "sim" else "well1")
    start_ms = parse_ms(start, tz_name)
    end_ms = parse_ms(end, tz_name)
    if end_ms <= start_ms:
        raise ValueError("end must be after start")
    wanted = tuple(types) if types else ()

    conn = connect_readonly(db_path or database_path(source))
    try:
        counts = _counts(conn, device, start_ms, end_ms, wanted)
        rows = _rows(conn, device, start_ms, end_ms, wanted)
    finally:
        conn.close()

    truncated = len(rows) > MAX_EVENTS
    if truncated:
        rows = rows[-MAX_EVENTS:]
    return {
        "start_utc": format_utc(start_ms),
        "end_utc": format_utc(end_ms),
        "tz": tz_name,
        "source": source,
        "dev": device,
        "truncated": truncated,
        "counts": counts,
        "events": [_event(row, tz_name) for row in rows],
    }


def _where(wanted: tuple[str, ...]) -> tuple[str, list]:
    if not wanted:
        return "", []
    marks = ", ".join("?" for _ in wanted)
    return f" AND type IN ({marks})", list(wanted)


def _counts(conn, dev: str, start_ms: int, end_ms: int, wanted: tuple[str, ...]) -> dict[str, int]:
    clause, args = _where(wanted)
    rows = conn.execute(
        f"""
        SELECT type, COUNT(*) FROM events
        WHERE dev = ? AND ts >= ? AND ts < ?{clause}
        GROUP BY type ORDER BY type
        """,
        [dev, start_ms, end_ms, *args],
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _rows(conn, dev: str, start_ms: int, end_ms: int, wanted: tuple[str, ...]):
    clause, args = _where(wanted)
    return conn.execute(
        f"""
        SELECT ts, type, data FROM events
        WHERE dev = ? AND ts >= ? AND ts < ?{clause}
        ORDER BY ts, seq
        """,
        [dev, start_ms, end_ms, *args],
    ).fetchall()


def _event(row, tz_name: str) -> dict:
    data = row["data"]
    if isinstance(data, str):
        data = json.loads(data)
    return {"time": format_local(row["ts"], tz_name), "type": row["type"], "data": data}
