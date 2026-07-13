BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TYPE vantage_role AS ENUM ('ORG_ADMIN','PROPERTY_MANAGER','INSPECTOR','HOUSEKEEPER','OWNER','FACILITIES','OFFICE_DISPATCH');
CREATE TYPE lifecycle_state AS ENUM ('active','archived');
CREATE TYPE inspection_kind AS ENUM ('onboarding','turnover');
CREATE TYPE inspection_status AS ENUM ('draft','in_progress','paused','completed','cancelled');
CREATE TYPE upload_status AS ENUM ('pending','verified','failed','abandoned');
CREATE TYPE inventory_action AS ENUM ('created','reviewed','moved','archived');

CREATE TABLE organization (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE portfolio (
  organization_id uuid NOT NULL REFERENCES organization(id), id uuid NOT NULL DEFAULT gen_random_uuid(), name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (organization_id,id)
);
CREATE TABLE app_user (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), email text NOT NULL, active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX app_user_email_lower_unique ON app_user (lower(email));
CREATE TABLE organization_membership (
  organization_id uuid NOT NULL REFERENCES organization(id), user_id uuid NOT NULL REFERENCES app_user(id),
  role vantage_role NOT NULL, active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,user_id,role)
);
CREATE TABLE home (
  organization_id uuid NOT NULL REFERENCES organization(id), id uuid NOT NULL DEFAULT gen_random_uuid(),
  portfolio_id uuid NOT NULL, unit_code text, name text NOT NULL, lifecycle_state lifecycle_state NOT NULL DEFAULT 'active',
  legacy_property_id text, google_place_id text, formatted_address text, latitude double precision, longitude double precision,
  places_validated_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,id), FOREIGN KEY (organization_id,portfolio_id) REFERENCES portfolio(organization_id,id),
  UNIQUE (organization_id,unit_code)
);
CREATE TABLE google_calendar_connection (
  organization_id uuid NOT NULL, user_id uuid NOT NULL REFERENCES app_user(id), calendar_id text NOT NULL,
  encrypted_refresh_token text, status text NOT NULL DEFAULT 'connected', sync_token text, synced_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,user_id,calendar_id)
);
CREATE TABLE google_calendar_event (
  organization_id uuid NOT NULL, user_id uuid NOT NULL, calendar_id text NOT NULL, event_id text NOT NULL,
  task_id text, home_id uuid, summary text, starts_at timestamptz, ends_at timestamptz, status text,
  raw_event jsonb NOT NULL DEFAULT '{}'::jsonb, updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,user_id,calendar_id,event_id),
  FOREIGN KEY (organization_id,user_id,calendar_id) REFERENCES google_calendar_connection(organization_id,user_id,calendar_id),
  FOREIGN KEY (organization_id,home_id) REFERENCES home(organization_id,id)
);
CREATE TABLE field_task (
  organization_id uuid NOT NULL, id text NOT NULL, home_id uuid NOT NULL, arrival_date date,
  stage_name text, assignee text, PRIMARY KEY (organization_id,id),
  FOREIGN KEY (organization_id,home_id) REFERENCES home(organization_id,id)
);
CREATE TABLE home_grant (
  organization_id uuid NOT NULL, home_id uuid NOT NULL, user_id uuid NOT NULL REFERENCES app_user(id),
  permission text NOT NULL CHECK (permission IN ('read','manage')), created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,home_id,user_id), FOREIGN KEY (organization_id,home_id) REFERENCES home(organization_id,id)
);
CREATE TABLE room_type (
  organization_id uuid NOT NULL REFERENCES organization(id), id uuid NOT NULL DEFAULT gen_random_uuid(), name text NOT NULL,
  active boolean NOT NULL DEFAULT true, display_order integer NOT NULL DEFAULT 0,
  PRIMARY KEY (organization_id,id), UNIQUE (organization_id,name)
);
CREATE TABLE inspection (
  organization_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), home_id uuid NOT NULL,
  kind inspection_kind NOT NULL, status inspection_status NOT NULL DEFAULT 'draft', client_id uuid NOT NULL,
  created_by uuid NOT NULL REFERENCES app_user(id), task_id text, started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz, version integer NOT NULL DEFAULT 1, legacy_report_id text,
  PRIMARY KEY (organization_id,id), FOREIGN KEY (organization_id,home_id) REFERENCES home(organization_id,id),
  UNIQUE (organization_id,created_by,home_id,client_id)
);
CREATE TABLE room (
  organization_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), home_id uuid NOT NULL, room_type_id uuid NOT NULL,
  name text NOT NULL CHECK (btrim(name) <> ''), floor_area text, notes text, display_order integer NOT NULL DEFAULT 0,
  lifecycle_state lifecycle_state NOT NULL DEFAULT 'active', created_by uuid NOT NULL REFERENCES app_user(id),
  source text NOT NULL DEFAULT 'user', creating_inspection_id uuid, client_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,id), FOREIGN KEY (organization_id,home_id) REFERENCES home(organization_id,id),
  FOREIGN KEY (organization_id,room_type_id) REFERENCES room_type(organization_id,id),
  FOREIGN KEY (organization_id,creating_inspection_id) REFERENCES inspection(organization_id,id),
  UNIQUE (organization_id,created_by,home_id,client_id)
);
CREATE TABLE asset (
  organization_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), home_id uuid NOT NULL, room_id uuid NOT NULL,
  asset_type text NOT NULL DEFAULT '', name text NOT NULL DEFAULT '', location_description text,
  manufacturer text, model_number text, serial_number text, quantity integer CHECK (quantity IS NULL OR quantity > 0),
  condition text, condition_notes text, purchase_date date, purchase_price numeric(12,2), estimated_current_value numeric(12,2),
  estimated_replacement_cost numeric(12,2), warranty_provider text, warranty_expiration date, dimensions text,
  color_finish text, installation_date date, last_service_date date, product_identifier text, notes text, tags jsonb,
  lifecycle_state lifecycle_state NOT NULL DEFAULT 'active', completion_status text NOT NULL DEFAULT 'draft' CHECK (completion_status IN ('draft','complete')),
  created_by uuid NOT NULL REFERENCES app_user(id), source text NOT NULL DEFAULT 'user', creating_inspection_id uuid,
  client_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,id), FOREIGN KEY (organization_id,home_id) REFERENCES home(organization_id,id),
  FOREIGN KEY (organization_id,room_id) REFERENCES room(organization_id,id),
  FOREIGN KEY (organization_id,creating_inspection_id) REFERENCES inspection(organization_id,id),
  UNIQUE (organization_id,created_by,room_id,client_id)
);
CREATE TABLE photo (
  organization_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), home_id uuid NOT NULL, room_id uuid,
  asset_id uuid, inspection_id uuid, uploader_id uuid NOT NULL REFERENCES app_user(id), client_id uuid NOT NULL,
  purpose text NOT NULL, upload_status upload_status NOT NULL DEFAULT 'pending', original_object_key text,
  sha256 char(64), byte_size bigint CHECK (byte_size IS NULL OR byte_size > 0), mime_type text, failure_reason text,
  captured_at timestamptz, device_metadata jsonb, lens_metadata jsonb, source text NOT NULL DEFAULT 'user',
  legal_hold boolean NOT NULL DEFAULT false, retention_until timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,id), FOREIGN KEY (organization_id,home_id) REFERENCES home(organization_id,id),
  FOREIGN KEY (organization_id,room_id) REFERENCES room(organization_id,id),
  FOREIGN KEY (organization_id,asset_id) REFERENCES asset(organization_id,id),
  FOREIGN KEY (organization_id,inspection_id) REFERENCES inspection(organization_id,id),
  UNIQUE (organization_id,uploader_id,client_id),
  CHECK (upload_status <> 'verified' OR (original_object_key IS NOT NULL AND sha256 IS NOT NULL AND byte_size IS NOT NULL AND mime_type IS NOT NULL))
);
CREATE TABLE photo_derivative (
  organization_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), photo_id uuid NOT NULL,
  kind text NOT NULL, object_key text NOT NULL, sha256 char(64), created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,id), FOREIGN KEY (organization_id,photo_id) REFERENCES photo(organization_id,id)
);
CREATE TABLE inspection_inventory_link (
  organization_id uuid NOT NULL, inspection_id uuid NOT NULL, entity_type text NOT NULL CHECK (entity_type IN ('room','asset')),
  entity_id uuid NOT NULL, action inventory_action NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,inspection_id,entity_type,entity_id,action),
  FOREIGN KEY (organization_id,inspection_id) REFERENCES inspection(organization_id,id)
);
CREATE TABLE evidence_approval (
  organization_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), inspection_id uuid NOT NULL,
  photo_id uuid NOT NULL, item_id text, asset_id uuid, verdict text CHECK (verdict IN ('PASS','FAIL','NA','REVIEW')),
  approved_by uuid NOT NULL REFERENCES app_user(id),
  approved_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (organization_id,id),
  FOREIGN KEY (organization_id,inspection_id) REFERENCES inspection(organization_id,id),
  FOREIGN KEY (organization_id,photo_id) REFERENCES photo(organization_id,id),
  FOREIGN KEY (organization_id,asset_id) REFERENCES asset(organization_id,id),
  CHECK (item_id IS NOT NULL OR asset_id IS NOT NULL)
);
CREATE TABLE asset_document (
  organization_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), asset_id uuid NOT NULL,
  kind text NOT NULL, object_key text, source_url text, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,id), FOREIGN KEY (organization_id,asset_id) REFERENCES asset(organization_id,id)
);
CREATE TABLE asset_research_value (
  organization_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), asset_id uuid NOT NULL, field_name text NOT NULL,
  value jsonb NOT NULL, provenance text NOT NULL CHECK (provenance IN ('user_entered','agent_observed','photo_extracted','externally_researched')),
  source_reference text, retrieved_at timestamptz, confidence numeric(4,3) CHECK (confidence BETWEEN 0 AND 1),
  confirmed boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,id), FOREIGN KEY (organization_id,asset_id) REFERENCES asset(organization_id,id)
);
CREATE TABLE baseline_version (
  organization_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), home_id uuid NOT NULL, inspection_id uuid,
  version integer NOT NULL, reason text, created_by uuid NOT NULL REFERENCES app_user(id), created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,id), FOREIGN KEY (organization_id,home_id) REFERENCES home(organization_id,id),
  FOREIGN KEY (organization_id,inspection_id) REFERENCES inspection(organization_id,id), UNIQUE (organization_id,home_id,version)
);
CREATE TABLE baseline_photo (
  organization_id uuid NOT NULL, baseline_id uuid NOT NULL, photo_id uuid NOT NULL,
  PRIMARY KEY (organization_id,baseline_id,photo_id), FOREIGN KEY (organization_id,baseline_id) REFERENCES baseline_version(organization_id,id),
  FOREIGN KEY (organization_id,photo_id) REFERENCES photo(organization_id,id)
);
CREATE TABLE comparison (
  organization_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), home_id uuid NOT NULL, baseline_id uuid NOT NULL,
  inspection_id uuid NOT NULL, result jsonb, reviewed_by uuid REFERENCES app_user(id), reviewed_at timestamptz,
  PRIMARY KEY (organization_id,id), FOREIGN KEY (organization_id,home_id) REFERENCES home(organization_id,id),
  FOREIGN KEY (organization_id,baseline_id) REFERENCES baseline_version(organization_id,id),
  FOREIGN KEY (organization_id,inspection_id) REFERENCES inspection(organization_id,id)
);
CREATE TABLE damage_incident (
  organization_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), home_id uuid NOT NULL, comparison_id uuid,
  asset_id uuid, status text NOT NULL DEFAULT 'draft', summary text, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,id), FOREIGN KEY (organization_id,home_id) REFERENCES home(organization_id,id),
  FOREIGN KEY (organization_id,comparison_id) REFERENCES comparison(organization_id,id),
  FOREIGN KEY (organization_id,asset_id) REFERENCES asset(organization_id,id)
);
CREATE TABLE claim_export (
  organization_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), incident_id uuid NOT NULL,
  object_key text NOT NULL, manifest_sha256 char(64) NOT NULL, created_by uuid NOT NULL REFERENCES app_user(id),
  created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (organization_id,id),
  FOREIGN KEY (organization_id,incident_id) REFERENCES damage_incident(organization_id,id)
);
CREATE TABLE video (
  organization_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(), home_id uuid NOT NULL, inspection_id uuid,
  room_id uuid, uploader_id uuid NOT NULL REFERENCES app_user(id), raw_object_key text NOT NULL, mp4_object_key text,
  transcript text, transcode_status text NOT NULL DEFAULT 'pending', transcode_attempts integer NOT NULL DEFAULT 0,
  transcode_error text, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (organization_id,id),
  FOREIGN KEY (organization_id,home_id) REFERENCES home(organization_id,id),
  FOREIGN KEY (organization_id,inspection_id) REFERENCES inspection(organization_id,id),
  FOREIGN KEY (organization_id,room_id) REFERENCES room(organization_id,id)
);
CREATE TABLE magic_code_challenge (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), email text NOT NULL, code_hash text NOT NULL, salt text NOT NULL,
  expires_at timestamptz NOT NULL, attempts integer NOT NULL DEFAULT 0, max_attempts integer NOT NULL DEFAULT 5,
  used_at timestamptz, provider_message_id text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX magic_code_email_created_idx ON magic_code_challenge (lower(email),created_at DESC);
