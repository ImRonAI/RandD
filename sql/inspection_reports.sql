-- Turnover-inspection forms, one row per form instance (form_uuid comes from
-- the form itself, minted at first open and preserved across exports).
-- The row is upserted on EVERY form export (live progress while filling) and
-- stamped with S3 URIs + archived_utc when the report is archived.
-- Applied idempotently by backend/app/report_db.py; lives in the shared
-- STRQC sqlite database (STRQC_DB_PATH).
CREATE TABLE IF NOT EXISTS inspection_reports (
    form_uuid TEXT PRIMARY KEY,
    created_utc TEXT NOT NULL,               -- when the form was first opened
    updated_utc TEXT NOT NULL,               -- last export received
    property TEXT,                           -- property/unit name from the form
    signed_off INTEGER NOT NULL DEFAULT 0,   -- 1 when inspector signed off
    items_total INTEGER,                     -- checklist size
    items_done INTEGER,                      -- checklist items completed
    sections INTEGER,                        -- walkthrough sections in the form
    repairs TEXT,                            -- free-text repairs summary
    state_json TEXT NOT NULL,                -- full window.__QC_STATE__ payload
    html_bytes INTEGER,                      -- size of the latest export
    archived_utc TEXT,                       -- set when shipped to S3
    s3_summary_uri TEXT,                     -- searchable digest in the KB bucket
    s3_artifact_uri TEXT                     -- full interactive HTML artifact
);
CREATE INDEX IF NOT EXISTS idx_inspection_reports_property
    ON inspection_reports (property, updated_utc);
