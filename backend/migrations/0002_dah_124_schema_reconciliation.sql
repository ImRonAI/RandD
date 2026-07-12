BEGIN;

-- DAH-124 freezes inspection_type as the physical/API name. 0001 is retained
-- byte-for-byte because it is the released foundation migration.
ALTER TYPE inspection_kind RENAME TO inspection_type;
ALTER TABLE inspection RENAME COLUMN kind TO inspection_type;

-- Client identifiers are opaque, stable offline replay keys. The canonical
-- FastAPI/SQLite contract accepts non-empty text, so PostgreSQL must not reject
-- valid existing clients merely because their identifiers are not UUIDs.
ALTER TABLE inspection ALTER COLUMN client_id TYPE text USING client_id::text;
ALTER TABLE room ALTER COLUMN client_id TYPE text USING client_id::text;
ALTER TABLE asset ALTER COLUMN client_id TYPE text USING client_id::text;
ALTER TABLE photo ALTER COLUMN client_id TYPE text USING client_id::text;

CREATE TYPE photo_purpose AS ENUM (
  'asset_original','inspection_evidence','maintenance_before','maintenance_after','owner_report'
);
CREATE TYPE inspection_result AS ENUM ('PASS','FAIL','NA');

DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM photo WHERE purpose NOT IN
      ('asset_original','inspection_evidence','maintenance_before','maintenance_after','owner_report')) THEN
    RAISE EXCEPTION 'DAH-124 cannot map unknown photo purpose values';
  END IF;
END $guard$;

ALTER TABLE photo ALTER COLUMN purpose DROP DEFAULT;
ALTER TABLE photo ALTER COLUMN purpose TYPE photo_purpose USING purpose::photo_purpose;
ALTER TABLE photo ALTER COLUMN purpose SET DEFAULT 'asset_original'::photo_purpose;

ALTER TABLE inspection ADD CONSTRAINT inspection_org_home_id_unique UNIQUE (organization_id,home_id,id);
ALTER TABLE room ADD CONSTRAINT room_org_home_id_unique UNIQUE (organization_id,home_id,id);
ALTER TABLE asset ADD CONSTRAINT asset_org_home_id_unique UNIQUE (organization_id,home_id,id);
ALTER TABLE asset ADD CONSTRAINT asset_org_home_room_id_unique UNIQUE (organization_id,home_id,room_id,id);
ALTER TABLE photo ADD CONSTRAINT photo_org_home_id_unique UNIQUE (organization_id,home_id,id);
ALTER TABLE photo ADD CONSTRAINT photo_org_home_inspection_id_unique UNIQUE (organization_id,home_id,inspection_id,id);

DO $preflight$
BEGIN
  IF EXISTS (
    SELECT 1 FROM room r JOIN inspection i
      ON i.organization_id=r.organization_id AND i.id=r.creating_inspection_id
    WHERE r.creating_inspection_id IS NOT NULL AND r.home_id<>i.home_id
  ) THEN RAISE EXCEPTION 'DAH-124 preflight: room creating inspection belongs to another home'; END IF;
  IF EXISTS (
    SELECT 1 FROM asset a JOIN room r
      ON r.organization_id=a.organization_id AND r.id=a.room_id
    WHERE a.home_id<>r.home_id
  ) THEN RAISE EXCEPTION 'DAH-124 preflight: asset room belongs to another home'; END IF;
  IF EXISTS (
    SELECT 1 FROM asset a JOIN inspection i
      ON i.organization_id=a.organization_id AND i.id=a.creating_inspection_id
    WHERE a.creating_inspection_id IS NOT NULL AND a.home_id<>i.home_id
  ) THEN RAISE EXCEPTION 'DAH-124 preflight: asset creating inspection belongs to another home'; END IF;
  IF EXISTS (
    SELECT 1 FROM photo p LEFT JOIN room r
      ON r.organization_id=p.organization_id AND r.id=p.room_id
    WHERE p.room_id IS NOT NULL AND (r.id IS NULL OR p.home_id<>r.home_id)
  ) THEN RAISE EXCEPTION 'DAH-124 preflight: photo room is missing or belongs to another home'; END IF;
  IF EXISTS (
    SELECT 1 FROM photo p LEFT JOIN asset a
      ON a.organization_id=p.organization_id AND a.id=p.asset_id
    WHERE p.asset_id IS NOT NULL AND
      (p.room_id IS NULL OR a.id IS NULL OR p.home_id<>a.home_id OR p.room_id<>a.room_id)
  ) THEN RAISE EXCEPTION 'DAH-124 preflight: photo asset is missing or belongs to another room/home'; END IF;
  IF EXISTS (
    SELECT 1 FROM photo p LEFT JOIN inspection i
      ON i.organization_id=p.organization_id AND i.id=p.inspection_id
    WHERE p.inspection_id IS NOT NULL AND (i.id IS NULL OR p.home_id<>i.home_id)
  ) THEN RAISE EXCEPTION 'DAH-124 preflight: photo inspection is missing or belongs to another home'; END IF;
