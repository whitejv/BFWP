"""Device status: online flag, latest health, and the last day's sequence gaps.

The scenario test never hands the truth log to the tool. `now` is the test clock.
"""

import json
import sqlite3
import subprocess
from pathlib import Path

from bfwp_mcp.clock import parse_ms
from bfwp_mcp.status import get_device_status

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "bfwp-spec" / "contracts" / "sqlite" / "schema-v1.sql"
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "sensor_fault_and_reboot.yaml"
TWIN = REPO / "bfwp-twin" / ".venv" / "bin" / "bfwp-twin"
INGEST = REPO / "bfwp-ingest" / ".venv" / "bin" / "bfwp-ingest"
NOW = "2026-10-09T04:00:00"


def test_status_matches_latest_rows_and_reboot_gap(tmp_path: Path):
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
        next(
            row["ts"]
            for row in (json.loads(line) for line in truth_log.read_text().splitlines())
            if row["inject"] == "reboot"
        )
    )
    answer = get_device_status(dev="twin1", source="sim", db_path=db, now=NOW)
    now_ms = parse_ms(NOW)

    conn = sqlite3.connect(db)
    status = conn.execute(
        """
        SELECT received_ts, online, fw FROM status_log
        WHERE dev = 'twin1' AND received_ts < ?
        ORDER BY received_ts DESC LIMIT 1
        """,
        (now_ms,),
    ).fetchone()
    health = conn.execute(
        """
        SELECT ts, uptime_s, rssi, buffer_used, buffer_capacity, watchdog_timeouts, enclosure_f
        FROM health WHERE dev = 'twin1' AND ts < ?
        ORDER BY ts DESC, seq DESC LIMIT 1
        """,
        (now_ms,),
    ).fetchone()
    last = conn.execute(
        """
        SELECT MAX(ts) FROM (
          SELECT ts FROM readings WHERE dev = 'twin1' AND ts < ?
          UNION ALL SELECT ts FROM events WHERE dev = 'twin1' AND ts < ?
          UNION ALL SELECT ts FROM health WHERE dev = 'twin1' AND ts < ?
          UNION ALL SELECT received_ts FROM status_log WHERE dev = 'twin1' AND received_ts < ?
        )
        """,
        (now_ms,) * 4,
    ).fetchone()[0]
    conn.close()

    assert answer["online"] is True
    assert status[1] == 1
    assert answer["fw"] == status[2]
    assert parse_ms(answer["status_time"]) == status[0]
    assert parse_ms(answer["last_message"]) == last
    assert parse_ms(answer["health"]["time"]) == health[0]
    assert answer["health"]["uptime_s"] == health[1]
    assert answer["health"]["rssi"] == health[2]
    assert answer["health"]["buffer_used"] == health[3]
    assert answer["health"]["buffer_capacity"] == health[4]
    assert answer["health"]["watchdog_timeouts"] == health[5]
    assert answer["health"]["enclosure_f"] == health[6]
    assert len(answer["seq_gaps"]) == 1
    assert parse_ms(answer["seq_gaps"][0]["to"]) == reboot_ms
    assert answer["seq_gaps"][0]["missing"] >= 1


def test_last_will_reports_offline(tmp_path: Path):
    db = tmp_path / "well-sim.db"
    conn = sqlite3.connect(db)
    script = "\n".join(
        line for line in SCHEMA.read_text().splitlines() if not line.strip().startswith("PRAGMA")
    )
    conn.executescript(script)
    ts = parse_ms("2026-10-09T03:30:00")
    conn.execute(
        "INSERT INTO status_log (dev, received_ts, online, fw, rssi) VALUES ('twin1', ?, 0, NULL, NULL)",
        (ts,),
    )
    conn.commit()
    conn.close()

    answer = get_device_status(dev="twin1", source="sim", db_path=db, now=NOW)
    assert answer["online"] is False
    assert answer["fw"] is None
    assert answer["health"] is None
    assert answer["seq_gaps"] == []
    assert parse_ms(answer["last_message"]) == ts
