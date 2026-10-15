# 05 — MCP tools (v1 draft)

The MCP server exists so Claude can answer well-monitor questions without pulling millions
of rows. Tools are shaped around those questions.

## Scope
This server is solely the well monitor: pressure, pump current, flow, pump runs, and
monitor health. It does not store Hydrawise zone runs and it does not call the Hydrawise
API. Zone schedules and controller status come from a separate Hydrawise MCP. Claude
fuses the two when a question needs both.

## Common parameters
| Param | Type | Default | Notes |
|---|---|---|---|
| `start`, `end` | ISO-8601 string | — | Without an offset, interpreted as **America/Chicago**. |
| `dev` | string | `well1` (real) / `twin1` (sim) | |
| `source` | `"real"` \| `"sim"` | `"real"` | Selects `well.db` or `well-sim.db`. |

All responses include `start_utc`, `end_utc`, `tz`, and timestamps as ISO-8601 in local
time with offset (easy to read, unambiguous). Responses over ~2,000 rows are downsampled
and say so (`"resolution": "5min"`).

## Tools
| Tool | Returns | Typical question |
|---|---|---|
| `get_device_status(dev)` | Online/offline, last message time, fw, latest health report (uptime, RSSI, buffer fill, watchdog timeouts, enclosure °F), seq gaps in last 24 h | "Is the well monitor alive and healthy?" |
| `get_device_health(start, end)` | Health reports over time: reboots and reset reasons, RSSI, memory, enclosure temperature | "Has the device been rebooting? Is the box overheating?" |
| `get_data_coverage(start, end)` | Time spans with/without data and seq gaps, judged against each reading's `mode` (active 1 s / idle 60 s) | "Can I trust last night's data?" |
| `get_readings(start, end, resolution="auto", fields=[…])` | psi/amps/gpm/pump series (raw ≤ 6 h, else 1-min or coarser) | "Show pressure 10 pm–6 am." |
| `get_events(start, end, types=[…])` | Device events | "Any alarms this week?" |
| `get_pump_cycles(start, end)` | Each cycle: start, duration, gallons, psi/amps stats | "How often did the pump run overnight?" |
| `get_overnight_decay(date, window="00:00-05:00")` | psi start/end, rate (psi/h), gallons metered, pump cycles in window — for each night in range | "Is pressure holding overnight?" |
| `get_flow_totals(start, end, bucket="day")` | Gallons per local day | "Water used per day this month?" |

## Analysis recipes (how the tools combine)
Gallons, pressure, and pump runs come from this server. Whether a zone was open comes
from the Hydrawise MCP. Claude lines the timestamps up.

- **Flow in a window:** `get_flow_totals` for whole days, or `get_readings` / `gal_total`
  for a shorter span. The difference in `gal_total` is the gallons.
- **Leak upstream of meter / check valve / tank:** pressure decays overnight with **zero**
  metered gallons (`psi_decay` events).
- **Leak downstream of meter:** gallons accumulate in a window where the Hydrawise MCP
  reports no zone running.
- **Broken head or stuck valve:** during a zone the Hydrawise MCP says was running,
  compare this server's psi, amps, and gpm with other runs of that same window shape.
- **Pump wear:** `get_pump_cycles` over months → amps rising at similar psi/gpm.
- **Pressure tank waterlogged:** `short_cycle` events, very short pump cycles.
