from __future__ import annotations

import sqlite3

ROOM_TYPES = (
    "Bedroom", "Bathroom", "Common Area", "Game Room", "Dock Area", "Pool",
    "Casita / Guest House", "Basement", "Kitchen", "Other",
)

SQLITE_SCHEMA = r"""
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS organization (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS portfolio (
  id TEXT NOT NULL, organization_id TEXT NOT NULL, name TEXT NOT NULL,
  PRIMARY KEY (organization_id, id),
  FOREIGN KEY (organization_id) REFERENCES organization(id)
);
CREATE TABLE IF NOT EXISTS app_user (
  id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS organization_membership (
  organization_id TEXT NOT NULL, user_id TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (organization_id, user_id, role),
  FOREIGN KEY (organization_id) REFERENCES organization(id), FOREIGN KEY (user_id) REFERENCES app_user(id)
);
CREATE TABLE IF NOT EXISTS home (
  organization_id TEXT NOT NULL, id TEXT NOT NULL, portfolio_id TEXT NOT NULL, name TEXT NOT NULL, unit_code TEXT,
  lifecycle_state TEXT NOT NULL DEFAULT 'active', legacy_property_id TEXT, google_place_id TEXT,
  formatted_address TEXT, latitude REAL, longitude REAL, places_validated_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (organization_id, id),
  FOREIGN KEY (organization_id, portfolio_id) REFERENCES portfolio(organization_id, id)
);
CREATE TABLE IF NOT EXISTS google_calendar_connection (
  organization_id TEXT NOT NULL, user_id TEXT NOT NULL, calendar_id TEXT NOT NULL,
  encrypted_refresh_token TEXT, status TEXT NOT NULL DEFAULT 'connected', sync_token TEXT, synced_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (organization_id,user_id,calendar_id)
);
CREATE TABLE IF NOT EXISTS google_calendar_event (
  organization_id TEXT NOT NULL, user_id TEXT NOT NULL, calendar_id TEXT NOT NULL, event_id TEXT NOT NULL,
  task_id TEXT, home_id TEXT, summary TEXT, starts_at TEXT, ends_at TEXT, status TEXT,
  raw_event_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (organization_id,user_id,calendar_id,event_id),
  FOREIGN KEY (organization_id,home_id) REFERENCES home(organization_id,id)
);
CREATE TABLE IF NOT EXISTS field_task (
  organization_id TEXT NOT NULL, id TEXT NOT NULL, home_id TEXT NOT NULL, arrival_date TEXT,
  stage_name TEXT, assignee TEXT, PRIMARY KEY (organization_id,id),
  FOREIGN KEY (organization_id,home_id) REFERENCES home(organization_id,id)
);
CREATE TABLE IF NOT EXISTS home_grant (
  organization_id TEXT NOT NULL, home_id TEXT NOT NULL, user_id TEXT NOT NULL, permission TEXT NOT NULL DEFAULT 'read',
  PRIMARY KEY (organization_id, home_id, user_id),
  FOREIGN KEY (organization_id, home_id) REFERENCES home(organization_id, id), FOREIGN KEY (user_id) REFERENCES app_user(id)
);
CREATE TABLE IF NOT EXISTS room_type (
  organization_id TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (organization_id, id), UNIQUE (organization_id, name),
  FOREIGN KEY (organization_id) REFERENCES organization(id)
);
CREATE TABLE IF NOT EXISTS inspection (
  organization_id TEXT NOT NULL, id TEXT NOT NULL, home_id TEXT NOT NULL, inspection_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft', client_id TEXT NOT NULL, created_by TEXT NOT NULL,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at TEXT,
  PRIMARY KEY (organization_id, id), UNIQUE (organization_id, created_by, home_id, client_id),
  CHECK (inspection_type IN ('onboarding','turnover')),
  FOREIGN KEY (organization_id, home_id) REFERENCES home(organization_id, id)
);
CREATE TABLE IF NOT EXISTS room (
  organization_id TEXT NOT NULL, id TEXT NOT NULL, home_id TEXT NOT NULL, room_type_id TEXT NOT NULL,
  name TEXT NOT NULL, floor_area TEXT, notes TEXT, display_order INTEGER NOT NULL DEFAULT 0,
  lifecycle_state TEXT NOT NULL DEFAULT 'active', created_by TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'user',
  creating_inspection_id TEXT, client_id TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (organization_id, id), UNIQUE (organization_id, created_by, home_id, client_id),
  FOREIGN KEY (organization_id, home_id) REFERENCES home(organization_id, id),
  FOREIGN KEY (organization_id, room_type_id) REFERENCES room_type(organization_id, id),
  FOREIGN KEY (organization_id, creating_inspection_id) REFERENCES inspection(organization_id, id)
);
CREATE TABLE IF NOT EXISTS asset (
  organization_id TEXT NOT NULL, id TEXT NOT NULL, home_id TEXT NOT NULL, room_id TEXT NOT NULL,
  asset_type TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '', location_description TEXT,
  manufacturer TEXT, model_number TEXT, serial_number TEXT, quantity INTEGER, condition TEXT, condition_notes TEXT,
  purchase_date TEXT, purchase_price TEXT, estimated_current_value TEXT, estimated_replacement_cost TEXT,
  warranty_provider TEXT, warranty_expiration TEXT, dimensions TEXT, color_finish TEXT, installation_date TEXT,
  last_service_date TEXT, product_identifier TEXT, notes TEXT, tags_json TEXT,
  lifecycle_state TEXT NOT NULL DEFAULT 'active', completion_status TEXT NOT NULL DEFAULT 'draft',
  created_by TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'user', creating_inspection_id TEXT, client_id TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (organization_id, id), UNIQUE (organization_id, created_by, room_id, client_id),
  FOREIGN KEY (organization_id, room_id) REFERENCES room(organization_id, id),
  FOREIGN KEY (organization_id, home_id) REFERENCES home(organization_id, id),
  FOREIGN KEY (organization_id, creating_inspection_id) REFERENCES inspection(organization_id, id)
);
CREATE TABLE IF NOT EXISTS photo (
  organization_id TEXT NOT NULL, id TEXT NOT NULL, home_id TEXT NOT NULL, room_id TEXT, asset_id TEXT,
  inspection_id TEXT, uploader_id TEXT NOT NULL, client_id TEXT NOT NULL, purpose TEXT NOT NULL DEFAULT 'asset_original',
  upload_status TEXT NOT NULL DEFAULT 'pending', original_object_key TEXT, sha256 TEXT, byte_size INTEGER, mime_type TEXT,
  failure_reason TEXT, captured_at TEXT, device_metadata_json TEXT, lens_metadata_json TEXT,
  source TEXT NOT NULL DEFAULT 'user', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (organization_id, id), UNIQUE (organization_id, uploader_id, client_id),
  FOREIGN KEY (organization_id, home_id) REFERENCES home(organization_id, id),
  FOREIGN KEY (organization_id, room_id) REFERENCES room(organization_id, id),
  FOREIGN KEY (organization_id, asset_id) REFERENCES asset(organization_id, id),
  FOREIGN KEY (organization_id, inspection_id) REFERENCES inspection(organization_id, id),
  CHECK (upload_status IN ('pending','verified','failed'))
);
CREATE TABLE IF NOT EXISTS inspection_inventory_link (
  organization_id TEXT NOT NULL, inspection_id TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
  action TEXT NOT NULL, PRIMARY KEY (organization_id, inspection_id, entity_type, entity_id, action),
  FOREIGN KEY (organization_id, inspection_id) REFERENCES inspection(organization_id, id)
);
CREATE TABLE IF NOT EXISTS evidence_approval (
  organization_id TEXT NOT NULL, id TEXT NOT NULL, inspection_id TEXT NOT NULL, photo_id TEXT NOT NULL,
  item_id TEXT, asset_id TEXT, verdict TEXT, approved_by TEXT NOT NULL, approved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (organization_id,id), UNIQUE (organization_id,inspection_id,photo_id,item_id,asset_id),
  FOREIGN KEY (organization_id,inspection_id) REFERENCES inspection(organization_id,id),
  FOREIGN KEY (organization_id,photo_id) REFERENCES photo(organization_id,id),
  FOREIGN KEY (organization_id,asset_id) REFERENCES asset(organization_id,id)
);
CREATE TABLE IF NOT EXISTS asset_research_value (
  organization_id TEXT NOT NULL, id TEXT NOT NULL, asset_id TEXT NOT NULL, field_name TEXT NOT NULL, value_json TEXT NOT NULL,
  provenance TEXT NOT NULL, source_reference TEXT, retrieved_at TEXT, confidence REAL, confirmed INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (organization_id, id), FOREIGN KEY (organization_id, asset_id) REFERENCES asset(organization_id, id)
);
CREATE TABLE IF NOT EXISTS magic_code_challenge (
  id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL, code_hash TEXT NOT NULL, salt TEXT NOT NULL,
  expires_at REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 5,
  used_at TEXT, provider_message_id TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS revoked_token (
  jti TEXT PRIMARY KEY, kind TEXT NOT NULL, expires_at INTEGER NOT NULL, consumed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS legacy_inspection_report (
  id TEXT PRIMARY KEY, property TEXT, state_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def install_sqlite_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SQLITE_SCHEMA)
    connection.commit()
