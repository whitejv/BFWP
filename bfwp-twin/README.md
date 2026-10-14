# bfwp-twin — ESP32 digital twin

Runs on the Mac and behaves like the well-house ESP32: models the pressure tank, pressure
switch, pump, zones, flow meter and leaks; applies the same event rules as the firmware;
and publishes **spec v1** messages to HiveMQ under the simulation topic root.

Driven three ways (see `bfwp-spec/docs/06-digital-twin.md`):
1. **Scenario files** (`scenarios/*.yaml`) — repeatable timelines with expected events.
2. **Live control** — commands on `bfwp-sim/<dev>/cmd` or the CLI.
3. **Hydrawise mirror** — replays the real Hydrawise schedule.

Every run writes a **truth log** of what was injected, for checking analysis results.

## Offline check
From the repo root, `cmake --build build` installs this app. Then:

```bash
bfwp-twin/.venv/bin/bfwp-twin run bfwp-spec/contracts/scenarios/baseline_normal_night.yaml
```

That writes two files under `bfwp-twin/truth-logs/` and does not connect to a broker:

- `baseline_normal_night-<run-id>.jsonl` — injected zone runs
- `baseline_normal_night-<run-id>.messages.jsonl` — telemetry, telemetry batches,
  events, health, and status

`cmake --build build --target test` runs this offline check.

## Broker check
`--mqtt` publishes that same message file to HiveMQ at QoS 1, under `bfwp-sim/` only.
Copy `.env.example` to `.env` to point at another broker. With no `.env`, the public
broker in the example is used. It does not check the password.

```bash
BFWP_MQTT=1 bfwp-twin/.venv/bin/pytest -q bfwp-twin/tests/test_baseline_broker.py
```

A subscriber on `bfwp-sim/twin1/#` must see the same messages as the offline file.
