-- 0001 baseline: onboard monitoring schema and provisional sensor configuration.
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

INSERT INTO sensor_config (kind, unit, stale_after_seconds, normal_min, normal_max,
                           range_role, provisional, range_source, updated_at)
SELECT column1, column2, column3, column4, column5, column6, 1, column7,
       strftime('%Y-%m-%dT%H:%M:%S', 'now') || '.000000Z'
FROM (VALUES
  ('heart_rate',             'bpm',     300,    60,   100,  'health',          'AHA / Mayo Clinic'),
  ('spo2',                   '%',       300,    95,   100,  'health',          'Mayo Clinic'),
  ('muscle_density',         NULL,      604800, NULL, NULL, 'health',          NULL),
  ('urine_ph',               'pH',      86400,  4.6,  8.0,  'health',          'MedlinePlus'),
  ('urine_salinity',         NULL,      86400,  NULL, NULL, 'health',          NULL),
  ('urine_color',            'rgb_hex', 86400,  NULL, NULL, 'health',          NULL),
  ('urine_temperature',      '°C',      86400,  32,   38,   'sample_validity', '49 CFR 40.65'),
  ('urine_radiation_marker', NULL,      86400,  NULL, NULL, 'health',          NULL)
);