END $preflight$;

ALTER TABLE room DROP CONSTRAINT room_organization_id_creating_inspection_id_fkey;
ALTER TABLE room ADD CONSTRAINT room_creating_inspection_same_home_fk
  FOREIGN KEY (organization_id,home_id,creating_inspection_id)
  REFERENCES inspection(organization_id,home_id,id);

ALTER TABLE asset DROP CONSTRAINT asset_organization_id_room_id_fkey;
ALTER TABLE asset DROP CONSTRAINT asset_organization_id_creating_inspection_id_fkey;
ALTER TABLE asset ADD CONSTRAINT asset_room_same_home_fk
  FOREIGN KEY (organization_id,home_id,room_id) REFERENCES room(organization_id,home_id,id);
ALTER TABLE asset ADD CONSTRAINT asset_creating_inspection_same_home_fk
  FOREIGN KEY (organization_id,home_id,creating_inspection_id)
  REFERENCES inspection(organization_id,home_id,id);

ALTER TABLE photo DROP CONSTRAINT photo_organization_id_room_id_fkey;
ALTER TABLE photo DROP CONSTRAINT photo_organization_id_asset_id_fkey;
ALTER TABLE photo DROP CONSTRAINT photo_organization_id_inspection_id_fkey;
ALTER TABLE photo ADD CONSTRAINT photo_asset_requires_room CHECK (asset_id IS NULL OR room_id IS NOT NULL);
ALTER TABLE photo ADD CONSTRAINT photo_room_same_home_fk
  FOREIGN KEY (organization_id,home_id,room_id) REFERENCES room(organization_id,home_id,id);
ALTER TABLE photo ADD CONSTRAINT photo_asset_same_room_home_fk
  FOREIGN KEY (organization_id,home_id,room_id,asset_id)
  REFERENCES asset(organization_id,home_id,room_id,id);
ALTER TABLE photo ADD CONSTRAINT photo_inspection_same_home_fk
  FOREIGN KEY (organization_id,home_id,inspection_id)
  REFERENCES inspection(organization_id,home_id,id);

ALTER TABLE inspection_inventory_link ADD COLUMN home_id uuid;
ALTER TABLE inspection_inventory_link ADD COLUMN room_id uuid;
ALTER TABLE inspection_inventory_link ADD COLUMN asset_id uuid;
UPDATE inspection_inventory_link link SET home_id=inspection.home_id
  FROM inspection WHERE inspection.organization_id=link.organization_id AND inspection.id=link.inspection_id;
UPDATE inspection_inventory_link SET room_id=entity_id WHERE entity_type='room';
UPDATE inspection_inventory_link SET asset_id=entity_id WHERE entity_type='asset';
DO $inventory_preflight$
BEGIN
  IF EXISTS (
    SELECT 1 FROM inspection_inventory_link link
    LEFT JOIN room r ON r.organization_id=link.organization_id AND r.id=link.room_id
    LEFT JOIN asset a ON a.organization_id=link.organization_id AND a.id=link.asset_id
    WHERE link.home_id IS NULL
       OR (link.entity_type='room' AND (r.id IS NULL OR r.home_id<>link.home_id))
       OR (link.entity_type='asset' AND (a.id IS NULL OR a.home_id<>link.home_id))
       OR link.entity_type NOT IN ('room','asset')
  ) THEN
    RAISE EXCEPTION 'DAH-124 preflight: inspection inventory link is dangling, cross-home, or has an unknown entity type';
  END IF;
