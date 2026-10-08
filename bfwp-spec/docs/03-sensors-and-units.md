# 03 — Sensors and units

| Signal | Field | Unit | Range | Resolution | Source |
|---|---|---|---|---|---|
| Well pressure | `psi` | psi (gauge) | 0.0 – 100.0 | 0.1 | Pressure transducer near the pressure tank |
| Pump motor current | `amps` | A (RMS) | 0.0 – 512.0 | 0.1 | Clamp-on current transformer (CT) on one motor leg |
| Pump state | `pump` | 0/1 | — | — | Derived: `amps >= PUMP_ON_AMPS` (with hysteresis) |
| Cumulative flow | `gal_total` | gallons | 0 – 2^53 | 1 gal | Hydrawise flow meter, 1 pulse = 1 gallon |
| Flow rate | `gpm` | gal/min | 0.0 – 200.0 | 0.1 | Derived from pulse timing |

## Pressure
- Transducer range 0–100 psi. Values outside `[-2, 102]` are treated as a sensor fault
  (`sensor_fault`, field sent as `null`).
- Calibrate zero with the system depressurized; record offsets in firmware config.

## Amperage
- Contract range is 0–512 A, per the current sensor/ADC selection.
- **Open question:** typical well motors draw roughly 5–30 A running, with brief inrush
  spikes several times higher. Confirm whether 0–512 is the true amp range or a raw ADC
  count. The contract always carries **calibrated amps**; firmware may add `amps_raw`
  (optional) during calibration.
- RMS is computed over at least several AC cycles (≥ 100 ms window).

## Flow
- The Hydrawise flow meter emits one pulse per gallon. The ESP32 taps that signal through
  an **optocoupler / pulse splitter** so it cannot disturb the Hydrawise controller.
- `gal_total` is the source of truth. It never resets (persisted across reboots).
  Gallons over any interval = difference of `gal_total` values.
- `gpm` is computed from the interval between the last two pulses, decaying to 0 when no
  pulse arrives within `FLOW_TIMEOUT_S` (default 120 s). At 1 gal/pulse, low flows
  (< ~1 gpm) are coarse; leak analysis should use `gal_total` over long windows.

## Derived quantities used in analysis
| Quantity | Definition |
|---|---|
| Pump cycle | Interval from `pump_on` to `pump_off` |
| Cycle gallons | `gal_total(off) − gal_total(on)` |
| Idle flow | Gallons accumulated while `pump = 0` and no Hydrawise zone is running |
| Overnight decay | psi at window start − psi at window end, with pump off and no zone running |
| Zone signature | Mean psi, amps, gpm during the steady part of a zone run (skip first 30 s) |
