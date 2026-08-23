#!/bin/sh

set -eu

: "${MQTT_USERNAME:?MQTT_USERNAME missing (check /etc/mosquitto/env)}"
: "${MQTT_PASSWORD:?MQTT_PASSWORD missing (check /etc/mosquitto/env)}"

rm -f /mosquitto/config/passwd
mosquitto_passwd -c -b /mosquitto/config/passwd "$MQTT_USERNAME" "$MQTT_PASSWORD"

exec mosquitto -c /mosquitto/config/mosquitto.conf
