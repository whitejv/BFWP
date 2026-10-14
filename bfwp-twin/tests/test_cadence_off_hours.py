"""Offline cadence for cadence_off_hours, including an upstream leak. No MQTT."""

import json
from pathlib import Path

import jsonschema

from bfwp_twin.expect import check_cadence, check_expect
from bfwp_twin.scenario import clock_ms, load_scenario
from bfwp_twin.simulate import run_offline

REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "cadence_off_hours.yaml"
SCHEMAS = REPO / "bfwp-spec" / "contracts" / "schemas" / "v1"
SCHEMA_FOR = {
    "telemetry": "telemetry.schema.json",
    "event": "event.schema.json",
    "health": "health.schema.json",
    "status": "status.schema.json",
}


def test_cadence_off_hours_offline_messages(tmp_path):
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
    check_cadence(scenario, telemetry)

    rows = [json.loads(line) for line in result.physics.truth_log_path.read_text().splitlines()]
    assert rows[-1]["inject"] == "leak"
    assert rows[-1]["location"] == "upstream"
    assert rows[-1]["gpm"] == 1.0

    leak_at = clock_ms(scenario.start, "06:00")
    gallons = [
        (row["ts"], row["gal_total"])
        for row in telemetry
        if row["ts"] >= leak_at
    ]
    assert gallons
    assert gallons[-1][1] == gallons[0][1]