END $inventory_preflight$;
ALTER TABLE inspection_inventory_link ALTER COLUMN home_id SET NOT NULL;
ALTER TABLE inspection_inventory_link DROP CONSTRAINT inspection_inventory_link_organization_id_inspection_id_fkey;
ALTER TABLE inspection_inventory_link ADD CONSTRAINT inventory_link_inspection_same_home_fk
  FOREIGN KEY (organization_id,home_id,inspection_id) REFERENCES inspection(organization_id,home_id,id);
ALTER TABLE inspection_inventory_link ADD CONSTRAINT inventory_link_room_same_home_fk
  FOREIGN KEY (organization_id,home_id,room_id) REFERENCES room(organization_id,home_id,id);
ALTER TABLE inspection_inventory_link ADD CONSTRAINT inventory_link_asset_same_home_fk
  FOREIGN KEY (organization_id,home_id,asset_id) REFERENCES asset(organization_id,home_id,id);
ALTER TABLE inspection_inventory_link ADD CONSTRAINT inventory_link_typed_destination_check
  CHECK ((entity_type='room' AND room_id IS NOT NULL AND room_id=entity_id AND asset_id IS NULL)
      OR (entity_type='asset' AND asset_id IS NOT NULL AND asset_id=entity_id AND room_id IS NULL));

CREATE TABLE checklist_item (
  item_key text PRIMARY KEY,
  section_name text NOT NULL,
  label text NOT NULL UNIQUE,
  display_order integer NOT NULL UNIQUE,
  active boolean NOT NULL DEFAULT true
);

INSERT INTO checklist_item(item_key,section_name,label,display_order) VALUES
('hot_tub.up_and_working','Hot Tub','Up and Working',1),
('hot_tub.full','Hot Tub','Full',2),
('hot_tub.fresh','Hot Tub','Fresh',3),
('hot_tub.clear','Hot Tub','Clear',4),
('hot_tub.temperature_103','Hot Tub','103',5),
('housekeeping.kitchen.dishes_glasses_silverware_clean','HouseKeeping / Kitchen','Dishes, glasses, and silverware are clean',6),
('housekeeping.kitchen.pots_pans_clean','HouseKeeping / Kitchen','Pots, pans are clean',7),
('housekeeping.kitchen.dishwasher_empty','HouseKeeping / Kitchen','Dishwasher is Empty',8),
('housekeeping.kitchen.sink_clean_food_free','HouseKeeping / Kitchen','Sink is Cleaned & Free from Food',9),
('housekeeping.kitchen.garbage_disposal_clear_fresh','HouseKeeping / Kitchen','Garbage Disposal is Clear & Fresh',10),
('housekeeping.kitchen.refrigerator_cold_clean','HouseKeeping / Kitchen','Refrigerator is Cold and Clean',11),
('housekeeping.kitchen.oven_clean','HouseKeeping / Kitchen','Oven is Clean',12),
('housekeeping.bathrooms.towels_displayed','HouseKeeping / Bathrooms','Towels are displayed',13),
('housekeeping.bathrooms.floors_mopped','HouseKeeping / Bathrooms','Floors are mopped',14),
('housekeeping.bathrooms.bathtub_shower_clean','HouseKeeping / Bathrooms','Bath tub shower is clean',15),
('housekeeping.bathrooms.toilet_clean_fresh','HouseKeeping / Bathrooms','Toilet is clean and fresh',16),
('housekeeping.bathrooms.sink_mirrors_wiped','HouseKeeping / Bathrooms','Sink and mirrors are wiped off',17),
('housekeeping.bedroom.beds_made','HouseKeeping / Bedroom','All Beds are made properly w/ skirts',18),
('housekeeping.bedroom.remotes_in_holders','HouseKeeping / Bedroom','Remotes are in holders',19),
('housekeeping.bedroom.closets_organized','HouseKeeping / Bedroom','Closets are organized',20),
('housekeeping.home.smells_normal_fresh','HouseKeeping / Home','House smells Normal Fresh',21),
('housekeeping.home.surfaces_cleaned_dusted','HouseKeeping / Home','All surfaces cleaned or dusted',22),
('housekeeping.home.floors_vacuumed_mopped','HouseKeeping / Home','All floor have been vacuumed or mopped.',23),
('housekeeping.home.clean_organized','HouseKeeping / Home','The house is clean and organized.',24),
('housekeeping.home.open_welcoming','HouseKeeping / Home','The home is open and welcoming',25),
('housekeeping.home.carpets_no_stains','HouseKeeping / Home','Carpets Look Good no Stains',26),
('housekeeping.outdoors.walkways_driveway_clean','HouseKeeping / Outdoors','Walk ways and Drive way Cleaned off',27),
('housekeeping.outdoors.garbage_cans_put_away','HouseKeeping / Outdoors','Garbage cans are Put Away',28),
('housekeeping.outdoors.yard_maintained','HouseKeeping / Outdoors','Yard is Maintained',29),
('housekeeping.outdoors.bbq_clean','HouseKeeping / Outdoors','BBQ has been Cleaned',30),
('housekeeping.outdoors.furniture_arranged','HouseKeeping / Outdoors','Outdoor furniture arranged',31),
('housekeeping.outdoors.windows_presentable','HouseKeeping / Outdoors','Windows are presentable',32),
('utilities.gas','Utilities','Gas',33),
('utilities.wifi','Utilities','Wi-Fi',34),
('utilities.power','Utilities','Power',35),
('utilities.water','Utilities','Water',36),
('gifts.coffee_cream','Gifts','Coffee & Cream',37),
('gifts.deodorant_setup','Gifts','Deodorant set up',38);

