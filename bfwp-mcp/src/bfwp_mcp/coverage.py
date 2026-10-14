"""Whether a time range has the readings its cadence promised, and whether seq skipped."""

from __future__ import annotations

from pathlib import Path

from bfwp_mcp.clock import LOCAL_TZ, format_local, format_utc, parse_ms
from bfwp_mcp.db import connect_readonly, database_path

# Contract: a hole is > 3 s between active readings, or > 90 s between idle readings.
ACTIVE_LIMIT_S = 3
IDLE_LIMIT_S = 90


def get_data_coverage(
    start: str,
    end: str,
    dev: str = "",
    source: str = "real",
    db_path: Path | None = None,
    tz_name: str = LOCAL_TZ,
) -> dict:
    """Spans with and without telemetry, plus missing sequence numbers, in [start, end).

    A gap between two active readings is longer than 3 s. Any other pair, or the
    edge of the window, uses 90 s. Sequence numbers come from readings, events,
    and health together.
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
        readings = conn.execute(
            """
            SELECT seq, ts, mode FROM readings
            WHERE dev = ? AND ts >= ? AND ts < ?
            ORDER BY ts, seq
            """,
            (device, start_ms, end_ms),
        ).fetchall()
        numbered = conn.execute(
            """
            SELECT seq, ts FROM readings WHERE dev = ? AND ts >= ? AND ts < ?
            UNION ALL
            SELECT seq, ts FROM events WHERE dev = ? AND ts >= ? AND ts < ?
            UNION ALL
            SELECT seq, ts FROM health WHERE dev = ? AND ts >= ? AND ts < ?
            ORDER BY seq, ts
            """,
            (device, start_ms, end_ms) * 3,
        ).fetchall()
    finally:
        conn.close()

    time_gaps = _time_gaps(start_ms, end_ms, readings)
    seq_gaps = _seq_gaps(numbered)
    return {
        "start_utc": format_utc(start_ms),
        "end_utc": format_utc(end_ms),
        "tz": tz_name,
        "source": source,
        "dev": device,
        "readings": len(readings),
        "time_gaps": [_format_time_gap(gap, tz_name) for gap in time_gaps],
        "seq_gaps": [_format_seq_gap(gap, tz_name) for gap in seq_gaps],
        "spans": [_format_span(span, tz_name) for span in _spans(start_ms, end_ms, time_gaps)],
    }


def _limit_s(left: str | None, right: str | None) -> int:
    if left == "active" and right == "active":
        return ACTIVE_LIMIT_S
    return IDLE_LIMIT_S


def _time_gaps(start_ms: int, end_ms: int, readings) -> list[dict]:
    if not readings:
        return [
            {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "from_mode": None,
                "to_mode": None,
                "limit_s": IDLE_LIMIT_S,
            }
        ]
    gaps = []
    first = readings[0]
    head_limit = _limit_s(first["mode"], first["mode"])
    if first["ts"] - start_ms > head_limit * 1000:
        gaps.append(
            {
                "start_ms": start_ms,
                "end_ms": first["ts"],
                "from_mode": None,
                "to_mode": first["mode"],
                "limit_s": head_limit,
            }
        )
    for left, right in zip(readings, readings[1:]):
        limit = _limit_s(left["mode"], right["mode"])
        if right["ts"] - left["ts"] > limit * 1000:
            gaps.append(
                {
                    "start_ms": left["ts"],
                    "end_ms": right["ts"],
                    "from_mode": left["mode"],
                    "to_mode": right["mode"],
                    "limit_s": limit,
                }
            )
    last = readings[-1]
    tail_limit = _limit_s(last["mode"], last["mode"])
    if end_ms - last["ts"] > tail_limit * 1000:
        gaps.append(
            {
                "start_ms": last["ts"],
                "end_ms": end_ms,
                "from_mode": last["mode"],
                "to_mode": None,
                "limit_s": tail_limit,
            }
        )
    return gaps


def _seq_gaps(rows) -> list[dict]:
    ordered = []
    seen: set[int] = set()
    for row in rows:
        seq = int(row["seq"])
        if seq in seen:
            continue
        seen.add(seq)
        ordered.append((seq, int(row["ts"])))
    gaps = []
    for (left_seq, left_ts), (right_seq, right_ts) in zip(ordered, ordered[1:]):
        missing = right_seq - left_seq - 1
        if missing > 0:
            gaps.append(
                {
                    "from_seq": left_seq,
                    "to_seq": right_seq,
                    "missing": missing,
                    "from_ms": left_ts,
                    "to_ms": right_ts,
                }
            )
    return gaps


def _spans(start_ms: int, end_ms: int, gaps: list[dict]) -> list[dict]:
    spans = []
    cursor = start_ms
    for gap in gaps:
        if gap["start_ms"] > cursor:
            spans.append({"start_ms": cursor, "end_ms": gap["start_ms"], "data": True})
        spans.append({"start_ms": gap["start_ms"], "end_ms": gap["end_ms"], "data": False})
        cursor = gap["end_ms"]
    if cursor < end_ms:
        spans.append({"start_ms": cursor, "end_ms": end_ms, "data": True})
    return spans


def _format_time_gap(gap: dict, tz_name: str) -> dict:
    return {
        "start": format_local(gap["start_ms"], tz_name),
        "end": format_local(gap["end_ms"], tz_name),
        "seconds": round((gap["end_ms"] - gap["start_ms"]) / 1000, 3),
        "from_mode": gap["from_mode"],
        "to_mode": gap["to_mode"],
        "limit_s": gap["limit_s"],
    }


def _format_seq_gap(gap: dict, tz_name: str) -> dict:
    return {
        "from_seq": gap["from_seq"],
        "to_seq": gap["to_seq"],
        "missing": gap["missing"],
        "from": format_local(gap["from_ms"], tz_name),
        "to": format_local(gap["to_ms"], tz_name),
    }


def _format_span(span: dict, tz_name: str) -> dict:
    return {
        "start": format_local(span["start_ms"], tz_name),
        "end": format_local(span["end_ms"], tz_name),
        "data": span["data"],
    }
