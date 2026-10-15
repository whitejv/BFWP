# 01 — Architecture

## Goal
Give Claude (and the Landscape Committee) the signals the well monitor measures: **well
pressure, pump motor current, and flow**, with device timestamps in SQLite. This MCP
covers the well monitor only. Zone schedules and controller status belong to a separate
Hydrawise MCP. When a question needs both, Claude fuses the two results.

## Data flow
```
 Well house                         Cloud                    Mac mini (home)
┌──────────────────┐   TLS 8883   ┌─────────────┐  TLS   ┌──────────────────────────┐
│ ESP32-C6 (well1) │ ───────────► │ HiveMQ      │ ─────► │ bfwp-ingest (launchd)    │
│  psi · amps ·    │  bfwp/well1/…│ Cloud       │        │   validate → SQLite (WAL)│
│  flow pulses     │              │ (broker)    │        │   rollups · pump cycles  │
└──────────────────┘              │             │        └────────────┬─────────────┘
┌──────────────────┐              │             │                     │ read-only
│ bfwp-twin (Mac)  │ ───────────► │             │                     │
│  simulated twin1 │ bfwp-sim/…   └─────────────┘        ┌────────────▼─────────────┐
└──────────────────┘                                     │ bfwp-mcp  → Claude       │
                                                         │ well monitor only        │
                                                         └──────────────────────────┘
```
Claude may also talk to a Hydrawise MCP. That server is not part of this repo, and
`bfwp-mcp` does not call it.

The well-house Wi-Fi is isolated from the home network, so a cloud broker is the
rendezvous point. Neither side needs inbound ports.

## Mac mini supervisor
launchd runs ingest as a user agent, `com.bfwp.ingest`, loaded at login for the account
that stays logged in on the Mac mini. `KeepAlive` restarts the process if it exits.
`bfwp-start.sh` and `bfwp-stop.sh` at the repo root load and unload that agent. The plist
template is `bfwp-ingest/launchd/com.bfwp.ingest.plist.example`; the start script writes
the filled-in copy to `~/Library/LaunchAgents/`. Logs are `~/BFWP-data/logs/ingest.log`.

The twin is a dev tool and is started by hand. Cursor starts the MCP server over stdio.

## Components and ownership
All components live in one git repo (`BFWP`), one folder each.

| Component | Folder | Writes | Reads |
|---|---|---|---|
| Contracts & design | `bfwp-spec` | — | — |
| Device | `bfwp-firmware` | MQTT `bfwp/<dev>/…` | sensors |
| Digital twin | `bfwp-twin` | MQTT `bfwp-sim/<dev>/…`, truth log | scenarios, `…/cmd` |
| Ingest | `bfwp-ingest` | `well.db`, `well-sim.db` (**sole writer, owns schema**) | MQTT |
| Query server | `bfwp-mcp` | nothing | databases (read-only). Well monitor only. |

## Key design decisions
1. **All unit conversion on the ESP32** (ESP-IDF firmware); messages carry engineering units.
   Calibration constants live on the device. Hardware: `../../hardware.md`.
2. **Activity-based publishing cadence** — 1 s while water/pump activity is seen, 60 s plus
   report-on-change when idle; never time-of-day based.
3. **Device timestamps, UTC epoch ms**, after NTP sync. Receive time is stored separately
   and never used for analysis.
4. **`seq` per device, never reused** (persisted in flash). `(dev, seq)` is the idempotency
   key, so duplicates (QoS 1) and late buffered batches are harmless.
5. **Cumulative flow counter (`gal_total`)**, so gallons between any two readings are exact
   even when messages are lost.
6. **Persistent MQTT session** for ingest (fixed client ID, clean session off, QoS 1) plus
   **device-side flash buffering**, so neither a sleeping Mac nor a Wi-Fi outage loses data.
7. **SQLite on local disk**, WAL mode, nightly `.backup` to a synced folder.
8. **Sim data is physically separate**: different topic root and different database file.
9. **MCP tools are question-shaped** (pump cycles, overnight decay, flow totals), not raw
   dumps, and downsample long ranges. They do not join Hydrawise zone runs.

## Security
- TLS to HiveMQ always (port 8883).
- Separate credentials per client: `bfwp-well1` (publish `bfwp/well1/#`),
  `bfwp-twin` (publish `bfwp-sim/#`, subscribe `bfwp-sim/+/cmd`),
  `bfwp-ingest` (subscribe `bfwp/#`, `bfwp-sim/#`). Restrict by topic if the HiveMQ plan
  allows (see open questions).
- No credentials in git: `.env` / `bfwp-firmware/main/secrets.h` are gitignored; `*.example` files
  are committed.
- The device accepts **no** inbound telemetry commands in v1 (only the twin has a `cmd`
  topic). OTA firmware/config updates are planned and must be authenticated — see
  `07-firmware-design.md` §OTA.
