PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cluster (
  cluster_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT
);

CREATE TABLE IF NOT EXISTS stakeholder (
  stakeholder_id INTEGER PRIMARY KEY,
  full_name TEXT NOT NULL,
  email TEXT,
  phone TEXT,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS role (
  role_id INTEGER PRIMARY KEY,
  role_key TEXT NOT NULL UNIQUE,
  role_name TEXT NOT NULL
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
  wifi_password_ciphertext TEXT,
  wifi_password_secret_ref TEXT,
  door_code_ciphertext TEXT,
  door_code_secret_ref TEXT,
  qc_assignee_stakeholder_id INTEGER,
  standing_instructions TEXT,
  cluster_id INTEGER,
  roster_active INTEGER NOT NULL DEFAULT 1 CHECK (roster_active IN (0, 1)),
  source_system TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (cluster_id) REFERENCES cluster(cluster_id) ON DELETE SET NULL ON UPDATE CASCADE,
  FOREIGN KEY (qc_assignee_stakeholder_id) REFERENCES stakeholder(stakeholder_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS stakeholder_role (
  stakeholder_role_id INTEGER PRIMARY KEY,
  stakeholder_id INTEGER NOT NULL,
  role_id INTEGER NOT NULL,
  property_id INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (stakeholder_id) REFERENCES stakeholder(stakeholder_id) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (role_id) REFERENCES role(role_id) ON DELETE RESTRICT ON UPDATE CASCADE,
  FOREIGN KEY (property_id) REFERENCES property(property_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_stakeholder_role_global_unique
  ON stakeholder_role (stakeholder_id, role_id)
  WHERE property_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_stakeholder_role_property_unique
  ON stakeholder_role (stakeholder_id, role_id, property_id)
  WHERE property_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS notification_trigger (
  trigger_id INTEGER PRIMARY KEY,
  event_key TEXT NOT NULL UNIQUE,
  description TEXT NOT NULL,
  default_role_id INTEGER NOT NULL,
  FOREIGN KEY (default_role_id) REFERENCES role(role_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS stage_definition (
  stage_definition_id INTEGER PRIMARY KEY,
  stage_key TEXT NOT NULL UNIQUE,
  stage_name TEXT NOT NULL,
  display_order INTEGER NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS task (
  task_id INTEGER PRIMARY KEY,
  property_id INTEGER NOT NULL,
  arrival_date TEXT,
  assigned_housekeeper_stakeholder_id INTEGER,
  current_stage_definition_id INTEGER,
  source_row_number INTEGER,
  source_system TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (property_id) REFERENCES property(property_id) ON DELETE RESTRICT ON UPDATE CASCADE,
  FOREIGN KEY (assigned_housekeeper_stakeholder_id) REFERENCES stakeholder(stakeholder_id) ON DELETE SET NULL ON UPDATE CASCADE,
  FOREIGN KEY (current_stage_definition_id) REFERENCES stage_definition(stage_definition_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS task_stage_event (
  stage_event_id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  stage_definition_id INTEGER NOT NULL,
  is_complete INTEGER NOT NULL CHECK (is_complete IN (0, 1)),
  completed_at TEXT,
  completed_by_stakeholder_id INTEGER,
  source_value TEXT,
  UNIQUE (task_id, stage_definition_id),
  FOREIGN KEY (task_id) REFERENCES task(task_id) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (stage_definition_id) REFERENCES stage_definition(stage_definition_id) ON DELETE RESTRICT ON UPDATE CASCADE,
  FOREIGN KEY (completed_by_stakeholder_id) REFERENCES stakeholder(stakeholder_id) ON DELETE SET NULL ON UPDATE CASCADE
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
  FOREIGN KEY (checklist_template_id) REFERENCES checklist_template(checklist_template_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS checklist_item_template (
  checklist_item_template_id INTEGER PRIMARY KEY,
  checklist_category_id INTEGER NOT NULL,
  item_text TEXT NOT NULL,
  display_order INTEGER NOT NULL,
  required_photo INTEGER NOT NULL DEFAULT 0 CHECK (required_photo IN (0, 1)),
  maintenance_required INTEGER NOT NULL DEFAULT 0 CHECK (maintenance_required IN (0, 1)),
  UNIQUE (checklist_category_id, item_text),
  FOREIGN KEY (checklist_category_id) REFERENCES checklist_category(checklist_category_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS photo_memory (
  photo_memory_id INTEGER PRIMARY KEY,
  property_id INTEGER,
  task_id INTEGER,
  inspection_id INTEGER,
  uri TEXT,
  storage_ref TEXT,
  content_hash TEXT,
  caption TEXT,
  captured_at TEXT NOT NULL DEFAULT (datetime('now')),
  metadata_json TEXT,
  FOREIGN KEY (property_id) REFERENCES property(property_id) ON DELETE SET NULL ON UPDATE CASCADE,
  FOREIGN KEY (task_id) REFERENCES task(task_id) ON DELETE SET NULL ON UPDATE CASCADE,
  FOREIGN KEY (inspection_id) REFERENCES inspection(inspection_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS inspection (
  inspection_id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  checklist_template_id INTEGER NOT NULL,
  inspector_stakeholder_id INTEGER,
  started_at TEXT,
  submitted_at TEXT,
  FOREIGN KEY (task_id) REFERENCES task(task_id) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (checklist_template_id) REFERENCES checklist_template(checklist_template_id) ON DELETE RESTRICT ON UPDATE CASCADE,
  FOREIGN KEY (inspector_stakeholder_id) REFERENCES stakeholder(stakeholder_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS inspection_item_result (
  inspection_item_result_id INTEGER PRIMARY KEY,
  inspection_id INTEGER NOT NULL,
  checklist_item_template_id INTEGER NOT NULL,
  result TEXT NOT NULL CHECK (result IN ('PASS', 'FAIL', 'NA')),
  photo_memory_id INTEGER,
  notes TEXT,
  observed_at TEXT NOT NULL DEFAULT (datetime('now')),
  inspector_stakeholder_id INTEGER,
  FOREIGN KEY (inspection_id) REFERENCES inspection(inspection_id) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (checklist_item_template_id) REFERENCES checklist_item_template(checklist_item_template_id) ON DELETE RESTRICT ON UPDATE CASCADE,
  FOREIGN KEY (photo_memory_id) REFERENCES photo_memory(photo_memory_id) ON DELETE SET NULL ON UPDATE CASCADE,
  FOREIGN KEY (inspector_stakeholder_id) REFERENCES stakeholder(stakeholder_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS property_feature_type (
  feature_type_id INTEGER PRIMARY KEY,
  feature_key TEXT NOT NULL UNIQUE,
  feature_name TEXT NOT NULL,
  supports_quantity INTEGER NOT NULL DEFAULT 1 CHECK (supports_quantity IN (0, 1))
);

CREATE TABLE IF NOT EXISTS property_feature (
  property_feature_id INTEGER PRIMARY KEY,
  property_id INTEGER NOT NULL,
  feature_type_id INTEGER NOT NULL,
  location_label TEXT NOT NULL DEFAULT '',
  quantity INTEGER,
  notes TEXT,
  last_verified_at TEXT,
  UNIQUE (property_id, feature_type_id, location_label),
  FOREIGN KEY (property_id) REFERENCES property(property_id) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (feature_type_id) REFERENCES property_feature_type(feature_type_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS maintenance_check (
  maintenance_check_id INTEGER PRIMARY KEY,
  property_feature_id INTEGER NOT NULL,
  check_type TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('PENDING', 'PASS', 'FAIL', 'NA')),
  notes TEXT,
  due_at TEXT,
  completed_at TEXT,
  completed_by_stakeholder_id INTEGER,
  photo_memory_id INTEGER,
  FOREIGN KEY (property_feature_id) REFERENCES property_feature(property_feature_id) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (completed_by_stakeholder_id) REFERENCES stakeholder(stakeholder_id) ON DELETE SET NULL ON UPDATE CASCADE,
  FOREIGN KEY (photo_memory_id) REFERENCES photo_memory(photo_memory_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS work_order (
  work_order_id INTEGER PRIMARY KEY,
  task_id INTEGER,
  property_id INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('NEW', 'ASSIGNED', 'IN_PROGRESS', 'BLOCKED', 'DONE', 'CANCELLED')),
  priority TEXT NOT NULL DEFAULT 'MEDIUM' CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')),
  assigned_facilities_stakeholder_id INTEGER,
  opened_at TEXT NOT NULL DEFAULT (datetime('now')),
  closed_at TEXT,
  details TEXT,
  FOREIGN KEY (task_id) REFERENCES task(task_id) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (property_id) REFERENCES property(property_id) ON DELETE RESTRICT ON UPDATE CASCADE,
  FOREIGN KEY (assigned_facilities_stakeholder_id) REFERENCES stakeholder(stakeholder_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS work_order_source_item (
  work_order_id INTEGER NOT NULL,
  inspection_item_result_id INTEGER NOT NULL,
  PRIMARY KEY (work_order_id, inspection_item_result_id),
  FOREIGN KEY (work_order_id) REFERENCES work_order(work_order_id) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (inspection_item_result_id) REFERENCES inspection_item_result(inspection_item_result_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS report (
  report_id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  property_id INTEGER NOT NULL,
  inspection_id INTEGER,
  ready_for_guests INTEGER NOT NULL CHECK (ready_for_guests IN (0, 1)),
  signed_off_by_stakeholder_id INTEGER,
  signed_off_at TEXT,
  export_uri TEXT,
  summary_text TEXT,
  generated_by_model TEXT,
  FOREIGN KEY (task_id) REFERENCES task(task_id) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (property_id) REFERENCES property(property_id) ON DELETE RESTRICT ON UPDATE CASCADE,
  FOREIGN KEY (inspection_id) REFERENCES inspection(inspection_id) ON DELETE SET NULL ON UPDATE CASCADE,
  FOREIGN KEY (signed_off_by_stakeholder_id) REFERENCES stakeholder(stakeholder_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS migration_issue (
  migration_issue_id INTEGER PRIMARY KEY,
  issue_type TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('INFO', 'WARN', 'ERROR')),
  source_name TEXT NOT NULL,
  row_number INTEGER,
  property_code TEXT,
  property_id INTEGER,
  message TEXT NOT NULL,
  raw_payload TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (property_id) REFERENCES property(property_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_task_property ON task(property_id);
CREATE INDEX IF NOT EXISTS idx_task_arrival_date ON task(arrival_date);
CREATE INDEX IF NOT EXISTS idx_work_order_status ON work_order(status);
CREATE INDEX IF NOT EXISTS idx_inspection_item_result_result ON inspection_item_result(result);
CREATE INDEX IF NOT EXISTS idx_task_stage_event_task ON task_stage_event(task_id);
CREATE INDEX IF NOT EXISTS idx_migration_issue_property_code ON migration_issue(property_code);

INSERT OR IGNORE INTO role (role_id, role_key, role_name)
VALUES
  (1, 'OWNER', 'Owner'),
  (2, 'HOUSEKEEPER', 'Housekeeper'),
  (3, 'FACILITIES', 'Facilities / Maintenance'),
  (4, 'QC_INSPECTOR', 'QC Inspector'),
  (5, 'PROPERTY_MANAGER', 'Property Manager'),
  (6, 'OFFICE_DISPATCH', 'Office / Dispatch');

INSERT OR IGNORE INTO stage_definition (stage_definition_id, stage_key, stage_name, display_order)
VALUES
  (1, 'QC', 'QC', 1),
  (2, 'B2B', 'B2B', 2),
  (3, 'CLN', 'Cleaning', 3),
  (4, 'DONE', 'Task Done', 4),
  (5, 'OWN', 'Owner Review', 5),
  (6, 'WO', 'Work Order', 6),
  (7, 'DONE_WO', 'Work Order Done', 7),
  (8, 'REPORT', 'Report', 8);

INSERT OR IGNORE INTO property_feature_type (feature_type_id, feature_key, feature_name, supports_quantity)
VALUES
  (1, 'HOT_TUB', 'Hot Tub', 1),
  (2, 'TV', 'TV', 1),
  (3, 'EV_CHARGER', 'EV Charger', 1),
  (4, 'ARCADE_GAME', 'Arcade Game', 1),
  (5, 'PATIO', 'Patio', 1),
  (6, 'PORCH', 'Porch', 1),
  (7, 'BATHROOM', 'Bathroom', 1),
  (8, 'BEDROOM', 'Bedroom', 1);

INSERT OR IGNORE INTO notification_trigger (event_key, description, default_role_id)
VALUES
  ('CHECKLIST_ITEM_FAILED', 'Checklist item failed and requires action.', 3),
  ('TASK_READY_FOR_OWNER_REVIEW', 'Task has completed enough stages for owner review.', 1),
  ('WORK_ORDER_BLOCKED', 'Work order blocked and needs escalation.', 6),
  ('REPORT_SIGN_OFF_PENDING', 'Report generated and waiting for sign-off.', 5);