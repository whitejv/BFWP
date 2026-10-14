"""Load a twin message file into the sim database."""

from __future__ import annotations

import json
import time
from pathlib import Path

from bfwp_ingest.store import Store


def load_records(store: Store, records: list[dict], received_ts: int) -> None:
    for record in records:
        store.ingest(record["topic"], record["payload"], received_ts)


def load_jsonl(path: Path, db_path: Path, received_ts: int | None = None) -> Store:
    """Load every line. The returned store is finished and left open."""
    clock = int(time.time() * 1000) if received_ts is None else received_ts
    store = Store(db_path)
    for line_no, raw in enumerate(path.read_text().splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            store._reject("bfwp-sim/invalid/telemetry", {"raw": raw}, f"line {line_no}: {exc.msg}", clock)
            continue
        topic = record.get("topic")
        payload = record.get("payload")
        if not isinstance(topic, str) or not isinstance(payload, dict):
            store._reject(str(topic), payload if isinstance(payload, dict) else {"raw": raw}, "line needs topic and payload", clock)
            continue
        store.ingest(topic, payload, clock)
    store.finish()
    return store
