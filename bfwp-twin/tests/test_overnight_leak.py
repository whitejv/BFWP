"""Offline overnight_leak: downstream leak, then a Wi-Fi outage flushes batches. No MQTT."""

import json
from pathlib import Path

import jsonschema

from bfwp_twin.expect import check_expect
from bfwp_twin.scenario import load_scenario
from bfwp_twin.simulate import run_offline

REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "overnight_leak.yaml"
SCHEMAS = REPO / "bfwp-spec" / "contracts" / "schemas" / "v1"
SCHEMA_FOR = {
    "telemetry": "telemetry.schema.json",
    "batch": "telemetry-batch.schema.json",
    "event": "event.schema.json",
    "health": "health.schema.json",
    "status": "status.schema.json",
}


def _validators():
    out = {}
    for kind, name in SCHEMA_FOR.items():
        schema = json.loads((SCHEMAS / name).read_text())
        out[kind] = jsonschema.Draft7Validator(schema)
    return out


def _kind(record: dict) -> str:
    return record["topic"].rsplit("/", 1)[-1]


def test_overnight_leak_offline_messages(tmp_path):
    scenario = load_scenario(SCENARIO)
    result = run_offline(SCENARIO, truth_log_dir=tmp_path)
    validators = _validators()
    outage = scenario.outages[0]
    down = int(outage.at.timestamp() * 1000)
    up = int(outage.end.timestamp() * 1000)

    telemetry = []
    events = []
    seqs = []
    batches = []
    reconnect_at = None

    for index, record in enumerate(result.records):
        kind = _kind(record)
        payload = record["payload"]
        if kind == "telemetry" and "batch" in payload:
            validators["batch"].validate(payload)
            batches.append(payload["batch"])
            for item in payload["batch"]:
                telemetry.append(item)
                seqs.append(item["seq"])
                assert down <= item["ts"] < up
            assert reconnect_at is not None and index > reconnect_at
        else:
            validators[kind].validate(payload)
            if kind == "telemetry":
                telemetry.append(payload)
                assert payload["ts"] < down or payload["ts"] >= up
            elif kind == "event":
                events.append(payload)
                if down <= payload["ts"] < up:
                    assert reconnect_at is not None and index > reconnect_at
            elif kind == "health":
                assert payload["ts"] < down or payload["ts"] >= up
            elif kind == "status" and payload["ts"] == up:
                reconnect_at = index
                assert payload["online"] is True
            if "seq" in payload:
                seqs.append(payload["seq"])

    assert batches, "wifi outage produced no telemetry batch"
    assert all(1 <= len(batch) <= 100 for batch in batches)
    assert reconnect_at is not None
    assert seqs == list(range(len(seqs)))
    check_expect(scenario, events)

    health_after = [
        record["payload"]
        for record in result.records
        if _kind(record) == "health" and record["payload"]["ts"] >= up
    ]
    assert health_after
    assert health_after[0]["wifi_reconnects"] == 1
    assert health_after[0]["buffer_used"] == 0

    leak_at = int(scenario.leaks[0].at.timestamp() * 1000)
    gallons = [row["gal_total"] for row in telemetry if row["ts"] >= leak_at]
    assert gallons
    assert gallons[-1] > gallons[0]
    before = [row["gal_total"] for row in telemetry if row["ts"] < down]
    during = [item["gal_total"] for batch in batches for item in batch]
    assert during[-1] > before[-1]

    rows = [json.loads(line) for line in result.physics.truth_log_path.read_text().splitlines()]
    leak = next(row for row in rows if row["inject"] == "leak")
    assert leak["gpm"] == 0.4
    assert leak["location"] == "downstream"
    assert any(row["inject"] == "wifi_down" and row["minutes"] == 20 for row in rows)
