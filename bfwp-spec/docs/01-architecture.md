# 01 — Architecture

## Goal
Give Claude (and the Landscape Committee) signals Hydrawise can't provide — **well
pressure, pump motor current, and independent flow** — time-aligned with Hydrawise zone
runs, so questions like *"is there a leak?"*, *"is the pump wearing?"* and *"which zone is
misbehaving?"* can be answered from data.

## Data flow
```
 Well house                         Cloud                    Mac mini (home)
┌──────────────────┐   TLS 8883   ┌─────────────┐  TLS   ┌──────────────────────────┐
│ ESP32  (well1)   │ ───────────► │ HiveMQ      │ ─────► │ bfwp-ingest (launchd)    │
│  psi · amps ·    │  bfwp/well1/…│ Cloud       │        │   validate → SQLite (WAL)│
│  flow pulses     │              │ (broker)    │        │   rollups · pump cycles  │
└──────────────────┘              │             │        │   Hydrawise run sync     │
┌──────────────────┐              │             │        └────────────┬─────────────┘
│ bfwp-twin (Mac)  │ ───────────► │             │                     │ read-only
│  simulated twin1 │ bfwp-sim/…   └─────────────┘        ┌────────────▼─────────────┐
└──────────────────┘                                     │ bfwp-mcp  → Claude       │
                                                         │ (+ Hydrawise MCP)        │
                                                         └──────────────────────────┘
```
The well-house Wi-Fi is isolated from the home network, so a cloud broker is the
rendezvous point. Neither side needs inbound ports.

## Components and ownership
| Component | Repo | Writes | Reads |
|---|---|---|---|
| Contracts & design | `bfwp-spec` | — | — |
| Device | `bfwp-firmware` | MQTT `bfwp/<dev>/…` | sensors |
| Digital twin | `bfwp-twin` | MQTT `bfwp-sim/<dev>/…`, truth log | scenarios, `…/cmd` |
| Ingest | `bfwp-ingest` | `well.db`, `well-sim.db` (**sole writer, owns schema**) | MQTT, Hydrawise API |
| Query server | `bfwp-mcp` | nothing | databases (read-only) |

## Key design decisions
1. **Device timestamps, UTC epoch ms**, after NTP sync. Receive time is stored separately
   and never used for analysis.
2. **`seq` per device, never reused** (persisted in flash). `(dev, seq)` is the idempotency
   key, so duplicates (QoS 1) and late buffered batches are harmless.
3. **Cumulative flow counter (`gal_total`)**, so gallons between any two readings are exact
   even when messages are lost.
4. **Persistent MQTT session** for ingest (fixed client ID, clean session off, QoS 1) plus
   **device-side flash buffering**, so neither a sleeping Mac nor a Wi-Fi outage loses data.
5. **SQLite on local disk**, WAL mode, nightly `.backup` to a synced folder.
6. **Sim data is physically separate**: different topic root and different database file.
7. **MCP tools are question-shaped** (pump cycles, overnight decay, zone signatures), not raw
   dumps, and downsample long ranges.

## Security
- TLS to HiveMQ always (port 8883).
- Separate credentials per client: `bfwp-well1` (publish `bfwp/well1/#`),
  `bfwp-twin` (publish `bfwp-sim/#`, subscribe `bfwp-sim/+/cmd`),
  `bfwp-ingest` (subscribe `bfwp/#`, `bfwp-sim/#`). Restrict by topic if the HiveMQ plan
  allows (see open questions).
- No credentials in git: `.env` / `include/secrets.h` are gitignored; `*.example` files
  are committed.
- The device accepts **no** inbound commands in v1 (only the twin has a `cmd` topic).
