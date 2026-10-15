"""Daily gallons match the meter. The tool never sees the truth log."""

import json
import sqlite3
import subprocess
from pathlib import Path

from bfwp_mcp.clock import parse_ms
from bfwp_mcp.flow import get_flow_totals

REPO = Path(__file__).resolve().parents[2]
BASELINE = REPO / "bfwp-spec" / "contracts" / "scenarios" / "baseline_normal_night.yaml"
LEAK = REPO / "bfwp-spec" / "contracts" / "scenarios" / "overnight_leak.yaml"
TWIN = REPO / "bfwp-twin" / ".venv" / "bin" / "bfwp-twin"
INGEST = REPO / "bfwp-ingest" / ".venv" / "bin" / "bfwp-ingest"


def _load(tmp_path: Path, scenario: Path, stem: str) -> tuple[Path, list[dict]]:
    subprocess.run(
        [str(TWIN), "run", str(scenario), "--truth-log-dir", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    truth_log = next(path for path in tmp_path.glob(f"{stem}-*.jsonl") if path.suffixes == [".jsonl"])
    messages = next(tmp_path.glob(f"{stem}-*.messages.jsonl"))
    db = tmp_path / "well-sim.db"
    subprocess.run([str(INGEST), "load", str(messages), "--db", str(db)], check=True)
    injected = [json.loads(line) for line in truth_log.read_text().splitlines()]
    return db, injected


def _gallons(db: Path, start_ms: int, end_ms: int) -> int:
    conn = sqlite3.connect(db)
    after = conn.execute(
        "SELECT gal_total FROM readings WHERE dev = 'twin1' AND ts < ? ORDER BY ts DESC, seq DESC LIMIT 1",
        (end_ms,),
    ).fetchone()
    before = conn.execute(
        "SELECT gal_total FROM readings WHERE dev = 'twin1' AND ts < ? ORDER BY ts DESC, seq DESC LIMIT 1",
        (start_ms,),
    ).fetchone()
    conn.close()
    return int(after[0]) - (0 if before is None else int(before[0]))


def test_baseline_night_gallon_totals(tmp_path: Path):
    db, _injected = _load(tmp_path, BASELINE, "baseline_normal_night")
    answer = get_flow_totals(
        "2026-10-08T21:00:00",
        "2026-10-09T07:00:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )

    by_date = {bucket["date"]: bucket for bucket in answer["buckets"]}
    assert list(by_date) == ["2026-10-08", "2026-10-09"]
    for bucket in answer["buckets"]:
        assert "scheduled" not in bucket
        assert bucket["gallons"] == _gallons(db, parse_ms(bucket["start"]), parse_ms(bucket["end"]))
    assert by_date["2026-10-08"]["gallons"] > 0
    assert by_date["2026-10-09"]["gallons"] == 0


def test_overnight_leak_gallons_continue_after_midnight(tmp_path: Path):
    db, injected = _load(tmp_path, LEAK, "overnight_leak")
    leak = next(row for row in injected if row["inject"] == "leak")
    answer = get_flow_totals(
        "2026-10-08T21:00:00",
        "2026-10-09T07:00:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )
    by_date = {bucket["date"]: bucket for bucket in answer["buckets"]}
    midnight = parse_ms("2026-10-09T00:00:00")
    end = parse_ms("2026-10-09T07:00:00")
    assert leak["location"] == "downstream"
    assert by_date["2026-10-08"]["gallons"] > _gallons(db, int(leak["ts"]), midnight) > 0
    assert by_date["2026-10-09"]["gallons"] == _gallons(db, midnight, end) > 0
