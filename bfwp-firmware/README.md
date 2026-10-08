# bfwp-firmware — well-house ESP32

PlatformIO project for the ESP32 at the well house. Reads a 0–100 psi pressure
transducer, a current sensor on the pump motor, and the Hydrawise flow meter's
1-pulse-per-gallon output (isolated tap), then publishes spec v1 messages to HiveMQ Cloud
over the well-house Wi-Fi. Buffers to flash while offline.

Design: `bfwp-spec/docs/07-firmware-design.md`.

Setup: install the PlatformIO extension in Cursor, then
`cp include/secrets.example.h include/secrets.h` and fill it in.
