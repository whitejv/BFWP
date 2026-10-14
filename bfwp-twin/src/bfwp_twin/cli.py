"""bfwp-twin command line. Runs a scenario and, with --mqtt, publishes to HiveMQ."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bfwp_twin.mqtt import load_mqtt_config, publish_records
from bfwp_twin.simulate import run_offline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bfwp-twin")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="integrate a scenario and write its truth log and message file")
    run.add_argument("scenario", type=Path)
    run.add_argument(
        "--truth-log-dir",
        type=Path,
        default=None,
        help="directory for the JSONL truth log (default: bfwp-twin/truth-logs)",
    )
    run.add_argument(
        "--mqtt",
        action="store_true",
        help="also publish the message file to HiveMQ (bfwp-twin/.env or the public broker)",
    )
    args = parser.parse_args(argv)
    result = run_offline(args.scenario, truth_log_dir=args.truth_log_dir)
    print(result.physics.truth_log_path)
    print(result.messages_path)
    if args.mqtt:
        config = load_mqtt_config()
        try:
            publish_records(result.records, config)
        except Exception as exc:
            print(f"mqtt publish failed: {exc}", file=sys.stderr)
            return 1
        print(f"published {len(result.records)} messages to {config.describe()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
