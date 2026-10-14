"""Open the sim database and apply the spec v1 schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO / "bfwp-spec" / "contracts" / "sqlite" / "schema-v1.sql"
SCHEMAS = REPO / "bfwp-spec" / "contracts" / "schemas" / "v1"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    script = "\n".join(
        line for line in SCHEMA_PATH.read_text().splitlines() if not line.strip().startswith("PRAGMA")
    )
    conn.executescript(script)
    return conn
