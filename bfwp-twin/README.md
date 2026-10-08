# bfwp-twin — ESP32 digital twin

Runs on the Mac and behaves like the well-house ESP32: models the pressure tank, pressure
switch, pump, zones, flow meter and leaks; applies the same event rules as the firmware;
and publishes **spec v1** messages to HiveMQ under the simulation topic root.

Driven three ways (see `bfwp-spec/docs/06-digital-twin.md`):
1. **Scenario files** (`scenarios/*.yaml`) — repeatable timelines with expected events.
2. **Live control** — commands on `bfwp-sim/<dev>/cmd` or the CLI.
3. **Hydrawise mirror** — replays the real Hydrawise schedule.

Every run writes a **truth log** of what was injected, for checking analysis results.

## Setup (planned)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env   # fill in HiveMQ sim credentials
bfwp-twin run scenarios/overnight_leak.yaml
```
