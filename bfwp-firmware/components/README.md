# Components

- `bfwp_core/` — pure logic (calibration, flow/gpm, cadence, events, seq, buffer, JSON).
  No ESP-IDF calls, so it builds and unit-tests on the Mac.
- `bfwp_hal/` — ESP-IDF drivers and services: ADC (ADS1x15), flow input (GPIO ISR + PCNT),
  One-Wire temperature, fan, Wi-Fi, MQTT (TLS), NVS settings, offline storage, OTA.

Most of `bfwp_hal` starts from the MWPSensors components — see the reuse table in
`bfwp-spec/docs/07-firmware-design.md`. Each component gets its own `CMakeLists.txt`
(`idf_component_register`) when code is added.
