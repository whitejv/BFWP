"""Hydrawise zone-run sync. The HTTP call is a later check."""

from __future__ import annotations

from pathlib import Path


def sync_zone_runs(
    db_path: Path,
    start_ms: int,
    end_ms: int,
    source: str = "real",
    api_key: str = "",
) -> dict:
    """Count zone runs Hydrawise would add for [start_ms, end_ms).

    The database path is the file a later sync will write. This check does not
    open it and does not call the controller.
    """
    if source not in ("real", "sim"):
        raise ValueError(f"source must be real or sim, not {source}")
    if end_ms <= start_ms:
        raise ValueError("end must be after start")
    del db_path
    if source == "sim":
        status = "sim_uses_twin"
    elif not api_key.strip():
        status = "not_configured"
    else:
        status = "deferred"
    return {"fetched": 0, "inserted": 0, "unchanged": 0, "hydrawise": status}
