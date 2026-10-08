# bfwp-firmware — well-house ESP32-C6 (ESP-IDF)

ESP-IDF firmware for the BFWP well-house monitor. Reads well pressure (0–100 psi transducer),
pump motor current (0–5 V current sensor, measured as in the MWP project) and the Hydrawise
flow meter (1 pulse = 1 gallon, isolated tap); converts everything to engineering units on
the device; and publishes spec v1 JSON to HiveMQ Cloud over TLS. Buffers to flash while
offline; publishes 1 s while active, 60 s (+ report-on-change) while idle.

- Design: `../bfwp-spec/docs/07-firmware-design.md`
- Hardware: `../hardware.md`

## Setup
```bash
# ESP-IDF v5.x installed and exported (. $IDF_PATH/export.sh)
cp main/secrets.example.h main/secrets.h     # fill in Wi-Fi + HiveMQ credentials
idf.py set-target esp32c6
idf.py build
idf.py flash monitor
```
