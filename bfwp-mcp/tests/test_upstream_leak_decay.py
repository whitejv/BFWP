"""Upstream leak: overnight pressure falls and the meter stays at zero.

The tool never sees the truth log or the scenario file.
"""

import json
import sqlite3
import subprocess
from pathlib import Path

from bfwp_mcp.clock import parse_ms
from bfwp_mcp.decay import get_overnight_decay

REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "upstream_leak_decay.yaml"
TWIN = REPO / "bfwp-twin" / ".venv" / "bin" / "bfwp-twin"
INGEST = REPO / "bfwp-ingest" / ".venv" / "bin" / "bfwp-ingest"


def _expect_analysis(path: Path) -> dict:
    text = path.read_text().split("analysis:", 1)[1]
    location = text.split("leak_location:", 1)[1].split()[0]
    return {
        "leak_detected": "leak_detected: true" in text,
        "leak_location": location,
    }


def test_upstream_leak_decays_with_zero_gallons(tmp_path: Path):
    subprocess.run(
        [str(TWIN), "run", str(SCENARIO), "--truth-log-dir", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    truth_log = next(
        path for path in tmp_path.glob("upstream_leak_decay-*.jsonl") if path.suffixes == [".jsonl"]
    )
    messages = next(tmp_path.glob("upstream_leak_decay-*.messages.jsonl"))
    db = tmp_path / "well-sim.db"
    subprocess.run([str(INGEST), "load", str(messages), "--db", str(db)], check=True)

    injected = [json.loads(line) for line in truth_log.read_text().splitlines()]
    leak = next(row for row in injected if row["inject"] == "leak")
    analysis = _expect_analysis(SCENARIO)

    answer = get_overnight_decay("2026-10-09", dev="twin1", source="sim", db_path=db)
    night = answer["nights"][0]

    start_ms = parse_ms("2026-10-09T00:00:00")
    end_ms = parse_ms("2026-10-09T05:00:00")
    assert parse_ms(night["start"]) == start_ms
    assert parse_ms(night["end"]) == end_ms

    conn = sqlite3.connect(db)
    totals = [row[0] for row in conn.execute("SELECT gal_total FROM readings WHERE dev = 'twin1'")]
    psis = [
        row[0]
        for row in conn.execute(
            """
            SELECT psi FROM readings
            WHERE dev = 'twin1' AND psi IS NOT NULL AND ts >= ? AND ts < ?
            ORDER BY ts, seq
            """,
            (start_ms, end_ms),
        )
    ]
    conn.close()

    assert analysis["leak_detected"] is True
    assert analysis["leak_location"] == leak["location"] == "upstream"
    assert set(totals) == {0}
    assert night["gallons"] == 0
    assert psis
    assert night["psi_start"] == psis[0]
    assert night["psi_end"] == psis[-1]
    assert night["psi_min"] == min(psis)
    assert night["psi_max"] == max(psis)
    assert night["psi_max"] - night["psi_min"] >= 5
    assert all(cycle["gallons"] == 0 for cycle in night["cycles"])
