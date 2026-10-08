# 07 — Firmware design (ESP32-C6, ESP-IDF)

Status: **draft**. The sections marked **CONTRACT** (publishing cadence, event rules) are
shared behavior — the digital twin must implement them identically. Hardware facts and open
hardware questions live in [`../../hardware.md`](../../hardware.md).

## Platform
| Item | Choice |
|---|---|
| Framework | **ESP-IDF v5.x** (FreeRTOS), C; C++ only where a reused component needs it (ADS1x15 driver) |
| Board | Adafruit ESP32-C6 Feather (same as MWP) — proposed, see hardware.md |
| Build | `idf.py build / flash / monitor` from Cursor's terminal |
| Starting point | Components from the MWPSensors project (below) |

## Reuse from MWPSensors
| MWP component | BFWP use | Changes for BFWP |
|---|---|---|
| `i2c_manager` | Shared I2C bus (SDA GPIO19, SCL GPIO18, STEMMA power GPIO20) | none expected |
| `i2c_adc_manager` (espp ADS1x15, retries + backoff) | ADS1015 → current, ADS1115 → pressure | 100 ms sampling for the channels we use; apply calibration on device; output engineering units |
| `pcnt_flow_manager` | Hardware pulse counter as a **cross-check** of the gallon count | single channel; primary counting moves to a timestamped GPIO interrupt (needed for `gpm`) |
| `onewire_temp_manager` | Enclosure temperature (DS18B20) | one sensor; reported in `health` |
| Fan control (GPIO2, threshold) | Optional enclosure fan | threshold configurable |
| `wifi_manager` | Auto-connect + reconnect | count reconnects for `health` |
| `mqtt_manager` / `mqtt_publisher` | MQTT client, snapshot-then-publish | **TLS to HiveMQ Cloud**, username/password, Last Will, QoS 1, JSON v1 contract; drop the binary struct |
| `watchdog` | Per-task registration + heartbeats | count timeouts for `health` |
| `panic_stats` | Reset reason / crash tracking | feeds `boot.reset_reason` and `health.reset_reason` |
| `error_recovery` | Recovery strategies per error | add MQTT/TLS and buffer-full strategies |
| `task_monitor` + production gate | Runtime stats in development | compiled out of production builds |
| SNTP plan (`FUTURE_UPGRADES.md`) | Time sync | required in BFWP (timestamps) |
| OTA guide (`OTA_IMPLEMENTATION_GUIDE.md`) | Remote updates | secured for a public broker (see §OTA) |

**Not carried over:** the 104-byte `genericSens_` binary struct, QoS 2 binary + QoS 0 JSON
dual publishing, `cycle_count`, plain-text local broker on port 1883, raw-volt output with
downstream conversion.

## Project layout
```
bfwp-firmware/
  CMakeLists.txt             ESP-IDF project
  sdkconfig.defaults         committed defaults (sdkconfig itself is generated, not committed)
  partitions.csv             nvs · otadata · ota_0 · ota_1 · storage (offline buffer)
  main/
    main.c                   wiring/startup only
    secrets.example.h        template → copy to secrets.h (gitignored)
  components/
    bfwp_core/               PURE LOGIC — no ESP-IDF calls; host-testable
      calib       volts → psi / amps (linear, constants from settings)
      flow        pulse timestamps → gal_total, gpm, debounce
      cadence     active / idle / report-on-change decision
      events      event rules (below)
      seq_store   seq + gal_total persistence policy
      buffer      offline record ring + batch builder (≤ 100 items)
      message     JSON v1 builders
    bfwp_hal/                hardware + network (ESP-IDF)
      adc, flow_input (GPIO ISR + PCNT), onewire, fan, wifi, mqtt, nvs_settings, storage, ota
```
`bfwp_core` is unit-tested on the Mac (ESP-IDF `linux` target, or plain CMake + Unity) and
run against the shared scenarios in `bfwp-spec/contracts/scenarios/`.

