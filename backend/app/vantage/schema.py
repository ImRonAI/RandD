from __future__ import annotations

import sqlite3
import re

ROOM_TYPES = (
    "Bedroom", "Bathroom", "Common Area", "Game Room", "Dock Area", "Pool",
    "Casita / Guest House", "Basement", "Kitchen", "Other",
)

INSPECTION_TYPES = ("onboarding", "turnover")
INSPECTION_RESULTS = ("PASS", "FAIL", "NA")
PHOTO_PURPOSES = (
    "asset_original",
    "inspection_evidence",
    "maintenance_before",
    "maintenance_after",
    "owner_report",
)

# Stable storage keys for the exact 38 labels exported by app.qc_journal.
# Labels remain verbatim for legacy report rendering; keys are immutable API/database identifiers.
QC_CHECKLIST_ITEMS = (
    ("hot_tub.up_and_working", "Hot Tub", "Up and Working"),
    ("hot_tub.full", "Hot Tub", "Full"),
    ("hot_tub.fresh", "Hot Tub", "Fresh"),
    ("hot_tub.clear", "Hot Tub", "Clear"),
    ("hot_tub.temperature_103", "Hot Tub", "103"),
    ("housekeeping.kitchen.dishes_glasses_silverware_clean", "HouseKeeping / Kitchen", "Dishes, glasses, and silverware are clean"),
    ("housekeeping.kitchen.pots_pans_clean", "HouseKeeping / Kitchen", "Pots, pans are clean"),
    ("housekeeping.kitchen.dishwasher_empty", "HouseKeeping / Kitchen", "Dishwasher is Empty"),
    ("housekeeping.kitchen.sink_clean_food_free", "HouseKeeping / Kitchen", "Sink is Cleaned & Free from Food"),
    ("housekeeping.kitchen.garbage_disposal_clear_fresh", "HouseKeeping / Kitchen", "Garbage Disposal is Clear & Fresh"),
    ("housekeeping.kitchen.refrigerator_cold_clean", "HouseKeeping / Kitchen", "Refrigerator is Cold and Clean"),
    ("housekeeping.kitchen.oven_clean", "HouseKeeping / Kitchen", "Oven is Clean"),
    ("housekeeping.bathrooms.towels_displayed", "HouseKeeping / Bathrooms", "Towels are displayed"),
    ("housekeeping.bathrooms.floors_mopped", "HouseKeeping / Bathrooms", "Floors are mopped"),
    ("housekeeping.bathrooms.bathtub_shower_clean", "HouseKeeping / Bathrooms", "Bath tub shower is clean"),
    ("housekeeping.bathrooms.toilet_clean_fresh", "HouseKeeping / Bathrooms", "Toilet is clean and fresh"),
    ("housekeeping.bathrooms.sink_mirrors_wiped", "HouseKeeping / Bathrooms", "Sink and mirrors are wiped off"),
    ("housekeeping.bedroom.beds_made", "HouseKeeping / Bedroom", "All Beds are made properly w/ skirts"),
    ("housekeeping.bedroom.remotes_in_holders", "HouseKeeping / Bedroom", "Remotes are in holders"),
    ("housekeeping.bedroom.closets_organized", "HouseKeeping / Bedroom", "Closets are organized"),
    ("housekeeping.home.smells_normal_fresh", "HouseKeeping / Home", "House smells Normal Fresh"),
    ("housekeeping.home.surfaces_cleaned_dusted", "HouseKeeping / Home", "All surfaces cleaned or dusted"),
    ("housekeeping.home.floors_vacuumed_mopped", "HouseKeeping / Home", "All floor have been vacuumed or mopped."),
    ("housekeeping.home.clean_organized", "HouseKeeping / Home", "The house is clean and organized."),
    ("housekeeping.home.open_welcoming", "HouseKeeping / Home", "The home is open and welcoming"),
    ("housekeeping.home.carpets_no_stains", "HouseKeeping / Home", "Carpets Look Good no Stains"),
    ("housekeeping.outdoors.walkways_driveway_clean", "HouseKeeping / Outdoors", "Walk ways and Drive way Cleaned off"),
    ("housekeeping.outdoors.garbage_cans_put_away", "HouseKeeping / Outdoors", "Garbage cans are Put Away"),
    ("housekeeping.outdoors.yard_maintained", "HouseKeeping / Outdoors", "Yard is Maintained"),
    ("housekeeping.outdoors.bbq_clean", "HouseKeeping / Outdoors", "BBQ has been Cleaned"),
    ("housekeeping.outdoors.furniture_arranged", "HouseKeeping / Outdoors", "Outdoor furniture arranged"),
    ("housekeeping.outdoors.windows_presentable", "HouseKeeping / Outdoors", "Windows are presentable"),
    ("utilities.gas", "Utilities", "Gas"),
    ("utilities.wifi", "Utilities", "Wi-Fi"),
    ("utilities.power", "Utilities", "Power"),
    ("utilities.water", "Utilities", "Water"),
    ("gifts.coffee_cream", "Gifts", "Coffee & Cream"),
    ("gifts.deodorant_setup", "Gifts", "Deodorant set up"),
)