CREATE TABLE inspection_item_result (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  home_id uuid NOT NULL,
  inspection_id uuid NOT NULL,
  item_key text NOT NULL REFERENCES checklist_item(item_key),
  result inspection_result NOT NULL,
  note text NOT NULL DEFAULT '',
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  supersedes_result_id uuid,
  recorded_by uuid NOT NULL REFERENCES app_user(id),
  client_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,id),
  UNIQUE (organization_id,inspection_id,item_key,version),
  UNIQUE (organization_id,recorded_by,inspection_id,client_id),
  UNIQUE (organization_id,home_id,inspection_id,id),
  UNIQUE (organization_id,home_id,inspection_id,item_key,id),
  FOREIGN KEY (organization_id,home_id,inspection_id)
    REFERENCES inspection(organization_id,home_id,id),
  FOREIGN KEY (organization_id,home_id,inspection_id,item_key,supersedes_result_id)
    REFERENCES inspection_item_result(organization_id,home_id,inspection_id,item_key,id),
  CHECK ((version=1 AND supersedes_result_id IS NULL)
      OR (version>1 AND supersedes_result_id IS NOT NULL))
);

CREATE TABLE result_photo (
  organization_id uuid NOT NULL,
  home_id uuid NOT NULL,
  inspection_id uuid NOT NULL,
  result_id uuid NOT NULL,
  photo_id uuid NOT NULL,
  display_order integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,result_id,photo_id),
  UNIQUE (organization_id,result_id,display_order),
  FOREIGN KEY (organization_id,home_id,inspection_id,result_id)
    REFERENCES inspection_item_result(organization_id,home_id,inspection_id,id),
  FOREIGN KEY (organization_id,home_id,inspection_id,photo_id)
    REFERENCES photo(organization_id,home_id,inspection_id,id)
);

ALTER TABLE evidence_approval ADD COLUMN home_id uuid;
ALTER TABLE evidence_approval ADD COLUMN result_id uuid;
ALTER TABLE evidence_approval ADD COLUMN legacy_item_id text;
UPDATE evidence_approval approval SET home_id = photo.home_id
FROM photo WHERE photo.organization_id=approval.organization_id AND photo.id=approval.photo_id;
ALTER TABLE evidence_approval ALTER COLUMN home_id SET NOT NULL;
ALTER TABLE evidence_approval DROP CONSTRAINT evidence_approval_check;
UPDATE evidence_approval SET legacy_item_id=item_id, item_id=NULL WHERE item_id IS NOT NULL;

ALTER TABLE evidence_approval DROP CONSTRAINT evidence_approval_organization_id_inspection_id_fkey;
ALTER TABLE evidence_approval DROP CONSTRAINT evidence_approval_organization_id_photo_id_fkey;
ALTER TABLE evidence_approval DROP CONSTRAINT evidence_approval_organization_id_asset_id_fkey;
ALTER TABLE evidence_approval ADD CONSTRAINT evidence_approval_inspection_same_home_fk
  FOREIGN KEY (organization_id,home_id,inspection_id) REFERENCES inspection(organization_id,home_id,id);
