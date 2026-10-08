# 03 — Sensors and units

All conversion to engineering units happens **on the ESP32**. (In the MWP home project a
Raspberry Pi converts raw volts downstream; BFWP has no such step.) Hardware details and open
hardware questions: [`../../hardware.md`](../../hardware.md).

| Signal | Field | Unit | Range | Resolution | Source |
|---|---|---|---|---|---|
| Well pressure | `psi` | psi (gauge) | 0.0 – 100.0 | 0.1 | 0–100 psi pressure transducer near the pressure tank, read by an ADS1x15 ADC |
| Pump motor current | `amps` | A (RMS) | 0.0 – 200.0 (provisional) | 0.1 | Current sensor with a 0–5 V output proportional to current — **same method as MWP** — read by an ADS1015 ADC |
| Pump state | `pump` | 0/1 | — | — | Derived: `amps ≥ PUMP_ON_AMPS` (with hysteresis) |
| Cumulative flow | `gal_total` | gallons | 0 – 2^53 | 1 gal | Hydrawise flow meter, **1 pulse = 1 gallon** |
| Flow rate | `gpm` | gal/min | 0.0 – 200.0 | 0.1 | Derived from the time between pulses |
| Enclosure temp | `enclosure_f` (health) | °F | −40 – 185 | 0.1 | DS18B20 One-Wire sensor inside the enclosure |
| Raw sensor volts | `psi_v`, `amps_v` (optional) | V | 0 – 5 (sensor side) | 0.001 | Same ADC readings, before conversion |

## Conversion on the device
Each analog channel is converted with a linear calibration stored in flash (NVS):

```
volts_at_sensor = adc_volts × divider_ratio          (divider_ratio = 1 if no divider)
value           = (volts_at_sensor − offset_v) × scale
```
| Channel | Default `offset_v` | Default `scale` | Notes |
|---|---|---|---|
| Pressure (0.5–4.5 V transducer) | 0.5 V | 25 psi/V | 0.5 V = 0 psi, 4.5 V = 100 psi. Use 0 V / 20 psi/V for a 0–5 V sensor. Confirm sensor type. |
| Current | 0 V | TBD A/V | From the current sensor's spec — same factor as the MWP Pi conversion. **Open.** |

- Constants are changed without reflashing (via OTA config or a provisioning command); every
  change gets a new `calib_id`, reported in `health`.
- Out-of-range readings (pressure outside [−2, 102] psi, ADC railed, sensor-open) for 3
  consecutive samples → `sensor_fault`, and the field is sent as `null` until `sensor_ok`.

## Pressure
- Range 0–100 psi. Calibrate zero with the system depressurized; record the offset in the
  calibration constants.

## Amperage
- Measured exactly as in MWP: the current sensor outputs a voltage proportional to motor
  current (0–5 V), read by an ADS1015 (12-bit, gain 2/3 → ±6.144 V full scale, 3 mV/count;
  0–5 V ≈ 0–1,666 counts). The earlier "0–512" figure was a misremembered raw encoding, not
  an amp range — the contract carries amps.
- The ESP32 computes RMS-equivalent amps from the sensor output. If the sensor already
  outputs a DC level proportional to RMS current (typical for 0–5 V current transducers), the
  firmware simply averages; if it outputs AC, the firmware computes RMS over ≥ 100 ms.
  **Which one depends on the sensor — open question.**
- Typical well motors run roughly 5–30 A with brief start-up spikes several times higher; the
  provisional 0–200 A schema bound is a sanity limit, tightened once the sensor is known.

## Flow (gallons and gallons per minute)
The Hydrawise flow meter emits **one pulse per gallon**, so counting pulses *is* counting
gallons. Two values are reported:

1. **`gal_total` (raw gallons)** — the cumulative pulse count. Persisted across reboots,
   never reset. Gallons over any interval = difference of `gal_total` values, exact even if
   messages are lost.
2. **`gpm` (gallons per minute)** — at 1 gal/pulse a 12 gpm flow gives a pulse only every 5 s,
   so counting pulses per 1 s reading would bounce between 0 and 12. Instead:
   - Timestamp every pulse (µs) as it arrives.
   - `gpm = 60 / (seconds between the last two pulses)`.
   - If the time since the last pulse already exceeds the last interval, report
     `gpm = 60 / (seconds since last pulse)` — so the rate falls smoothly when flow stops
     instead of holding its last value.
   - After `FLOW_TIMEOUT_S` (120 s) with no pulse, `gpm = 0`.
   - Very low flows (< ~0.5 gpm) are coarse by nature; leak analysis uses `gal_total` over
     long windows instead.
- **Debounce:** ignore pulses within `FLOW_DEBOUNCE_MS` (100 ms) of the previous one. Even at
  100 gpm pulses are 600 ms apart; this rejects reed-switch contact bounce.
- The meter's signal is shared with the Hydrawise controller, so the ESP32 taps it through an
  **isolating input** (optocoupler / pulse splitter) — see `hardware.md`.

## Derived quantities used in analysis
| Quantity | Definition |
|---|---|
| Pump cycle | Interval from `pump_on` to `pump_off` |
| Cycle gallons | `gal_total(off) − gal_total(on)` |
| Idle flow | Gallons accumulated while no Hydrawise zone is running |
| Overnight decay | psi at window start − psi at window end, with pump off and no zone running |
| Zone signature | Mean psi, amps, gpm during the steady part of a zone run (skip first 30 s) |
