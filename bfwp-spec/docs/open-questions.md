# Open questions

**Hardware questions** (H1–H13: Wi-Fi band, pump motor, pressure switch, transducer type,
current sensor, flow meter, isolation, power, enclosure) are tracked in
[`../../hardware.md`](../../hardware.md) §9.

| # | Question | Affects | Status |
|---|---|---|---|
| 1 | Amperage: measured as in MWP (0–5 V ∝ amps). Volts→amps factor and sensor output type still needed (hardware H9). The earlier "0–512" was a raw-encoding misremembering. | calibration, `AMPS_HIGH`, schema `amps` bound (provisional 0–200 A) | Partly resolved |
| 2 | Real pressure-switch settings and tank size / pre-charge (hardware H3) | twin model, `PSI_LOW/HIGH` | Open |
| 3 | Flow meter model and pulse type (hardware H10, H11) | firmware input circuit | Open |
| 4 | Is the flow meter downstream of the pressure tank (hardware H12)? | leak-location logic | Open |
| 5 | HiveMQ Cloud plan: per-credential topic permissions? Queue limit for offline persistent sessions? | security, ingest | Open |
| 6 | Pressure transducer output type (hardware H6) | firmware front end | Open |
| 7 | Overnight "no watering" window for decay analysis (default 00:00–05:00) — matches the 2027 schedule? | MCP `get_overnight_decay` | Open |
| 8 | Hydrawise controller ID(s) to sync, and zone count | ingest zone sync | Open |
| 9 | Data folder on the Mac mini (`~/BFWP-data/`?) and backup destination | ingest | Open |
| 10 | GitHub account/org for remotes | dev workflow | Resolved: single private repo `whitejv/BFWP` |
| 11 | OTA trigger topic and admin credential (`bfwp/<dev>/ota`) — specify in contract v1.1 | contract, firmware, security | Open |
| 12 | Include optional `psi_v` / `amps_v` in normal operation, or only during calibration? (Contract allows both.) | message size, recalibration | Open |
| 13 | Cadence defaults (`FAST_DPSI` 2 psi/10 s, `IDLE_DPSI` 1 psi, `IDLE_HOLD_S` 120 s) — tune after first real data | firmware, twin | Open |
| 14 | Platform: ESP-IDF on the ESP32-C6 Feather, reusing MWPSensors components | firmware | Resolved |
