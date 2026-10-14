"""Device behavior on top of the hydraulic model.

Publishing cadence, seq, flow-meter gpm, and the event rules from
bfwp-spec/docs/07-firmware-design.md. A wifi_down outage buffers telemetry
and events, then flushes telemetry as batches. Messages are captured in
memory. Nothing is sent to a broker.
"""

from __future__ import annotations

import json
from pathlib import Path

from bfwp_twin.scenario import Scenario

FW = "twin-0.1.0"
CALIB_ID = "twin-default"
RSSI = -50
TOPIC_ROOT = "bfwp-sim"

SAMPLE_MS = 100
PUMP_ON_AMPS = 3.0
PUMP_OFF_AMPS = 2.0
FAST_DPSI = 2.0
IDLE_DPSI = 1.0
IDLE_HOLD_MS = 120_000
FLOW_DEBOUNCE_MS = 100
FLOW_TIMEOUT_MS = 120_000
FLOW_IDLE_WINDOW_MS = 600_000
DECAY_PSI = 5.0
DECAY_WINDOW_MS = 3_600_000
SHORT_CYCLE_N = 6
SHORT_CYCLE_WINDOW_MS = 600_000
HEALTH_MS = 300_000
AMPS_RUN_BASE = 6.0
AMPS_PER_PSI = 0.05
INRUSH_MS = 300
INRUSH_MUL = 4.0
BUFFER_CAPACITY = 9000
BATCH_MAX = 100
FAULT_SAMPLES = 3
SEQ_SAVE_EVERY = 100
GAL_SAVE_EVERY = 10


def _round1(value: float) -> float:
    return round(value, 1)


