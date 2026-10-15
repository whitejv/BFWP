# bfwp-mcp — well-monitor query server

MCP server that gives Claude read-only access to BFWP well data in SQLite. It covers
the well monitor only: pressure, pump current, flow, pump runs, and monitor health.
Zone schedules stay on a separate Hydrawise MCP. Claude fuses the two. Tool contract:
`bfwp-spec/docs/05-mcp-tools.md`.

`get_pump_cycles` reads `well-sim.db` or `well.db` and does not write. Each cycle is
the pump run ingest stored, with its gallons, duration, and pressure and current stats.

`get_overnight_decay` reports pressure at the start and end of a night window
(default 00:00–05:00 Chicago), the gallons the meter counted, and the pump cycles
in that window.

`get_data_coverage` reports spans with and without readings. A hole is longer than
3 seconds between active readings, or 90 seconds otherwise. It also lists skipped
sequence numbers across readings, events, and health.

`get_device_health` returns health reports for a range: reset reason, uptime, RSSI,
memory, and enclosure temperature. A report with uptime zero is a reboot. A range
longer than about 2,000 reports is thinned, and those reboots are kept.

`get_device_status` reports the latest online flag, firmware, last message time, and
latest health report (uptime, RSSI, buffer fill, watchdog timeouts, enclosure
temperature), plus sequence gaps in the last 24 hours.

`get_readings` returns psi, amps, gpm, and pump. A span of six hours or less stays
on the raw readings when that is about 2,000 points or fewer. Longer spans use the
one-minute rollup, or a coarser bucket, and the response names that resolution.

`get_events` returns device events for a range, with a count per type. `types` limits
the list. More than about 2,000 events keeps the latest ones, and the counts still
cover the whole range.

`get_flow_totals` returns gallons per local day from the well meter.

```bash
bfwp-mcp/.venv/bin/bfwp-mcp
```
