# CLAUDE.md — bfwp-mcp

## What this is
Python MCP server exposing analysis-oriented tools over the BFWP SQLite databases.

## Contract
- Targets **spec v1** (draft; will be tagged `spec-v1.0`).
- Tools: `../bfwp-spec/docs/05-mcp-tools.md`. Database: `../bfwp-spec/contracts/sqlite/schema-v1.sql`.
- If a tool needs data the schema doesn't have, report it — schema changes go through
  `../bfwp-spec/` and are implemented in `../bfwp-ingest/`.

## Rules
- **Open databases read-only** (`file:...?mode=ro`). This server never writes well data.
  (Exception: `sync_zone_runs` asks ingest to sync; it does not write itself.)
- Accept times as ISO-8601; times without an offset are America/Chicago. Convert to UTC ms.
- Every tool takes `source: "real" | "sim"` (default `real`).
- Keep responses small: auto-downsample long ranges to the 1-minute rollup or coarser.
- Develop against `well-sim.db` produced by twin scenarios.

## Commands (once implemented)
- `pip install -e .[dev]` · `pytest`

## Work style
Follow the project-wide rules in `../CLAUDE.md`: change files only in this folder, commit
with the `mcp:` prefix, branch as `mcp/<topic>`, and summarize changes for review.
