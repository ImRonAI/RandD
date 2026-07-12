BEGIN;

CREATE TYPE original_upload_status AS ENUM ('pending','failed','verified','abandoned');

CREATE TABLE original_upload (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  home_id uuid NOT NULL,
  photo_id uuid NOT NULL,
  storage_bucket text NOT NULL,
  object_key text NOT NULL,
  status original_upload_status NOT NULL DEFAULT 'pending',
  expected_byte_size bigint NOT NULL CHECK (expected_byte_size>0),
  expected_sha256 char(64) NOT NULL CHECK (expected_sha256 ~ '^[0-9a-f]{64}$'),
  expected_mime_type text NOT NULL,
  storage_version_id text,
  etag text,
  encryption_algorithm text,
  kms_key_id text,
  object_lock_mode text,
  retention_until timestamptz,
  legal_hold_status text,
  verification_attempts integer NOT NULL DEFAULT 0 CHECK (verification_attempts>=0),
  last_error_code text,
  verified_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id,id),
  UNIQUE (organization_id,photo_id),
  UNIQUE (organization_id,home_id,photo_id,id),
  UNIQUE (storage_bucket,object_key),
  FOREIGN KEY (organization_id,home_id,photo_id) REFERENCES photo(organization_id,home_id,id),
  CHECK (status<>'verified' OR (
    storage_version_id IS NOT NULL AND length(storage_version_id)>0
    AND encryption_algorithm='aws:kms'
    AND kms_key_id IS NOT NULL AND length(kms_key_id)>0
    AND object_lock_mode='COMPLIANCE'
    AND retention_until IS NOT NULL
    AND verified_at IS NOT NULL
    AND last_error_code IS NULL
    AND retention_until > verified_at
  ))
);

ALTER TABLE original_upload ENABLE ROW LEVEL SECURITY;
ALTER TABLE original_upload FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON original_upload
  USING (organization_id=app_org_id()) WITH CHECK (organization_id=app_org_id());

COMMENT ON TABLE original_upload IS
  'Server-owned original upload capability and trusted storage verification facts; client declarations never set photo VERIFIED.';

COMMIT;
