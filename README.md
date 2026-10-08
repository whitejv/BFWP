# Bella Flora Water Project (BFWP)

Well-house monitoring for the Bella Flora HOA irrigation system. An ESP32 near the well
reads **well pressure**, **pump motor amperage**, and **flow-meter pulses**, publishes JSON
over HiveMQ Cloud, and a Mac mini ingests the data into SQLite so an MCP server can
answer questions that combine it with Hydrawise zone-run data (leaks, pump health, zone
signatures).

Open `bfwp.code-workspace` in Cursor to see all five repos together.

| Repo | Purpose |
|---|---|
| `bfwp-spec` | Design docs and the message/storage/tool **contracts**. Everything else builds to it. |
| `bfwp-twin` | Digital twin of the ESP32 — simulates the well system and publishes real-format messages. |
| `bfwp-ingest` | Mac service: HiveMQ subscriber -> SQLite. Owns the database schema. |
| `bfwp-mcp` | MCP server: read-only queries over SQLite + Hydrawise joins. |
| `bfwp-firmware` | ESP32 firmware (PlatformIO). |

Start with `bfwp-spec/docs/01-architecture.md`.
