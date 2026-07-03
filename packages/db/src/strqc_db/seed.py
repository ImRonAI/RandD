"""Local development fixtures: a small Big Bear cluster.

Usage:
    python -m strqc_db.seed --db-path ./str_qc.sqlite
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .connection import connect

_SEED = """
INSERT OR IGNORE INTO cluster (cluster_id, name, description) VALUES
  (1, 'Big Bear Lake — Moonridge', 'East side cluster'),
  (2, 'Big Bear Lake — Boulder Bay', 'West side cluster');

INSERT OR IGNORE INTO stakeholder (stakeholder_id, full_name, email, phone) VALUES
  (1, 'Maribel Ortiz', 'maribel@example.com', '+1-909-555-0101'),
  (2, 'Bertha Nguyen', 'bertha@example.com', '+1-909-555-0102'),
  (3, 'Gabriella Reyes', 'gabriella@example.com', '+1-909-555-0103'),
  (4, 'Frank Delgado', 'frank@example.com', '+1-909-555-0104'),
  (5, 'Dana Whitfield', 'dana@example.com', '+1-909-555-0105'),
  (6, 'Owen Marsh', 'owen@example.com', '+1-909-555-0106');

INSERT OR IGNORE INTO stakeholder_role (stakeholder_id, role_id, property_id) VALUES
  (1, 2, NULL),  -- Maribel: housekeeper
  (2, 2, NULL),  -- Bertha: housekeeper
  (3, 2, NULL),  -- Gabriella: housekeeper
  (4, 3, NULL),  -- Frank: facilities
  (5, 4, NULL),  -- Dana: QC inspector
  (6, 1, NULL);  -- Owen: owner

INSERT OR IGNORE INTO property
  (property_id, unit_code, display_name, address_line_1, city, state_province,
   postal_code, cluster_id, qc_assignee_stakeholder_id, standing_instructions) VALUES
  (1, 'BBL-014', 'Grizzly Pines', '43210 Moonridge Rd', 'Big Bear Lake', 'CA',
   '92315', 1, 5, 'Hot tub cover straps must be clipped. Thermostat to 62°F on departure.'),
  (2, 'BBL-027', 'Cedar Hollow', '612 Boulder Bay Ave', 'Big Bear Lake', 'CA',
   '92315', 2, 5, 'EV charger cable coiled on wall hook. Check arcade tokens drawer.'),
  (3, 'BBL-033', 'Lakeview Lodge', '39400 Lakeview Dr', 'Big Bear Lake', 'CA',
   '92315', 2, 5, NULL);

INSERT OR IGNORE INTO property_feature (property_id, feature_type_id, location_label, quantity) VALUES
  (1, 1, 'back deck', 1),      -- hot tub
  (1, 2, 'living room', 2),    -- TVs
  (1, 8, '', 3),               -- bedrooms
  (1, 7, '', 2),               -- bathrooms
  (2, 3, 'driveway', 1),       -- EV charger
  (2, 4, 'game room', 2),      -- arcade
  (2, 8, '', 4),
  (2, 7, '', 3),
  (3, 2, 'den', 1),
  (3, 8, '', 2),
  (3, 7, '', 2);

INSERT OR IGNORE INTO checklist_template (checklist_template_id, template_name, version_label) VALUES
  (1, 'Standard Turnover', 'v1');

INSERT OR IGNORE INTO checklist_category (checklist_category_id, checklist_template_id, category_name, display_order) VALUES
  (1, 1, 'Hot Tub', 1),
  (2, 1, 'Housekeeping/Kitchen', 2),
  (3, 1, 'Housekeeping/Bathrooms', 3),
  (4, 1, 'Housekeeping/Bedroom', 4),
  (5, 1, 'Housekeeping/Home', 5),
  (6, 1, 'Outdoors', 6),
  (7, 1, 'Utilities', 7),
  (8, 1, 'Gifts', 8);

INSERT OR IGNORE INTO checklist_item_template
  (checklist_item_template_id, checklist_category_id, item_text, display_order, required_photo, maintenance_required) VALUES
  (1, 1, 'Water clear and 100–104°F', 1, 1, 1),
  (2, 1, 'Cover on, straps clipped', 2, 1, 0),
  (3, 2, 'Counters, sink, appliances clean', 1, 1, 0),
  (4, 2, 'Dishwasher empty; dishes stocked', 2, 0, 0),
  (5, 3, 'Towels: 2 per guest, folded', 1, 1, 0),
  (6, 3, 'Toilets/showers clean, no hair', 2, 1, 0),
  (7, 4, 'Beds made with fresh linens', 1, 1, 0),
  (8, 5, 'Floors vacuumed/mopped', 1, 0, 0),
  (9, 5, 'Smoke/CO detectors present, no alarm lights', 2, 1, 1),
  (10, 6, 'Patio furniture arranged; BBQ clean', 1, 1, 0),
  (11, 7, 'Thermostat set per standing instructions', 1, 0, 0),
  (12, 8, 'Welcome basket stocked', 1, 1, 0);

INSERT OR IGNORE INTO task
  (task_id, property_id, arrival_date, assigned_housekeeper_stakeholder_id, current_stage_definition_id) VALUES
  (1, 1, date('now', '+1 day'), 1, 1),
  (2, 2, date('now', '+2 day'), 2, 1),
  (3, 3, date('now'), 3, 3);
"""


def seed(db_path: str | Path) -> None:
    conn = connect(db_path)
    try:
        with conn:
            conn.executescript(_SEED)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", required=True)
    args = parser.parse_args()
    seed(args.db_path)
    print(f"seeded {args.db_path}")


if __name__ == "__main__":
    main()
