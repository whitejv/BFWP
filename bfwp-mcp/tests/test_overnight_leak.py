"""Overnight leak: unscheduled metered flow after the injection matches expect.analysis.

The tool never sees the truth log or the scenario file.
"""

import json
import sqlite3
import subprocess
from pathlib import Path

from bfwp_mcp.clock import parse_ms
from bfwp_mcp.unscheduled import get_unscheduled_pump_runs

REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "overnight_leak.yaml"
TWIN = REPO / "bfwp-twin" / ".venv" / "bin" / "bfwp-twin"
INGEST = REPO / "bfwp-ingest" / ".venv" / "bin" / "bfwp-ingest"


def _expect_analysis(path: Path) -> dict:
    text = path.read_text().split("analysis:", 1)[1]
    lo, hi = (
        text.split("leak_gpm_approx:", 1)[1].split("]", 1)[0].strip().lstrip("[").split(",")
    )
    location = text.split("leak_location:", 1)[1].split()[0]
    return {
        "leak_detected": "leak_detected: true" in text,
        "leak_location": location,
        "leak_gpm_approx": [float(lo), float(hi)],
    }


def _metered_after(db: Path, dev: str, start_ms: int, end_ms: int) -> int:
    """Gallons that left after `start_ms`: last total before the end, minus last total before the leak."""
    conn = sqlite3.connect(db)
    before = conn.execute(
        "SELECT gal_total FROM readings WHERE dev = ? AND ts < ? ORDER BY ts DESC, seq DESC LIMIT 1",
        (dev, start_ms),
    ).fetchone()
    after = conn.execute(
        "SELECT gal_total FROM readings WHERE dev = ? AND ts < ? ORDER BY ts DESC, seq DESC LIMIT 1",
        (dev, end_ms),
    ).fetchone()
    conn.close()
    assert before is not None and after is not None
    return int(after[0]) - int(before[0])


def test_overnight_leak_unscheduled_flow_matches_analysis(tmp_path: Path):
    subprocess.run(
        [str(TWIN), "run", str(SCENARIO), "--truth-log-dir", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    truth_log = next(
        path for path in tmp_path.glob("overnight_leak-*.jsonl") if path.suffixes == [".jsonl"]
    )
    messages = next(tmp_path.glob("overnight_leak-*.messages.jsonl"))
    db = tmp_path / "well-sim.db"
    subprocess.run([str(INGEST), "load", str(messages), "--db", str(db)], check=True)
    subprocess.run([str(INGEST), "load-zones", str(truth_log), "--db", str(db)], check=True)

    injected = [json.loads(line) for line in truth_log.read_text().splitlines()]
    leak = next(row for row in injected if row["inject"] == "leak")
    zone = next(row for row in injected if row["inject"] == "zone_on")
    leak_ms = int(leak["ts"])
    zone_start = int(zone["ts"])
    zone_end = zone_start + int(round(float(zone["minutes"]) * 60_000))
    analysis = _expect_analysis(SCENARIO)
    end_ms = parse_ms("2026-10-09T07:00:00-05:00")

    answer = get_unscheduled_pump_runs(
        "2026-10-08T21:00:00-05:00",
        "2026-10-09T07:00:00-05:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )

    assert analysis["leak_detected"] is True
    assert analysis["leak_location"] == leak["location"] == "downstream"
    after = [
        span for span in answer["flow"] if parse_ms(span["start"]) >= leak_ms
    ]
    assert len(after) == 1
    span = after[0]
    metered = _metered_after(db, "twin1", leak_ms, end_ms)
    assert metered > 0
    assert abs(span["gallons"] - metered) <= 2
    lo, hi = analysis["leak_gpm_approx"]
    assert lo <= span["gpm"] <= hi

    assert answer["cycles"]
    for cycle in answer["cycles"]:
        start = parse_ms(cycle["start"])
        end = end_ms if cycle["end"] is None else parse_ms(cycle["end"])
        overlaps_zone = start < zone_end and end > zone_start
        assert not overlaps_zone
        assert start >= leak_ms
