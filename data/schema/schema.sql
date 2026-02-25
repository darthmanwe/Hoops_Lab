-- HoopsLab initial schema placeholder.
-- Full canonical schema will be added in the implementation phase.

CREATE TABLE IF NOT EXISTS etl_runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  notes TEXT
);