class Device:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.dev = scenario.device
        self.start_ms = int(scenario.start.timestamp() * 1000)
        self.seq = 0
        self.records: list[dict] = []
        self.mode = "idle"
        self.pump_flag = 0
        self.high_n = 0
        self.low_n = 0
        self.hydraulic_on = False
        self.inrush_until = 0
        self.psi = 0.0
        self.amps = 0.0
        self.gpm = 0.0
        self.gal_total = 0
        self.partial_gal = 0.0
        self.last_pulse_ms: int | None = None
        self.interval_ms: int | None = None
        self.psi_ring: list[float] = []
        self.ring_i = 0
        self.quiet_since: int | None = None
        self.last_pub_psi: float | None = None
        self.booted = False
        self.t_ms = self.start_ms
        self.flow_window_end = self.start_ms + FLOW_IDLE_WINDOW_MS
        self.idle_gal = 0
        self.decay_tracking = False
        self.decay_rearmed = True
        self.decay_start_psi = 0.0
        self.decay_start_ms = 0
        self.pump_on_times: list[int] = []
        self.short_cycle_until = 0
        self.cycle_psi: list[float] = []
        self.cycle_amps: list[float] = []
        self.cycle_start_ms = 0
        self.cycle_gal = 0
        self.uptime_origin = self.start_ms
        self.outages = tuple(
            (int(outage.at.timestamp() * 1000), int(outage.end.timestamp() * 1000))
            for outage in scenario.outages
        )
        self.link_down = False
        self.buffer: list[dict] = []
        self.pub_ok = 0
        self.wifi_reconnects = 0
        self._in_overflow = False
        self.seq_saved = 0
        self.gal_saved = 0
        self.reset_reason = "poweron"
        self.health_at_ms: int | None = None
        self.faults = tuple(
            (int(fault.at.timestamp() * 1000), int(fault.end.timestamp() * 1000), fault.sensor, fault.mode)
            for fault in scenario.faults
        )
        self.reboot_ms = {int(reboot.at.timestamp() * 1000) for reboot in scenario.reboots}
        self.reboots_done: set[int] = set()
        self.fault_bad = {"psi": 0, "amps": 0, "flow": 0}
        self.fault_good = {"psi": 0, "amps": 0, "flow": 0}
        self.faulted = {"psi": False, "amps": False, "flow": False}
        self.fault_since: dict[str, int] = {}

    def observe(self, t_ms: int, psi: float, hydraulic_on: bool, demand_gpm: float) -> None:
        self.t_ms = t_ms
        self._update_link()
        self.psi = psi
        rebooted = self._maybe_reboot()
        if not self.psi_ring:
            self.psi_ring = [psi] * 100
        if t_ms == self.start_ms and not self.booted:
            self._emit_status()
            self._emit_event("boot", {
                "fw": FW,
                "reset_reason": "poweron",
                "buffered": 0,
                "rssi": RSSI,
            })
            self._emit_health()
            self.booted = True

        pulse = self._integrate_flow(demand_gpm)
        self._update_amps(hydraulic_on)
        event = self._update_faults() or rebooted
        event = self._update_pump_events() or event
        if (not self.pump_flag) and pulse:
            self.idle_gal += 1
        event = self._flow_idle_windows() or event
        event = self._psi_decay(pulse) or event
        self._update_cadence(pulse, event)
        self._publish_health()
        self._publish_telemetry()
        if self.pump_flag:
            self.cycle_psi.append(psi)
            self.cycle_amps.append(self.amps)

    def write(self, path: Path) -> None:
        path.write_text("".join(json.dumps(record, separators=(",", ":")) + "\n" for record in self.records))

    def _integrate_flow(self, demand_gpm: float) -> bool:
        self.partial_gal += demand_gpm * (SAMPLE_MS / 60_000.0)
        if self.partial_gal < 1.0:
            self._update_gpm()
            return False
        if self.last_pulse_ms is not None and self.t_ms - self.last_pulse_ms < FLOW_DEBOUNCE_MS:
            self._update_gpm()
            return False
        self.partial_gal -= 1.0
        self.gal_total += 1
        if self.gal_total // GAL_SAVE_EVERY > self.gal_saved // GAL_SAVE_EVERY:
            self.gal_saved = (self.gal_total // GAL_SAVE_EVERY) * GAL_SAVE_EVERY
        if self.last_pulse_ms is not None:
            self.interval_ms = self.t_ms - self.last_pulse_ms
            self.gpm = 60_000.0 / self.interval_ms
        self.last_pulse_ms = self.t_ms
        return True

    def _update_gpm(self) -> None:
        if self.last_pulse_ms is None:
            self.gpm = 0.0
            return
        since_ms = self.t_ms - self.last_pulse_ms
        if since_ms >= FLOW_TIMEOUT_MS:
            self.gpm = 0.0
        elif self.interval_ms and since_ms > self.interval_ms:
            self.gpm = 60_000.0 / since_ms
        elif self.interval_ms:
            self.gpm = 60_000.0 / self.interval_ms

    def _update_amps(self, hydraulic_on: bool) -> None:
        if hydraulic_on and not self.hydraulic_on:
            self.inrush_until = self.t_ms + INRUSH_MS
        self.hydraulic_on = hydraulic_on
        if not hydraulic_on:
            self.amps = 0.0
        else:
            self.amps = AMPS_RUN_BASE + AMPS_PER_PSI * self.psi
            if self.t_ms < self.inrush_until:
                self.amps *= INRUSH_MUL
        if self.amps >= PUMP_ON_AMPS:
            self.high_n += 1
            self.low_n = 0
        elif self.amps < PUMP_OFF_AMPS:
            self.low_n += 1
            self.high_n = 0
        else:
            self.high_n = 0
            self.low_n = 0

    def _update_pump_events(self) -> bool:
        if (not self.pump_flag) and self.high_n >= 2:
            self.pump_flag = 1
            self.cycle_start_ms = self.t_ms
            self.cycle_gal = self.gal_total
            self.cycle_psi = []
            self.cycle_amps = []
            self.pump_on_times.append(self.t_ms)
            self._emit_event("pump_on", {"psi": _round1(self.psi), "gal_total": self.gal_total})
            self._maybe_short_cycle()
            return True
        if self.pump_flag and self.low_n >= 2:
            samples_psi = self.cycle_psi or [self.psi]
            samples_amps = self.cycle_amps or [self.amps]
            self.pump_flag = 0
            self._emit_event("pump_off", {
                "start_ts": self.cycle_start_ms,
                "duration_s": (self.t_ms - self.cycle_start_ms) / 1000.0,
                "gallons": self.gal_total - self.cycle_gal,
                "psi_avg": _round1(sum(samples_psi) / len(samples_psi)),
                "psi_min": _round1(min(samples_psi)),
                "psi_max": _round1(max(samples_psi)),
                "amps_avg": _round1(sum(samples_amps) / len(samples_amps)),
                "amps_max": _round1(max(samples_amps)),
                "gal_total": self.gal_total,
            })
            self.decay_rearmed = True
            self.decay_tracking = False
            self.gal_saved = self.gal_total
            return True
        return False

    def _maybe_short_cycle(self) -> None:
        recent = [stamp for stamp in self.pump_on_times if self.t_ms - stamp <= SHORT_CYCLE_WINDOW_MS]
        self.pump_on_times = recent
        if len(recent) >= SHORT_CYCLE_N and self.t_ms >= self.short_cycle_until:
            self._emit_event("short_cycle", {"cycles": len(recent), "window_s": SHORT_CYCLE_WINDOW_MS // 1000})
            self.short_cycle_until = self.t_ms + SHORT_CYCLE_WINDOW_MS

    def _flow_idle_windows(self) -> bool:
        fired = False
        while self.t_ms >= self.flow_window_end:
            if self.idle_gal >= 1:
                self._emit_event("flow_idle", {
                    "gallons": self.idle_gal,
                    "window_s": FLOW_IDLE_WINDOW_MS // 1000,
                    "psi": _round1(self.psi),
                }, ts=self.flow_window_end - 1)
                fired = True
            self.idle_gal = 0
            self.flow_window_end += FLOW_IDLE_WINDOW_MS
        return fired

    def _psi_decay(self, pulse: bool) -> bool:
        if self.faulted["psi"] or self.pump_flag or pulse:
            self.decay_tracking = False
            return False
        if not self.decay_rearmed:
            return False
        if not self.decay_tracking:
            self.decay_tracking = True
            self.decay_start_psi = self.psi
            self.decay_start_ms = self.t_ms
            return False
        elapsed = self.t_ms - self.decay_start_ms
        if elapsed > DECAY_WINDOW_MS:
            self.decay_start_psi = self.psi
            self.decay_start_ms = self.t_ms
            return False
        if self.decay_start_psi - self.psi >= DECAY_PSI:
            self._emit_event("psi_decay", {
                "psi_start": _round1(self.decay_start_psi),
                "psi_end": _round1(self.psi),
                "window_s": elapsed / 1000.0,
            })
            self.decay_rearmed = False
            self.decay_tracking = False
            return True
        return False

    def _update_cadence(self, pulse: bool, event: bool) -> None:
        if self.faulted["psi"]:
            fast = False
        else:
            old = self.psi_ring[self.ring_i]
            self.psi_ring[self.ring_i] = self.psi
            self.ring_i = (self.ring_i + 1) % 100
            fast = abs(self.psi - old) >= FAST_DPSI
        if self.amps >= PUMP_ON_AMPS or pulse or fast or event:
            self.mode = "active"
            self.quiet_since = None
            return
        quiet = self.pump_flag == 0 and not pulse and not fast
        if not quiet:
            self.quiet_since = None
            return
        if self.quiet_since is None:
            self.quiet_since = self.t_ms
        elif self.mode == "active" and self.t_ms - self.quiet_since >= IDLE_HOLD_MS:
            self.mode = "idle"

    def _maybe_reboot(self) -> bool:
        if self.t_ms not in self.reboot_ms or self.t_ms in self.reboots_done:
            return False
        self.reboots_done.add(self.t_ms)
        self.seq = self.seq_saved + SEQ_SAVE_EVERY
        self.gal_total = self.gal_saved
        self.partial_gal = 0.0
        self.mode = "idle"
        self.pump_flag = 0
        self.high_n = 0
        self.low_n = 0
        self.hydraulic_on = False
        self.inrush_until = 0
        self.gpm = 0.0
        self.last_pulse_ms = None
        self.interval_ms = None
        self.psi_ring = []
        self.ring_i = 0
        self.quiet_since = None
        self.last_pub_psi = None
        self.idle_gal = 0
        self.decay_tracking = False
        self.decay_rearmed = True
        self.pump_on_times = []
        self.short_cycle_until = 0
        self.cycle_psi = []
        self.cycle_amps = []
        self.uptime_origin = self.t_ms
        self.pub_ok = 0
        self.wifi_reconnects = 0
        self.reset_reason = "sw"
        for sensor in self.faulted:
            self.fault_bad[sensor] = 0
            self.fault_good[sensor] = 0
            self.faulted[sensor] = False
        self.fault_since.clear()
        buffered = len(self.buffer)
        self._emit_status()
        self._flush_buffer()
        self._emit_event("boot", {
            "fw": FW,
            "reset_reason": self.reset_reason,
            "buffered": buffered,
            "rssi": RSSI,
        })
        self._emit_health()
        return True

    def _update_faults(self) -> bool:
        active = {
            sensor
            for start, end, sensor, _mode in self.faults
            if start <= self.t_ms < end
        }
        fired = False
        for sensor in ("psi", "amps", "flow"):
            if sensor in active:
                self.fault_good[sensor] = 0
                self.fault_bad[sensor] += 1
                if not self.faulted[sensor] and self.fault_bad[sensor] >= FAULT_SAMPLES:
                    self.faulted[sensor] = True
                    self.fault_since[sensor] = self.t_ms
                    self._emit_event("sensor_fault", {
                        "sensor": sensor,
                        "raw": None,
                        "reason": "disconnected",
                    })
                    fired = True
            else:
                self.fault_bad[sensor] = 0
                if not self.faulted[sensor]:
                    continue
                self.fault_good[sensor] += 1
                if self.fault_good[sensor] >= FAULT_SAMPLES:
                    fault_s = (self.t_ms - self.fault_since[sensor]) / 1000.0
                    self.faulted[sensor] = False
                    self._emit_event("sensor_ok", {"sensor": sensor, "fault_s": fault_s})
                    fired = True
        return fired

    def _update_link(self) -> None:
        offline = any(start <= self.t_ms < end for start, end in self.outages)
        if self.link_down and not offline:
            self.link_down = False
            self.wifi_reconnects += 1
            self._emit_status()
            self._flush_buffer()
        else:
            self.link_down = offline

    def _publish_health(self) -> None:
        # Health is not buffered: a stale report is dropped for the whole outage.
        # The boot step already wrote the t=0 health report.
        if self.link_down or self.health_at_ms == self.t_ms:
            return
        if self.t_ms != self.start_ms and (self.t_ms - self.start_ms) % HEALTH_MS == 0:
            self._emit_health()

    def _publish_telemetry(self) -> None:
        elapsed = self.t_ms - self.start_ms
        on_second = elapsed % 1000 == 0
        on_minute = elapsed % 60_000 == 0
        if self.mode == "active" and on_second:
            self._emit_telemetry()
        elif self.mode == "idle" and on_minute:
            self._emit_telemetry()
        elif (
            self.mode == "idle"
            and self.last_pub_psi is not None
            and abs(self.psi - self.last_pub_psi) >= IDLE_DPSI
        ):
            self._emit_telemetry()

    def _emit_telemetry(self) -> None:
        self._emit("telemetry", {
            "mode": self.mode,
            "psi": None if self.faulted["psi"] else _round1(self.psi),
            "amps": _round1(self.amps),
            "pump": self.pump_flag,
            "gal_total": self.gal_total,
            "gpm": _round1(self.gpm),
        })
        self.last_pub_psi = self.psi

    def _emit_health(self) -> None:
        self._emit("health", {
            "fw": FW,
            "uptime_s": (self.t_ms - self.uptime_origin) // 1000,
            "reset_reason": self.reset_reason,
            "heap_free": 200000,
            "heap_min": 180000,
            "rssi": RSSI,
            "wifi_reconnects": self.wifi_reconnects,
            "mqtt_pub_ok": self.pub_ok,
            "mqtt_pub_fail": 0,
            "buffer_used": len(self.buffer),
            "buffer_capacity": BUFFER_CAPACITY,
            "watchdog_timeouts": 0,
            "i2c_devices": ["0x48", "0x49"],
            "enclosure_f": 72.0,
            "fan": 0,
            "calib_id": CALIB_ID,
        })
        self.health_at_ms = self.t_ms

    def _emit_status(self) -> None:
        self.records.append({
            "topic": f"{TOPIC_ROOT}/{self.dev}/status",
            "payload": {
                "dev": self.dev,
                "online": True,
                "ts": self.t_ms,
                "fw": FW,
                "rssi": RSSI,
            },
        })
        self.pub_ok += 1

    def _flush_buffer(self) -> None:
        """Oldest first. Telemetry groups into batches; an event is sent on its own."""
        items: list[dict] = []

        def flush_items() -> None:
            if not items:
                return
            self.records.append({
                "topic": f"{TOPIC_ROOT}/{self.dev}/telemetry",
                "payload": {"v": 1, "dev": self.dev, "batch": list(items)},
            })
            self.pub_ok += 1
            items.clear()

        for record in self.buffer:
            kind = record["topic"].rsplit("/", 1)[-1]
            if kind == "telemetry":
                payload = record["payload"]
                items.append({
                    "seq": payload["seq"],
                    "ts": payload["ts"],
                    "mode": payload["mode"],
                    "psi": payload["psi"],
                    "amps": payload["amps"],
                    "pump": payload["pump"],
                    "gal_total": payload["gal_total"],
                    "gpm": payload["gpm"],
                })
                if len(items) == BATCH_MAX:
                    flush_items()
            else:
                flush_items()
                self.records.append(record)
                self.pub_ok += 1
        flush_items()
        self.buffer.clear()

    def _remember(self, record: dict) -> None:
        dropped: list[int] = []
        while len(self.buffer) >= BUFFER_CAPACITY:
            dropped.append(self.buffer.pop(0)["payload"]["seq"])
        self.buffer.append(record)
        if not dropped or self._in_overflow:
            return
        while len(self.buffer) >= BUFFER_CAPACITY:
            dropped.append(self.buffer.pop(0)["payload"]["seq"])
        self._in_overflow = True
        try:
            self._emit_event("buffer_overflow", {
                "dropped": len(dropped),
                "from_seq": dropped[0],
                "to_seq": dropped[-1],
            })
        finally:
            self._in_overflow = False

    def _emit_event(self, event_type: str, data: dict, ts: int | None = None) -> None:
        saved = self.t_ms
        if ts is not None:
            self.t_ms = ts
        self._emit("event", {"type": event_type, "data": data})
        self.t_ms = saved

    def _emit(self, suffix: str, body: dict) -> None:
        payload = {"v": 1, "dev": self.dev, "seq": self.seq, "ts": self.t_ms, **body}
        self.seq += 1
        if self.seq % SEQ_SAVE_EVERY == 0:
            self.seq_saved = self.seq
        record = {"topic": f"{TOPIC_ROOT}/{self.dev}/{suffix}", "payload": payload}
        if self.link_down:
            self._remember(record)
        else:
            self.records.append(record)
            self.pub_ok += 1
