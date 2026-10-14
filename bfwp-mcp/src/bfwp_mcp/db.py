"""Open a well database read-only."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def database_path(source: str) -> Path:
    if source == "sim":
        return Path(os.environ.get("SIM_DB_PATH", "~/BFWP-data/well-sim.db")).expanduser()
    if source == "real":
        return Path(os.environ.get("DB_PATH", "~/BFWP-data/well.db")).expanduser()
    raise ValueError(f"source must be real or sim, not {source}")


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn
