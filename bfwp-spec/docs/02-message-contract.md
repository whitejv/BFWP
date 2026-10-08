# 02 — Message contract (v1)

Machine-readable versions: `contracts/topics.v1.json`, `contracts/schemas/v1/`,
examples in `contracts/examples/v1/`. If this doc and the schemas disagree, **the schemas
win** and this doc gets fixed.

## Topics
| Topic | Direction | QoS | Retained | Payload |
|---|---|---|---|---|
| `bfwp/<dev>/telemetry` | device → broker | 1 | no | telemetry **or** telemetry batch |
| `bfwp/<dev>/event` | device → broker | 1 | no | event |
| `bfwp/<dev>/status` | device → broker | 1 | **yes** | status (also the Last Will) |
| `bfwp/<dev>/health` | device → broker | 1 | no | health (every 300 s and after boot) |
| `bfwp-sim/<dev>/…` | twin → broker | 1 | same as above | same payloads |
| `bfwp-sim/<dev>/cmd` | you/tools → twin | 1 | no | sim command (twin only) |

`<dev>`: lowercase `[a-z0-9-]`, e.g. `well1`, `twin1`.

## Envelope (every telemetry and event message)
| Field | Type | Rule |
|---|---|---|
| `v` | int | Contract major version. `1`. |
| `dev` | string | Device ID; must match the topic's `<dev>`. |
| `seq` | int ≥ 0 | One counter per device across telemetry and events. Never reused; gaps allowed. |
| `ts` | int | UTC epoch **milliseconds**, device clock after NTP sync. Must be ≥ 2025-01-01. |

## Telemetry
All values are in engineering units, **converted on the ESP32** using calibration constants
stored on the device (there is no downstream conversion step).
```json
{"v":1,"dev":"well1","seq":48213,"ts":1791384000123,"mode":"active",
 "psi":52.4,"amps":9.8,"pump":1,"gal_total":1284337,"gpm":18.0}
```
| Field | Type | Notes |
|---|---|---|
| `mode` | `"active"` \| `"idle"` | Cadence in effect when the reading was published (see below). |
| `psi` | number \| null | Well pressure, 0–100 psi, 0.1 resolution. `null` while the sensor is faulted. |
| `amps` | number \| null | Pump current, A RMS, 0.1 resolution. Schema bound 0–200 is provisional until the current sensor is chosen. `null` while faulted. |
| `pump` | 0 \| 1 | Pump running (from amps threshold with hysteresis). |
| `gal_total` | int | Cumulative gallons = cumulative flow-meter pulses (**1 pulse = 1 gallon**). Never resets. |
| `gpm` | number | Flow rate in gallons per minute, from the time between pulses (algorithm in `03-sensors-and-units.md`). |
| `psi_v`, `amps_v` | number | *Optional.* Measured sensor output volts (referred to the sensor side of any divider), so history can be recalibrated. |

### Cadence (activity-based, not time-of-day)
The device samples continuously (≈ every 100 ms) and runs event detection on every sample;
only **publishing** is throttled.

| Mode | Publishes | Enter when **any** of | Leave when **all** of, for `IDLE_HOLD_S` (120 s) |
|---|---|---|---|
| `active` | every 1 s | pump current ≥ `PUMP_ON_AMPS`; a flow pulse arrives; psi changes ≥ `FAST_DPSI` (2 psi) within 10 s; any event fires | pump off, no flow pulse, psi steady |
| `idle` | every 60 s on a fixed grid, **plus** report-on-change | — | — |

- **Report-on-change (idle only):** publish an extra reading as soon as psi differs by
  ≥ `IDLE_DPSI` (1 psi) from the last published reading. It does not shift the 60 s grid, so
  extra readings appear between the regular ones.
- Events are always published immediately, in either mode.
- Thresholds are device settings (stored in flash), adjustable without rebuilding firmware;
  the values in use are reported via `calib_id` / firmware config, defaults in
  `07-firmware-design.md`.
- Consumers judge gaps by `mode`: > 3 s between `active` readings, or > 90 s between `idle`
  readings, indicates lost data or an outage.

### Telemetry batch
Used when flushing the offline buffer. Same topic. `v` and `dev` are hoisted to the top;
each item carries its own `seq` and `ts`. Max 100 items per message.
```json
{"v":1,"dev":"well1","batch":[
  {"seq":48214,"ts":1791384001123,"psi":52.3,"amps":9.8,"pump":1,"gal_total":1284337,"gpm":18.0},
  {"seq":48215,"ts":1791384002124,"psi":52.5,"amps":9.9,"pump":1,"gal_total":1284338,"gpm":18.1}]}
```
A consumer tells the two apart by the presence of `batch`.

## Events
Envelope + `type` + `data` (an object; shape depends on `type`).

