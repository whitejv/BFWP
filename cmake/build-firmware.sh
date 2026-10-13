#!/bin/sh
# Cross-build bfwp-firmware. The default host build does not run this.
set -eu

root=$1

if [ -z "${IDF_PATH:-}" ]; then
  echo "firmware: IDF_PATH is not set. Source the ESP-IDF export script, then run this target again." >&2
  exit 1
fi

if ! command -v idf.py >/dev/null 2>&1; then
  echo "firmware: idf.py is not on PATH. Source \$IDF_PATH/export.sh, then run this target again." >&2
  exit 1
fi

idf.py -C "$root/bfwp-firmware" build
