#!/bin/sh
# Unload the ingest LaunchAgent.
set -eu

LABEL=com.bfwp.ingest
DOMAIN="gui/$(id -u)"

if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "$DOMAIN/$LABEL"
  echo "bfwp-stop: $LABEL unloaded"
else
  echo "bfwp-stop: $LABEL is not loaded"
fi
