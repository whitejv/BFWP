#!/bin/sh
# Contract validation, then pytest for each Python app that has a virtualenv.
set -eu

root=$1
cd "$root"

spec_py="$root/bfwp-spec/.venv/bin/python"
if [ ! -x "$spec_py" ]; then
  python3 -m venv "$root/bfwp-spec/.venv"
fi
if ! "$spec_py" -c "import jsonschema, yaml" >/dev/null 2>&1; then
  "$spec_py" -m pip install jsonschema PyYAML
fi

echo "validate contracts"
"$spec_py" bfwp-spec/tools/validate.py

for app in bfwp-twin bfwp-ingest bfwp-mcp; do
  pytest="$root/$app/.venv/bin/pytest"
  if [ -x "$pytest" ]; then
    echo "pytest $app"
    "$pytest" "$root/$app"
  else
    echo "$app: no pytest in .venv yet; skipping"
  fi
done
