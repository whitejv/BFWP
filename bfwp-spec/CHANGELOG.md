# Changelog

## Unreleased — 2026-10-15
- MWPSensors reuse note: share the sensor drivers through a reading callback, and add
  SNTP, a never-reused sequence, a short offline ring, and Last Will back to MWPSensors
  on its JSON topic only. See `docs/09-mwpsensors-reuse.md`.
- The well MCP covers the well monitor only. Dropped `zone_runs` and the tools that
  joined it (`get_unscheduled_pump_runs`, `get_zone_signature`,
  `compare_zone_signatures`, `sync_zone_runs`). `get_pump_cycles` returns pump runs.
  `get_flow_totals` returns gallons per day. Claude fuses those results with a separate
  Hydrawise MCP when a question needs zone times. Applying the schema drops `zone_runs`
  if a draft database still has it.

## Unreleased — 2026-10-08
- `cadence_off_hours`: upstream leak is 1 gpm and the run ends at 06:02, so pressure
  moves about 1 psi per minute (an idle report-on-change fits between 60 s reports)
  without a `psi_decay` or another pump start. `pump_on` is expected by 05:16, which
  is when a 4 gpm zone draws the 86 gal tank from 60 psi to 40 psi. Active mode is
  required from 05:11, after the first gallon pulse. Idle is required from 05:28
  until 05:30, when a `flow_idle` event returns the device to active.
- Development order is one element at a time, with the twin standing in for the ESP32
  until hardware exists. See `docs/08-dev-workflow.md`.
- Host rebuild is a root CMake project (`cmake -S . -B build`). Ingest on the Mac mini is
  supervised by launchd (`com.bfwp.ingest`); `bfwp-start.sh` / `bfwp-stop.sh` load and
  unload it. See `docs/01-architecture.md` and `docs/08-dev-workflow.md`.
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
