"""Health reports show the reboot in the truth log, and a long series is thinned."""

import json
import sqlite3
import subprocess
from pathlib import Path

from bfwp_mcp.clock import parse_ms
from bfwp_mcp.health import MAX_REPORTS, get_device_health

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "bfwp-spec" / "contracts" / "sqlite" / "schema-v1.sql"
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "sensor_fault_and_reboot.yaml"
TWIN = REPO / "bfwp-twin" / ".venv" / "bin" / "bfwp-twin"
INGEST = REPO / "bfwp-ingest" / ".venv" / "bin" / "bfwp-ingest"


def test_reboot_appears_in_health(tmp_path: Path):
    subprocess.run(
        [str(TWIN), "run", str(SCENARIO), "--truth-log-dir", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    truth_log = next(
        path
        for path in tmp_path.glob("sensor_fault_and_reboot-*.jsonl")
        if path.suffixes == [".jsonl"]
    )
    messages = next(tmp_path.glob("sensor_fault_and_reboot-*.messages.jsonl"))
    db = tmp_path / "well-sim.db"
    subprocess.run([str(INGEST), "load", str(messages), "--db", str(db)], check=True)

    reboot_ms = int(
        next(row["ts"] for row in (json.loads(line) for line in truth_log.read_text().splitlines()) if row["inject"] == "reboot")
    )
    answer = get_device_health(
        "2026-10-09T03:00:00",
        "2026-10-09T04:00:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )

    conn = sqlite3.connect(db)
    stored = conn.execute(
        """
        SELECT ts, reset_reason, uptime_s, rssi, heap_free, heap_min, enclosure_f
        FROM health WHERE dev = 'twin1' ORDER BY ts, seq
        """
    ).fetchall()
    conn.close()

    assert answer["resolution"] is None
    assert len(answer["reports"]) == len(stored) > 0
    for report, row in zip(answer["reports"], stored, strict=True):
        assert parse_ms(report["time"]) == row[0]
        assert report["reset_reason"] == row[1]
        assert report["uptime_s"] == row[2]
        assert report["rssi"] == row[3]
        assert report["heap_free"] == row[4]
        assert report["heap_min"] == row[5]
        assert report["enclosure_f"] == row[6]
    assert answer["reboots"] == [report for report in answer["reports"] if report["uptime_s"] == 0]
    matched = [report for report in answer["reboots"] if parse_ms(report["time"]) == reboot_ms]
    assert len(matched) == 1
    assert matched[0]["uptime_s"] == 0
    before = [report for report in answer["reports"] if parse_ms(report["time"]) < reboot_ms]
    assert before
    assert before[-1]["uptime_s"] > 0


def test_long_health_series_keeps_reboots(tmp_path: Path):
    db = tmp_path / "well-sim.db"
    conn = sqlite3.connect(db)
    script = "\n".join(
        line for line in SCHEMA.read_text().splitlines() if not line.strip().startswith("PRAGMA")
    )
    conn.executescript(script)
    start = parse_ms("2026-10-09T00:00:00")
    reboot_at = start + 1000 * 300_000
    for index in range(MAX_REPORTS + 1):
        ts = start + index * 300_000
        uptime = 0 if ts == reboot_at else index * 300
        reason = "sw" if ts == reboot_at else "poweron"
        conn.execute(
            """
            INSERT INTO health (
              dev, seq, ts, fw, uptime_s, reset_reason, heap_free, heap_min, rssi,
              wifi_reconnects, mqtt_pub_ok, mqtt_pub_fail, buffer_used, buffer_capacity,
              watchdog_timeouts, i2c_devices, enclosure_f, fan, calib_id, received_ts
            ) VALUES (
              'twin1', ?, ?, 'twin', ?, ?, 200000, 180000, -50,
              0, 0, 0, 0, 9000, 0, '[]', 72, 0, 'twin-default', ?
            )
            """,
            (index, ts, uptime, reason, ts),
        )
    conn.commit()
    conn.close()

    answer = get_device_health(
        "2026-10-09T00:00:00",
        "2026-10-16T00:00:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )
    assert answer["resolution"] is not None
    assert len(answer["reports"]) < MAX_REPORTS + 1
    assert any(parse_ms(report["time"]) == reboot_at and report["uptime_s"] == 0 for report in answer["reboots"])
