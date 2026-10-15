# Bella Flora Water Project (BFWP)

Well-house monitoring for the Bella Flora HOA irrigation system. An ESP32 near the well
reads **well pressure**, **pump motor amperage**, and **flow-meter pulses**, publishes JSON
over HiveMQ Cloud, and a Mac mini ingests the data into SQLite so an MCP server can
answer questions about the well monitor (pressure, pump current, flow, and monitor
health). Zone schedules stay on a separate Hydrawise MCP. Claude fuses the two.

This is a single git repository (`github.com/whitejv/BFWP`, private) containing five apps,
each in its own folder. Open the BFWP folder in Cursor, or open `bfwp.code-workspace` for
labeled folders.

| Folder | Purpose |
|---|---|
| `bfwp-spec/` | Design docs and the message/storage/tool **contracts**. Everything else builds to it. |
| `bfwp-twin/` | Digital twin of the ESP32 — simulates the well system and publishes real-format messages. |
| `bfwp-ingest/` | Mac service: HiveMQ subscriber -> SQLite. Owns the database schema. |
| `bfwp-mcp/` | MCP server: read-only queries over the well-monitor database. |
| `bfwp-firmware/` | ESP32-C6 firmware (ESP-IDF). |

Start with `bfwp-spec/docs/01-architecture.md`. Hardware: `hardware.md`. Development workflow:
`bfwp-spec/docs/08-dev-workflow.md`. Claude Code instructions: `CLAUDE.md` (project-wide)
plus one `CLAUDE.md` per app folder.

## Development order

No board is required to start. Build one element at a time, and pass that element's check
before starting the next. The digital twin stands in for the ESP32. The sequence is spec,
twin, ingest into `well-sim.db`, MCP questions checked against the truth log, `bfwp_core`
host tests, then bench and the well house. Checks, scenario order, and what to defer are
in `bfwp-spec/docs/08-dev-workflow.md`.

## Rebuild

The repo root is a host CMake project. It refreshes a virtualenv in each Python app that
has a `pyproject.toml` (`bfwp-twin`, `bfwp-ingest`, `bfwp-mcp`). It does not install into
`/usr/local`. Firmware stays an ESP-IDF project and is a separate target.

```bash
cmake -S . -B build
cmake --build build                  # virtualenvs
cmake --build build --target test    # contract validation and pytest
cmake --build build --target install # same virtualenv refresh
```

The test target installs `jsonschema` and `PyYAML` into `bfwp-spec/.venv` when they are
missing, then runs `tools/validate.py`. Pytest runs for an app only after that app's
virtualenv exists.

`cmake --build build --target firmware` runs `idf.py -C bfwp-firmware build`. It needs
`IDF_PATH` set (source the ESP-IDF `export.sh` first). A Mac without the IDF toolchain
can still build the host apps.

When `bfwp-firmware/components/bfwp_core/CMakeLists.txt` exists, the host build picks it
up so that library can be tested on the Mac.

## Run ingest on the Mac

launchd supervises ingest. `KeepAlive` restarts it if the process exits. The start script
writes `~/Library/LaunchAgents/com.bfwp.ingest.plist` from
`bfwp-ingest/launchd/com.bfwp.ingest.plist.example` and loads it. Logs are
`~/BFWP-data/logs/ingest.log`. The Mac mini user needs to be logged in.

```bash
./bfwp-start.sh
./bfwp-stop.sh
```

Start will fail until `bfwp-ingest` is installed into `bfwp-ingest/.venv` (the CMake build
does that once `bfwp-ingest/pyproject.toml` exists). The twin is started by hand. Cursor
starts the MCP server when a chat needs it.
