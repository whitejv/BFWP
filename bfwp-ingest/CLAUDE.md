# CLAUDE.md — bfwp-ingest

## What this is
Python service on the Mac mini: HiveMQ Cloud subscriber -> SQLite (WAL mode), plus
derived tables and Hydrawise zone-run sync.

## Contract
- Messages: **spec v1** in `../bfwp-spec/contracts/`. Do not change message formats here;
  report contract problems instead.
- Database: start from `../bfwp-spec/contracts/sqlite/schema-v1.sql`. **This repo is the
  only writer and owns migrations.** Any schema change must also update the spec doc.

## Rules
- Store all times as UTC epoch milliseconds. Never use receive time as `ts`.
- Insert with `INSERT OR IGNORE` on `(dev, seq)` — duplicates and late batches are normal.
- Real (`bfwp/...`) and sim (`bfwp-sim/...`) data go to separate database files.
- Invalid messages go to a reject log; never crash the subscriber on bad input.
- Live DB stays on local disk; backups use `sqlite3 .backup`, never a synced live file.
- Secrets in `.env` (gitignored).

## Commands (once implemented)
- `pip install -e .[dev]` · `pytest` · `bfwp-ingest run` · `bfwp-ingest backfill-rollups`

## Work style
Feature branches, small commits, summarize changes for review.
