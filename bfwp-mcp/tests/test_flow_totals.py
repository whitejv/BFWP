"""Daily gallons split into zone runs and flow outside them.

The tool never sees the truth log.
"""

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
    subprocess.run([str(INGEST), "load-zones", str(truth_log), "--db", str(db)], check=True)
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


def test_baseline_night_gallons_are_scheduled(tmp_path: Path):
    db, injected = _load(tmp_path, BASELINE, "baseline_normal_night")
    zones = [row for row in injected if row["inject"] == "zone_on"]
    answer = get_flow_totals(
        "2026-10-08T21:00:00",
        "2026-10-09T07:00:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )

    by_date = {bucket["date"]: bucket for bucket in answer["buckets"]}
    assert list(by_date) == ["2026-10-08", "2026-10-09"]
    scheduled = sum(
        _gallons(db, int(zone["ts"]), int(zone["ts"]) + int(round(float(zone["minutes"]) * 60_000)))
        for zone in zones
    )
    assert by_date["2026-10-08"]["scheduled"] == scheduled > 0
    assert by_date["2026-10-08"]["unscheduled"] == 0
    assert by_date["2026-10-09"]["scheduled"] == 0
    assert by_date["2026-10-09"]["unscheduled"] == 0
    for bucket in answer["buckets"]:
        assert bucket["gallons"] == bucket["scheduled"] + bucket["unscheduled"]


def test_overnight_leak_gallons_are_unscheduled(tmp_path: Path):
    db, injected = _load(tmp_path, LEAK, "overnight_leak")
    leak = next(row for row in injected if row["inject"] == "leak")
    answer = get_flow_totals(
        "2026-10-08T21:00:00",
        "2026-10-09T07:00:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )
    unscheduled = sum(bucket["unscheduled"] for bucket in answer["buckets"])
    metered = _gallons(db, int(leak["ts"]), parse_ms("2026-10-09T07:00:00"))
    assert leak["location"] == "downstream"
    assert unscheduled > 0
    assert abs(unscheduled - metered) <= 2
    assert sum(bucket["scheduled"] for bucket in answer["buckets"]) > 0
