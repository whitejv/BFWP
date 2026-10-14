"""Coverage: cadence holes, and the sequence jump a reboot leaves behind.

The scenario test never hands the truth log to the tool.
"""

import json
import sqlite3
import subprocess
from pathlib import Path

from bfwp_mcp.clock import parse_ms
from bfwp_mcp.coverage import get_data_coverage

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "bfwp-spec" / "contracts" / "sqlite" / "schema-v1.sql"
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "sensor_fault_and_reboot.yaml"
TWIN = REPO / "bfwp-twin" / ".venv" / "bin" / "bfwp-twin"
INGEST = REPO / "bfwp-ingest" / ".venv" / "bin" / "bfwp-ingest"

# Contract limit for a hole between two active readings.
ACTIVE_LIMIT_S = 3


def _empty_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    script = "\n".join(
        line for line in SCHEMA.read_text().splitlines() if not line.strip().startswith("PRAGMA")
    )
    conn.executescript(script)
    return conn


def _reading(conn, seq: int, ts: int, mode: str) -> None:
    conn.execute(
        """
        INSERT INTO readings (
          dev, seq, ts, mode, psi, amps, pump, gal_total, gpm, received_ts
        ) VALUES ('twin1', ?, ?, ?, 60, 0, 0, 0, 0, ?)
        """,
        (seq, ts, mode, ts),
    )


def test_active_hole_and_seq_gap(tmp_path: Path):
    start = parse_ms("2026-10-09T03:00:00")
    db = tmp_path / "well-sim.db"
    conn = _empty_db(db)
    _reading(conn, 1, start, "active")
    _reading(conn, 2, start + 1_000, "active")
    _reading(conn, 3, start + 6_000, "active")
    conn.execute(
        """
        INSERT INTO events (dev, seq, ts, type, data, received_ts)
        VALUES ('twin1', 6, ?, 'boot', '{}', ?)
        """,
        (start + 6_000, start + 6_000),
    )
    conn.commit()
    conn.close()

    answer = get_data_coverage(
        "2026-10-09T03:00:00",
        "2026-10-09T03:00:07",
        dev="twin1",
        source="sim",
        db_path=db,
    )
    assert len(answer["time_gaps"]) == 1
    gap = answer["time_gaps"][0]
    assert gap["seconds"] == 5.0
    assert gap["from_mode"] == "active"
    assert gap["to_mode"] == "active"
    assert gap["limit_s"] == ACTIVE_LIMIT_S
    assert [span["data"] for span in answer["spans"]] == [True, False, True]
    assert answer["seq_gaps"] == [
        {
            "from_seq": 3,
            "to_seq": 6,
            "missing": 2,
            "from": gap["end"],
            "to": gap["end"],
        }
    ]


def test_idle_minute_and_mode_change_stay_covered(tmp_path: Path):
    start = parse_ms("2026-10-09T03:00:00")
    db = tmp_path / "well-sim.db"
    conn = _empty_db(db)
    _reading(conn, 1, start, "idle")
    _reading(conn, 2, start + 60_000, "idle")
    _reading(conn, 3, start + 61_000, "active")
    _reading(conn, 4, start + 121_000, "idle")
    conn.commit()
    conn.close()

    answer = get_data_coverage(
        "2026-10-09T03:00:00",
        "2026-10-09T03:02:02",
        dev="twin1",
        source="sim",
        db_path=db,
    )
    assert answer["time_gaps"] == []
    assert answer["seq_gaps"] == []
    assert len(answer["spans"]) == 1
    assert answer["spans"][0]["data"] is True
    assert parse_ms(answer["spans"][0]["start"]) == start
    assert parse_ms(answer["spans"][0]["end"]) == parse_ms("2026-10-09T03:02:02")


def test_reboot_skips_seq_without_a_time_hole(tmp_path: Path):
    subprocess.run(
        [str(TWIN), "run", str(SCENARIO), "--truth-log-dir", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    truth_log = next(
        path
        for path in tmp_path.glob("sensor_fault_and_reboot-*.jsonl")
        if path.suffixes == [".jsonl"]
    )
    messages = next(tmp_path.glob("sensor_fault_and_reboot-*.messages.jsonl"))
    db = tmp_path / "well-sim.db"
    subprocess.run([str(INGEST), "load", str(messages), "--db", str(db)], check=True)

    injected = [json.loads(line) for line in truth_log.read_text().splitlines()]
    reboot_ms = int(next(row for row in injected if row["inject"] == "reboot")["ts"])
    answer = get_data_coverage(
        "2026-10-09T03:00:00",
        "2026-10-09T04:00:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )

    conn = sqlite3.connect(db)
    readings = conn.execute(
        """
        SELECT ts, mode FROM readings
        WHERE dev = 'twin1' AND ts >= ? AND ts < ?
        ORDER BY ts, seq
        """,
        (parse_ms("2026-10-09T03:00:00"), parse_ms("2026-10-09T04:00:00")),
    ).fetchall()
    seqs = [
        row[0]
        for row in conn.execute(
            """
            SELECT seq FROM readings WHERE dev = 'twin1'
            UNION ALL
            SELECT seq FROM events WHERE dev = 'twin1'
            UNION ALL
            SELECT seq FROM health WHERE dev = 'twin1'
            ORDER BY seq
            """
        )
    ]
    conn.close()

    assert answer["readings"] == len(readings) > 0
    assert answer["time_gaps"] == []
    assert _expected_time_gaps(readings) == []
    assert len(answer["seq_gaps"]) == 1
    gap = answer["seq_gaps"][0]
    assert gap["missing"] == _missing(seqs)
    assert gap["missing"] >= 1
    assert parse_ms(gap["to"]) == reboot_ms
    assert len(answer["spans"]) == 1
    assert answer["spans"][0]["data"] is True


def _limit_s(left: str, right: str) -> int:
    if left == "active" and right == "active":
        return ACTIVE_LIMIT_S
    return 90


def _expected_time_gaps(readings) -> list[tuple[int, int]]:
    gaps = []
    for left, right in zip(readings, readings[1:]):
        if right[0] - left[0] > _limit_s(left[1], right[1]) * 1000:
            gaps.append((left[0], right[0]))
    return gaps


def _missing(seqs: list[int]) -> int:
    holes = [right - left - 1 for left, right in zip(seqs, seqs[1:]) if right > left + 1]
    assert len(holes) == 1
    return holes[0]
