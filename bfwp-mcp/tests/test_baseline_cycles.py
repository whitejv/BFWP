"""Baseline night: pump cycles and zone gallons match the truth log. The tool never sees that log."""

import json
import sqlite3
import subprocess
from pathlib import Path

from bfwp_mcp.clock import parse_ms
from bfwp_mcp.cycles import get_pump_cycles
from bfwp_mcp.db import connect_readonly

REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "baseline_normal_night.yaml"
TWIN = REPO / "bfwp-twin" / ".venv" / "bin" / "bfwp-twin"
INGEST = REPO / "bfwp-ingest" / ".venv" / "bin" / "bfwp-ingest"


def _meter_delta(db: Path, dev: str, start_ms: int, end_ms: int) -> int:
    conn = sqlite3.connect(db)
    rows = conn.execute(
        """
        SELECT gal_total FROM readings
        WHERE dev = ? AND ts >= ? AND ts < ?
        ORDER BY ts, seq
        """,
        (dev, start_ms, end_ms),
    ).fetchall()
    conn.close()
    assert len(rows) >= 2
    return int(rows[-1][0]) - int(rows[0][0])


def test_baseline_cycles_and_zone_gallons_match_truth_log(tmp_path: Path):
    subprocess.run(
        [str(TWIN), "run", str(SCENARIO), "--truth-log-dir", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    truth_log = next(
        path for path in tmp_path.glob("baseline_normal_night-*.jsonl") if path.suffixes == [".jsonl"]
    )
    messages = next(tmp_path.glob("baseline_normal_night-*.messages.jsonl"))
    db = tmp_path / "well-sim.db"
    subprocess.run([str(INGEST), "load", str(messages), "--db", str(db)], check=True)
    subprocess.run([str(INGEST), "load-zones", str(truth_log), "--db", str(db)], check=True)

    injected = [
        json.loads(line)
        for line in truth_log.read_text().splitlines()
        if json.loads(line)["inject"] == "zone_on"
    ]
    answer = get_pump_cycles(
        "2026-10-08T21:00:00-05:00",
        "2026-10-09T07:00:00-05:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )

    assert answer["source"] == "sim"
    assert answer["dev"] == "twin1"
    assert [zone["zone_id"] for zone in answer["zone_runs"]] == [str(row["zone"]) for row in injected]
    for zone, row in zip(answer["zone_runs"], injected, strict=True):
        start_ms = int(row["ts"])
        end_ms = start_ms + int(round(float(row["minutes"]) * 60_000))
        assert parse_ms(zone["start"]) == start_ms
        assert parse_ms(zone["end"]) == end_ms
        assert zone["gallons"] == _meter_delta(db, "twin1", start_ms, end_ms)
        assert zone["gallons"] > 0

    conn = connect_readonly(db)
    stored = conn.execute(
        "SELECT start_ts, gallons, duration_s FROM pump_cycles WHERE dev = 'twin1' ORDER BY start_ts"
    ).fetchall()
    conn.close()
    assert len(answer["cycles"]) == len(stored) > 0
    for cycle, row in zip(answer["cycles"], stored, strict=True):
        assert parse_ms(cycle["start"]) == row["start_ts"]
        assert cycle["gallons"] == row["gallons"]
        assert cycle["duration_s"] == row["duration_s"]
        assert cycle["zones"]
    first = parse_ms(answer["cycles"][0]["start"])
    assert parse_ms("2026-10-08T22:00:00-05:00") <= first <= parse_ms("2026-10-08T22:05:00-05:00")


def test_database_is_read_only(tmp_path: Path):
    db = tmp_path / "empty.db"
    db.write_bytes(b"")
    # An empty file is not a database the tool should migrate. Build a real empty schema
    # by opening it read-write outside the server, then prove the server connection cannot write.
    import sqlite3

    raw = sqlite3.connect(db)
    raw.execute("CREATE TABLE probe (id INTEGER)")
    raw.commit()
    raw.close()
    conn = connect_readonly(db)
    try:
        try:
            conn.execute("INSERT INTO probe (id) VALUES (1)")
            raised = False
        except sqlite3.OperationalError:
            raised = True
        assert raised
    finally:
        conn.close()