ALTER TABLE evidence_approval ADD CONSTRAINT evidence_approval_photo_same_inspection_fk
  FOREIGN KEY (organization_id,home_id,inspection_id,photo_id)
  REFERENCES photo(organization_id,home_id,inspection_id,id);
ALTER TABLE evidence_approval ADD CONSTRAINT evidence_approval_item_result_same_inspection_fk
  FOREIGN KEY (organization_id,home_id,inspection_id,item_id,result_id)
  REFERENCES inspection_item_result(organization_id,home_id,inspection_id,item_key,id);
ALTER TABLE evidence_approval ADD CONSTRAINT evidence_approval_asset_same_home_fk
  FOREIGN KEY (organization_id,home_id,asset_id) REFERENCES asset(organization_id,home_id,id);
DO $approval_preflight$
BEGIN
  IF EXISTS (SELECT 1 FROM evidence_approval WHERE result_id IS NOT NULL AND asset_id IS NOT NULL
      GROUP BY organization_id,inspection_id,photo_id,result_id,asset_id HAVING count(*)>1)
    OR EXISTS (SELECT 1 FROM evidence_approval WHERE result_id IS NOT NULL AND asset_id IS NULL
      GROUP BY organization_id,inspection_id,photo_id,result_id HAVING count(*)>1)
    OR EXISTS (SELECT 1 FROM evidence_approval WHERE result_id IS NULL AND asset_id IS NOT NULL
      GROUP BY organization_id,inspection_id,photo_id,asset_id HAVING count(*)>1)
    OR EXISTS (SELECT 1 FROM evidence_approval
      WHERE result_id IS NULL AND asset_id IS NULL AND legacy_item_id IS NOT NULL
      GROUP BY organization_id,inspection_id,photo_id,legacy_item_id HAVING count(*)>1) THEN
    RAISE EXCEPTION 'DAH-124 preflight: duplicate evidence approval destinations require reconciliation';
  END IF;
END $approval_preflight$;
CREATE UNIQUE INDEX evidence_approval_result_asset_unique
  ON evidence_approval(organization_id,inspection_id,photo_id,result_id,asset_id)
  WHERE result_id IS NOT NULL AND asset_id IS NOT NULL;
CREATE UNIQUE INDEX evidence_approval_result_only_unique
  ON evidence_approval(organization_id,inspection_id,photo_id,result_id)
  WHERE result_id IS NOT NULL AND asset_id IS NULL;
CREATE UNIQUE INDEX evidence_approval_asset_only_unique
  ON evidence_approval(organization_id,inspection_id,photo_id,asset_id)
  WHERE result_id IS NULL AND asset_id IS NOT NULL;
CREATE UNIQUE INDEX evidence_approval_legacy_unique
  ON evidence_approval(organization_id,inspection_id,photo_id,legacy_item_id)
  WHERE result_id IS NULL AND asset_id IS NULL AND legacy_item_id IS NOT NULL;
ALTER TABLE evidence_approval ADD CONSTRAINT evidence_approval_item_result_pair_check
  CHECK ((item_id IS NULL AND result_id IS NULL) OR (item_id IS NOT NULL AND result_id IS NOT NULL));
ALTER TABLE evidence_approval ADD CONSTRAINT evidence_approval_destination_check
  CHECK (result_id IS NOT NULL OR asset_id IS NOT NULL OR legacy_item_id IS NOT NULL);

CREATE TABLE legacy_inspection_report (
  organization_id uuid NOT NULL REFERENCES organization(id),
  id text NOT NULL,
  property text,
  state_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,id)
);
COMMENT ON TABLE legacy_inspection_report IS
  'Tenant-scoped raw House Keeping report history. DAH-127 assigns or quarantines source rows. No room rows are inferred.';

ALTER TABLE inspection_item_result ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspection_item_result FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON inspection_item_result
  USING (organization_id=app_org_id()) WITH CHECK (organization_id=app_org_id());
ALTER TABLE result_photo ENABLE ROW LEVEL SECURITY;
ALTER TABLE result_photo FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON result_photo
  USING (organization_id=app_org_id()) WITH CHECK (organization_id=app_org_id());
ALTER TABLE legacy_inspection_report ENABLE ROW LEVEL SECURITY;
ALTER TABLE legacy_inspection_report FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON legacy_inspection_report
  USING (organization_id=app_org_id()) WITH CHECK (organization_id=app_org_id());

COMMIT;