CREATE TABLE revoked_token (
  jti uuid PRIMARY KEY, kind text NOT NULL, expires_at timestamptz NOT NULL, consumed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE audit_event (
  organization_id uuid, id uuid NOT NULL DEFAULT gen_random_uuid(), actor_user_id uuid, action text NOT NULL,
  entity_type text, entity_id text, metadata jsonb, occurred_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,id), FOREIGN KEY (organization_id) REFERENCES organization(id),
  FOREIGN KEY (actor_user_id) REFERENCES app_user(id)
);

INSERT INTO room_type (organization_id,name,display_order)
SELECT o.id,v.name,v.ord FROM organization o CROSS JOIN (VALUES
 ('Bedroom',1),('Bathroom',2),('Common Area',3),('Game Room',4),('Dock Area',5),('Pool',6),
 ('Casita / Guest House',7),('Basement',8),('Kitchen',9),('Other',10)
) AS v(name,ord) ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION app_org_id() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.org_id', true),'')::uuid $$;
CREATE OR REPLACE FUNCTION app_user_id() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.user_id', true),'')::uuid $$;

ALTER TABLE organization ENABLE ROW LEVEL SECURITY;
ALTER TABLE organization FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON organization USING (id = app_org_id()) WITH CHECK (id = app_org_id());

DO $rls$
DECLARE tab text;
BEGIN
  FOREACH tab IN ARRAY ARRAY['portfolio','organization_membership','home','home_grant','google_calendar_connection','google_calendar_event','field_task','room_type','inspection','room','asset','photo','photo_derivative','inspection_inventory_link','evidence_approval','asset_document','asset_research_value','baseline_version','baseline_photo','comparison','damage_incident','claim_export','video','audit_event']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',tab);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',tab);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (organization_id = app_org_id()) WITH CHECK (organization_id = app_org_id())',tab);
  END LOOP;
END $rls$;

COMMIT;
