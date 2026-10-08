# 06 — Digital twin

`bfwp-twin` simulates the well system **and** the ESP32's behavior, publishing spec v1
messages to `bfwp-sim/<dev>/…`. Ingest stores them in `well-sim.db`. Purpose:
build and test ingest/MCP/analysis before hardware exists, and measure how well the
analysis detects injected problems.

## 1. Physical model (simulation step: 100 ms)
| Element | Model |
|---|---|
| Pressure tank | Pre-charge `P0` (default 38 psi), total volume `V` (default 86 gal ≈ 22 gal drawdown at 40→60). Pressure from Boyle's law on the air charge. |
| Pressure switch | Cut-in 40 psi, cut-out 60 psi (configurable to match the real switch). |
| Pump | Flow vs pressure from a simple pump curve; current = `I_idle_run + k·(psi)` scaled by `amps_scale` (wear); inrush spike ×4 for 0.3 s at start. |
| Zones | Each zone = a fixed demand in gpm at nominal pressure, scaled by √(psi/nominal). |
| Leak | Constant orifice-style demand, `downstream` (through the meter) or `upstream` (before the meter). |
| Flow meter | Integrates downstream flow; emits a pulse per gallon. |
| Noise | Gaussian noise on psi (±0.2) and amps (±0.1), configurable. |

## 2. Device behavior (must match firmware)
Same as `07-firmware-design.md` §Event rules and §Publishing cadence: seq handling,
activity-based cadence (`active` 1 s / `idle` 60 s + report-on-change, with the 2-minute
hold), event detection, `gpm` from pulse intervals, offline buffering + batch flush, boot
event, periodic `health` reports, retained status and Last Will. The twin publishes values
already in engineering units (it simulates the device *after* conversion) and may include
`psi_v`/`amps_v` computed from the default calibration. When `wifi_down` is injected, the twin buffers and flushes with batches exactly
as the device would.

## 3. Ways to drive it
1. **Scenario files** — YAML timelines (format below). Repeatable; used in CI-style tests.
2. **Live control** — publish sim commands to `bfwp-sim/<dev>/cmd` (schema
   `sim-command.schema.json`) or use the CLI (`bfwp-twin cmd leak --gpm 0.4`).
3. **Hydrawise mirror** — read the real Hydrawise schedule/run history and simulate those
   zone runs, writing matching `zone_runs` (source `twin`) so joins can be tested.

### Time modes
- `speed: 1` — real time (good for end-to-end and live demos).
- `speed: N` — N× faster; timestamps are simulated time.
- `speed: 0` — "as fast as possible" backfill (e.g. generate a month in minutes).
  Simulated `ts` values are used; ingest doesn't care how fast they arrive.

## 4. Scenario file format
```yaml
name: overnight_leak
description: Zone 3 runs, then a small downstream leak starts.
device: twin1
start: "2026-10-08T21:00:00-05:00"
end:   "2026-10-09T07:00:00-05:00"
speed: 0
seed: 42                         # makes noise reproducible
system:
  pressure_switch: {cut_in: 40, cut_out: 60}
  zones: {1: {gpm: 14}, 2: {gpm: 11}, 3: {gpm: 12}}
timeline:
  - {at: "22:00", zone_on:  {zone: 3, minutes: 15}}
  - {at: "23:30", leak:     {gpm: 0.4, location: downstream}}
  - {at: "02:00", wifi_down: {minutes: 20}}
expect:                          # shared assertions (twin AND firmware logic must pass)
  cadence:                       # optional: publishing-mode assertions
    - {mode: active, between: ["22:00", "22:15"]}
  events:
    - {type: pump_on,  between: ["22:00", "22:05"]}
    - {type: flow_idle, after: "23:30"}
  no_events:
    - {type: sensor_fault}
  analysis:                      # what the MCP-based analysis should conclude
    leak_detected: true
    leak_gpm_approx: [0.3, 0.5]
```
Times without a date are relative to `start`'s date and roll past midnight in order.

## 5. Truth log
Each run writes `truth-logs/<scenario>-<run-id>.jsonl`: one line per injected condition
with sim timestamps, e.g.
```json
{"ts":1791435000000,"inject":"leak","gpm":0.4,"location":"downstream"}
```
Workflow: run a scenario → ask Claude to analyze the sim data **without** the truth log →
compare. This measures detection sensitivity (e.g. smallest detectable leak).

## 6. Separation from real data
- Topic root `bfwp-sim`, device IDs `twin*`, database `well-sim.db`.
- Separate HiveMQ credential for the twin; it cannot publish to `bfwp/…`.
