# CLAUDE.md — bfwp-firmware

## What this is
ESP32 firmware (PlatformIO, Arduino framework) for the BFWP well-house monitor.

## Contract
- Messages, topics and shared scenarios: **spec v1** in `../bfwp-spec/contracts/`.
  Do not change formats here; report contract problems instead.
- Event rules must match `../bfwp-spec/docs/07-firmware-design.md` (shared with the twin).

## Rules
- Keep logic (event detection, seq, buffering, JSON building) **separate from hardware
  drivers**, so it compiles under `env:native` and can be unit-tested on the Mac.
- Never publish before NTP time sync; `ts` is UTC epoch ms.
- `seq` persisted in NVS every 100 messages; jump +100 on boot. Never reuse a seq.
- Publish under `bfwp/<dev>/...` only. Credentials in `include/secrets.h` (gitignored).
- Claude cannot test hardware: provide a simulated-sensor build flag, and list what the
  human must verify on the device after each change.

## Commands
- `pio run` · `pio test -e native` · `pio run -t upload` · `pio device monitor`
