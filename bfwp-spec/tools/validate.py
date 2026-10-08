#!/usr/bin/env python3
"""Validate BFWP contracts.

- Every file in contracts/examples/v1/ must validate against its schema.
- Every file in contracts/examples/v1/invalid/ must FAIL validation.
- Every scenario timeline action must be a valid sim command.
- The reference SQLite schema must load.

Requires: jsonschema (and PyYAML for scenarios).  Run: python3 tools/validate.py
"""
import json, sqlite3, sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent / "contracts"
SCHEMAS = ROOT / "schemas" / "v1"
EXAMPLES = ROOT / "examples" / "v1"

# Filename prefix -> schema (longest prefix first).
PREFIXES = [
    ("telemetry-batch", "telemetry-batch.schema.json"),
    ("telemetry", "telemetry.schema.json"),
    ("event", "event.schema.json"),
    ("status", "status.schema.json"),
    ("sim-command", "sim-command.schema.json"),
]


def load_schemas():
    out = {}
    for p in SCHEMAS.glob("*.schema.json"):
        s = json.loads(p.read_text())
        jsonschema.Draft7Validator.check_schema(s)
        out[p.name] = jsonschema.Draft7Validator(s)
    return out


def schema_for(name):
    for prefix, schema in PREFIXES:
        if name.startswith(prefix):
            return schema
    raise SystemExit(f"No schema mapping for {name}")


def main():
    validators = load_schemas()
    failures = 0

    for p in sorted(EXAMPLES.glob("*.json")):
        errs = list(validators[schema_for(p.name)].iter_errors(json.loads(p.read_text())))
        if errs:
            failures += 1
            print(f"FAIL  {p.name}: {errs[0].message}")
        else:
            print(f"ok    {p.name}")

    for p in sorted((EXAMPLES / "invalid").glob("*.json")):
        errs = list(validators[schema_for(p.name)].iter_errors(json.loads(p.read_text())))
        if errs:
            print(f"ok    invalid/{p.name} (rejected: {errs[0].message[:60]})")
        else:
            failures += 1
            print(f"FAIL  invalid/{p.name}: was accepted but should be rejected")

    try:
        import yaml
    except ImportError:
        print("skip  scenarios (PyYAML not installed)")
    else:
        cmd = validators["sim-command.schema.json"]
        for p in sorted((ROOT / "scenarios").glob("*.yaml")):
            sc = yaml.safe_load(p.read_text())
            bad = []
            for step in sc.get("timeline", []):
                actions = {k: v for k, v in step.items() if k != "at"}
                for name, args in actions.items():
                    msg = {"cmd": name}
                    if args:
                        msg["args"] = args
                    bad += [f"{step.get('at')} {name}: {e.message}" for e in cmd.iter_errors(msg)]
            for key in ("name", "device", "start", "end", "timeline", "expect"):
                if key not in sc:
                    bad.append(f"missing '{key}'")
            if bad:
                failures += 1
                print(f"FAIL  scenario {p.name}: {bad[0]}")
            else:
                print(f"ok    scenario {p.name}")

    db = sqlite3.connect(":memory:")
    try:
        db.executescript((ROOT / "sqlite" / "schema-v1.sql").read_text())
        tables = [r[0] for r in db.execute("select name from sqlite_master where type='table' order by 1")]
        print(f"ok    sqlite schema ({len(tables)} tables: {', '.join(tables)})")
    except sqlite3.Error as e:
        failures += 1
        print(f"FAIL  sqlite schema: {e}")

    print("\nAll contracts valid." if not failures else f"\n{failures} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
