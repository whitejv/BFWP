-- BFWP reference SQLite schema, v1.
-- Owned and migrated by bfwp-ingest (sole writer). bfwp-mcp opens read-only.
-- All *_ts columns are UTC epoch milliseconds.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', '1');

-- Raw telemetry, one row per reading (single or batch item).
CREATE TABLE IF NOT EXISTS readings (
  dev         TEXT    NOT NULL,
  seq         INTEGER NOT NULL,
  ts          INTEGER NOT NULL,
  psi         REAL,               -- NULL while sensor faulted
  amps        REAL,
  pump        INTEGER NOT NULL,   -- 0/1
  gal_total   INTEGER NOT NULL,
  gpm         REAL    NOT NULL,
  received_ts INTEGER NOT NULL,   -- Mac receive time (diagnostics only)
  PRIMARY KEY (dev, seq)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_readings_dev_ts ON readings(dev, ts);

-- Device events; data is the JSON object from the message.
CREATE TABLE IF NOT EXISTS events (
  dev         TEXT    NOT NULL,
  seq         INTEGER NOT NULL,
  ts          INTEGER NOT NULL,
  type        TEXT    NOT NULL,
  data        TEXT    NOT NULL,   -- JSON
  received_ts INTEGER NOT NULL,
  PRIMARY KEY (dev, seq)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_events_dev_ts   ON events(dev, ts);
CREATE INDEX IF NOT EXISTS idx_events_type_ts  ON events(type, ts);

-- Online/offline history (from retained status + Last Will).
CREATE TABLE IF NOT EXISTS status_log (
  dev         TEXT    NOT NULL,
  received_ts INTEGER NOT NULL,
  online      INTEGER NOT NULL,
  fw          TEXT,
  rssi        INTEGER,
  PRIMARY KEY (dev, received_ts)
);

-- Derived: one row per pump cycle (from pump_on/pump_off events, rebuilt from readings if needed).
CREATE TABLE IF NOT EXISTS pump_cycles (
  dev       TEXT    NOT NULL,
  start_ts  INTEGER NOT NULL,
  end_ts    INTEGER,              -- NULL while running
  duration_s REAL,
  gallons   INTEGER,
  psi_avg   REAL, psi_min REAL, psi_max REAL,
  amps_avg  REAL, amps_max REAL,
  PRIMARY KEY (dev, start_ts)
);

-- Derived: per-minute rollup for fast long-range queries.
CREATE TABLE IF NOT EXISTS readings_1min (
  dev        TEXT    NOT NULL,
  minute_ts  INTEGER NOT NULL,    -- start of minute, UTC ms
  n          INTEGER NOT NULL,    -- readings in the minute
  psi_avg    REAL, psi_min REAL, psi_max REAL,
  amps_avg   REAL, amps_max REAL,
  pump_secs  REAL NOT NULL,       -- seconds the pump was on
  gallons    INTEGER NOT NULL,    -- gal_total delta within the minute
  PRIMARY KEY (dev, minute_ts)
) WITHOUT ROWID;

-- Hydrawise zone runs (actual, from run history), synced by ingest.
CREATE TABLE IF NOT EXISTS zone_runs (
  controller_id TEXT    NOT NULL,
  zone_id       TEXT    NOT NULL,
  zone_name     TEXT,
  start_ts      INTEGER NOT NULL,
  end_ts        INTEGER NOT NULL,
  source        TEXT    NOT NULL DEFAULT 'hydrawise',  -- or 'twin' in the sim DB
  PRIMARY KEY (controller_id, zone_id, start_ts)
);
CREATE INDEX IF NOT EXISTS idx_zone_runs_time ON zone_runs(start_ts, end_ts);

-- Messages that failed validation (kept for debugging, pruned after 30 days).
CREATE TABLE IF NOT EXISTS rejects (
  received_ts INTEGER NOT NULL,
  topic       TEXT    NOT NULL,
  payload     TEXT    NOT NULL,
  error       TEXT    NOT NULL
);
