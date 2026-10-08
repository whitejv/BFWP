# 04 — Storage

Reference schema: [`contracts/sqlite/schema-v1.sql`](../contracts/sqlite/schema-v1.sql).

## Files
| File | Contents | Location |
|---|---|---|
| `well.db` | Real device data (`bfwp/…`) | `~/BFWP-data/` on the Mac mini's local disk |
| `well-sim.db` | Twin data (`bfwp-sim/…`) — disposable | same folder |
| Nightly backup | `sqlite3 well.db ".backup <dest>"` | a synced folder (iCloud/Drive) |

Never place a **live** database in a synced folder — sync tools can copy it mid-write and
corrupt it.

## Ownership
- **bfwp-ingest** is the only writer and owns migrations (`meta.schema_version`).
- **bfwp-mcp** opens with `mode=ro`. WAL mode lets it read while ingest writes.

## Tables
| Table | Purpose | Key |
|---|---|---|
| `readings` | Raw telemetry | `(dev, seq)` |
| `events` | Device events (JSON `data`) | `(dev, seq)` |
| `status_log` | Online/offline history | `(dev, received_ts)` |
| `health` | Periodic device health reports | `(dev, seq)` |
| `pump_cycles` | One row per pump run | `(dev, start_ts)` |
| `readings_1min` | Per-minute rollup | `(dev, minute_ts)` |
| `zone_runs` | Hydrawise actual zone runs | `(controller_id, zone_id, start_ts)` |
| `rejects` | Invalid messages | — |

## Write rules
- `INSERT OR IGNORE` on the primary key — duplicates and re-sent batches are no-ops.
- Late data (buffer flush hours later) is normal. When rows arrive for a minute that's
  already rolled up, ingest **recomputes that minute** (and any affected pump cycle).
- `received_ts` is diagnostics only; analysis always uses `ts`.

## Gaps and cadence
`readings.mode` records the cadence in effect. Coverage checks treat > 3 s between `active`
readings, or > 90 s between `idle` readings, as a gap.

## Volume and retention
At 1 Hz while active (~8 h/day worst case) plus 1/min idle and occasional report-on-change
readings: ≈ 30k readings/day ≈ 2–3 MB/day
including indexes, ~1 GB/year. Keep raw data indefinitely for now; revisit if the drive
fills (option: drop raw readings older than 2 years, keep rollups forever).

## Query patterns (what the indexes serve)
- Range scan: `WHERE dev=? AND ts BETWEEN ? AND ?` on `readings` / `events`.
- Long ranges (> 6 h): use `readings_1min`.
- Join with zones: overlap test
  `zone_runs.start_ts < :end AND zone_runs.end_ts > :start`.
