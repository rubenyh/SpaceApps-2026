-- Wellbeing database (wellbeing.db), version 1. Separate file from onboard.db.
-- Applied by onboard_api.repositories.database.init_db, which also writes
-- PRAGMA user_version. Timestamps: UTC YYYY-MM-DDTHH:MM:SS.ffffffZ.
-- Days: YYYY-MM-DD (UTC mission day). astronaut_id refers to onboard.db
-- (or is "unknown-<track>"), so there are no foreign keys to astronauts.
-- No images, video or face templates are ever stored: only derived metrics.

CREATE TABLE checkins (
  astronaut_id    TEXT NOT NULL,
  day             TEXT NOT NULL,
  sleep_hours     REAL NOT NULL,
  sleep_quality   INTEGER NOT NULL CHECK (sleep_quality BETWEEN 0 AND 4),
  energy          INTEGER NOT NULL CHECK (energy BETWEEN 0 AND 4),
  mood            INTEGER NOT NULL CHECK (mood BETWEEN 0 AND 4),
  interest        INTEGER NOT NULL CHECK (interest BETWEEN 0 AND 4),
  stress          INTEGER NOT NULL CHECK (stress BETWEEN 0 AND 4),
  crew_connection INTEGER NOT NULL CHECK (crew_connection BETWEEN 0 AND 4),
  comment         TEXT,
  source          TEXT NOT NULL,
  submitted_at    TEXT NOT NULL,
  PRIMARY KEY (astronaut_id, day)
);

CREATE TABLE signals (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  astronaut_id TEXT NOT NULL,
  kind         TEXT NOT NULL,
  value        REAL NOT NULL,
  unit         TEXT NOT NULL,
  recorded_at  TEXT NOT NULL,
  received_at  TEXT NOT NULL,
  quality      TEXT NOT NULL CHECK (quality IN ('good','suspect','bad')),
  source       TEXT NOT NULL
);
CREATE INDEX idx_signals_lookup ON signals (astronaut_id, recorded_at);

-- body: the full VisionSessionCreate JSON as received (validated by the API).
CREATE TABLE vision_sessions (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  astronaut_id TEXT NOT NULL,
  started_at   TEXT NOT NULL,
  body         TEXT NOT NULL,
  received_at  TEXT NOT NULL
);
CREATE INDEX idx_vision_lookup ON vision_sessions (astronaut_id, started_at);

-- body: the full CoPresenceCreate JSON. Members index who appears in it.
CREATE TABLE co_presence (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  window_start TEXT NOT NULL,
  body         TEXT NOT NULL,
  received_at  TEXT NOT NULL
);

CREATE TABLE co_presence_members (
  window_id    INTEGER NOT NULL REFERENCES co_presence(id) ON DELETE CASCADE,
  astronaut_id TEXT NOT NULL,
  PRIMARY KEY (window_id, astronaut_id)
);
CREATE INDEX idx_co_presence_member ON co_presence_members (astronaut_id);
