-- 0004 case reports: crew-reviewed medical reports (contracts/case-report) and their ship to ground queue.
-- id is the report UUID v4 from the assistant reply. Timestamps: UTC, YYYY-MM-DDTHH:MM:SS.ffffffZ.
-- received_at is ground's receipt time from its acknowledgement.

CREATE TABLE case_reports (
  id                     TEXT PRIMARY KEY,
  astronaut_id           TEXT,
  reported_by            TEXT,
  urgency                TEXT NOT NULL,
  protocol_id            TEXT,
  action                 TEXT,
  assessed_at            TEXT NOT NULL,
  created_at             TEXT NOT NULL,
  text                   TEXT NOT NULL,
  readings_json          TEXT NOT NULL,
  knowledge_version_json TEXT,
  incident_id            TEXT,
  status                 TEXT NOT NULL DEFAULT 'draft'
                         CHECK (status IN ('draft','queued','received','failed')),
  sent_by                TEXT,
  queued_at              TEXT,
  received_at            TEXT,
  error                  TEXT
);

CREATE INDEX case_reports_queue ON case_reports (queued_at) WHERE status = 'queued';
