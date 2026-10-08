# Changelog

## Unreleased — 2026-10-08
- Project moved from five repos to a single `BFWP` monorepo; docs updated to refer to
  app folders. Spec versions are now tagged `spec-vX.Y`.
- **Contract (v1 draft, before first tag):**
  - Telemetry: new required `mode` (`active`/`idle`); optional `psi_v`, `amps_v` (sensor
    volts) replace `amps_raw`; `amps` bound changed from 0–512 to provisional 0–200 A.
  - Activity-based publishing cadence specified (active 1 s; idle 60 s grid +
    report-on-change; 2-minute hold); never time-of-day based.
  - `gpm` algorithm and 1 pulse = 1 gallon made explicit; 100 ms flow debounce.
  - New `health` message (`bfwp/<dev>/health`, schema, example, SQLite `health` table).
  - `sensor_fault`/`sensor_ok` accept `enclosure_temp`.
  - SQLite `readings`: `mode`, `psi_v`, `amps_v` columns.
  - New shared scenario `cadence_off_hours`; scenarios may assert `expect.cadence`.
- All unit conversion happens on the ESP32 (no downstream conversion).
- Firmware design rewritten for ESP-IDF on the ESP32-C6 Feather, reusing MWPSensors
  components; OTA moved to planned. New project-level `hardware.md`.

## v1.0-draft — 2026-10-07
- Initial architecture, message contract, sensor definitions, storage, MCP tools,
  digital twin and firmware design docs.
- JSON Schemas: telemetry, telemetry batch, event, status, sim command.
- Reference SQLite schema v1.
- First shared scenario: `overnight_leak`.
