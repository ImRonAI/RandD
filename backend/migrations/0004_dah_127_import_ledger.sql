BEGIN;

-- Import compatibility fields intentionally preserve legacy values without
-- changing DAH-124's canonical inventory/checklist mapping.
ALTER TABLE app_user ADD COLUMN full_name text;
ALTER TABLE app_user ADD COLUMN phone text;

ALTER TABLE home ADD COLUMN cluster_name text;
ALTER TABLE home ADD COLUMN wifi_ssid text;
ALTER TABLE home ADD COLUMN wifi_password_ciphertext text;
ALTER TABLE home ADD COLUMN wifi_password_secret_ref text;
ALTER TABLE home ADD COLUMN door_code_ciphertext text;
ALTER TABLE home ADD COLUMN door_code_secret_ref text;
ALTER TABLE home ADD COLUMN standing_instructions text;
ALTER TABLE home ADD COLUMN roster_active boolean NOT NULL DEFAULT true;
ALTER TABLE home ADD COLUMN legacy_source_system text;

ALTER TABLE field_task ADD COLUMN assigned_housekeeper_user_id uuid REFERENCES app_user(id);
ALTER TABLE field_task ADD COLUMN legacy_source_row_number bigint;
ALTER TABLE field_task ADD COLUMN legacy_source_system text;
ALTER TABLE field_task ADD COLUMN legacy_stage_events jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE field_task ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE field_task ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();

ALTER TABLE legacy_inspection_report ADD COLUMN source_system text NOT NULL DEFAULT 'legacy-sqlite';
ALTER TABLE legacy_inspection_report ADD COLUMN source_checksum char(64);
ALTER TABLE legacy_inspection_report ADD COLUMN updated_at timestamptz;
ALTER TABLE legacy_inspection_report ADD COLUMN signed_off boolean NOT NULL DEFAULT false;
ALTER TABLE legacy_inspection_report ADD COLUMN artifact_uri text;
ALTER TABLE legacy_inspection_report ADD COLUMN artifact_sha256 char(64);
ALTER TABLE legacy_inspection_report ADD COLUMN mapping_status text NOT NULL DEFAULT 'mapped'
  CHECK (mapping_status IN ('mapped','review_required','quarantined'));

CREATE TYPE legacy_import_status AS ENUM ('running','completed','failed');
CREATE TYPE legacy_review_status AS ENUM ('pending','accepted','rejected');

CREATE TABLE legacy_import_run (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organization(id),
  source_manifest_sha256 char(64) NOT NULL,
  target_migration text NOT NULL DEFAULT '0004_dah_127_import_ledger.sql',
  mode text NOT NULL CHECK (mode IN ('apply')),
  status legacy_import_status NOT NULL DEFAULT 'running',
  code_revision text,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  checkpoint jsonb NOT NULL DEFAULT '{}'::jsonb,
  summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_message text,
  UNIQUE (organization_id,source_manifest_sha256,id)
);

CREATE TABLE legacy_id_map (
  organization_id uuid NOT NULL REFERENCES organization(id),
  source_system text NOT NULL,
  source_table text NOT NULL,
  source_pk text NOT NULL,
  target_table text NOT NULL,
  target_id text NOT NULL,
  source_checksum char(64) NOT NULL,
  import_run_id uuid NOT NULL REFERENCES legacy_import_run(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,source_system,source_table,source_pk),
  UNIQUE (organization_id,target_table,target_id)
);

CREATE TABLE legacy_import_error (
  id bigserial PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organization(id),
  import_run_id uuid NOT NULL REFERENCES legacy_import_run(id),
  source_system text NOT NULL,
  source_table text,
  source_pk text,
  severity text NOT NULL CHECK (severity IN ('warning','error')),
  error_code text NOT NULL,
  message text NOT NULL,
  retryable boolean NOT NULL DEFAULT false,
  resolved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE legacy_mapping_review (
  id bigserial PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organization(id),
  import_run_id uuid NOT NULL REFERENCES legacy_import_run(id),
  source_system text NOT NULL,
  source_table text NOT NULL,
  source_pk text NOT NULL,
  candidate_type text NOT NULL,
  reason_code text NOT NULL,
  source_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  status legacy_review_status NOT NULL DEFAULT 'pending',
  disposition jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id,source_system,source_table,source_pk,candidate_type,reason_code)
);

CREATE TABLE legacy_import_metric (
  organization_id uuid NOT NULL REFERENCES organization(id),
  import_run_id uuid NOT NULL REFERENCES legacy_import_run(id),
  source_system text NOT NULL,
  entity text NOT NULL,
  extracted_count bigint NOT NULL DEFAULT 0,
  inserted_count bigint NOT NULL DEFAULT 0,
  existing_count bigint NOT NULL DEFAULT 0,
  quarantined_count bigint NOT NULL DEFAULT 0,
  source_checksum char(64) NOT NULL,
  target_checksum char(64),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (import_run_id,source_system,entity)
);

CREATE TABLE legacy_artifact_manifest (
  organization_id uuid NOT NULL REFERENCES organization(id),
  import_run_id uuid NOT NULL REFERENCES legacy_import_run(id),
  source_system text NOT NULL,
  source_table text NOT NULL,
  source_pk text NOT NULL,
  artifact_kind text NOT NULL,
  source_uri text,
  sha256 char(64),
  byte_size bigint CHECK (byte_size IS NULL OR byte_size >= 0),
  validation_status text NOT NULL CHECK (validation_status IN ('present','missing','unverified','embedded')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,source_system,source_table,source_pk,artifact_kind)
);

-- Exact raw rows are retained for compatibility and audit. Sensitive values
-- remain ciphertext; importer diagnostics never serialize payload_json.
CREATE TABLE legacy_source_record (
  organization_id uuid NOT NULL REFERENCES organization(id),
  source_system text NOT NULL,
  source_table text NOT NULL,
  source_pk text NOT NULL,
  payload_json jsonb NOT NULL,
  source_checksum char(64) NOT NULL,
  import_run_id uuid NOT NULL REFERENCES legacy_import_run(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,source_system,source_table,source_pk)
);

DO $rls$
DECLARE tab text;
BEGIN
  FOREACH tab IN ARRAY ARRAY[
    'legacy_import_run','legacy_id_map','legacy_import_error','legacy_mapping_review',
    'legacy_import_metric','legacy_artifact_manifest','legacy_source_record'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',tab);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',tab);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (organization_id = app_org_id()) WITH CHECK (organization_id = app_org_id())',tab);
  END LOOP;
END $rls$;

COMMIT;
