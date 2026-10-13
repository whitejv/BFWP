#!/bin/sh
# Create or refresh one app virtualenv. Skips apps that are not packaged yet.
set -eu

app_dir=$1
name=$(basename "$app_dir")

if [ ! -f "$app_dir/pyproject.toml" ]; then
  echo "$name: no pyproject.toml yet; skipping virtualenv"
  exit 0
fi

python3 -m venv "$app_dir/.venv"
"$app_dir/.venv/bin/python" -m pip install --upgrade pip
( cd "$app_dir" && ./.venv/bin/python -m pip install -e '.[dev]' )
echo "$name: virtualenv ready ($app_dir/.venv)"
