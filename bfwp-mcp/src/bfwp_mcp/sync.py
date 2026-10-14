"""Ask ingest to sync Hydrawise zone runs. This server does not write."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from bfwp_mcp.clock import LOCAL_TZ, format_utc, parse_ms
from bfwp_mcp.db import database_path

_COUNTS = ("fetched", "inserted", "unchanged")


def sync_zone_runs(
    start: str,
    end: str,
    source: str = "real",
    db_path: Path | None = None,
    tz_name: str = LOCAL_TZ,
    ingest_cmd: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Run `bfwp-ingest sync-zones` for [start, end) and return its counts.

    api_key is omitted to inherit the environment. Tests pass "" so the child
    sees no Hydrawise key.
    """
    if source not in ("real", "sim"):
        raise ValueError(f"source must be real or sim, not {source}")
    start_ms = parse_ms(start, tz_name)
    end_ms = parse_ms(end, tz_name)
    if end_ms <= start_ms:
        raise ValueError("end must be after start")

    path = db_path or database_path(source)
    env = os.environ.copy()
    if api_key is not None:
        env["HYDRAWISE_API_KEY"] = api_key
    completed = subprocess.run(
        [
            _ingest_command(ingest_cmd),
            "sync-zones",
            "--start-ms",
            str(start_ms),
            "--end-ms",
            str(end_ms),
            "--source",
            source,
            "--db",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    counts = _parse_counts(completed.stdout)
    return {
        "start_utc": format_utc(start_ms),
        "end_utc": format_utc(end_ms),
        "tz": tz_name,
        "source": source,
        **counts,
    }


def _ingest_command(given: str | None) -> str:
    if given:
        return given
    override = os.environ.get("BFWP_INGEST")
    if override:
        return override
    found = shutil.which("bfwp-ingest")
    if found:
        return found
    sibling = Path(__file__).resolve().parents[3] / "bfwp-ingest" / ".venv" / "bin" / "bfwp-ingest"
    if sibling.is_file():
        return str(sibling)
    raise FileNotFoundError("bfwp-ingest")


def _parse_counts(text: str) -> dict:
    values = {}
    for line in text.splitlines():
        key, value = line.split(maxsplit=1)
        values[key] = value
    return {
        **{name: int(values[name]) for name in _COUNTS},
        "hydrawise": values["hydrawise"],
    }
