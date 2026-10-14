"""Write scenario zone runs into the sim database. Source is twin, not Hydrawise."""

from __future__ import annotations

import json
from pathlib import Path

from bfwp_ingest.db import connect


def load_zone_runs(truth_log: Path, db_path: Path) -> int:
    """Insert `zone_on` lines from a truth log. A second load does not add rows."""
    conn = connect(db_path)
    inserted = 0
    try:
        for raw in truth_log.read_text().splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            if row.get("inject") != "zone_on":
                continue
            start = int(row["ts"])
            end = start + int(round(float(row["minutes"]) * 60_000))
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO zone_runs (
                  controller_id, zone_id, zone_name, start_ts, end_ts, source
                ) VALUES ('twin', ?, NULL, ?, ?, 'twin')
                """,
                (str(int(row["zone"])), start, end),
            )
            inserted += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return inserted
