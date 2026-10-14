"""sync_zone_runs asks ingest and leaves the database bytes alone."""

import sqlite3
from pathlib import Path

from bfwp_mcp.clock import format_utc, parse_ms
from bfwp_mcp.sync import sync_zone_runs

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "bfwp-spec" / "contracts" / "sqlite" / "schema-v1.sql"
INGEST = REPO / "bfwp-ingest" / ".venv" / "bin" / "bfwp-ingest"


def test_real_sync_returns_zero_counts_without_writing(tmp_path: Path):
    db = tmp_path / "well.db"
    _zone(db)
    before = _files(tmp_path)
    start = "2026-10-08T21:00:00"
    end = "2026-10-09T07:00:00"

    answer = sync_zone_runs(
        start,
        end,
        source="real",
        db_path=db,
        ingest_cmd=str(INGEST),
        api_key="",
    )

    assert answer["start_utc"] == format_utc(parse_ms(start))
    assert answer["end_utc"] == format_utc(parse_ms(end))
    assert answer["tz"] == "America/Chicago"
    assert answer["source"] == "real"
    assert answer["fetched"] == 0
    assert answer["inserted"] == 0
    assert answer["unchanged"] == 0
    assert answer["hydrawise"] == "not_configured"
    assert _files(tmp_path) == before


def test_sim_sync_does_not_create_a_database(tmp_path: Path):
    db = tmp_path / "well-sim.db"
    answer = sync_zone_runs(
        "2026-10-08T21:00:00",
        "2026-10-09T07:00:00",
        source="sim",
        db_path=db,
        ingest_cmd=str(INGEST),
        api_key="secret",
    )
    assert answer["hydrawise"] == "sim_uses_twin"
    assert answer["inserted"] == 0
    assert not db.exists()


def _zone(db: Path) -> None:
    conn = sqlite3.connect(db)
    script = "\n".join(
        line for line in SCHEMA.read_text().splitlines() if not line.strip().startswith("PRAGMA")
    )
    conn.executescript(script)
    conn.execute(
        """
        INSERT INTO zone_runs (controller_id, zone_id, zone_name, start_ts, end_ts, source)
        VALUES ('twin', '3', NULL, 1000, 2000, 'twin')
        """
    )
    conn.commit()
    conn.close()


def _files(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}
