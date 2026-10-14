# bfwp-ingest — HiveMQ -> SQLite

Long-running Mac service (launchd) that subscribes to the BFWP topics on HiveMQ Cloud with
a persistent session (QoS 1, fixed client ID, clean session off), validates messages
against spec v1, and writes them to SQLite. Also computes derived tables (1-minute
rollups, pump cycles) and syncs Hydrawise zone runs.

- Real data: `bfwp/+/#` -> `well.db`
- Simulated data: `bfwp-sim/+/#` -> `well-sim.db`

**This app owns the database schema and migrations.** The reference schema lives in
`bfwp-spec/contracts/sqlite/schema-v1.sql`.

## File check (no MQTT)
Load a twin message file into the sim database. Device `ts` is stored as UTC epoch
milliseconds. A second load of the same file does not add rows. A reading that arrives
for a minute already closed recomputes that minute's rollup.

```bash
bfwp-ingest/.venv/bin/bfwp-ingest load path/to/scenario.messages.jsonl --db /tmp/well-sim.db
```

`bfwp-ingest run` subscribes to `bfwp-sim/#` and writes that same database. It does not
open `well.db`.

`bfwp-ingest load-zones truth-log.jsonl --db ~/BFWP-data/well-sim.db` records the truth
log's `zone_on` lines in `zone_runs` with source `twin`.

`bfwp-ingest sync-zones --start-ms … --end-ms … --source real` is the Hydrawise zone-run
sync. The HTTP call is not built yet. With no API key it returns zero counts and does
not open the database. The sim database stays on scenario zone rows.

On the Mac mini, launchd supervises the process. From the repo root, `./bfwp-start.sh`
installs and loads the agent; `./bfwp-stop.sh` unloads it. The template is
`launchd/com.bfwp.ingest.plist.example`. Logs: `~/BFWP-data/logs/ingest.log`.
