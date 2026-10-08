# 08 — Development workflow

## Environment
- Mac, **Cursor**, **Claude Code** run inside Cursor (run `claude` in Cursor's terminal;
  it installs the extension).
- Open `BFWP/bfwp.code-workspace` to see all five repos at once.
- Python apps: Python 3.11+, a `.venv` per repo, `pip install -e .[dev]`, `pytest`.
- Firmware: PlatformIO extension in Cursor.

## Git
- One git repo per app (`bfwp-spec`, `bfwp-twin`, `bfwp-ingest`, `bfwp-mcp`, `bfwp-firmware`),
  default branch `main`.
- Work on feature branches (`feat/…`, `fix/…`); merge to `main` after review.
- Remotes: private GitHub repos when ready (`gh repo create … --private --source . --push`).
- Consumers pin the spec version in their CLAUDE.md (e.g. "targets spec v1.0"). Once the spec
  has a remote, consumers may add it as a git submodule at `contracts/`.

## Each repo's CLAUDE.md
States: what the app is, which spec version it targets, its "stay in your lane" rules
(e.g. MCP never writes the DB), and its build/test commands. Claude Code reads it at the
start of every session.

## Build order and parallel agents
1. **Spec** — finalize and tag `v1.0` (alone; everything depends on it).
2. **Twin + ingest** — in parallel (two Claude Code sessions, one per repo). The twin gives
   ingest realistic traffic immediately.
3. **MCP** — against `well-sim.db` from twin scenarios; check analysis against truth logs.
4. **Firmware** — when hardware arrives; must pass the shared scenarios in `env:native`.

Guidelines for agents:
- One agent per repo at a time (use git worktrees if two must share a repo).
- If an agent believes the contract must change, it **stops and reports**; the change is
  made in `bfwp-spec`, logged, and tagged first.
- Each agent ends a task with a summary of changes and what a human must verify.

## Secrets
| Repo | File (gitignored) | Template (committed) |
|---|---|---|
| twin, ingest, mcp | `.env` | `.env.example` |
| firmware | `include/secrets.h` | `include/secrets.example.h` |

## Testing ladder
1. Schema validation (`bfwp-spec/tools/validate.py`).
2. Unit tests per repo.
3. Twin → HiveMQ → ingest → `well-sim.db` end-to-end, scenario by scenario.
4. MCP analysis vs truth log.
5. Real device on the bench (simulated sensors) → then in the well house.
