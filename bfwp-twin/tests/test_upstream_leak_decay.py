"""Offline upstream_leak_decay: pressure falls, the meter does not count. No MQTT."""

import json
from pathlib import Path

import jsonschema

from bfwp_twin.expect import check_expect
from bfwp_twin.scenario import load_scenario
from bfwp_twin.simulate import run_offline

REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "upstream_leak_decay.yaml"
SCHEMAS = REPO / "bfwp-spec" / "contracts" / "schemas" / "v1"
SCHEMA_FOR = {
    "telemetry": "telemetry.schema.json",
    "event": "event.schema.json",
    "health": "health.schema.json",
    "status": "status.schema.json",
}


def test_upstream_leak_decay_offline_messages(tmp_path):
    scenario = load_scenario(SCENARIO)
    result = run_offline(SCENARIO, truth_log_dir=tmp_path)
    validators = {}
    for kind, name in SCHEMA_FOR.items():
        schema = json.loads((SCHEMAS / name).read_text())
        validators[kind] = jsonschema.Draft7Validator(schema)

    telemetry = []
    events = []
    for record in result.records:
        kind = record["topic"].rsplit("/", 1)[-1]
        validators[kind].validate(record["payload"])
        if kind == "telemetry":
            telemetry.append(record["payload"])
        elif kind == "event":
            events.append(record["payload"])

    check_expect(scenario, events)

    decays = [event for event in events if event["type"] == "psi_decay"]
    assert decays
    drop = decays[0]["data"]["psi_start"] - decays[0]["data"]["psi_end"]
    assert drop >= 5.0

    assert telemetry
    assert {row["gal_total"] for row in telemetry} == {0}
    assert {row["gpm"] for row in telemetry} == {0.0}

    rows = [json.loads(line) for line in result.physics.truth_log_path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["inject"] == "leak"
    assert rows[0]["location"] == "upstream"
    assert rows[0]["gpm"] == 0.15
