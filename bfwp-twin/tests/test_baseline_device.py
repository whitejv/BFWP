"""Offline device messages for baseline_normal_night. No MQTT."""

import json
from pathlib import Path

import jsonschema

from bfwp_twin.expect import check_expect
from bfwp_twin.scenario import load_scenario
from bfwp_twin.simulate import run_offline

REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "baseline_normal_night.yaml"
SCHEMAS = REPO / "bfwp-spec" / "contracts" / "schemas" / "v1"
SCHEMA_FOR = {
    "telemetry": "telemetry.schema.json",
    "event": "event.schema.json",
    "health": "health.schema.json",
    "status": "status.schema.json",
}


def _validators():
    out = {}
    for kind, name in SCHEMA_FOR.items():
        schema = json.loads((SCHEMAS / name).read_text())
        jsonschema.Draft7Validator.check_schema(schema)
        out[kind] = jsonschema.Draft7Validator(schema)
    return out


def test_baseline_normal_night_offline_messages(tmp_path):
    scenario = load_scenario(SCENARIO)
    result = run_offline(SCENARIO, truth_log_dir=tmp_path)
    validators = _validators()
    seqs = []
    events = []
    kinds = set()

    assert result.records, "device produced no messages"
    for record in result.records:
        topic = record["topic"]
        assert topic.startswith(f"bfwp-sim/{scenario.device}/"), topic
        kind = topic.rsplit("/", 1)[-1]
        kinds.add(kind)
        validators[kind].validate(record["payload"])
        if "seq" in record["payload"]:
            seqs.append(record["payload"]["seq"])
        if kind == "event":
            events.append(record["payload"])

    assert kinds >= {"telemetry", "event", "health", "status"}
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))
    check_expect(scenario, events)

    text = result.messages_path.read_text().splitlines()
    assert len(text) == len(result.records)
