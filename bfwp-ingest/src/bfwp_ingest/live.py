"""Subscribe to bfwp-sim/# and write the sim database. Real topics are not opened."""

from __future__ import annotations

import json
import os
import ssl
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import paho.mqtt.client as mqtt

from bfwp_ingest.store import Store, count_rows

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


@dataclass(frozen=True)
class IngestConfig:
    host: str
    port: int
    username: str
    password: str
    client_id: str
    sim_root: str


def load_ingest_config() -> IngestConfig:
    values = {
        "MQTT_HOST": "broker.hivemq.com",
        "MQTT_PORT": "8883",
        "MQTT_USERNAME": "bfwp-ingest",
        "MQTT_PASSWORD": "",
        "MQTT_CLIENT_ID": "bfwp-ingest-macmini",
        "SIM_TOPIC_ROOT": "bfwp-sim",
    }
    if _ENV_FILE.is_file():
        values.update(_parse_env_file(_ENV_FILE))
    for key in values:
        if key in os.environ:
            values[key] = os.environ[key]
    return IngestConfig(
        host=values["MQTT_HOST"],
        port=int(values["MQTT_PORT"]),
        username=values["MQTT_USERNAME"],
        password=values["MQTT_PASSWORD"],
        client_id=values["MQTT_CLIENT_ID"],
        sim_root=values["SIM_TOPIC_ROOT"],
    )


class LiveIngest:
    """One connection. Call stop to roll up the open minute and close the database."""

    def __init__(self, db_path: Path, config: IngestConfig | None = None, client_id: str | None = None):
        self.config = config or load_ingest_config()
        self.store = Store(db_path)
        self._client_id = client_id or self.config.client_id
        self._subscribed = threading.Event()
        self._cv = threading.Condition()
        self.reading_count = 0
        self._client: mqtt.Client | None = None
        self._stopped = False

    def start(self) -> None:
        if self.config.sim_root != "bfwp-sim":
            raise ValueError("ingest live path writes only bfwp-sim into the sim database")
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self._client_id,
            protocol=mqtt.MQTTv311,
        )
        client.tls_set_context(ssl.create_default_context())
        if self.config.username:
            client.username_pw_set(self.config.username, self.config.password or None)
        client.user_data_set({"sub": self._subscribed})
        client.on_connect = self._on_connect
        client.on_subscribe = self._on_subscribe
        client.on_message = self._on_message
        client.connect(self.config.host, self.config.port, keepalive=60)
        client.loop_start()
        self._client = client
        if not self._subscribed.wait(20):
            self.stop()
            raise TimeoutError(f"subscribe {self.config.sim_root}/# timed out")

    def wait_for_readings(self, count: int, timeout_s: float) -> int:
        deadline = time.monotonic() + timeout_s
        with self._cv:
            while self.reading_count < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return self.reading_count
                self._cv.wait(remaining)
            return self.reading_count

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client.loop_stop()
            self._client = None
        self.store.finish()
        self.store.close()

    def _on_connect(self, client, _userdata, _flags, reason_code, _properties) -> None:
        if reason_code.is_failure:
            return
        client.subscribe(f"{self.config.sim_root}/#", qos=1)

    def _on_subscribe(self, _client, userdata, _mid, _reason_codes, _properties) -> None:
        userdata["sub"].set()

    def _on_message(self, _client, _userdata, message) -> None:
        if not message.payload:
            return
        received = int(time.time() * 1000)
        with self.store._lock:
            try:
                payload = json.loads(message.payload.decode())
            except json.JSONDecodeError as exc:
                self.store._reject(
                    message.topic,
                    {"raw": message.payload.decode(errors="replace")},
                    exc.msg,
                    received,
                )
                self.store.conn.commit()
                return
            if not isinstance(payload, dict):
                self.store._reject(message.topic, {"raw": payload}, "payload must be an object", received)
                self.store.conn.commit()
                return
            self.store.ingest(message.topic, payload, received)
            self.store.conn.commit()
            reading_count = count_rows(self.store.conn, "readings")
        with self._cv:
            self.reading_count = reading_count
            self._cv.notify_all()


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values
