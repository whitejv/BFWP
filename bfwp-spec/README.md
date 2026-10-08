# bfwp-spec — design and contracts

The single source of truth for the Bella Flora Water Project. The twin, ingest, MCP and
firmware apps (sibling folders in the BFWP repo) all build to a **tagged version** of this
spec (currently v1, draft).

## Docs
| Doc | Covers |
|---|---|
| [01 Architecture](docs/01-architecture.md) | Components, data flow, folders, ownership, security |
| [02 Message contract](docs/02-message-contract.md) | Envelope, telemetry, batches, events, status, topics, QoS |
| [03 Sensors and units](docs/03-sensors-and-units.md) | Pressure, amperage, flow — ranges, resolution, derivations |
| [04 Storage](docs/04-storage.md) | SQLite layout, derived tables, retention, backups |
| [05 MCP tools](docs/05-mcp-tools.md) | Query tools Claude uses for analysis |
| [06 Digital twin](docs/06-digital-twin.md) | Simulation model, scenarios, live control, truth log |
| [07 Firmware design](docs/07-firmware-design.md) | ESP32 hardware notes and the shared event rules |
| [08 Development workflow](docs/08-dev-workflow.md) | Cursor, Claude Code, monorepo git, parallel agents, secrets |
| [Open questions](docs/open-questions.md) | Decisions still pending |

## Contracts
```
contracts/
  topics.v1.json            MQTT topic map
  schemas/v1/*.schema.json  JSON Schemas (draft-07) for every message
  examples/v1/*.json        Valid example messages (also test vectors)
  sqlite/schema-v1.sql      Reference database schema (ingest writes, MCP reads)
  scenarios/*.yaml          Shared behavior scenarios (twin + firmware must pass)
```

## Validate
```bash
python3 tools/validate.py      # checks every example against its schema
```

## Versioning
- `v` in every message is the **major** contract version. Additive, optional fields don't
  bump it; anything that breaks a consumer does.
- Tag releases on the BFWP repo as `spec-v1.0`, `spec-v1.1`, … Each app records the spec
  version it targets in its CLAUDE.md.
- Record every change in `CHANGELOG.md`.
