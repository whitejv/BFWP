"""Validate payloads against the spec v1 schemas."""

from __future__ import annotations

import json

import jsonschema

from bfwp_ingest.db import SCHEMAS

_KINDS = {
    "telemetry": "telemetry.schema.json",
    "batch": "telemetry-batch.schema.json",
    "event": "event.schema.json",
    "health": "health.schema.json",
    "status": "status.schema.json",
}


def load_validators() -> dict[str, jsonschema.Draft7Validator]:
    validators = {}
    for kind, name in _KINDS.items():
        schema = json.loads((SCHEMAS / name).read_text())
        validators[kind] = jsonschema.Draft7Validator(schema)
    return validators


def explain(validator: jsonschema.Draft7Validator, payload: dict) -> str | None:
    errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.path))
    if not errors:
        return None
    err = errors[0]
    path = ".".join(str(part) for part in err.path)
    return f"{path}: {err.message}" if path else err.message
