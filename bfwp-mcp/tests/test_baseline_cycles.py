"""Baseline night: pump cycles match the rows ingest stored. The tool never sees the truth log."""

import subprocess
from pathlib import Path

from bfwp_mcp.clock import parse_ms
from bfwp_mcp.cycles import get_pump_cycles
from bfwp_mcp.db import connect_readonly

REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "baseline_normal_night.yaml"
TWIN = REPO / "bfwp-twin" / ".venv" / "bin" / "bfwp-twin"
INGEST = REPO / "bfwp-ingest" / ".venv" / "bin" / "bfwp-ingest"


def test_baseline_cycles_match_stored_runs(tmp_path: Path):
    subprocess.run(
        [str(TWIN), "run", str(SCENARIO), "--truth-log-dir", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    messages = next(tmp_path.glob("baseline_normal_night-*.messages.jsonl"))
    db = tmp_path / "well-sim.db"
    subprocess.run([str(INGEST), "load", str(messages), "--db", str(db)], check=True)

    answer = get_pump_cycles(
        "2026-10-08T21:00:00-05:00",
        "2026-10-09T07:00:00-05:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )

    assert answer["source"] == "sim"
    assert answer["dev"] == "twin1"
    assert "zone_runs" not in answer

    conn = connect_readonly(db)
    stored = conn.execute(
        "SELECT start_ts, gallons, duration_s FROM pump_cycles WHERE dev = 'twin1' ORDER BY start_ts"
    ).fetchall()
    conn.close()
    assert len(answer["cycles"]) == len(stored) > 0
    for cycle, row in zip(answer["cycles"], stored, strict=True):
        assert parse_ms(cycle["start"]) == row["start_ts"]
        assert cycle["gallons"] == row["gallons"]
        assert cycle["gallons"] > 0
        assert cycle["duration_s"] == row["duration_s"]
        assert "zones" not in cycle
    first = parse_ms(answer["cycles"][0]["start"])
    assert parse_ms("2026-10-08T22:00:00-05:00") <= first <= parse_ms("2026-10-08T22:05:00-05:00")


def test_database_is_read_only(tmp_path: Path):
    db = tmp_path / "empty.db"
    db.write_bytes(b"")
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
