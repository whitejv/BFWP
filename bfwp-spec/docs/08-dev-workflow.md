# 08 — Development workflow

## Environment
- Mac, **Cursor**, **Claude Code** run inside Cursor (run `claude` in Cursor's terminal;
  it installs the extension).
- Open the `BFWP` folder in Cursor (or `bfwp.code-workspace` for labeled folders).
- Python apps: Python 3.11+, a `.venv` per app folder, `pip install -e .[dev]`, `pytest`.
- Firmware: PlatformIO extension in Cursor.

## Git — one repo, five apps
- Single repo **`BFWP`** (GitHub: `whitejv/BFWP`, private), default branch `main`.
- Each app is a top-level folder: `bfwp-spec/`, `bfwp-twin/`, `bfwp-ingest/`, `bfwp-mcp/`,
  `bfwp-firmware/`. Each keeps its own `.gitignore`, README and CLAUDE.md.
- **Branches:** `<app>/<topic>` (e.g. `twin/physics-model`, `spec/add-temp-field`); merge to
  `main` after review.
- **Commits:** prefix with the app — `spec:`, `twin:`, `ingest:`, `mcp:`, `firmware:` —
  or `repo:` for top-level files. Prefer one app per commit, so history per app stays
  readable (`git log -- bfwp-twin/`).
- **Spec versions:** tags on the repo, `spec-v1.0`, `spec-v1.1`, …
  ```bash
  git tag spec-v1.0 && git push --tags
  ```
- **Contract changes:** land in `bfwp-spec/` as their own commit (schemas + examples + docs +
  CHANGELOG, passing `tools/validate.py`), then consumers update in follow-up commits.
  Because everything is in one repo, a consumer reads the spec directly at
  `../bfwp-spec/contracts/` — no copying or submodules.

## CLAUDE.md files
- `BFWP/CLAUDE.md` — project-wide rules (stay in your folder, contract-first, commit/branch
  conventions, secrets).
- `bfwp-*/CLAUDE.md` — what that app is, the spec version it targets, its own rules
  (e.g. MCP never writes the DB), and its build/test commands.

Claude Code loads the top-level CLAUDE.md plus the one for the folder it's working in.

## Build order and parallel agents
1. **Spec** — finalize and tag `spec-v1.0` (alone; everything depends on it).
2. **Twin + ingest** — in parallel (two Claude Code sessions, one per app folder). The twin
   gives ingest realistic traffic immediately.
3. **MCP** — against `well-sim.db` from twin scenarios; check analysis against truth logs.
4. **Firmware** — when hardware arrives; must pass the shared scenarios in `env:native`.

Running two sessions at once in one repo:
- Each session works **only in its own app folder**, on its own branch.
- Because both sessions share one working copy, give each its own **git worktree** so
  their branches and uncommitted changes don't collide:
  ```bash
  git worktree add ../BFWP-twin   -b twin/initial
  git worktree add ../BFWP-ingest -b ingest/initial
  # open each folder in its own Cursor window and run `claude` there
  # when merged:  git worktree remove ../BFWP-twin
  ```
- If an agent believes the contract must change, it **stops and reports**; the change is
  made in `bfwp-spec/`, logged, and tagged first.
- Each agent ends a task with a summary of changes and what a human must verify.

## Secrets
| App folder | File (gitignored) | Template (committed) |
|---|---|---|
| `bfwp-twin/`, `bfwp-ingest/`, `bfwp-mcp/` | `.env` | `.env.example` |
| `bfwp-firmware/` | `include/secrets.h` | `include/secrets.example.h` |

Check before pushing: `git status` should never list `.env` or `secrets.h`.

## Testing ladder
1. Schema validation (`python3 bfwp-spec/tools/validate.py`).
2. Unit tests per app folder.
3. Twin → HiveMQ → ingest → `well-sim.db` end-to-end, scenario by scenario.
4. MCP analysis vs truth log.
5. Real device on the bench (simulated sensors) → then in the well house.
