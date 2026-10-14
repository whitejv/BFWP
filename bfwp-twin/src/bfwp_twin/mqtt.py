"""Publish captured device messages to HiveMQ. Topics stay under bfwp-sim/."""

from __future__ import annotations

import json
import os
import ssl
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

import paho.mqtt.client as mqtt

TOPIC_ROOT = "bfwp-sim"
QOS = 1
INFLIGHT = 20
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


@dataclass(frozen=True)
class MqttConfig:
    host: str
    port: int
    username: str
    password: str
    topic_root: str

    def describe(self) -> str:
        return f"{self.username}@{self.host}:{self.port} topic root {self.topic_root}"


def load_mqtt_config() -> MqttConfig:
    """Defaults match `.env.example`. A `.env` file overrides them; the process environment wins."""
    values = {
        "MQTT_HOST": "broker.hivemq.com",
        "MQTT_PORT": "8883",
        "MQTT_USERNAME": "bfwp-twin",
        "MQTT_PASSWORD": "",
        "MQTT_TOPIC_ROOT": TOPIC_ROOT,
    }
    if _ENV_FILE.is_file():
        values.update(_parse_env_file(_ENV_FILE))
    for key in values:
        if key in os.environ:
            values[key] = os.environ[key]
    return MqttConfig(
        host=values["MQTT_HOST"],
        port=int(values["MQTT_PORT"]),
        username=values["MQTT_USERNAME"],
        password=values["MQTT_PASSWORD"],
        topic_root=values["MQTT_TOPIC_ROOT"],
    )


def publish_records(records: list[dict] | tuple[dict, ...], config: MqttConfig | None = None) -> None:
    """Publish each record at QoS 1. Status is retained. A clean disconnect does not send the Last Will."""
    config = config or load_mqtt_config()
    _require_sim_topics(config, records)
    if not records:
        return
    dev = str(records[0]["payload"]["dev"])
    link = _Link(
        config,
        f"bfwp-twin-{uuid.uuid4().hex[:8]}",
        will=(
            f"{TOPIC_ROOT}/{dev}/status",
            json.dumps({"dev": dev, "online": False}, separators=(",", ":")),
            QOS,
            True,
        ),
    )
    try:
        pending: list[mqtt.MQTTMessageInfo] = []
        for record in records:
            info = link.client.publish(
                record["topic"],
                json.dumps(record["payload"], separators=(",", ":")),
                qos=QOS,
                retain=record["topic"].endswith("/status"),
            )
            pending.append(info)
            if len(pending) >= INFLIGHT:
                _wait_published(pending.pop(0))
        for info in pending:
            _wait_published(info)
    finally:
        link.close()


def clear_retained_status(config: MqttConfig, dev: str) -> None:
    """Remove the retained status so a later subscriber does not receive a previous run."""
    _require_sim_topics(config, [])
    link = _Link(config, f"bfwp-twin-{uuid.uuid4().hex[:8]}")
    try:
        info = link.client.publish(f"{TOPIC_ROOT}/{dev}/status", b"", qos=QOS, retain=True)
        _wait_published(info)
    finally:
        link.close()


class Subscriber:
    """Collect messages on one filter. Call start before the publisher connects."""

    def __init__(self, config: MqttConfig, topic_filter: str):
        _require_sim_topics(config, [])
        if not topic_filter.startswith(f"{TOPIC_ROOT}/"):
            raise ValueError(f"refusing subscribe filter {topic_filter}")
        self._filter = topic_filter
        self._messages: list[dict] = []
        self._cv = threading.Condition()
        self._link = _Link(config, f"bfwp-sub-{uuid.uuid4().hex[:8]}")
        self._subscribed = threading.Event()
        self._link.client.on_message = self._on_message
        self._link.client.on_subscribe = self._on_subscribe
        self._link.client.user_data_set({"sub": self._subscribed})

    def start(self) -> None:
        self._link.client.subscribe(self._filter, qos=QOS)
        if not self._subscribed.wait(20):
            self.close()
            raise TimeoutError(f"subscribe {self._filter} timed out")

    def wait_for(self, count: int, timeout_s: float) -> list[dict]:
        import time

        deadline = time.monotonic() + timeout_s
        with self._cv:
            while len(self._messages) < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cv.wait(remaining)
            return list(self._messages)

    def close(self) -> None:
        self._link.close()

    def _on_message(self, _client, _userdata, message) -> None:
        if not message.payload:
            return
        item = {"topic": message.topic, "payload": json.loads(message.payload.decode())}
        with self._cv:
            self._messages.append(item)
            self._cv.notify_all()

    def _on_subscribe(self, _client, userdata, _mid, _reason_codes, _properties) -> None:
        userdata["sub"].set()


class _Link:
    def __init__(self, config: MqttConfig, client_id: str, will: tuple | None = None):
        self._up = threading.Event()
        self._reason = None
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )
        self.client.tls_set_context(ssl.create_default_context())
        if config.username:
            self.client.username_pw_set(config.username, config.password or None)
        if will is not None:
            topic, payload, qos, retain = will
            self.client.will_set(topic, payload, qos=qos, retain=retain)
        self.client.on_connect = self._on_connect
        self.client.connect(config.host, config.port, keepalive=60)
        self.client.loop_start()
        if not self._up.wait(20):
            self.close()
            raise TimeoutError(f"connect to {config.host}:{config.port} timed out")
        if self._reason is None or self._reason.is_failure:
            reason = self._reason
            self.close()
            raise ConnectionError(f"connect to {config.host}:{config.port} failed: {reason}")

    def close(self) -> None:
        try:
            self.client.disconnect()
        except Exception:
            pass
        self.client.loop_stop()

    def _on_connect(self, _client, _userdata, _flags, reason_code, _properties) -> None:
        self._reason = reason_code
        self._up.set()


def _require_sim_topics(config: MqttConfig, records) -> None:
    if config.topic_root != TOPIC_ROOT:
        raise ValueError(f"twin publishes only under {TOPIC_ROOT}")
    for record in records:
        topic = record["topic"]
        if not str(topic).startswith(f"{TOPIC_ROOT}/"):
            raise ValueError(f"refusing topic {topic}")


def _wait_published(info: mqtt.MQTTMessageInfo) -> None:
    info.wait_for_publish(timeout=30)
    if not info.is_published():
        raise RuntimeError("broker did not acknowledge a publish")


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values