| `type` | When | `data` fields |
|---|---|---|
| `boot` | After every start, once time is synced | `fw`, `reset_reason`, `buffered`, `rssi` |
| `pump_on` | Pump current crosses on-threshold | `psi`, `gal_total` |
| `pump_off` | Pump current crosses off-threshold | `start_ts`, `duration_s`, `gallons`, `psi_avg`, `psi_min`, `psi_max`, `amps_avg`, `amps_max`, `gal_total` |
| `flow_idle` | Flow pulses while the pump is off, summarized per window | `gallons`, `window_s`, `psi` |
| `psi_decay` | Pressure fell ≥ `DECAY_PSI` over `DECAY_WINDOW_S` with no flow pulses and pump off | `psi_start`, `psi_end`, `window_s` |
| `psi_low` / `psi_high` | Pressure beyond limit for ≥ `duration_s` | `value`, `limit`, `duration_s` |
| `amps_high` | Current beyond limit for ≥ `duration_s` | `value`, `limit`, `duration_s` |
| `short_cycle` | ≥ `N` pump cycles within `window_s` | `cycles`, `window_s` |
| `sensor_fault` | Reading out of range / disconnected | `sensor` (`psi`\|`amps`\|`flow`\|`enclosure_temp`), `raw`, `reason` |
| `sensor_ok` | Faulted sensor recovered | `sensor`, `fault_s` |
| `buffer_overflow` | Offline buffer full; oldest data dropped | `dropped`, `from_seq`, `to_seq` |

Notes:
- `flow_idle` is **not** by itself a leak: with a pressure tank, a zone can draw water while
  the pump is off. Ingest/MCP decide "leak" by checking whether any Hydrawise zone was
  running. `psi_decay` with **no** flow pulses points to a leak *upstream of the meter* or a
  check-valve / tank problem.
- Thresholds (`DECAY_PSI`, limits, `N`) are firmware config; defaults in
  `07-firmware-design.md`. The event reports the limit it used.
- Events are sent individually (not batched), including when flushing the buffer.

## Status (retained, Last Will)
```json
{"dev":"well1","online":true,"ts":1791406000000,"fw":"1.0.3","rssi":-71}
```
- Published retained with `online:true` on connect.
- Registered as the MQTT Last Will with `{"dev":"well1","online":false}` (no `ts` — the
  broker sends it, and ingest stamps receive time).
- No `v`/`seq`: status is current-state, not history.

## Health — `bfwp/<dev>/health`
Envelope (`v`, `dev`, `seq`, `ts`) plus device self-diagnostics. Sent every 300 s and right
after boot; **not** buffered while offline (a stale health report has little value).
```json
{"v":1,"dev":"well1","seq":50001,"ts":1791406005000,"fw":"1.0.3","uptime_s":5,
 "reset_reason":"poweron","heap_free":231044,"heap_min":228512,"rssi":-71,
 "wifi_reconnects":0,"mqtt_pub_ok":3,"mqtt_pub_fail":0,"buffer_used":42,
 "buffer_capacity":9000,"watchdog_timeouts":0,"i2c_devices":["0x48","0x49"],
 "enclosure_f":88.5,"fan":0,"calib_id":"2026-10-08a"}
```
| Field | Notes |
|---|---|
| `uptime_s`, `reset_reason` | Since boot; reason from ESP-IDF `esp_reset_reason()` |
| `heap_free`, `heap_min` | Free heap now / lowest since boot (leak detection for the firmware) |
| `rssi`, `wifi_reconnects` | Wi-Fi signal and reconnect count since boot |
| `mqtt_pub_ok`, `mqtt_pub_fail` | Publish counters since boot |
| `buffer_used`, `buffer_capacity` | Offline buffer fill, in records |
| `watchdog_timeouts` | Task-watchdog timeouts since boot |
| `i2c_devices` | Detected I2C addresses (expect the ADCs) |
| `enclosure_f`, `fan` | Enclosure temperature (°F, `null` if no sensor); fan state if fitted |
| `calib_id` | ID of the calibration constants in use; changes whenever they change |

## Sim command (twin only) — `bfwp-sim/<dev>/cmd`
```json
{"cmd":"leak","args":{"gpm":0.4}}
```
| `cmd` | `args` |
|---|---|
| `zone_on` | `zone` (int), `gpm`, `minutes` (optional) |
| `zone_off` | `zone` |
| `leak` | `gpm` (0 clears), `location`: `"downstream"` (through meter, default) \| `"upstream"` (before meter) |
| `fault` | `sensor`: `psi`\|`amps`\|`flow`, `mode`: `disconnected`\|`stuck`\|`noisy`, `minutes` |
| `clear_fault` | `sensor` |
| `wifi_down` | `minutes` |
| `reboot` | — |
| `pump_wear` | `amps_scale` (1.0 = healthy) |
| `set_speed` | `speed` (1 = real time) |
| `pause` / `resume` | — |
| `load_scenario` | `name` |

## Consumer rules
1. Validate against the schema; reject (log, don't crash) invalid messages.
2. Deduplicate on `(dev, seq)`.
3. Never reorder by arrival — always use `ts`.
4. Unknown **optional** fields are ignored (forward compatibility). Unknown `type` values
   are stored as-is.
