"""Events match the stored rows, and the fault and reboot show up in the list.

The tool never sees the truth log.
"""

import json
import sqlite3
import subprocess
from pathlib import Path

from bfwp_mcp.clock import parse_ms
from bfwp_mcp.events import MAX_EVENTS, get_events

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "bfwp-spec" / "contracts" / "sqlite" / "schema-v1.sql"
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "sensor_fault_and_reboot.yaml"
TWIN = REPO / "bfwp-twin" / ".venv" / "bin" / "bfwp-twin"
INGEST = REPO / "bfwp-ingest" / ".venv" / "bin" / "bfwp-ingest"


def test_fault_and_reboot_events_match_the_truth_log(tmp_path: Path):
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

    injected = [json.loads(line) for line in truth_log.read_text().splitlines()]
    fault = next(row for row in injected if row["inject"] == "fault")
    reboot_ms = int(next(row["ts"] for row in injected if row["inject"] == "reboot"))

    answer = get_events(
        "2026-10-09T03:00:00",
        "2026-10-09T04:00:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )
    conn = sqlite3.connect(db)
    stored = conn.execute(
        "SELECT ts, type, data FROM events WHERE dev = 'twin1' ORDER BY ts, seq"
    ).fetchall()
    conn.close()

    assert answer["truncated"] is False
    assert len(answer["events"]) == len(stored) > 0
    assert sum(answer["counts"].values()) == len(stored)
    for event, row in zip(answer["events"], stored, strict=True):
        assert parse_ms(event["time"]) == row[0]
        assert event["type"] == row[1]
        assert event["data"] == json.loads(row[2])

    faults = [event for event in answer["events"] if event["type"] == "sensor_fault"]
    assert len(faults) == 1
    assert faults[0]["data"]["sensor"] == fault["sensor"] == "psi"
    assert fault["ts"] <= parse_ms(faults[0]["time"]) < int(fault["ts"]) + 60_000
    boots = [event for event in answer["events"] if event["type"] == "boot"]
    assert any(parse_ms(event["time"]) == reboot_ms for event in boots)

    only_boots = get_events(
        "2026-10-09T03:00:00",
        "2026-10-09T04:00:00",
        types=["boot"],
        dev="twin1",
        source="sim",
        db_path=db,
    )
    assert {event["type"] for event in only_boots["events"]} == {"boot"}
    assert len(only_boots["events"]) == answer["counts"]["boot"]


def test_long_event_list_keeps_the_latest(tmp_path: Path):
    db = tmp_path / "well-sim.db"
    conn = sqlite3.connect(db)
    script = "\n".join(
        line for line in SCHEMA.read_text().splitlines() if not line.strip().startswith("PRAGMA")
    )
    conn.executescript(script)
    start = parse_ms("2026-10-09T00:00:00")
    total = MAX_EVENTS + 1
    for index in range(total):
        conn.execute(
            """
            INSERT INTO events (dev, seq, ts, type, data, received_ts)
            VALUES ('twin1', ?, ?, 'sensor_fault', '{"sensor":"psi"}', ?)
            """,
            (index, start + index * 1_000, start + index * 1_000),
        )
    conn.commit()
    conn.close()

    answer = get_events(
        "2026-10-09T00:00:00",
        "2026-10-10T00:00:00",
        dev="twin1",
        source="sim",
        db_path=db,
    )
    assert answer["truncated"] is True
    assert answer["counts"]["sensor_fault"] == total
    assert len(answer["events"]) == MAX_EVENTS
    assert parse_ms(answer["events"][-1]["time"]) == start + (total - 1) * 1_000
    assert parse_ms(answer["events"][0]["time"]) == start + 1_000
