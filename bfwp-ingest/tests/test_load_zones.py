"""Zone runs from a truth log land in the sim database once."""

import json
from pathlib import Path

from bfwp_ingest.db import connect
from bfwp_ingest.zones import load_zone_runs


def test_load_zone_runs_once(tmp_path: Path):
    log = tmp_path / "truth.jsonl"
    log.write_text(
        "\n".join(
            [
                json.dumps({"ts": 1_791_514_800_000, "inject": "zone_on", "zone": 1, "minutes": 15, "gpm": 14}),
                json.dumps({"ts": 1_791_515_700_000, "inject": "leak", "gpm": 0.4, "location": "downstream"}),
            ]
        )
        + "\n"
    )
    db = tmp_path / "well-sim.db"
    assert load_zone_runs(log, db) == 1
    assert load_zone_runs(log, db) == 0
    conn = connect(db)
    row = conn.execute(
        "SELECT zone_id, start_ts, end_ts, source FROM zone_runs"
    ).fetchone()
    conn.close()
    assert row["zone_id"] == "1"
    assert row["start_ts"] == 1_791_514_800_000
    assert row["end_ts"] == 1_791_514_800_000 + 15 * 60_000
    assert row["source"] == "twin"
