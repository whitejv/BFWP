"""Zone 3's steady draw matches the truth-log run, and a second run shows a delta.

The scenario test never hands the truth log to the tool.
"""

import json
import sqlite3
import subprocess
from pathlib import Path

from bfwp_mcp.clock import parse_ms
from bfwp_mcp.signature import STEADY_SKIP_MS, get_zone_signature

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "bfwp-spec" / "contracts" / "sqlite" / "schema-v1.sql"
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "baseline_normal_night.yaml"
TWIN = REPO / "bfwp-twin" / ".venv" / "bin" / "bfwp-twin"
INGEST = REPO / "bfwp-ingest" / ".venv" / "bin" / "bfwp-ingest"


def test_zone_three_signature_matches_its_run(tmp_path: Path):
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

    zone = next(
        row
        for row in (json.loads(line) for line in truth_log.read_text().splitlines())
        if row["inject"] == "zone_on" and row["zone"] == 3
    )
    start_ms = int(zone["ts"])
    end_ms = start_ms + int(round(float(zone["minutes"]) * 60_000))
    answer = get_zone_signature(
        "3",
        "2026-10-08T21:00:00",
        "2026-10-09T07:00:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )

    conn = sqlite3.connect(db)
    steady = conn.execute(
        """
        SELECT psi, amps, gpm FROM readings
        WHERE dev = 'twin1' AND ts >= ? AND ts < ?
        ORDER BY ts, seq
        """,
        (start_ms + STEADY_SKIP_MS, end_ms),
    ).fetchall()
    before = conn.execute(
        "SELECT gal_total FROM readings WHERE dev = 'twin1' AND ts < ? ORDER BY ts DESC LIMIT 1",
        (start_ms,),
    ).fetchone()
    after = conn.execute(
        "SELECT gal_total FROM readings WHERE dev = 'twin1' AND ts < ? ORDER BY ts DESC LIMIT 1",
        (end_ms,),
    ).fetchone()
    conn.close()

    assert len(answer["runs"]) == 1
    run = answer["runs"][0]
    assert parse_ms(run["start"]) == start_ms
    assert parse_ms(run["end"]) == end_ms
    assert run["psi"] == _mean(row[0] for row in steady)
    assert run["amps"] == _mean(row[1] for row in steady)
    assert run["gpm"] == _mean(row[2] for row in steady)
    assert run["gallons"] == int(after[0]) - int(before[0])
    assert run["gallons"] > 0
    assert answer["baseline"]["runs"] == 1
    assert run["psi_delta"] == 0
    assert run["amps_delta"] == 0
    assert run["gpm_delta"] == 0
    assert run["gallons_delta"] == 0


def test_second_run_deviates_from_the_median(tmp_path: Path):
    db = tmp_path / "well-sim.db"
    conn = sqlite3.connect(db)
    script = "\n".join(
        line for line in SCHEMA.read_text().splitlines() if not line.strip().startswith("PRAGMA")
    )
    conn.executescript(script)
    first = parse_ms("2026-10-08T22:00:00")
    second = parse_ms("2026-10-09T22:00:00")
    _zone(conn, first, already=0, gallons=10, psi=50.0, amps=8.0, gpm=12.0)
    _zone(conn, second, already=10, gallons=30, psi=40.0, amps=8.0, gpm=18.0)
    conn.commit()
    conn.close()

    answer = get_zone_signature(
        "1",
        "2026-10-08T00:00:00",
        "2026-10-10T00:00:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )
    assert answer["baseline"]["psi"] == 45
    assert answer["baseline"]["gpm"] == 15
    assert answer["baseline"]["gallons"] == 20
    assert [run["psi_delta"] for run in answer["runs"]] == [5, -5]
    assert [run["gpm_delta"] for run in answer["runs"]] == [-3, 3]
    assert [run["gallons_delta"] for run in answer["runs"]] == [-10, 10]


def _zone(conn, start_ms: int, already: int, gallons: int, psi: float, amps: float, gpm: float) -> None:
    end_ms = start_ms + 60_000
    conn.execute(
        """
        INSERT INTO zone_runs (controller_id, zone_id, zone_name, start_ts, end_ts, source)
        VALUES ('twin', '1', NULL, ?, ?, 'twin')
        """,
        (start_ms, end_ms),
    )
    # One reading before the steady window, then one inside it.
    for offset, total in ((0, already), (STEADY_SKIP_MS, already + gallons)):
        conn.execute(
            """
            INSERT INTO readings (
              dev, seq, ts, mode, psi, amps, pump, gal_total, gpm, received_ts
            ) VALUES ('twin1', ?, ?, 'active', ?, ?, 1, ?, ?, ?)
            """,
            (start_ms + offset, start_ms + offset, psi, amps, total, gpm, start_ms + offset),
        )


def _mean(values) -> float:
    numbers = [value for value in values if value is not None]
    return sum(numbers) / len(numbers)
