# 05 — MCP tools (v1 draft)

The MCP server exists so Claude can answer analysis questions without pulling millions of
rows. Tools are shaped around those questions.

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
| `get_pump_cycles(start, end)` | Each cycle: start, duration, gallons, psi/amps stats, **overlapping zone runs** | "How often did the pump run overnight?" |
| `get_unscheduled_pump_runs(start, end)` | Pump cycles / flow with **no** overlapping Hydrawise zone run | "Is anything drawing water outside the schedule?" |
| `get_overnight_decay(date, window="00:00-05:00")` | psi start/end, rate (psi/h), gallons metered, pump cycles in window — for each night in range | "Is pressure holding overnight?" |
| `get_flow_totals(start, end, bucket="day")` | Gallons per bucket, split scheduled vs unscheduled | "Water used per day this month?" |
| `get_zone_signature(zone, start, end)` | Per run: steady-state psi, amps, gpm, gallons; plus baseline median and deviations | "Is zone 3 behaving differently than usual?" |
| `compare_zone_signatures(start, end)` | All zones' current vs baseline signature | "Which zone changed?" |
| `sync_zone_runs(start, end)` | Triggers ingest's Hydrawise sync for the range; returns counts | Before any zone-join analysis |

## Analysis recipes (how the tools combine)
- **Leak downstream of meter:** `get_unscheduled_pump_runs` shows metered gallons outside
  zone runs; `get_overnight_decay` shows steady loss with metered flow.
- **Leak upstream of meter / check valve / tank:** pressure decays overnight with **zero**
  metered gallons (`psi_decay` events).
- **Broken head / lateral leak in a zone:** `get_zone_signature` → gpm up, psi down vs
  baseline for that zone only.
- **Stuck or partially closed valve:** gpm down, psi up vs baseline.
- **Pump wear:** `get_pump_cycles` over months → amps rising at similar psi/gpm.
- **Pressure tank waterlogged:** `short_cycle` events, very short pump cycles.
