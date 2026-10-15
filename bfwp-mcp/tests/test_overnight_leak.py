"""Overnight leak: the meter advances after the injection. The server does not label it.

The tool never sees the truth log or the scenario file.
"""

import json
import sqlite3
import subprocess
from pathlib import Path

from bfwp_mcp.clock import parse_ms
from bfwp_mcp.decay import get_overnight_decay

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


def _metered(db: Path, start_ms: int, end_ms: int) -> int:
    conn = sqlite3.connect(db)
    before = conn.execute(
        "SELECT gal_total FROM readings WHERE dev = 'twin1' AND ts < ? ORDER BY ts DESC, seq DESC LIMIT 1",
        (start_ms,),
    ).fetchone()
    after = conn.execute(
        "SELECT gal_total FROM readings WHERE dev = 'twin1' AND ts < ? ORDER BY ts DESC, seq DESC LIMIT 1",
        (end_ms,),
    ).fetchone()
    conn.close()
    assert before is not None and after is not None
    return int(after[0]) - int(before[0])


def test_overnight_leak_moves_the_meter(tmp_path: Path):
    subprocess.run(
        [str(TWIN), "run", str(SCENARIO), "--truth-log-dir", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    truth_log = next(path for path in tmp_path.glob("overnight_leak-*.jsonl") if path.suffixes == [".jsonl"])
    messages = next(tmp_path.glob("overnight_leak-*.messages.jsonl"))
    db = tmp_path / "well-sim.db"
    subprocess.run([str(INGEST), "load", str(messages), "--db", str(db)], check=True)

    injected = [json.loads(line) for line in truth_log.read_text().splitlines()]
    leak = next(row for row in injected if row["inject"] == "leak")
    analysis = _expect_analysis(SCENARIO)
    start_ms = parse_ms("2026-10-09T00:00:00")
    end_ms = parse_ms("2026-10-09T05:00:00")

    answer = get_overnight_decay("2026-10-09", dev="twin1", source="sim", db_path=db)
    night = answer["nights"][0]
    minutes = (end_ms - start_ms) / 60_000

    assert analysis["leak_detected"] is True
    assert analysis["leak_location"] == leak["location"] == "downstream"
    assert int(leak["ts"]) < start_ms
    assert night["gallons"] == _metered(db, start_ms, end_ms)
    assert night["gallons"] > 0
    lo, hi = analysis["leak_gpm_approx"]
    assert lo <= night["gallons"] / minutes <= hi
