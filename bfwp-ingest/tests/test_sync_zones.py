"""Zone sync returns counts and does not write or call Hydrawise."""

import socket
from pathlib import Path

from bfwp_ingest.cli import main
from bfwp_ingest.db import connect
from bfwp_ingest.hydrawise import sync_zone_runs


def test_sync_does_not_create_or_call_out(tmp_path: Path, monkeypatch, capsys):
    def opened(*_args, **_kwargs):
        raise AssertionError("sync opened a socket")

    monkeypatch.setattr(socket, "socket", opened)
    monkeypatch.setenv("HYDRAWISE_API_KEY", "")
    missing = tmp_path / "well.db"
    assert sync_zone_runs(missing, 1, 2, source="real", api_key="") == {
        "fetched": 0,
        "inserted": 0,
        "unchanged": 0,
        "hydrawise": "not_configured",
    }
    assert sync_zone_runs(missing, 1, 2, source="real", api_key="secret")["hydrawise"] == "deferred"
    assert sync_zone_runs(missing, 1, 2, source="sim", api_key="secret")["hydrawise"] == "sim_uses_twin"
    assert not missing.exists()

    assert main(["sync-zones", "--start-ms", "10", "--end-ms", "20", "--db", str(missing), "--source", "real"]) == 0
    text = capsys.readouterr().out
    assert "fetched 0" in text
    assert "inserted 0" in text
    assert "unchanged 0" in text
    assert "hydrawise not_configured" in text
    assert not missing.exists()


def test_sync_leaves_an_existing_zone_run(tmp_path: Path):
    db = tmp_path / "well.db"
    conn = connect(db)
    conn.execute(
        """
        INSERT INTO zone_runs (controller_id, zone_id, zone_name, start_ts, end_ts, source)
        VALUES ('twin', '3', NULL, 1000, 2000, 'twin')
        """
    )
    conn.commit()
    conn.close()
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}

    result = sync_zone_runs(db, 1000, 3000, source="real", api_key="")

    after = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    assert result["hydrawise"] == "not_configured"
    assert after == before
