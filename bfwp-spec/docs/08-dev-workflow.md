# 08 — Development workflow

## Environment
- Mac, **Cursor**, **Claude Code** run inside Cursor (run `claude` in Cursor's terminal;
  it installs the extension).
- Open the `BFWP` folder in Cursor (or `bfwp.code-workspace` for labeled folders).
- Python apps: Python 3.11+, a `.venv` per app folder, `pip install -e .[dev]`, `pytest`.
- Firmware: ESP-IDF v5.x (`idf.py`); the Espressif ESP-IDF extension in Cursor is optional.
- Rebuild everything that runs on the Mac from the repo root:

  ```bash
  cmake -S . -B build
  cmake --build build                  # .venv in twin, ingest, and mcp
  cmake --build build --target test    # validate.py and pytest
  cmake --build build --target firmware  # idf.py; requires IDF_PATH
  ```

  Apps without a `pyproject.toml` are skipped. The test target keeps `jsonschema` and
  `PyYAML` in `bfwp-spec/.venv` so contract validation does not depend on the system
  Python. `bfwp_core` joins the host build once
  `bfwp-firmware/components/bfwp_core/CMakeLists.txt` exists. Ingest on the Mac mini is
  started with `./bfwp-start.sh` and stopped with `./bfwp-stop.sh` (launchd, see
  `01-architecture.md`).

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

## Build order

One element at a time. The digital twin stands in for the ESP32 until a board exists.
Shared scenarios in `contracts/scenarios/` are the checklist. Do not start the next
element until the current element's check passes. After each merge,
`cmake --build build --target test` stays green.

A contract problem stops the element. The fix lands in `bfwp-spec/` first (schemas,
examples, docs, `CHANGELOG.md`, passing `tools/validate.py`). Open hardware questions in
`../../hardware.md` do not block this sequence. Tag `spec-v1.0` at the start of twin
work, once the message, SQLite, and scenario contracts are the ones the twin will build to.

The default is one branch and one element. Worktrees are for the rare case where two
folders must move at once:

```bash
git worktree add ../BFWP-twin   -b twin/initial
git worktree add ../BFWP-ingest -b ingest/initial
# open each folder in its own Cursor window
# when merged:  git worktree remove ../BFWP-twin
```

Each agent ends a task with a summary of changes and what a human must verify.

### 1. Spec gate

Already drafted. Check: `cmake --build build --target test` reports all contracts valid.
That check remains the standing bar for every later element.

### 2. Twin, as the hardware

Build `bfwp-twin` in three checks, in this order. Publish only under `bfwp-sim/twin1/…`.
Every run writes the truth log described in `06-digital-twin.md`.

1. **Physics.** 100 ms step, `speed: 0`, scenario `baseline_normal_night` only. Check: the
   truth log lists the injected zone runs, and tank pressure cycles between the scenario's
   cut-in and cut-out. No MQTT yet.
2. **Device behavior.** The same process emits spec v1 telemetry, events, health, and
   status. Check one scenario at a time, offline: messages captured to a file, each
   validated against the v1 schemas, and `expect.events` / `expect.cadence` /
   `expect.no_events` pass.
   - `baseline_normal_night` — a normal night, no faults
   - `cadence_off_hours` — active 1 s, idle 60 s, report-on-change
   - `overnight_leak` — downstream leak plus a Wi-Fi outage that flushes a batch
   - `upstream_leak_decay` — pressure loss with no metered gallons
   - `sensor_fault_and_reboot` — null psi, then boot and a seq jump
3. **Broker.** `bfwp-twin run` publishes `baseline_normal_night` to HiveMQ. Check: a
   subscriber sees the same messages the offline file already validated.

Live `cmd` waits until a later element needs it. A Hydrawise mirror is out of scope.

### 3. Ingest

Build `bfwp-ingest` against twin output, into `well-sim.db` only.

1. **File first.** Load the offline capture from element 2. Check: `INSERT OR IGNORE` on
   `(dev, seq)`, device `ts` stored as UTC epoch ms, invalid messages in `rejects`, and a
   replay of the same file does not duplicate rows. Recompute the 1-minute rollup for the
   Wi-Fi-outage minute in `overnight_leak` after the late batch arrives.
2. **Live path.** `./bfwp-start.sh`, then the twin publishes `baseline_normal_night`.
   Check: `well-sim.db` matches the file-ingest result for that scenario. `well.db` stays
   empty.

### 4. MCP, one question at a time

Build `bfwp-mcp` read-only on `well-sim.db`. The server answers well-monitor questions
only. Ask with the truth log withheld, then compare. Pass a question before adding the
next tool.

1. Baseline night: pump cycles agree with the rows ingest stored from that night.
2. `overnight_leak`: the meter advances after the injected leak; `expect.analysis` is
   the scenario's label, not a classification this server makes.
3. `upstream_leak_decay`: overnight psi drop with zero metered gallons.
4. Then coverage, health, and the remaining tools in `05-mcp-tools.md`.

### 5. Firmware logic, still no board

`bfwp_core` on the Mac, no ESP-IDF calls, same five scenarios and the same `expect`
blocks the twin already passes. This is the check that twin and device rules did not
drift. HAL, Wi-Fi, TLS, and flash wait for a board.

### 6. Hardware, last

Bench with simulated sensors, then the well house. The twin keeps publishing on
`bfwp-sim/…` into `well-sim.db`. The device publishes on `bfwp/…` into `well.db`.

## Secrets
| App folder | File (gitignored) | Template (committed) |
|---|---|---|
| `bfwp-twin/`, `bfwp-ingest/`, `bfwp-mcp/` | `.env` | `.env.example` |
| `bfwp-firmware/` | `main/secrets.h` | `main/secrets.example.h` |

Check before pushing: `git status` should never list `.env` or `secrets.h`.

## Testing ladder

Each rung is the check for one element above. Stay on a rung until it passes.

1. Schema validation (`cmake --build build --target test`, which runs
   `tools/validate.py`).
2. Twin physics truth log for `baseline_normal_night`, then offline message files for
   each scenario in the order in §2, then one live HiveMQ publish of the baseline.
3. File ingest into `well-sim.db` (idempotent `(dev, seq)`, rejects, late rollup), then
   the same baseline through launchd and HiveMQ. `well.db` stays empty.
4. MCP answers for baseline, `overnight_leak`, and `upstream_leak_decay`, compared with
   the truth log withheld, then the remaining tools.
5. `bfwp_core` host tests pass the same five scenario `expect` blocks.
6. Bench with simulated sensors, then the well house.
