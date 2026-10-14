"""Every zone's latest run against its own median.

The scenario test never hands the truth log to the tool.
"""

import sqlite3
import subprocess
from pathlib import Path

from bfwp_mcp.compare import compare_zone_signatures
from bfwp_mcp.clock import parse_ms
from bfwp_mcp.signature import STEADY_SKIP_MS, get_zone_signature

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "bfwp-spec" / "contracts" / "sqlite" / "schema-v1.sql"
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "baseline_normal_night.yaml"
TWIN = REPO / "bfwp-twin" / ".venv" / "bin" / "bfwp-twin"
INGEST = REPO / "bfwp-ingest" / ".venv" / "bin" / "bfwp-ingest"


def test_baseline_night_zones_match_their_only_run(tmp_path: Path):
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

    answer = compare_zone_signatures(
        "2026-10-08T21:00:00",
        "2026-10-09T07:00:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )
    signature = get_zone_signature(
        "3",
        "2026-10-08T21:00:00",
        "2026-10-09T07:00:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )

    assert [zone["zone"] for zone in answer["zones"]] == ["1", "2", "3"]
    for zone in answer["zones"]:
        assert zone["baseline"]["runs"] == 1
        assert zone["psi_delta"] == 0
        assert zone["amps_delta"] == 0
        assert zone["gpm_delta"] == 0
        assert zone["gallons_delta"] == 0
        assert zone["current"]["gallons"] > 0
    zone_three = answer["zones"][2]
    run = signature["runs"][0]
    assert zone_three["current"]["psi"] == run["psi"]
    assert zone_three["current"]["amps"] == run["amps"]
    assert zone_three["current"]["gpm"] == run["gpm"]
    assert zone_three["current"]["gallons"] == run["gallons"]
    assert zone_three["baseline"]["psi"] == signature["baseline"]["psi"]


def test_latest_run_is_compared_with_the_median(tmp_path: Path):
    db = tmp_path / "well-sim.db"
    conn = sqlite3.connect(db)
    script = "\n".join(
        line for line in SCHEMA.read_text().splitlines() if not line.strip().startswith("PRAGMA")
    )
    conn.executescript(script)
    _zone(conn, "1", parse_ms("2026-10-08T22:00:00"), already=0, gallons=10, psi=50.0, amps=8.0, gpm=12.0)
    _zone(conn, "2", parse_ms("2026-10-08T23:00:00"), already=10, gallons=5, psi=60.0, amps=7.0, gpm=10.0)
    _zone(conn, "1", parse_ms("2026-10-09T22:00:00"), already=15, gallons=30, psi=40.0, amps=8.0, gpm=18.0)
    _zone(conn, "10", parse_ms("2026-10-10T22:00:00"), already=45, gallons=8, psi=55.0, amps=7.0, gpm=9.0)
    conn.commit()
    conn.close()

    answer = compare_zone_signatures(
        "2026-10-08T00:00:00",
        "2026-10-11T00:00:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )
    by_zone = {zone["zone"]: zone for zone in answer["zones"]}
    assert list(by_zone) == ["1", "2", "10"]

    changed = by_zone["1"]
    assert changed["baseline"]["runs"] == 2
    assert changed["current"]["psi"] == 40
    assert changed["current"]["gpm"] == 18
    assert changed["current"]["gallons"] == 30
    assert changed["baseline"]["psi"] == 45
    assert changed["baseline"]["gpm"] == 15
    assert changed["baseline"]["gallons"] == 20
    assert changed["psi_delta"] == -5
    assert changed["gpm_delta"] == 3
    assert changed["gallons_delta"] == 10

    assert by_zone["2"]["psi_delta"] == 0
    assert by_zone["2"]["gpm_delta"] == 0
    assert by_zone["2"]["gallons_delta"] == 0
    assert by_zone["2"]["current"]["gallons"] == 5
    assert by_zone["10"]["psi_delta"] == 0
    assert by_zone["10"]["current"]["gallons"] == 8


def _zone(conn, zone_id: str, start_ms: int, already: int, gallons: int, psi: float, amps: float, gpm: float) -> None:
    end_ms = start_ms + 60_000
    conn.execute(
        """
        INSERT INTO zone_runs (controller_id, zone_id, zone_name, start_ts, end_ts, source)
        VALUES ('twin', ?, NULL, ?, ?, 'twin')
        """,
        (zone_id, start_ms, end_ms),
    )
    for offset, total in ((0, already), (STEADY_SKIP_MS, already + gallons)):
        conn.execute(
            """
            INSERT INTO readings (
              dev, seq, ts, mode, psi, amps, pump, gal_total, gpm, received_ts
            ) VALUES ('twin1', ?, ?, 'active', ?, ?, 1, ?, ?, ?)
            """,
            (start_ms + offset, start_ms + offset, psi, amps, total, gpm, start_ms + offset),
        )
