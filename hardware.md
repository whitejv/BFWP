# Hardware — Bella Flora Water Project

Everything currently known about the well-house monitor hardware, what is still assumed,
and the open hardware questions. Status tags: **Known** (decided or confirmed), **Planned**
(intended, following the MWP home project), **Assumed** (working assumption — verify),
**Open** (see questions at the end).

Related: firmware design `bfwp-spec/docs/07-firmware-design.md`, signal definitions
`bfwp-spec/docs/03-sensors-and-units.md`.

## 1. Site

| Item | Detail | Status |
|---|---|---|
| Location | Well house serving the Bella Flora HOA irrigation system | Known |
| Network | Dedicated Wi-Fi access point in the well house, with internet access; **separate from and not near Jay's home network** — hence the cloud broker (HiveMQ Cloud) | Known |
| Wi-Fi band | ESP32-C6 is 2.4 GHz only (Wi-Fi 4/6), so the well-house AP must offer 2.4 GHz | Open (H1) |
| Water system | Well pump → pressure tank / pressure switch → irrigation mainline → Hydrawise-controlled zone valves | Assumed |
| Pump motor | Electric well pump motor; supply voltage, phase and running current not yet recorded | Open (H2) |
| Pressure switch | Cut-in / cut-out settings not yet recorded (twin assumes 40/60 psi) | Open (H3) |
| Pressure tank | Size and pre-charge not yet recorded (twin assumes 86 gal, 38 psi) | Open (H3) |
| Irrigation controller | Hydrawise controller, with the Hydrawise flow meter wired to it | Known |
| AC power in well house | Available outlet/circuit for a 5 V supply not yet confirmed | Open (H4) |

## 2. System block diagram

```
 SENSORS                       FRONT END                 CONTROLLER (in enclosure)
 Pressure transducer ───► divider / shunt ───► ADS1115 0x49 ──┐
   0–100 psi                                                  ├── I2C  SDA GPIO19 / SCL GPIO18
 Current sensor ────────► divider ───────────► ADS1015 0x48 ──┘          │
   0–5 V ∝ pump amps                                                    ▼
 Hydrawise flow meter ──► isolating input (opto) ─────── GPIO7 ──► Adafruit ESP32-C6 Feather
   1 pulse = 1 gal,                                                (ESP-IDF)
   shared with Hydrawise                                                │
 DS18B20 enclosure temp ──────────────────────────────── GPIO6 ──►      │
 Fan (optional) ◄── MOSFET ◄──────────────────────────── GPIO2 ◄──      │
 5 V supply ──► Feather + sensors                                       │
                                                                        ▼
                                          well-house Wi-Fi ──► HiveMQ Cloud (TLS)
```

## 3. Controller board

| Item | Detail | Status |
|---|---|---|
| Board | **Adafruit ESP32-C6 Feather** — same board as the MWP project | Planned |
| MCU | ESP32-C6: single-core RISC-V, 2.4 GHz Wi-Fi 6, Bluetooth LE | Known (for this board) |
| Flash | 4 MB assumed → partition plan: NVS, 2 × 1.5 MB OTA app slots, ~900 KB offline buffer | Assumed (H5) |
| Firmware | ESP-IDF v5.x, C | Known |
| I2C bus | SDA **GPIO19**, SCL **GPIO18**, STEMMA QT power enable **GPIO20** (driven by firmware), 4.7 kΩ pull-ups to 3.3 V | Planned (from MWP) |
| Power input | 5 V via USB-C or the Feather's 5 V pin | Planned |
| Battery | Feather has a LiPo charger; a small LiPo could carry the ESP32 through short outages (sensors would still lose 5 V) | Open (H4) |

### Pin map (proposed, follows MWP where possible)
| Function | GPIO | Feather pin | Notes |
|---|---|---|---|
| I2C SDA | 19 | D19 | Shared by both ADCs |
| I2C SCL | 18 | D18 | Shared by both ADCs |
| I2C power enable | 20 | — | STEMMA QT power; firmware drives HIGH |
| Flow pulse input | 7 | D7 | GPIO interrupt (timestamps) + PCNT cross-check; MWP "Flow Sensor 1" pin |
| One-Wire (enclosure temp) | 6 | D6/A2 | DS18B20, 4.7 kΩ pull-up |
| Fan control | 2 | D2/A5 | Through a MOSFET/transistor; optional |

