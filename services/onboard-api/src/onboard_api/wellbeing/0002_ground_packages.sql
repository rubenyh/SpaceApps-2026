-- Wellbeing schema version 2: packages for the ground psychologist.
-- Created only with explicit astronaut consent; queued on board, never sent
-- automatically. body: the GroundPackageCreate JSON as received.

CREATE TABLE ground_packages (
  id                  TEXT PRIMARY KEY,
  astronaut_id        TEXT NOT NULL,
  body                TEXT NOT NULL,
  status              TEXT NOT NULL CHECK (status IN ('queued','withdrawn','sent')),
  consent_recorded_at TEXT NOT NULL,
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL
);
CREATE INDEX idx_ground_packages_astronaut ON ground_packages (astronaut_id, created_at);

PRAGMA user_version = 2;
