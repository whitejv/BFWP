"""Live ingest of baseline_normal_night matches a file load. No writes to well.db.

Skipped unless BFWP_MQTT=1.
"""

import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bfwp-twin" / "src"))

from bfwp_twin.simulate import run_offline  # noqa: E402

from bfwp_ingest.live import LiveIngest  # noqa: E402
from bfwp_ingest.load import load_records  # noqa: E402
from bfwp_ingest.store import Store  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.environ.get("BFWP_MQTT") != "1",
    reason="set BFWP_MQTT=1 to ingest baseline_normal_night from HiveMQ",
)

SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "baseline_normal_night.yaml"
TWIN_PY = REPO / "bfwp-twin" / ".venv" / "bin" / "python"
TWIN_BIN = REPO / "bfwp-twin" / ".venv" / "bin" / "bfwp-twin"
RECEIVED_TS = 1_800_000_000_000


def _clear_retained() -> None:
    subprocess.run(
        [
            str(TWIN_PY),
            "-c",
            "from bfwp_twin.mqtt import clear_retained_status, load_mqtt_config; "
            "clear_retained_status(load_mqtt_config(), 'twin1')",
        ],
        check=True,
    )


def _column(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    return [tuple(row) for row in conn.execute(sql)]


def test_live_baseline_matches_file_and_leaves_well_db_unused(tmp_path):
    records = list(run_offline(SCENARIO, truth_log_dir=tmp_path).records)
    file_db = tmp_path / "from-file.db"
    live_db = tmp_path / "from-mqtt.db"
    well_db = tmp_path / "well.db"

    file_store = Store(file_db)
    load_records(file_store, records, RECEIVED_TS)
    file_store.finish()
    expected = file_store.conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    assert expected > 0

    _clear_retained()
    live = LiveIngest(live_db, client_id=f"bfwp-ingest-{uuid.uuid4().hex[:8]}")
    live.start()
    try:
        subprocess.run(
            [str(TWIN_BIN), "run", str(SCENARIO), "--mqtt", "--truth-log-dir", str(tmp_path / "live-run")],
            check=True,
        )
        got = live.wait_for_readings(expected, timeout_s=60)
    finally:
        live.stop()
        _clear_retained()

    assert got == expected
    assert not well_db.exists()

    file_conn = sqlite3.connect(file_db)
    live_conn = sqlite3.connect(live_db)
    try:
        reading_sql = """
            SELECT dev, seq, ts, mode, psi, amps, pump, gal_total, gpm
            FROM readings ORDER BY seq
        """
        assert _column(live_conn, reading_sql) == _column(file_conn, reading_sql)
        assert _column(
            live_conn,
            "SELECT dev, seq, ts, type, data FROM events ORDER BY seq",
        ) == _column(file_conn, "SELECT dev, seq, ts, type, data FROM events ORDER BY seq")
        assert _column(
            live_conn,
            "SELECT dev, minute_ts, n, gallons, pump_secs FROM readings_1min ORDER BY minute_ts",
        ) == _column(
            file_conn,
            "SELECT dev, minute_ts, n, gallons, pump_secs FROM readings_1min ORDER BY minute_ts",
        )
        assert _column(
            live_conn, "SELECT COUNT(*) FROM rejects"
        ) == [(0,)]
    finally:
        file_conn.close()
        live_conn.close()
        file_store.close()
