"""Offline sensor_fault_and_reboot: null psi, then a boot with a seq jump. No MQTT."""

import json
from pathlib import Path

import jsonschema

from bfwp_twin.expect import check_expect
from bfwp_twin.scenario import load_scenario
from bfwp_twin.simulate import run_offline

REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "sensor_fault_and_reboot.yaml"
SCHEMAS = REPO / "bfwp-spec" / "contracts" / "schemas" / "v1"
SCHEMA_FOR = {
    "telemetry": "telemetry.schema.json",
    "event": "event.schema.json",
    "health": "health.schema.json",
    "status": "status.schema.json",
}


def test_sensor_fault_and_reboot_offline_messages(tmp_path):
    scenario = load_scenario(SCENARIO)
    result = run_offline(SCENARIO, truth_log_dir=tmp_path)
    validators = {}
    for kind, name in SCHEMA_FOR.items():
        schema = json.loads((SCHEMAS / name).read_text())
        validators[kind] = jsonschema.Draft7Validator(schema)

    telemetry = []
    events = []
    health = []
    seqs = []
    for record in result.records:
        kind = record["topic"].rsplit("/", 1)[-1]
        payload = record["payload"]
        validators[kind].validate(payload)
        if kind == "telemetry":
            telemetry.append(payload)
        elif kind == "event":
            events.append(payload)
        elif kind == "health":
            health.append(payload)
        if "seq" in payload:
            seqs.append(payload["seq"])

    check_expect(scenario, events)

    fault = next(event for event in events if event["type"] == "sensor_fault")
    ok = next(event for event in events if event["type"] == "sensor_ok")
    assert fault["data"]["sensor"] == "psi"
    assert fault["data"]["reason"] == "disconnected"
    assert fault["data"]["raw"] is None
    assert ok["data"] == {"sensor": "psi", "fault_s": 300.0}

    nulls = [row for row in telemetry if row["psi"] is None]
    assert nulls
    assert all(fault["ts"] < row["ts"] < ok["ts"] for row in nulls)
    assert all(row["psi"] is not None for row in telemetry if row["ts"] <= fault["ts"] or row["ts"] >= ok["ts"])

    boots = [event for event in events if event["type"] == "boot"]
    assert [boot["data"]["reset_reason"] for boot in boots] == ["poweron", "sw"]
    reboot = boots[1]
    previous = seqs[seqs.index(reboot["seq"]) - 1]
    assert reboot["seq"] % 100 == 0
    assert reboot["seq"] >= previous + 2
    assert len(seqs) == len(set(seqs))

    reboot_health = next(row for row in health if row["ts"] == reboot["ts"])
    assert reboot_health["reset_reason"] == "sw"
    assert reboot_health["uptime_s"] == 0
    assert {row["gal_total"] for row in telemetry} == {0}

    rows = [json.loads(line) for line in result.physics.truth_log_path.read_text().splitlines()]
    assert rows[0]["inject"] == "fault"
    assert rows[0]["sensor"] == "psi"
    assert rows[0]["mode"] == "disconnected"
    assert rows[0]["minutes"] == 5
    assert rows[1]["inject"] == "reboot"