## 4. Analog front end (pressure and current)

| Item | Detail | Status |
|---|---|---|
| Current ADC | **ADS1015** 12-bit, I2C **0x48**, gain 2/3 (±6.144 V FS, 3 mV/count) — same as MWP's pump-amperage channels | Planned |
| Pressure ADC | **ADS1115** 16-bit, I2C **0x49**, gain 2/3 (0.1875 mV/count) | Planned |
| ADC supply | 3.3 V in MWP's wiring guide | Planned — see input-limit note |
| Sample rate | Every 100 ms (firmware sampler) | Planned |

**Input-voltage limit (important).** An ADS1x15 analog input must stay within its supply
voltage + 0.3 V, regardless of the gain setting. With the ADCs powered at 3.3 V, a 0–5 V
sensor output must be scaled down — e.g. a 10 kΩ / 15 kΩ divider (×0.6: 5 V → 3.0 V). The
divider ratio is entered as a calibration constant so readings are still reported in sensor
volts and engineering units. Verify how MWP is actually wired before copying it (H7).

### Pressure transducer
| Item | Detail | Status |
|---|---|---|
| Range | 0–100 psi (gauge) | Known |
| Output | 0.5–4.5 V ratiometric, 0–5 V, or 4–20 mA — **not yet chosen** (MWP's notes include 4–20 mA references) | Open (H6) |
| Supply | 5 V (voltage types) or 12–24 V loop (4–20 mA) | Depends on H6 |
| If 4–20 mA | 150 Ω shunt → 0.6–3.0 V, fits a 3.3 V ADC with no divider; robust over long cable runs | Option |
| If 0.5–4.5 V ratiometric | Output scales with the 5 V supply — use a well-regulated 5 V, or measure the supply on a spare ADC channel and correct | Option |
| Mounting | On a tee near the pressure tank, ideally with an isolation ball valve and a pressure snubber; 1/4" NPT typical | Assumed (H8) |
| Calibration | Zero with system depressurized; check against a mechanical gauge at two or more pressures | Planned |

### Current sensor
| Item | Detail | Status |
|---|---|---|
| Method | **Same as MWP**: a current sensor whose output voltage (0–5 V) is proportional to pump-motor current, read by the ADS1015; converted to amps on the ESP32 | Known |
| "0–512" | Earlier figure was a misremembered raw encoding, not an amp range. MWP sends volts; its Raspberry Pi converts to amps. In BFWP the ESP32 converts | Resolved |
| Volts → amps factor | Same factor the MWP Pi code uses — not yet located | Open (H9) |
| Sensor model / output type | Model unknown; whether it outputs DC proportional to RMS (most 0–5 V transducers) or AC (needs RMS in firmware) | Open (H9) |
| Mounting | Split-core around one motor conductor; panel-side work by an electrician | Planned |
| Calibration | Compare with a clamp meter while the pump runs | Planned |

## 5. Flow meter input

| Item | Detail | Status |
|---|---|---|
| Meter | The **Hydrawise flow meter** already installed with the Hydrawise controller | Known |
| Output | **1 pulse per gallon** — counting pulses = counting gallons | Known |
| Reported | `gal_total` (raw gallons, cumulative) and `gpm` (from time between pulses) | Known |
| Model / electrical type | Meter model, and whether the pulse is a dry contact (reed switch) or a powered sensor output | Open (H10) |
| Shared signal | Must be tapped without disturbing the Hydrawise controller's reading → isolating input (optocoupler) or a commercial pulse splitter; exact circuit depends on H10 | Planned / Open (H11) |
| Debounce | Firmware ignores pulses < 100 ms apart (reed-switch bounce); hardware RC filter optional | Planned |
| Location | Where the meter sits (in the well house? after the pressure tank, on the mainline?) and the cable run to the ESP32 | Open (H12) |
| Calibration | Compare `gal_total` deltas with Hydrawise's own flow totals | Planned |

## 6. Enclosure, environment, power

| Item | Detail | Status |
|---|---|---|
| Enclosure temperature | DS18B20 on One-Wire (GPIO6), reported in `health` as `enclosure_f` | Planned (from MWP) |
| Fan | Optional, GPIO2 via MOSFET, temperature-threshold control (MWP uses 70 °F) | Open (H13) |
| Enclosure | Weatherproof (NEMA 4X-type) box, cable glands, mounted away from splash/condensation | Assumed |
| Wiring practice | Keep sensor and pulse wiring away from motor leads; shielded cable for longer analog runs | Planned |
| Power supply | 5 V regulated supply from a well-house outlet; enough for Feather + sensors (≈ 0.5 A budget) | Assumed (H4) |
| Outage behavior | Device publishes a `boot` event with `reset_reason` after power returns; data during the outage is not captured | Known (firmware) |

## 7. Safety
- The pump circuit is likely 240 V. Installing the current sensor at the panel/motor leads
  should be done by a licensed electrician with power off.
- Plumbing work (pressure-transducer tee) with the system depressurized and the pump breaker
  off.
- Low-voltage side (ESP32, ADCs, sensors) is isolated from mains: the current sensor is
  non-contact, and the flow input is opto-isolated.

## 8. Draft bill of materials
| Qty | Item | Status |
|---|---|---|
| 1 | Adafruit ESP32-C6 Feather | Planned |
| 1 | ADS1015 breakout (0x48) | Planned |
| 1 | ADS1115 breakout (0x49) | Planned |
| 1 | Pressure transducer, 0–100 psi (output type per H6) | Open |
| 1 | Current sensor, 0–5 V output (same type as MWP) | Open (H9) |
| 1 | Pulse isolator: optocoupler circuit or commercial pulse splitter | Open (H11) |
| 1 | DS18B20 temperature probe + 4.7 kΩ resistor | Planned |
| — | Divider resistors (or 150 Ω shunt for 4–20 mA), 4.7 kΩ I2C pull-ups | Planned |
| 1 | 5 V regulated power supply | Planned |
| 1 | Weatherproof enclosure, glands, terminal blocks | Planned |
| 0–1 | Small fan + MOSFET | Optional |
| 0–1 | LiPo battery for the Feather | Optional |
| 1 | Tee, isolation valve, snubber for the transducer | Assumed |

## 9. Outstanding hardware questions

| # | Question | Why it matters |
|---|---|---|
| H1 | Does the well-house access point offer **2.4 GHz** Wi-Fi, and what is the signal strength at the enclosure location? | ESP32-C6 is 2.4 GHz only; weak signal → frequent buffering |
| H2 | Pump motor: supply voltage (120/240 V), single or three phase, horsepower, nameplate full-load amps? | Current-sensor range, `PUMP_ON_AMPS`, `AMPS_HIGH` defaults, schema `amps` bound |
| H3 | Pressure switch cut-in/cut-out settings; pressure tank size and pre-charge? | Twin model, `PSI_LOW`/`PSI_HIGH`, decay analysis |
| H4 | Is a power outlet available in the well house? Is a battery/UPS wanted to ride through short outages? | Power design |
| H5 | Confirm the Feather's flash size (assumed 4 MB). | Partition plan: OTA slots + offline buffer capacity |
| H6 | Pressure transducer output type: 0.5–4.5 V ratiometric, 0–5 V, or 4–20 mA? Specific model? | Front-end circuit (divider vs shunt), calibration constants |
| H7 | How are MWP's 0–5 V sensors wired to the ADS1x15s — ADC powered at 3.3 V or 5 V, and is there a divider? | ADC input limit; copy a proven, safe design |
| H8 | Plumbing access for the transducer: existing gauge port or new tee near the tank? Thread size? | Installation |
| H9 | Current sensor model used in MWP, its output type (DC ∝ RMS vs AC), and the volts→amps factor in the MWP Pi code | Calibration `scale`, firmware RMS handling |
| H10 | Hydrawise flow meter model and pulse electrical type (dry contact/reed vs powered output; voltage)? | Isolation circuit, debounce |
| H11 | Optocoupler circuit vs commercial pulse splitter for sharing the meter signal with the Hydrawise controller — and confirm the controller's reading isn't affected | Must not disturb the Hydrawise flow readings |
| H12 | Where is the flow meter (well house? after the pressure tank?) and how far is it from the enclosure? | Cable run; leak-location logic (upstream vs downstream of the meter) |
| H13 | Does the enclosure need a fan (well-house summer temperatures)? | Thermal design; optional parts |
