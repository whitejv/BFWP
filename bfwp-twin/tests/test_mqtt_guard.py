"""The twin must not publish on the real device topic root. No network."""

from bfwp_twin.mqtt import MqttConfig, publish_records
import pytest


def test_publish_refuses_real_device_topic():
    config = MqttConfig("broker.hivemq.com", 8883, "bfwp-twin", "", "bfwp-sim")
    with pytest.raises(ValueError, match="refusing topic"):
        publish_records(
            [{"topic": "bfwp/well1/status", "payload": {"dev": "well1", "online": True}}],
            config,
        )


def test_publish_refuses_real_topic_root():
    config = MqttConfig("broker.hivemq.com", 8883, "bfwp-twin", "", "bfwp")
    with pytest.raises(ValueError, match="bfwp-sim"):
        publish_records([], config)
