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
```json
{"v":1,"dev":"well1","seq":48213,"ts":1791384000123,
 "psi":52.4,"amps":9.8,"pump":1,"gal_total":1284337,"gpm":18.0}
```
| Field | Type | Notes |
|---|---|---|
| `psi` | number \| null | 0–100, 0.1 resolution. `null` while the sensor is faulted. |
| `amps` | number \| null | 0–512, 0.1 resolution. `null` while faulted. |
| `pump` | 0 \| 1 | Pump running (from amps threshold with hysteresis). |
| `gal_total` | int | Cumulative gallons, never resets. |
| `gpm` | number | Instantaneous flow estimate. |
| `amps_raw` | int | *Optional*, calibration only. |

**Cadence:** every **1 s** while *active* (pump on, or a flow pulse within the last 120 s),
otherwise every **60 s**.

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
| `sensor_fault` | Reading out of range / disconnected | `sensor`, `raw`, `reason` |
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
