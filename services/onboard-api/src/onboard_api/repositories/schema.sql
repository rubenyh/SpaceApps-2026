-- Schema version 1. Applied by onboard_api.repositories.database.init_db
-- inside one transaction when PRAGMA user_version is 0.
-- All timestamps are UTC, fixed-width ISO 8601: YYYY-MM-DDTHH:MM:SS.ffffffZ

CREATE TABLE astronauts (
  id           TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  created_at   TEXT NOT NULL
);

CREATE TABLE sensor_config (
  kind                TEXT PRIMARY KEY,
  unit                TEXT,
  stale_after_seconds INTEGER,
  normal_min          REAL,
  normal_max          REAL,
  range_role          TEXT NOT NULL DEFAULT 'health'
                      CHECK (range_role IN ('health','sample_validity')),
  provisional         INTEGER NOT NULL DEFAULT 1,
  range_source        TEXT,
  updated_at          TEXT NOT NULL
);

CREATE TABLE readings (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  astronaut_id TEXT NOT NULL REFERENCES astronauts(id),
  kind         TEXT NOT NULL REFERENCES sensor_config(kind),
  value        REAL,
  value_text   TEXT,
  unit         TEXT NOT NULL,
  recorded_at  TEXT NOT NULL,
  received_at  TEXT NOT NULL,
  quality      TEXT NOT NULL CHECK (quality IN ('good','suspect','bad')),
  source       TEXT NOT NULL,
  CHECK ((value IS NULL) <> (value_text IS NULL))
);

CREATE INDEX idx_readings_lookup ON readings (astronaut_id, kind, recorded_at DESC);

PRAGMA user_version = 1;