## Tasks (FreeRTOS)
| Task | Period | Priority | Does |
|---|---|---|---|
| Flow ISR | per pulse | ISR | Timestamp pulse (`esp_timer_get_time`), debounce, increment count |
| Sampler | 100 ms | high | Read ADC channels, convert to psi/amps, update flow-derived gpm, run event rules + cadence |
| Publisher | 1 s tick | medium | Snapshot-then-publish: copy state under mutex, publish outside it if cadence says so; else enqueue to buffer when offline |
| Buffer flush | when connected | low | Send buffered records oldest-first as batches, throttled so live data still flows |
| Health | 300 s | low | Build and publish `health` |
| Temperature | 5 s | background | DS18B20 read, fan control |
| Wi-Fi / MQTT / SNTP | event-driven | medium | Connect, reconnect, time sync |

All tasks register with the watchdog (MWP pattern).

## Analog inputs and calibration
- **Current:** ADS1015 (0x48), gain 2/3 (±6.144 V FS, 3 mV/count), same sensor approach as MWP.
- **Pressure:** ADS1115 (0x49), gain 2/3 (0.1875 mV/count).
- **Input voltage limit:** an ADS1x15 input must not exceed its supply + 0.3 V. With the ADC
  powered at 3.3 V (as in MWP's wiring guide), 0–5 V sensor outputs need a resistor divider
  (e.g. 10 kΩ / 15 kΩ → ×0.6, 5 V → 3.0 V). The divider ratio is a calibration constant, and
  `psi_v`/`amps_v` are reported at the sensor side. **Verify against MWP's actual wiring.**
- Conversion: `value = (adc_volts × divider_ratio − offset_v) × scale` (see 03-sensors-and-units).
- Calibration constants and thresholds live in **NVS** (`nvs_settings`), with compiled-in
  defaults. Each set has a `calib_id`, reported in `health`. Changeable without reflashing
  (OTA config, later a provisioning command).

## Flow input
- The meter's pulse line is shared with the Hydrawise controller → isolated input
  (optocoupler); the ESP32 sees a clean logic-level pulse per gallon.
- **Primary:** GPIO interrupt timestamps each pulse; pulses within `FLOW_DEBOUNCE_MS` of the
  previous are ignored. `gpm` per 03-sensors-and-units.
- **Cross-check:** PCNT unit (MWP component) counts the same edges with a glitch filter; a
  persistent mismatch raises `sensor_fault` (`flow`, reason `noisy`).

## Time
- SNTP after Wi-Fi connects (`pool.ntp.org`, `time.nist.gov`); re-sync hourly.
- **No publishing before the first sync**; readings before then are discarded.
- If sync is later lost, keep the RTC running and keep publishing.

## Seq and counters
- `seq`: NVS-saved every 100 messages; on boot `seq = saved + 100`. Never reused.
- `gal_total`: NVS-saved every 10 gallons and on `pump_off`; restored on boot. Up to ~10 gal
  can be lost on a power cut — accepted limitation.

## MQTT
- ESP-IDF `esp-mqtt`, `mqtts://` port 8883, server verified with the ESP-IDF certificate
  bundle; username/password from `main/secrets.h`.
- Fixed client ID `bfwp-<dev>`, keepalive 60 s, QoS 1 for everything.
- Last Will on `bfwp/<dev>/status`: `{"dev":"<dev>","online":false}` (retained); on connect
  publish retained `online:true` status.

## Offline buffering
- `storage` partition (LittleFS or a raw ring) holding compact binary records; converted to
  JSON only when flushed.
- Target capacity ≥ 24 h of idle data + ≥ 2 h of active data (≈ 9,000 records).
- Flush oldest-first as telemetry batches (≤ 100 items); events individually; `health` is not
  buffered.
- Overflow: drop oldest, emit `buffer_overflow`.

## Publishing cadence (CONTRACT)
The sampler runs every `SAMPLE_MS`; only publishing is throttled.

- Enter **active** (publish every 1 s) on any of: `amps ≥ PUMP_ON_AMPS`; a flow pulse;
  |Δpsi| ≥ `FAST_DPSI` within 10 s; any event.
- Return to **idle** when pump off, no flow pulse, and |Δpsi| < `FAST_DPSI` have all held for
  `IDLE_HOLD_S`.
- **Idle:** publish on a fixed 60 s grid, plus an extra reading whenever psi differs from the
  last published reading by ≥ `IDLE_DPSI` (grid not shifted).
- Events publish immediately in either mode. Every telemetry message carries `mode`.

## Event rules (CONTRACT — twin must match)
| Constant | Default |
|---|---|
| `SAMPLE_MS` | 100 |
| `PUMP_ON_AMPS` / `PUMP_OFF_AMPS` | 3.0 / 2.0 A (hysteresis) — tune once the motor's running current is known |
| `FAST_DPSI` / `IDLE_DPSI` / `IDLE_HOLD_S` | 2.0 psi (in 10 s) / 1.0 psi / 120 s |
| `FLOW_DEBOUNCE_MS` / `FLOW_TIMEOUT_S` | 100 / 120 |
| `FLOW_IDLE_WINDOW_S` | 600 |
| `DECAY_PSI` / `DECAY_WINDOW_S` | 5.0 psi / 3600 s |
| `PSI_LOW` / `PSI_HIGH` | 30 / 75 psi, sustained 10 s |
| `AMPS_HIGH` | 1.3 × running baseline (fixed 28 A until a baseline exists), sustained 5 s |
| `SHORT_CYCLE_N` / window | 6 cycles / 600 s |
| `HEALTH_INTERVAL_S` | 300 |

1. **pump_on** when amps ≥ `PUMP_ON_AMPS` for 2 consecutive samples; **pump_off** when
   amps < `PUMP_OFF_AMPS` for 2 samples, with the cycle summary. Ignore the first 1 s after
   pump_on for `amps_high` (start-up inrush).
2. **flow_idle**: while the pump is off, accumulate gallons; at the end of each
   `FLOW_IDLE_WINDOW_S` with ≥ 1 gallon, emit one event with the window total.
3. **psi_decay**: while the pump is off **and** no pulses, track psi; if it falls ≥
   `DECAY_PSI` within `DECAY_WINDOW_S`, emit once, then re-arm after the next pump cycle.
4. **psi_low / psi_high / amps_high**: emit when the condition holds for its duration; do not
   re-emit until the value has been back inside the limit for 60 s.
5. **short_cycle**: on each pump_on, count pump_on events in the trailing window; emit when
   ≥ N, then not again for one window.
6. **sensor_fault** when a reading is out of range (psi outside [−2, 102], ADC railed or not
   responding, temperature sensor missing) for 3 samples; the field is `null` until
   **sensor_ok**.
7. **boot** once per start, after time sync.

## Health
Every `HEALTH_INTERVAL_S` and right after `boot`: uptime, reset reason, heap, RSSI, Wi-Fi
reconnects, MQTT publish ok/fail, buffer fill, watchdog timeouts, detected I2C devices,
enclosure °F, fan, `calib_id` (contract: `health.schema.json`).

## OTA (planned)
The well house is remote, so OTA moves from "later" to planned, based on MWP's
`OTA_IMPLEMENTATION_GUIDE.md` (HTTP(S) OTA, dual app partitions, rollback):
- Device **pulls** the image over HTTPS from a URL; it never accepts code over MQTT.
- Trigger via a dedicated topic (e.g. `bfwp/<dev>/ota`) that only a separate admin credential
  can publish to — **adds a topic to the contract (v1.1); not yet specified.**
- Image signature verification (ESP-IDF secure boot v2 / signed app images) and automatic
  rollback if the new image doesn't confirm itself healthy.
- Same mechanism can deliver calibration/threshold updates.

## Secrets
`main/secrets.h` (gitignored) holds Wi-Fi SSID/password and HiveMQ host/username/password;
`main/secrets.example.h` is the committed template. (Unlike MWP, credentials are never in
`config.h`.)

## Human verification after each firmware change
Claude can build and run host tests but cannot test hardware. Each change ends with a list of
on-device checks (serial log, MQTT messages in HiveMQ's web client, sensor readings vs. a
gauge/clamp meter).
