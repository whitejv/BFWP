# 07 — Firmware design (ESP32)

Hardware choices are **draft**; the event rules section is **contract** (shared with the twin).

## Hardware (draft)
| Function | Candidate | Notes |
|---|---|---|
| MCU | ESP32 dev board (e.g. ESP32-DevKitC) | Wi-Fi to the well-house AP |
| Pressure | 0–100 psi transducer, 0.5–4.5 V or 4–20 mA | 5 V sensor output exceeds the ESP32's 3.3 V ADC — use a divider or, better, an **ADS1115** external ADC (ESP32's built-in ADC is non-linear) |
| Current | Clamp-on CT on one motor leg + burden resistor, or a voltage-output CT | Non-invasive; RMS computed in firmware. Panel-side work by an electrician (240 V). |
| Flow | Tap of the Hydrawise meter's pulse line | **Optocoupler / pulse splitter** so the Hydrawise controller's signal isn't loaded. Count with the ESP32 PCNT peripheral, debounced. |
| Storage | On-chip flash (LittleFS + NVS) | Offline ring buffer; seq and `gal_total` persistence |
| Power | 5 V supply in the well house; optional small UPS | A `boot` event after outages records `reset_reason` |
| Enclosure | Weatherproof box, cable glands | Keep transducer wiring away from motor leads |

## Software structure
```
src/
  main.cpp            wiring only
  hal/                sensor + network drivers (hardware-specific)
  core/               pure logic, compiles under env:native
    sampler           cadence (1 s active / 60 s idle)
    events            event rules (below)
    seq_store         seq persistence (NVS every 100, +100 on boot)
    buffer            offline ring buffer, batch builder (≤100 items)
    message           JSON building per spec v1
```
`core/` has unit tests run on the Mac (`pio test -e native`), using the shared scenarios.

## Time
- Connect Wi-Fi → NTP sync → only then publish. Readings before the first sync are discarded.
- Re-sync every 6 h. If sync is lost, keep the RTC running (ESP32 drift is small over hours).

## Seq and counters
- `seq`: NVS-saved every 100 messages; on boot `seq = saved + 100`.
- `gal_total`: NVS-saved every 10 gallons and on `pump_off`; on boot restore. Up to ~10 gal
  may be lost on a power cut — acceptable; noted as a known limitation.

## Offline buffering
- Ring buffer in LittleFS; target ≥ 24 h of idle-rate data plus ~2 h of active data.
- On reconnect: flush oldest-first as telemetry **batches** (≤100 items), events individually,
  throttled so live data still flows.
- If the buffer overflows: drop oldest, emit `buffer_overflow`.

## Event rules (CONTRACT — twin must match)
Defaults (configurable):

| Constant | Default |
|---|---|
| `PUMP_ON_AMPS` / `PUMP_OFF_AMPS` | 3.0 / 2.0 A (hysteresis) |
| `FLOW_TIMEOUT_S` | 120 |
| `FLOW_IDLE_WINDOW_S` | 600 |
| `DECAY_PSI` / `DECAY_WINDOW_S` | 5.0 psi / 3600 s |
| `PSI_LOW` / `PSI_HIGH` | 30 / 75 psi, sustained 10 s |
| `AMPS_HIGH` | 1.3 × running baseline (or fixed 28 A until baseline exists), sustained 5 s |
| `SHORT_CYCLE_N` / window | 6 cycles / 600 s |

Rules:
1. **pump_on** when amps ≥ `PUMP_ON_AMPS` for 2 consecutive samples (sampling at 1 Hz
   once active). **pump_off** when amps < `PUMP_OFF_AMPS` for 2 samples; includes the cycle
   summary. Ignore the first 1 s after pump_on for `amps_max` alarm purposes (inrush).
2. **flow_idle**: while pump is off, accumulate pulses; at the end of each
   `FLOW_IDLE_WINDOW_S` with ≥ 1 gallon, emit one event with the window total.
3. **psi_decay**: while pump is off **and** no pulses, track psi; if it drops ≥ `DECAY_PSI`
   within `DECAY_WINDOW_S`, emit once, then re-arm after the next pump cycle.
4. **psi_low / psi_high / amps_high**: emit when the condition holds for its duration; do not
   re-emit until the value has returned inside the limit for 60 s.
5. **short_cycle**: on each pump_on, count pump_on events in the trailing window; emit when
   ≥ N, then not again for one window.
6. **sensor_fault** when a reading is out of range (`psi` outside [-2, 102], ADC railed, CT
   open) for 3 samples; the field is sent as `null` until **sensor_ok**.
7. **boot** once per start after time sync.

## Not in v1
- Inbound commands / OTA updates to the device (consider OTA in v2, with signed images).
