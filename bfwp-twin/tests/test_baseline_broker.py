"""Publish baseline_normal_night and confirm a subscriber sees the same messages.

Skipped unless BFWP_MQTT=1. The ordinary test run stays offline.
"""

import os
from collections import Counter
from pathlib import Path

import pytest

from bfwp_twin.mqtt import Subscriber, clear_retained_status, load_mqtt_config, publish_records
from bfwp_twin.scenario import load_scenario
from bfwp_twin.simulate import run_offline

pytestmark = pytest.mark.skipif(
    os.environ.get("BFWP_MQTT") != "1",
    reason="set BFWP_MQTT=1 to publish baseline_normal_night to HiveMQ",
)

REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "baseline_normal_night.yaml"


def _key(record: dict) -> str:
    import json

    return record["topic"] + "\n" + json.dumps(record["payload"], sort_keys=True, separators=(",", ":"))


def test_baseline_normal_night_reaches_subscriber(tmp_path):
    scenario = load_scenario(SCENARIO)
    result = run_offline(SCENARIO, truth_log_dir=tmp_path)
    config = load_mqtt_config()
    topic_filter = f"bfwp-sim/{scenario.device}/#"
    clear_retained_status(config, scenario.device)
    subscriber = Subscriber(config, topic_filter)
    subscriber.start()
    try:
        publish_records(result.records, config)
        received = subscriber.wait_for(len(result.records), timeout_s=180)
    finally:
        subscriber.close()
        clear_retained_status(config, scenario.device)

    assert len(received) == len(result.records)
    assert Counter(_key(row) for row in received) == Counter(_key(row) for row in result.records)
