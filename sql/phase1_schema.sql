PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cluster (
  cluster_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT
);

CREATE TABLE IF NOT EXISTS property (
  property_id INTEGER PRIMARY KEY,
  unit_code TEXT NOT NULL UNIQUE,
  display_name TEXT,
  address_line_1 TEXT,
  city TEXT,
  state_province TEXT,
  postal_code TEXT,
  wifi_ssid TEXT,
  wifi_password TEXT,
  wifi_raw TEXT,
  door_code TEXT,
  qc_assignee_name TEXT,
  has_hot_tub INTEGER NOT NULL DEFAULT 0 CHECK (has_hot_tub IN (0, 1)),
  has_tv INTEGER NOT NULL DEFAULT 0 CHECK (has_tv IN (0, 1)),
  has_ev_charger INTEGER NOT NULL DEFAULT 0 CHECK (has_ev_charger IN (0, 1)),
  standing_instructions TEXT,
  cluster_id INTEGER,
  roster_active INTEGER NOT NULL DEFAULT 1 CHECK (roster_active IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (cluster_id) REFERENCES cluster(cluster_id)
);

CREATE TABLE IF NOT EXISTS stakeholder (
  stakeholder_id INTEGER PRIMARY KEY,
  full_name TEXT NOT NULL,
  email TEXT,
  phone TEXT,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS role (
  role_id INTEGER PRIMARY KEY,
  role_key TEXT NOT NULL UNIQUE,
  role_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stakeholder_role (
  stakeholder_role_id INTEGER PRIMARY KEY,
  stakeholder_id INTEGER NOT NULL,
  role_id INTEGER NOT NULL,
  property_id INTEGER,
  UNIQUE (stakeholder_id, role_id, property_id),
  FOREIGN KEY (stakeholder_id) REFERENCES stakeholder(stakeholder_id),
  FOREIGN KEY (role_id) REFERENCES role(role_id),
  FOREIGN KEY (property_id) REFERENCES property(property_id)
);

CREATE TABLE IF NOT EXISTS notification_trigger (
  trigger_id INTEGER PRIMARY KEY,
  event_key TEXT NOT NULL UNIQUE,
  description TEXT NOT NULL,
  default_role_key TEXT NOT NULL,
  FOREIGN KEY (default_role_key) REFERENCES role(role_key)
);

CREATE TABLE IF NOT EXISTS task (
  task_id INTEGER PRIMARY KEY,
  property_id INTEGER NOT NULL,
  arrival_date TEXT,
  assigned_housekeeper_name TEXT,
  current_stage TEXT,
  source_row_number INTEGER,
  source_system TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (property_id) REFERENCES property(property_id)
);

CREATE TABLE IF NOT EXISTS task_stage_event (
  stage_event_id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  stage_key TEXT NOT NULL CHECK (stage_key IN ('QC', 'B2B', 'CLN', 'DONE', 'OWN', 'WO', 'DONE_WO', 'REPORT')),
  is_complete INTEGER NOT NULL CHECK (is_complete IN (0, 1)),
  completed_at TEXT,
  completed_by_stakeholder_id INTEGER,
  source_value TEXT,
  UNIQUE (task_id, stage_key),
  FOREIGN KEY (task_id) REFERENCES task(task_id),
  FOREIGN KEY (completed_by_stakeholder_id) REFERENCES stakeholder(stakeholder_id)
);

CREATE TABLE IF NOT EXISTS checklist_template (
  checklist_template_id INTEGER PRIMARY KEY,
  template_name TEXT NOT NULL,
  version_label TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (template_name, version_label)
);

CREATE TABLE IF NOT EXISTS checklist_category (
  checklist_category_id INTEGER PRIMARY KEY,
  checklist_template_id INTEGER NOT NULL,
  category_name TEXT NOT NULL,
  display_order INTEGER NOT NULL,
  UNIQUE (checklist_template_id, category_name),
  FOREIGN KEY (checklist_template_id) REFERENCES checklist_template(checklist_template_id)
);

CREATE TABLE IF NOT EXISTS checklist_item_template (
  checklist_item_template_id INTEGER PRIMARY KEY,
  checklist_category_id INTEGER NOT NULL,
  item_text TEXT NOT NULL,
  display_order INTEGER NOT NULL,
  required_photo INTEGER NOT NULL DEFAULT 0 CHECK (required_photo IN (0, 1)),
  UNIQUE (checklist_category_id, item_text),
  FOREIGN KEY (checklist_category_id) REFERENCES checklist_category(checklist_category_id)
);

CREATE TABLE IF NOT EXISTS inspection (
  inspection_id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  checklist_template_id INTEGER NOT NULL,
  inspector_stakeholder_id INTEGER,
  started_at TEXT,
  submitted_at TEXT,
  FOREIGN KEY (task_id) REFERENCES task(task_id),
  FOREIGN KEY (checklist_template_id) REFERENCES checklist_template(checklist_template_id),
  FOREIGN KEY (inspector_stakeholder_id) REFERENCES stakeholder(stakeholder_id)
);

CREATE TABLE IF NOT EXISTS inspection_item_result (
  inspection_item_result_id INTEGER PRIMARY KEY,
  inspection_id INTEGER NOT NULL,
  checklist_item_template_id INTEGER NOT NULL,
  result TEXT NOT NULL CHECK (result IN ('PASS', 'FAIL', 'NA')),
  photo_uri TEXT,
  notes TEXT,
  observed_at TEXT NOT NULL DEFAULT (datetime('now')),
  inspector_stakeholder_id INTEGER,
  FOREIGN KEY (inspection_id) REFERENCES inspection(inspection_id),
  FOREIGN KEY (checklist_item_template_id) REFERENCES checklist_item_template(checklist_item_template_id),
  FOREIGN KEY (inspector_stakeholder_id) REFERENCES stakeholder(stakeholder_id)
);

CREATE TABLE IF NOT EXISTS work_order (
  work_order_id INTEGER PRIMARY KEY,
  task_id INTEGER,
  property_id INTEGER NOT NULL,
  inspection_item_result_id INTEGER,
  status TEXT NOT NULL CHECK (status IN ('NEW', 'ASSIGNED', 'IN_PROGRESS', 'BLOCKED', 'DONE', 'CANCELLED')),
  priority TEXT NOT NULL DEFAULT 'MEDIUM' CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')),
  assigned_facilities_stakeholder_id INTEGER,
  opened_at TEXT NOT NULL DEFAULT (datetime('now')),
  closed_at TEXT,
  details TEXT,
  FOREIGN KEY (task_id) REFERENCES task(task_id),
  FOREIGN KEY (property_id) REFERENCES property(property_id),
  FOREIGN KEY (inspection_item_result_id) REFERENCES inspection_item_result(inspection_item_result_id),
  FOREIGN KEY (assigned_facilities_stakeholder_id) REFERENCES stakeholder(stakeholder_id)
);

CREATE TABLE IF NOT EXISTS report (
  report_id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  property_id INTEGER NOT NULL,
  checklist_template_id INTEGER,
  ready_for_guests INTEGER NOT NULL CHECK (ready_for_guests IN (0, 1)),
  signed_off_by_stakeholder_id INTEGER,
  signed_off_at TEXT,
  export_uri TEXT,
  summary_text TEXT,
  FOREIGN KEY (task_id) REFERENCES task(task_id),
  FOREIGN KEY (property_id) REFERENCES property(property_id),
  FOREIGN KEY (checklist_template_id) REFERENCES checklist_template(checklist_template_id),
  FOREIGN KEY (signed_off_by_stakeholder_id) REFERENCES stakeholder(stakeholder_id)
);

CREATE TABLE IF NOT EXISTS migration_issue (
  migration_issue_id INTEGER PRIMARY KEY,
  issue_type TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('INFO', 'WARN', 'ERROR')),
  source_name TEXT NOT NULL,
  row_number INTEGER,
  property_code TEXT,
  message TEXT NOT NULL,
  raw_payload TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO role (role_key, role_name)
VALUES
  ('OWNER', 'Owner'),
  ('HOUSEKEEPER', 'Housekeeper'),
  ('FACILITIES', 'Facilities / Maintenance'),
  ('QC_INSPECTOR', 'QC Inspector'),
  ('PROPERTY_MANAGER', 'Property Manager'),
  ('OFFICE_DISPATCH', 'Office / Dispatch');

INSERT OR IGNORE INTO notification_trigger (event_key, description, default_role_key)
VALUES
  ('CHECKLIST_ITEM_FAILED', 'Checklist item failed and requires action.', 'FACILITIES'),
  ('TASK_READY_FOR_OWNER_REVIEW', 'Task has completed enough stages for owner review.', 'OWNER'),
  ('WORK_ORDER_BLOCKED', 'Work order blocked and needs escalation.', 'OFFICE_DISPATCH'),
  ('REPORT_SIGN_OFF_PENDING', 'Report generated and waiting for sign-off.', 'PROPERTY_MANAGER');
