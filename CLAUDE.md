# CLAUDE.md — Bella Flora Water Project (monorepo)

## Layout
One git repo, five apps, each in its own folder with its own `CLAUDE.md`:
- `bfwp-spec/` — design docs + contracts (schemas, examples, SQLite schema, scenarios). Source of truth.
- `bfwp-twin/` — Python digital twin of the ESP32.
- `bfwp-ingest/` — Python HiveMQ -> SQLite service. Sole database writer; owns migrations.
- `bfwp-mcp/` — Python MCP server, read-only over the databases.
- `bfwp-firmware/` — ESP32 PlatformIO project.

Read the app folder's `CLAUDE.md` before working in it.

## Rules for every session
- **Stay in your folder.** Change files only in the app folder you were asked to work on.
  Reading other folders (especially `bfwp-spec/`) is expected.
- **Contracts change in `bfwp-spec/` first.** If the contract looks wrong or incomplete,
  stop and report it. A contract change is its own commit that updates schemas, examples,
  docs and `bfwp-spec/CHANGELOG.md`, and passes `python3 bfwp-spec/tools/validate.py`.
  Consumer code may follow in later commits.
- **Commits:** small, one app per commit where possible, message prefixed with the folder
  short name: `spec:`, `twin:`, `ingest:`, `mcp:`, `firmware:` (or `repo:` for top-level files).
- **Branches:** `<app>/<topic>` (e.g. `twin/physics-model`), merged to `main` after review.
- **Never commit secrets.** `.env` and `bfwp-firmware/include/secrets.h` are gitignored;
  only `*.example` templates are committed.
- End each task with a summary of what changed and what a human must verify.

## Spec versions
Tagged on this repo as `spec-vMAJOR.MINOR` (e.g. `spec-v1.0`). Each app's `CLAUDE.md`
names the spec version it targets.
