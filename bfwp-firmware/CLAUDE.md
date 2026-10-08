# CLAUDE.md — bfwp-firmware

## What this is
ESP-IDF (v5.x, C) firmware for the BFWP well-house monitor on an ESP32-C6
(Adafruit ESP32-C6 Feather, as in MWPSensors).

## Contract
- Targets **spec v1** (draft; will be tagged `spec-v1.0`).
- Messages, topics and shared scenarios: `../bfwp-spec/contracts/`.
  Do not change formats here; report contract problems instead.
- Publishing cadence and event rules must match `../bfwp-spec/docs/07-firmware-design.md`
  (shared with the twin). Hardware facts: `../hardware.md`.

## Rules
- Keep logic in `components/bfwp_core` free of ESP-IDF calls so it builds and is unit-tested
  on the Mac; hardware/network code goes in `components/bfwp_hal`.
- Reuse MWPSensors components where the design doc's reuse table says so, adapting them —
  don't copy the binary `genericSens_` struct or plain-text MQTT.
- All unit conversion happens on the device; calibration constants live in NVS with defaults.
- Never publish before SNTP time sync; `ts` is UTC epoch ms.
- `seq` persisted in NVS every 100 messages; jump +100 on boot. Never reuse a seq.
- Publish under `bfwp/<dev>/...` only, over TLS. Credentials only in `main/secrets.h` (gitignored).
- Claude cannot test hardware: keep a simulated-sensor build option, and list what the human
  must verify on the device after each change.

## Commands
- `idf.py set-target esp32c6` · `idf.py build` · `idf.py flash monitor`
- Host tests for `bfwp_core`: to be set up (ESP-IDF linux target or CMake + Unity).

## Work style
Follow the project-wide rules in `../CLAUDE.md`: change files only in this folder, commit
with the `firmware:` prefix, branch as `firmware/<topic>`, and summarize changes for review.
