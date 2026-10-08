# Open questions

| # | Question | Affects | Status |
|---|---|---|---|
| 1 | Is 0–512 the true amperage range, or a raw ADC count? Expected running current of the well motor? | sensors, firmware, `AMPS_HIGH` default | Open |
| 2 | Real pressure-switch settings (cut-in / cut-out) and tank size / pre-charge | twin model, `PSI_LOW/HIGH` | Open |
| 3 | Hydrawise flow-meter model and pulse electrical characteristics (dry contact? voltage?) — determines the isolation circuit | firmware hardware | Open |
| 4 | Is the flow meter downstream of the pressure tank (on the irrigation mainline)? | leak-location logic | Open |
| 5 | HiveMQ Cloud plan: per-credential topic permissions? Queue limit for offline persistent sessions? | security, ingest | Open |
| 6 | Pressure transducer output type (0.5–4.5 V vs 4–20 mA) and ADC choice (ADS1115?) | firmware hardware | Open |
| 7 | Overnight "no watering" window for decay analysis (default 00:00–05:00) — matches the 2027 schedule? | MCP `get_overnight_decay` | Open |
| 8 | Hydrawise controller ID(s) to sync, and zone count | ingest zone sync | Open |
| 9 | Data folder on the Mac mini (`~/BFWP-data/`?) and backup destination | ingest | Open |
| 10 | GitHub account/org for remotes | dev workflow | Resolved: single private repo `whitejv/BFWP` |
