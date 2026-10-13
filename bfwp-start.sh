#!/bin/sh
# Load the ingest LaunchAgent. launchd is the parent; this script does not background the process.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
LABEL=com.bfwp.ingest
INGEST_DIR="$ROOT/bfwp-ingest"
INGEST_BIN="$INGEST_DIR/.venv/bin/bfwp-ingest"
TEMPLATE="$INGEST_DIR/launchd/com.bfwp.ingest.plist.example"
LOG_DIR="${HOME}/BFWP-data/logs"
AGENTS="${HOME}/Library/LaunchAgents"
PLIST="$AGENTS/${LABEL}.plist"
DOMAIN="gui/$(id -u)"

if [ ! -x "$INGEST_BIN" ]; then
  echo "bfwp-start: $INGEST_BIN is missing." >&2
  echo "Build the host apps first:" >&2
  echo "  cmake -S \"$ROOT\" -B \"$ROOT/build\" && cmake --build \"$ROOT/build\"" >&2
  echo "bfwp-ingest is installed once bfwp-ingest/pyproject.toml exists." >&2
  exit 1
fi

mkdir -p "$LOG_DIR" "$AGENTS"

python3 - "$TEMPLATE" "$PLIST" "$INGEST_BIN" "$INGEST_DIR" "$LOG_DIR" <<'PY'
import sys
from pathlib import Path

template, dest, bin_path, workdir, log_dir = sys.argv[1:]
text = Path(template).read_text()
for key, value in (
    ("@INGEST_BIN@", bin_path),
    ("@INGEST_DIR@", workdir),
    ("@LOG_DIR@", log_dir),
):
    text = text.replace(key, value)
Path(dest).write_text(text)
PY

if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "$DOMAIN/$LABEL"
fi

launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl enable "$DOMAIN/$LABEL"
launchctl kickstart -k "$DOMAIN/$LABEL"
echo "bfwp-start: $LABEL loaded ($DOMAIN)"
echo "logs: $LOG_DIR/ingest.log"
