"""Raw readings for a short fault hour, and the one-minute rollup for a long night.

The tool never sees the truth log.
"""

import json
import sqlite3
import subprocess
from pathlib import Path

from bfwp_mcp.clock import parse_ms
from bfwp_mcp.readings import get_readings

REPO = Path(__file__).resolve().parents[2]
FAULT = REPO / "bfwp-spec" / "contracts" / "scenarios" / "sensor_fault_and_reboot.yaml"
NIGHT = REPO / "bfwp-spec" / "contracts" / "scenarios" / "baseline_normal_night.yaml"
TWIN = REPO / "bfwp-twin" / ".venv" / "bin" / "bfwp-twin"
INGEST = REPO / "bfwp-ingest" / ".venv" / "bin" / "bfwp-ingest"


def _load(tmp_path: Path, scenario: Path, stem: str) -> tuple[Path, Path]:
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
    return db, truth_log


def test_short_range_is_raw_and_null_psi_matches_the_fault(tmp_path: Path):
    db, truth_log = _load(tmp_path, FAULT, "sensor_fault_and_reboot")
    fault = next(
        row
        for row in (json.loads(line) for line in truth_log.read_text().splitlines())
        if row["inject"] == "fault"
    )
    answer = get_readings(
        "2026-10-09T03:00:00",
        "2026-10-09T04:00:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )

    conn = sqlite3.connect(db)
    stored = conn.execute(
        """
        SELECT ts, psi, amps, gpm, pump FROM readings
        WHERE dev = 'twin1' ORDER BY ts, seq
        """
    ).fetchall()
    conn.close()

    assert answer["resolution"] == "raw"
    assert len(answer["points"]) == len(stored) > 0
    nulls = []
    for point, row in zip(answer["points"], stored, strict=True):
        assert parse_ms(point["time"]) == row[0]
        assert point["psi"] == row[1]
        assert point["amps"] == row[2]
        assert point["gpm"] == row[3]
        assert point["pump"] == row[4]
        if point["psi"] is None:
            nulls.append(parse_ms(point["time"]))
    fault_at = int(fault["ts"])
    fault_end = fault_at + int(round(float(fault["minutes"]) * 60_000))
    assert nulls
    assert all(fault_at <= ts < fault_end + 1_000 for ts in nulls)
    assert all(row[1] is not None for row in stored if row[0] < fault_at or row[0] >= fault_end + 1_000)


def test_long_night_uses_one_minute_rollup(tmp_path: Path):
    db, _truth = _load(tmp_path, NIGHT, "baseline_normal_night")
    answer = get_readings(
        "2026-10-08T21:00:00",
        "2026-10-09T07:00:00",
        fields=["psi", "gpm", "pump"],
        dev="twin1",
        source="sim",
        db_path=db,
    )

    conn = sqlite3.connect(db)
    minutes = conn.execute(
        """
        SELECT minute_ts, psi_avg, psi_min, psi_max, gallons, pump_secs
        FROM readings_1min WHERE dev = 'twin1' ORDER BY minute_ts
        """
    ).fetchall()
    raw_count = conn.execute("SELECT COUNT(*) FROM readings WHERE dev = 'twin1'").fetchone()[0]
    conn.close()

    assert answer["resolution"] == "1min"
    assert len(answer["points"]) == len(minutes) > 0
    assert len(answer["points"]) < raw_count
    for point, row in zip(answer["points"], minutes, strict=True):
        assert parse_ms(point["time"]) == row[0]
        assert point["psi"] == row[1]
        assert point["psi_min"] == row[2]
        assert point["psi_max"] == row[3]
        assert point["gpm"] == row[4]
        assert point["pump"] == row[5]
        assert "amps" not in point
