-- D1 schema. The Worker creates these on first request; this file is here so
-- you can read the shape without running it, or apply it by hand with:
--   wrangler d1 execute <DB_NAME> --remote --file=worker/schema.sql

CREATE TABLE IF NOT EXISTS metric_daily (
     metric TEXT NOT NULL, day TEXT NOT NULL, unit TEXT,
     value REAL, mn REAL, mx REAL, cnt INTEGER, src TEXT,
     updated_at INTEGER, PRIMARY KEY (metric, day));

CREATE INDEX IF NOT EXISTS idx_metric_daily_day ON metric_daily(day);

CREATE TABLE IF NOT EXISTS sleep_daily (
     day TEXT PRIMARY KEY, core REAL, deep REAL, rem REAL, awake REAL,
     in_bed REAL, updated_at INTEGER);

CREATE TABLE IF NOT EXISTS workouts (
     id TEXT PRIMARY KEY, day TEXT, type TEXT, duration_min REAL,
     distance_km REAL, energy_kcal REAL, avg_hr REAL, source TEXT);

CREATE INDEX IF NOT EXISTS idx_workouts_day ON workouts(day);

CREATE TABLE IF NOT EXISTS hsample (
     metric TEXT NOT NULL, ts INTEGER NOT NULL, end_ts INTEGER NOT NULL,
     src TEXT NOT NULL, day TEXT NOT NULL, unit TEXT, value REAL,
     PRIMARY KEY (metric, ts, end_ts, src));

CREATE INDEX IF NOT EXISTS idx_hsample_metric_day ON hsample(metric, day);
