"""bfwp-ingest command line. load reads a file; run subscribes to bfwp-sim/#."""

from __future__ import annotations

import argparse
import os
import threading
from pathlib import Path

from bfwp_ingest.live import LiveIngest, load_ingest_config
from bfwp_ingest.load import load_jsonl
from bfwp_ingest.store import count_rows


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
    args = parser.parse_args(argv)
    db_path = _db_path(args.db)
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


def _db_path(given: Path | None) -> Path:
    if given is not None:
        return given
    default = os.environ.get("SIM_DB_PATH", "~/BFWP-data/well-sim.db")
    return Path(default).expanduser()


if __name__ == "__main__":
    raise SystemExit(main())
