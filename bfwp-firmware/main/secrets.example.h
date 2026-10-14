// Copy to main/secrets.h (gitignored) and fill in. Never commit real credentials.
#pragma once
#define WIFI_SSID      "well-house-ssid"
#define WIFI_PASSWORD  ""
// Public HiveMQ broker. It does not check the username or password.
// A private broker later is a new URI plus a password here.
#define MQTT_URI       "mqtts://broker.hivemq.com:8883"
#define MQTT_USERNAME  "bfwp-well1"     // ignored by the public broker; publish-only on a private one
#define MQTT_PASSWORD  ""
#define DEVICE_ID      "well1"
#define TOPIC_ROOT     "bfwp"
