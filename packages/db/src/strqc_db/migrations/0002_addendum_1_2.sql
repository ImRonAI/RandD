-- 0002: Addendum-1 (report delivery, photo report inclusion) and
--       Addendum-2 (Escapia integration surface) schema extensions.
-- See AGENTS.md "Addendum 1" and "Addendum 2"; tracked as TASKS.md M1.2–M1.5.

PRAGMA foreign_keys = ON;

-- ── Addendum 1: report delivery ────────────────────────────────────────────
ALTER TABLE report ADD COLUMN delivery_channel TEXT NOT NULL DEFAULT 'SLACK'
  CHECK (delivery_channel IN ('SLACK', 'EMAIL', 'TEAMS'));
ALTER TABLE report ADD COLUMN delivered_at TEXT;
ALTER TABLE report ADD COLUMN delivery_status TEXT NOT NULL DEFAULT 'PENDING'
  CHECK (delivery_status IN ('PENDING', 'SENT', 'FAILED'));

-- Addendum 1: photo report inclusion
ALTER TABLE photo_memory ADD COLUMN include_in_report INTEGER NOT NULL DEFAULT 0
  CHECK (include_in_report IN (0, 1));

-- ── Addendum 2: Escapia native identifiers ─────────────────────────────────
ALTER TABLE property ADD COLUMN escapia_unit_native_pms_id TEXT;
ALTER TABLE property ADD COLUMN escapia_pmc_id TEXT;
ALTER TABLE task ADD COLUMN escapia_reservation_native_pms_id TEXT;
ALTER TABLE task ADD COLUMN escapia_housekeeping_task_native_pms_id TEXT;
ALTER TABLE work_order ADD COLUMN escapia_work_order_native_pms_id TEXT;
ALTER TABLE stakeholder ADD COLUMN escapia_owner_native_pms_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_property_escapia_unit
  ON property (escapia_pmc_id, escapia_unit_native_pms_id)
  WHERE escapia_unit_native_pms_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_task_escapia_reservation
  ON task (escapia_reservation_native_pms_id)
  WHERE escapia_reservation_native_pms_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_work_order_escapia
  ON work_order (escapia_work_order_native_pms_id)
  WHERE escapia_work_order_native_pms_id IS NOT NULL;

-- ── Addendum 2: sync cursors (delta for Reservations, poll for the rest) ───
CREATE TABLE IF NOT EXISTS sync_cursor (
  sync_cursor_id INTEGER PRIMARY KEY,
  pmc_id TEXT NOT NULL,
  resource TEXT NOT NULL CHECK (resource IN
    ('RESERVATIONS', 'UNITS', 'OWNERS', 'HOUSEKEEPING', 'WORK_ORDERS', 'GUESTS')),
  start_version INTEGER,          -- Reservations delta feed cursor
  last_polled_at TEXT,            -- poll-based resources
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (pmc_id, resource)
);

-- ── Addendum 2: per-PMC housekeeping status mapping (never hardcode) ───────
CREATE TABLE IF NOT EXISTS housekeeping_status_map (
  housekeeping_status_map_id INTEGER PRIMARY KEY,
  pmc_id TEXT NOT NULL,
  stage_definition_id INTEGER NOT NULL,
  escapia_clean_status_id TEXT NOT NULL,
  escapia_status_label TEXT,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (pmc_id, stage_definition_id),
  FOREIGN KEY (stage_definition_id) REFERENCES stage_definition(stage_definition_id)
    ON DELETE CASCADE ON UPDATE CASCADE
);
