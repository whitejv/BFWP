# CLAUDE.md — bfwp-twin

## What this is
Python digital twin of the BFWP well-house ESP32. It must be indistinguishable from the
real device to `bfwp-ingest`, except for its device ID and topic root.

## Contract
- Targets **spec v1** (draft; will be tagged `spec-v1.0`).
- Build to **spec v1** in `../bfwp-spec/contracts/` (schemas, examples, topics, scenarios).
- **Do not change the message format here.** If the contract seems wrong or incomplete,
  stop and report it — changes happen in `../bfwp-spec/` first (see `../CLAUDE.md`).
- Every message published must validate against the v1 JSON Schemas (add a test).

## Rules
- Publish only under `bfwp-sim/<dev>/...` (default dev `twin1`). Never `bfwp/...`.
- Event rules (pump_on/off, flow_idle, psi_decay, alarms) must match
  `bfwp-spec/docs/07-firmware-design.md` — they are shared behavior with the firmware.
- Every run writes a truth log (JSONL) of injected conditions.
- Secrets live in `.env` (gitignored). Never commit credentials.

## Commands (once implemented)
- `pip install -e .[dev]` · `pytest` · `bfwp-twin run <scenario.yaml>` · `bfwp-twin live`

## Work style
Follow the project-wide rules in `../CLAUDE.md`: change files only in this folder, commit
with the `twin:` prefix, branch as `twin/<topic>`, and summarize changes for review.