def _legacy_checklist_id(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


LEGACY_CHECKLIST_ID_TO_KEY = {
    _legacy_checklist_id(label): key for key, _section, label in QC_CHECKLIST_ITEMS
}

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
  CHECK (status IN ('draft','in_progress','paused','completed','cancelled')),
  UNIQUE (organization_id, home_id, id),
  FOREIGN KEY (organization_id, home_id) REFERENCES home(organization_id, id)
);
CREATE TABLE IF NOT EXISTS room (
  organization_id TEXT NOT NULL, id TEXT NOT NULL, home_id TEXT NOT NULL, room_type_id TEXT NOT NULL,
  name TEXT NOT NULL, floor_area TEXT, notes TEXT, display_order INTEGER NOT NULL DEFAULT 0,
  lifecycle_state TEXT NOT NULL DEFAULT 'active', created_by TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'user',
  creating_inspection_id TEXT, client_id TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (organization_id, id), UNIQUE (organization_id, created_by, home_id, client_id),
  UNIQUE (organization_id, home_id, id),
  FOREIGN KEY (organization_id, home_id) REFERENCES home(organization_id, id),
  FOREIGN KEY (organization_id, room_type_id) REFERENCES room_type(organization_id, id),
  FOREIGN KEY (organization_id, home_id, creating_inspection_id) REFERENCES inspection(organization_id, home_id, id)
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
  UNIQUE (organization_id, home_id, id), UNIQUE (organization_id, home_id, room_id, id),
  FOREIGN KEY (organization_id, home_id, room_id) REFERENCES room(organization_id, home_id, id),
  FOREIGN KEY (organization_id, home_id) REFERENCES home(organization_id, id),
  FOREIGN KEY (organization_id, home_id, creating_inspection_id) REFERENCES inspection(organization_id, home_id, id)
);
CREATE TABLE IF NOT EXISTS photo (
  organization_id TEXT NOT NULL, id TEXT NOT NULL, home_id TEXT NOT NULL, room_id TEXT, asset_id TEXT,
  inspection_id TEXT, uploader_id TEXT NOT NULL, client_id TEXT NOT NULL, purpose TEXT NOT NULL DEFAULT 'asset_original',
  upload_status TEXT NOT NULL DEFAULT 'pending', original_object_key TEXT, sha256 TEXT, byte_size INTEGER, mime_type TEXT,
  failure_reason TEXT, captured_at TEXT, device_metadata_json TEXT, lens_metadata_json TEXT,
  source TEXT NOT NULL DEFAULT 'user', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (organization_id, id), UNIQUE (organization_id, uploader_id, client_id),
  UNIQUE (organization_id, home_id, id), UNIQUE (organization_id, home_id, inspection_id, id),
  FOREIGN KEY (organization_id, home_id) REFERENCES home(organization_id, id),
  FOREIGN KEY (organization_id, home_id, room_id) REFERENCES room(organization_id, home_id, id),
  FOREIGN KEY (organization_id, home_id, room_id, asset_id) REFERENCES asset(organization_id, home_id, room_id, id),
  FOREIGN KEY (organization_id, home_id, inspection_id) REFERENCES inspection(organization_id, home_id, id),
  CHECK (purpose IN ('asset_original','inspection_evidence','maintenance_before','maintenance_after','owner_report')),
  CHECK (asset_id IS NULL OR room_id IS NOT NULL),
  CHECK (upload_status IN ('pending','verified','failed','abandoned')),
  CHECK (upload_status != 'verified' OR (original_object_key IS NOT NULL AND sha256 IS NOT NULL AND byte_size IS NOT NULL AND mime_type IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS checklist_item (
  item_key TEXT PRIMARY KEY, section_name TEXT NOT NULL, label TEXT NOT NULL UNIQUE,
  display_order INTEGER NOT NULL UNIQUE, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS inspection_item_result (
  organization_id TEXT NOT NULL, id TEXT NOT NULL, home_id TEXT NOT NULL, inspection_id TEXT NOT NULL,
  item_key TEXT NOT NULL, result TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1,
  supersedes_result_id TEXT, recorded_by TEXT NOT NULL, client_id TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (organization_id,id), UNIQUE (organization_id,inspection_id,item_key,version),
  UNIQUE (organization_id,recorded_by,inspection_id,client_id),
  UNIQUE (organization_id,home_id,inspection_id,id),
  UNIQUE (organization_id,home_id,inspection_id,item_key,id),
  FOREIGN KEY (item_key) REFERENCES checklist_item(item_key),
  FOREIGN KEY (organization_id,home_id,inspection_id) REFERENCES inspection(organization_id,home_id,id),
  FOREIGN KEY (organization_id,home_id,inspection_id,item_key,supersedes_result_id)
    REFERENCES inspection_item_result(organization_id,home_id,inspection_id,item_key,id),
  CHECK (result IN ('PASS','FAIL','NA')), CHECK (version > 0),
  CHECK ((version=1 AND supersedes_result_id IS NULL)
      OR (version>1 AND supersedes_result_id IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS result_photo (
  organization_id TEXT NOT NULL, home_id TEXT NOT NULL, inspection_id TEXT NOT NULL,
  result_id TEXT NOT NULL, photo_id TEXT NOT NULL, display_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (organization_id,result_id,photo_id), UNIQUE (organization_id,result_id,display_order),
  FOREIGN KEY (organization_id,home_id,inspection_id,result_id) REFERENCES inspection_item_result(organization_id,home_id,inspection_id,id),
  FOREIGN KEY (organization_id,home_id,inspection_id,photo_id) REFERENCES photo(organization_id,home_id,inspection_id,id)
);
CREATE TABLE IF NOT EXISTS inspection_inventory_link (
  organization_id TEXT NOT NULL, inspection_id TEXT NOT NULL, home_id TEXT NOT NULL,
  entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, room_id TEXT, asset_id TEXT,
  action TEXT NOT NULL, PRIMARY KEY (organization_id, inspection_id, entity_type, entity_id, action),
  FOREIGN KEY (organization_id,home_id,inspection_id) REFERENCES inspection(organization_id,home_id,id),
  FOREIGN KEY (organization_id,home_id,room_id) REFERENCES room(organization_id,home_id,id),
  FOREIGN KEY (organization_id,home_id,asset_id) REFERENCES asset(organization_id,home_id,id),
  CHECK ((entity_type='room' AND room_id IS NOT NULL AND room_id=entity_id AND asset_id IS NULL)
      OR (entity_type='asset' AND asset_id IS NOT NULL AND asset_id=entity_id AND room_id IS NULL))
);
CREATE TABLE IF NOT EXISTS evidence_approval (
  organization_id TEXT NOT NULL, id TEXT NOT NULL, home_id TEXT NOT NULL, inspection_id TEXT NOT NULL, photo_id TEXT NOT NULL,
  item_id TEXT, result_id TEXT, legacy_item_id TEXT, asset_id TEXT, verdict TEXT, approved_by TEXT NOT NULL, approved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (organization_id,id), UNIQUE (organization_id,inspection_id,photo_id,result_id,asset_id),
  FOREIGN KEY (organization_id,home_id,inspection_id) REFERENCES inspection(organization_id,home_id,id),
  FOREIGN KEY (organization_id,home_id,inspection_id,photo_id) REFERENCES photo(organization_id,home_id,inspection_id,id),
  FOREIGN KEY (organization_id,home_id,inspection_id,item_id,result_id)
    REFERENCES inspection_item_result(organization_id,home_id,inspection_id,item_key,id),
  FOREIGN KEY (organization_id,home_id,asset_id) REFERENCES asset(organization_id,home_id,id),
  CHECK (verdict IS NULL OR verdict IN ('PASS','FAIL','NA','REVIEW')),
  CHECK ((item_id IS NULL AND result_id IS NULL) OR (item_id IS NOT NULL AND result_id IS NOT NULL)),
  CHECK (result_id IS NOT NULL OR asset_id IS NOT NULL OR legacy_item_id IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS evidence_approval_result_asset_unique
  ON evidence_approval(organization_id,inspection_id,photo_id,result_id,asset_id)
  WHERE result_id IS NOT NULL AND asset_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS evidence_approval_result_only_unique
  ON evidence_approval(organization_id,inspection_id,photo_id,result_id)
  WHERE result_id IS NOT NULL AND asset_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS evidence_approval_asset_only_unique
  ON evidence_approval(organization_id,inspection_id,photo_id,asset_id)
  WHERE result_id IS NULL AND asset_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS evidence_approval_legacy_unique
  ON evidence_approval(organization_id,inspection_id,photo_id,legacy_item_id)
  WHERE result_id IS NULL AND asset_id IS NULL AND legacy_item_id IS NOT NULL;
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
  organization_id TEXT NOT NULL, id TEXT NOT NULL, property TEXT, state_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (organization_id,id),
  FOREIGN KEY (organization_id) REFERENCES organization(id)
);
"""


def install_sqlite_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SQLITE_SCHEMA)
    connection.executemany(
        "INSERT OR IGNORE INTO checklist_item(item_key,section_name,label,display_order) VALUES (?,?,?,?)",
        [(key, section, label, index) for index, (key, section, label) in enumerate(QC_CHECKLIST_ITEMS, 1)],
    )
    connection.commit()
