-- 0002 incidents: urgent medical incidents and their event history (also the ground telemetry queue).
-- Ids are UUID v4 text generated onboard. Timestamps: UTC, YYYY-MM-DDTHH:MM:SS.ffffffZ.

CREATE TABLE incidents (
  id                      TEXT PRIMARY KEY,
  trigger_key             TEXT NOT NULL,
  status                  TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
  astronaut_id            TEXT,
  reported_by             TEXT,
  began_at                TEXT NOT NULL,
  closed_at               TEXT,
  urgency                 TEXT NOT NULL,
  action                  TEXT,
  protocol_id             TEXT,
  steps_json              TEXT NOT NULL,
  matched_rules_json      TEXT NOT NULL,
  findings_json           TEXT NOT NULL,
  data_notices_json       TEXT NOT NULL,
  mission_procedures_json TEXT NOT NULL,
  missing_guidance_json   TEXT NOT NULL
);

CREATE UNIQUE INDEX incidents_open_trigger ON incidents (trigger_key) WHERE status = 'open';

CREATE TABLE incident_events (
  id              TEXT PRIMARY KEY,
  incident_id     TEXT NOT NULL REFERENCES incidents(id),
  type            TEXT NOT NULL CHECK (type IN ('created','acknowledged','closed')),
  occurred_at     TEXT NOT NULL,
  acknowledged_by TEXT REFERENCES astronauts(id),
  delivered_at    TEXT
);

CREATE UNIQUE INDEX incident_events_created ON incident_events (incident_id) WHERE type = 'created';
CREATE UNIQUE INDEX incident_events_ack ON incident_events (incident_id, acknowledged_by)
  WHERE type = 'acknowledged';
CREATE INDEX incident_events_queue ON incident_events (occurred_at) WHERE delivered_at IS NULL;
