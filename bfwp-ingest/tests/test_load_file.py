"""File ingest of overnight_leak into a sim database. No MQTT."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bfwp-twin" / "src"))

from bfwp_twin.simulate import run_offline  # noqa: E402

from bfwp_ingest.load import load_records  # noqa: E402
from bfwp_ingest.store import Store, count_rows, minute_ts  # noqa: E402

SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "overnight_leak.yaml"
RECEIVED_TS = 1_800_000_000_000


def _capture(tmp_path: Path) -> list[dict]:
    result = run_offline(SCENARIO, truth_log_dir=tmp_path)
    return list(result.records)


def _counts(store: Store) -> dict[str, int]:
    return {
        table: count_rows(store.conn, table)
        for table in ("readings", "events", "health", "status_log", "readings_1min", "rejects")
    }


def test_replay_keeps_device_timestamps_and_does_not_duplicate(tmp_path):
    records = _capture(tmp_path)
    db = tmp_path / "well-sim.db"
    store = Store(db)
    load_records(store, records, RECEIVED_TS)
    store.finish()
    first = _counts(store)

    assert first["readings"] > 0
    assert first["rejects"] == 0
    assert count_rows(store.conn, "pump_cycles") > 0
    row = store.conn.execute(
        "SELECT ts, received_ts FROM readings ORDER BY ts LIMIT 1"
    ).fetchone()
    assert row["ts"] >= 1_735_689_600_000
    assert row["ts"] != row["received_ts"]
    assert row["received_ts"] == RECEIVED_TS

    before = store.inserted
    load_records(store, records, RECEIVED_TS)
    store.finish()
    assert _counts(store) == first
    assert store.ignored >= before
    store.close()


def test_invalid_message_is_rejected(tmp_path):
    db = tmp_path / "well-sim.db"
    store = Store(db)
    store.ingest(
        "bfwp-sim/twin1/telemetry",
        {"v": 1, "dev": "twin1", "seq": 1, "ts": RECEIVED_TS, "mode": "idle", "psi": 50},
        RECEIVED_TS,
    )
    store.finish()
    assert count_rows(store.conn, "readings") == 0
    assert count_rows(store.conn, "rejects") == 1
    error = store.conn.execute("SELECT error FROM rejects").fetchone()["error"]
    assert "required property" in error
    store.close()


def test_late_batch_recomputes_outage_minute(tmp_path):
    records = _capture(tmp_path)
    prefix = [record for record in records if "batch" not in record["payload"]]
    batches = [record for record in records if "batch" in record["payload"]]
    assert batches

    sample = batches[0]["payload"]["batch"][0]
    minute = minute_ts(sample["ts"])
    dev = batches[0]["payload"]["dev"]

    db = tmp_path / "well-sim.db"
    store = Store(db)
    load_records(store, prefix, RECEIVED_TS)
    store.finish()
    early = store.conn.execute(
        "SELECT COUNT(*) FROM readings WHERE dev = ? AND ts >= ? AND ts < ?",
        (dev, minute, minute + 60_000),
    ).fetchone()[0]
    rollup = store.conn.execute(
        "SELECT n FROM readings_1min WHERE dev = ? AND minute_ts = ?",
        (dev, minute),
    ).fetchone()
    assert early == 0
    assert rollup is None

    recomputes_before = store.recomputes
    load_records(store, batches, RECEIVED_TS)
    store.finish()
    after = store.conn.execute(
        "SELECT n, gallons FROM readings_1min WHERE dev = ? AND minute_ts = ?",
        (dev, minute),
    ).fetchone()
    readings = store.conn.execute(
        "SELECT gal_total FROM readings WHERE dev = ? AND ts >= ? AND ts < ? ORDER BY ts, seq",
        (dev, minute, minute + 60_000),
    ).fetchall()
    assert store.recomputes > recomputes_before
    assert after["n"] == len(readings)
    assert after["n"] > 0
    assert after["gallons"] == readings[-1]["gal_total"] - readings[0]["gal_total"]
    store.close()
