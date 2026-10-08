# bfwp-ingest — HiveMQ -> SQLite

Long-running Mac service (launchd) that subscribes to the BFWP topics on HiveMQ Cloud with
a persistent session (QoS 1, fixed client ID, clean session off), validates messages
against spec v1, and writes them to SQLite. Also computes derived tables (1-minute
rollups, pump cycles) and syncs Hydrawise zone runs.

- Real data: `bfwp/+/#` -> `well.db`
- Simulated data: `bfwp-sim/+/#` -> `well-sim.db`

**This app owns the database schema and migrations.** The reference schema lives in
`bfwp-spec/contracts/sqlite/schema-v1.sql`.
