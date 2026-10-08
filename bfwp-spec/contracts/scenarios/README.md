# Shared scenarios

Each scenario is a timeline of injected conditions plus **expectations**. The digital twin
runs them end-to-end; the firmware runs its `core/` logic against them in `env:native`.
Both must meet the `expect.events` / `expect.no_events` assertions. `expect.analysis` is
what the MCP-based analysis should conclude from the resulting data.

Format: see `docs/06-digital-twin.md` §4. Timeline actions use the same names and
arguments as sim commands (`contracts/schemas/v1/sim-command.schema.json`);
`tools/validate.py` checks that.
