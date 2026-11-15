-- 0003 incident origin: where the urgent call came from and which readings it showed.
-- Rows created before this version keep reported_via NULL and reading_ids_json '[]'.

ALTER TABLE incidents ADD COLUMN reported_via TEXT CHECK (reported_via IN ('console','watch'));
ALTER TABLE incidents ADD COLUMN reading_ids_json TEXT NOT NULL DEFAULT '[]';
