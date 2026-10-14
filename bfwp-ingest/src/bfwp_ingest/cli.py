"""bfwp-ingest command line. load reads a file; run subscribes to bfwp-sim/#."""

from __future__ import annotations

import argparse
import os
import threading
from pathlib import Path

from bfwp_ingest.hydrawise import sync_zone_runs
from bfwp_ingest.live import LiveIngest, load_ingest_config
from bfwp_ingest.load import load_jsonl
from bfwp_ingest.store import count_rows
from bfwp_ingest.zones import load_zone_runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bfwp-ingest")
    sub = parser.add_subparsers(dest="cmd", required=True)
    load = sub.add_parser("load", help="load a twin message file into well-sim.db")
    load.add_argument("file", type=Path)
    load.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite file (default: SIM_DB_PATH or ~/BFWP-data/well-sim.db)",
    )
    run = sub.add_parser("run", help="subscribe to bfwp-sim/# and write the sim database")
    run.add_argument("--db", type=Path, default=None)
    zones = sub.add_parser("load-zones", help="load zone_on lines from a truth log into zone_runs")
    zones.add_argument("truth_log", type=Path)
    zones.add_argument("--db", type=Path, default=None)
    sync = sub.add_parser("sync-zones", help="sync Hydrawise zone runs for a time range")
    sync.add_argument("--start-ms", type=int, required=True)
    sync.add_argument("--end-ms", type=int, required=True)
    sync.add_argument("--source", choices=("real", "sim"), default="real")
    sync.add_argument("--db", type=Path, default=None)
    args = parser.parse_args(argv)
    source = getattr(args, "source", "sim")
    db_path = _db_path(args.db, source)
    if args.cmd == "sync-zones":
        counts = sync_zone_runs(
            db_path,
            args.start_ms,
            args.end_ms,
            source=args.source,
            api_key=os.environ.get("HYDRAWISE_API_KEY", ""),
        )
        print(f"fetched {counts['fetched']}")
        print(f"inserted {counts['inserted']}")
        print(f"unchanged {counts['unchanged']}")
        print(f"hydrawise {counts['hydrawise']}")
        return 0
    if args.cmd == "load-zones":
        inserted = load_zone_runs(args.truth_log, db_path)
        print(db_path)
        print(f"zone_runs {inserted}")
        return 0
    if args.cmd == "run":
        live = LiveIngest(db_path, load_ingest_config())
        live.start()
        print(f"ingest subscribed to {live.config.sim_root}/# writing {db_path}")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            live.stop()
        return 0
    store = load_jsonl(args.file, db_path)
    try:
        print(db_path)
        print(
            f"inserted {store.inserted} ignored {store.ignored} rejected {store.rejected} "
            f"readings {count_rows(store.conn, 'readings')} "
            f"recomputes {store.recomputes}"
        )
    finally:
        store.close()
    return 0


def _db_path(given: Path | None, source: str = "sim") -> Path:
    if given is not None:
        return given
    if source == "real":
        default = os.environ.get("DB_PATH", "~/BFWP-data/well.db")
    else:
        default = os.environ.get("SIM_DB_PATH", "~/BFWP-data/well-sim.db")
    return Path(default).expanduser()


if __name__ == "__main__":
    raise SystemExit(main())
