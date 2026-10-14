"""Write spec v1 messages into SQLite.

Duplicates are ignored on (dev, seq). A reading that arrives for a minute
already closed — a flushed offline batch — recomputes that minute.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from bfwp_ingest.db import connect
from bfwp_ingest.validate import explain, load_validators

MINUTE_MS = 60_000
SIM_ROOT = "bfwp-sim"


def minute_ts(ts: int) -> int:
    return ts - ts % MINUTE_MS


class Store:
    def __init__(self, db_path: Path):
        self.conn = connect(db_path)
        self._lock = threading.RLock()
        self.validators = load_validators()
        self.high_water: dict[str, int] = {}
        self.inserted = 0
        self.ignored = 0
        self.rejected = 0
        self.recomputes = 0

    def close(self) -> None:
        self.conn.close()

    def ingest(self, topic: str, payload: dict, received_ts: int) -> None:
        with self._lock:
            self._ingest(topic, payload, received_ts)

    def _ingest(self, topic: str, payload: dict, received_ts: int) -> None:
        parts = topic.split("/")
        if len(parts) != 3 or parts[0] != SIM_ROOT:
            self._reject(topic, payload, f"topic must be {SIM_ROOT}/<dev>/<kind>", received_ts)
            return
        _root, dev, kind = parts
        if payload.get("dev") != dev:
            self._reject(topic, payload, "payload dev does not match the topic", received_ts)
            return
        if kind == "telemetry" and "batch" in payload:
            self._batch(topic, dev, payload, received_ts)
        elif kind == "telemetry":
            self._one_reading(topic, dev, payload, received_ts)
        elif kind == "event":
            self._event(topic, dev, payload, received_ts)
        elif kind == "health":
            self._health(topic, dev, payload, received_ts)
        elif kind == "status":
            self._status(topic, dev, payload, received_ts)
        else:
            self._reject(topic, payload, f"unknown topic kind {kind}", received_ts)

    def finish(self) -> None:
        """Roll up the still-open minute, then treat every older minute as closed."""
        with self._lock:
            self._finish()

    def _finish(self) -> None:
        for dev, open_minute in list(self.high_water.items()):
            self._recompute(dev, open_minute)
            self.high_water[dev] = open_minute + MINUTE_MS
        self.conn.commit()

    def _batch(self, topic: str, dev: str, payload: dict, received_ts: int) -> None:
        error = explain(self.validators["batch"], payload)
        if error:
            self._reject(topic, payload, error, received_ts)
            return
        for item in payload["batch"]:
            self._insert_reading(dev, item, received_ts)

    def _one_reading(self, topic: str, dev: str, payload: dict, received_ts: int) -> None:
        error = explain(self.validators["telemetry"], payload)
        if error:
            self._reject(topic, payload, error, received_ts)
            return
        self._insert_reading(dev, payload, received_ts)
        self._advance(dev, int(payload["ts"]))

    def _insert_reading(self, dev: str, row: dict, received_ts: int) -> None:
        ts = int(row["ts"])
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO readings (
              dev, seq, ts, mode, psi, amps, pump, gal_total, gpm, psi_v, amps_v, received_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dev,
                int(row["seq"]),
                ts,
                row["mode"],
                row["psi"],
                row["amps"],
                int(row["pump"]),
                int(row["gal_total"]),
                float(row["gpm"]),
                row.get("psi_v"),
                row.get("amps_v"),
                received_ts,
            ),
        )
        if cur.rowcount == 0:
            self.ignored += 1
            return
        self.inserted += 1
        minute = minute_ts(ts)
        high = self.high_water.get(dev)
        if high is not None and minute < high:
            self._recompute(dev, minute)
            self.recomputes += 1

    def _advance(self, dev: str, ts: int) -> None:
        minute = minute_ts(ts)
        high = self.high_water.get(dev)
        if high is None:
            self.high_water[dev] = minute
            return
        if minute <= high:
            return
        closed = high
        while closed < minute:
            self._recompute(dev, closed)
            closed += MINUTE_MS
        self.high_water[dev] = minute

    def _recompute(self, dev: str, minute: int) -> None:
        rows = self.conn.execute(
            """
            SELECT psi, amps, pump, gal_total FROM readings
            WHERE dev = ? AND ts >= ? AND ts < ?
            ORDER BY ts, seq
            """,
            (dev, minute, minute + MINUTE_MS),
        ).fetchall()
        if not rows:
            self.conn.execute(
                "DELETE FROM readings_1min WHERE dev = ? AND minute_ts = ?",
                (dev, minute),
            )
            return
        psis = [row["psi"] for row in rows if row["psi"] is not None]
        amps = [row["amps"] for row in rows if row["amps"] is not None]
        self.conn.execute(
            """
            INSERT INTO readings_1min (
              dev, minute_ts, n, psi_avg, psi_min, psi_max, amps_avg, amps_max, pump_secs, gallons
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dev, minute_ts) DO UPDATE SET
              n = excluded.n,
              psi_avg = excluded.psi_avg,
              psi_min = excluded.psi_min,
              psi_max = excluded.psi_max,
              amps_avg = excluded.amps_avg,
              amps_max = excluded.amps_max,
              pump_secs = excluded.pump_secs,
              gallons = excluded.gallons
            """,
            (
                dev,
                minute,
                len(rows),
                sum(psis) / len(psis) if psis else None,
                min(psis) if psis else None,
                max(psis) if psis else None,
                sum(amps) / len(amps) if amps else None,
                max(amps) if amps else None,
                float(sum(row["pump"] for row in rows)),
                int(rows[-1]["gal_total"]) - int(rows[0]["gal_total"]),
            ),
        )

    def _event(self, topic: str, dev: str, payload: dict, received_ts: int) -> None:
        error = explain(self.validators["event"], payload)
        if error:
            self._reject(topic, payload, error, received_ts)
            return
        ts = int(payload["ts"])
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO events (dev, seq, ts, type, data, received_ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                dev,
                int(payload["seq"]),
                ts,
                payload["type"],
                json.dumps(payload["data"], separators=(",", ":")),
                received_ts,
            ),
        )
        if cur.rowcount == 0:
            self.ignored += 1
        else:
            self.inserted += 1
            if payload["type"] == "pump_off":
                self._pump_cycle(dev, payload["data"])
        self._advance(dev, ts)

    def _pump_cycle(self, dev: str, data: dict) -> None:
        start = int(data["start_ts"])
        duration = float(data["duration_s"])
        self.conn.execute(
            """
            INSERT INTO pump_cycles (
              dev, start_ts, end_ts, duration_s, gallons, psi_avg, psi_min, psi_max, amps_avg, amps_max
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dev, start_ts) DO UPDATE SET
              end_ts = excluded.end_ts,
              duration_s = excluded.duration_s,
              gallons = excluded.gallons,
              psi_avg = excluded.psi_avg,
              psi_min = excluded.psi_min,
              psi_max = excluded.psi_max,
              amps_avg = excluded.amps_avg,
              amps_max = excluded.amps_max
            """,
            (
                dev,
                start,
                start + int(duration * 1000),
                duration,
                int(data["gallons"]),
                data["psi_avg"],
                data["psi_min"],
                data["psi_max"],
                data["amps_avg"],
                data["amps_max"],
            ),
        )

    def _health(self, topic: str, dev: str, payload: dict, received_ts: int) -> None:
        error = explain(self.validators["health"], payload)
        if error:
            self._reject(topic, payload, error, received_ts)
            return
        ts = int(payload["ts"])
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO health (
              dev, seq, ts, fw, uptime_s, reset_reason, heap_free, heap_min, rssi,
              wifi_reconnects, mqtt_pub_ok, mqtt_pub_fail, buffer_used, buffer_capacity,
              watchdog_timeouts, i2c_devices, enclosure_f, fan, calib_id, received_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dev,
                int(payload["seq"]),
                ts,
                payload["fw"],
                int(payload["uptime_s"]),
                payload["reset_reason"],
                int(payload["heap_free"]),
                int(payload["heap_min"]),
                int(payload["rssi"]),
                int(payload["wifi_reconnects"]),
                int(payload["mqtt_pub_ok"]),
                int(payload["mqtt_pub_fail"]),
                int(payload["buffer_used"]),
                int(payload["buffer_capacity"]),
                int(payload["watchdog_timeouts"]),
                json.dumps(payload["i2c_devices"], separators=(",", ":")),
                payload.get("enclosure_f"),
                payload.get("fan"),
                payload["calib_id"],
                received_ts,
            ),
        )
        if cur.rowcount == 0:
            self.ignored += 1
        else:
            self.inserted += 1
        self._advance(dev, ts)

    def _status(self, topic: str, dev: str, payload: dict, received_ts: int) -> None:
        error = explain(self.validators["status"], payload)
        if error:
            self._reject(topic, payload, error, received_ts)
            return
        # The payload clock keeps a replay of the same file from inserting a second row.
        stamped = int(payload["ts"]) if isinstance(payload.get("ts"), int) else received_ts
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO status_log (dev, received_ts, online, fw, rssi)
            VALUES (?, ?, ?, ?, ?)
            """,
            (dev, stamped, 1 if payload["online"] else 0, payload.get("fw"), payload.get("rssi")),
        )
        if cur.rowcount == 0:
            self.ignored += 1
        else:
            self.inserted += 1
        if isinstance(payload.get("ts"), int):
            self._advance(dev, int(payload["ts"]))

    def _reject(self, topic: str, payload: dict, error: str, received_ts: int) -> None:
        self.conn.execute(
            "INSERT INTO rejects (received_ts, topic, payload, error) VALUES (?, ?, ?, ?)",
            (received_ts, topic, json.dumps(payload, separators=(",", ":")), error),
        )
        self.rejected += 1


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
