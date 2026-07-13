BEGIN;

DO $$
BEGIN
  IF to_regclass('public.original_upload') IS NULL THEN
    RAISE EXCEPTION 'DAH-131: original_upload table is missing';
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relname = 'original_upload'
       AND c.relrowsecurity
       AND c.relforcerowsecurity
  ) THEN
    RAISE EXCEPTION 'DAH-131: original_upload must force row level security';
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
     WHERE schemaname='public'
       AND tablename='original_upload'
       AND policyname='tenant_isolation'
       AND qual='(organization_id = app_org_id())'
       AND with_check='(organization_id = app_org_id())'
  ) THEN
    RAISE EXCEPTION 'DAH-131: original_upload tenant RLS policy is missing or weak';
  END IF;
END $$;

INSERT INTO original_upload(
  organization_id,id,home_id,photo_id,storage_bucket,object_key,
  expected_byte_size,expected_sha256,expected_mime_type)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000131001',
  '00000000-0000-0000-0000-000000000031',
  '00000000-0000-0000-0000-000000000081',
  'vantage-originals-285527663773-us-east-1',
  '00000000-0000-0000-0000-000000000001/00000000-0000-0000-0000-000000000031/originals/00000000-0000-0000-0000-000000000081.jpg',
  16,
  repeat('a', 64),
  'image/jpeg'
);

DO $$
BEGIN
  BEGIN
    UPDATE original_upload SET status='verified'
     WHERE id='00000000-0000-0000-0000-000000131001';
    RAISE EXCEPTION 'DAH-131: verified upload without immutable storage facts was accepted';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;
END $$;

DO $$
BEGIN
  BEGIN
    UPDATE original_upload
       SET status='verified',
           storage_version_id='',
           encryption_algorithm='AES256',
           kms_key_id='arn:aws:kms:us-east-1:285527663773:key/baf88381-c321-4bdb-8936-a91e28384a50',
           object_lock_mode='COMPLIANCE',
           retention_until='2026-07-13T12:46:58Z',
           verified_at=now(),
           last_error_code=NULL
     WHERE id='00000000-0000-0000-0000-000000131001';
    RAISE EXCEPTION 'DAH-131: empty version verified upload was accepted';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;
  BEGIN
    UPDATE original_upload
       SET status='verified',
           storage_version_id='bad-version',
           encryption_algorithm='AES256',
           kms_key_id='arn:aws:kms:us-east-1:285527663773:key/baf88381-c321-4bdb-8936-a91e28384a50',
           object_lock_mode='COMPLIANCE',
           retention_until='2026-07-13T12:46:58Z',
           verified_at=now(),
           last_error_code=NULL
     WHERE id='00000000-0000-0000-0000-000000131001';
    RAISE EXCEPTION 'DAH-131: non-KMS verified upload was accepted';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;
  BEGIN
    UPDATE original_upload
       SET status='verified',
           storage_version_id='bad-version',
           encryption_algorithm='aws:kms',
           kms_key_id=NULL,
           object_lock_mode='COMPLIANCE',
           retention_until='2026-07-13T12:46:58Z',
           verified_at=now(),
           last_error_code=NULL
     WHERE id='00000000-0000-0000-0000-000000131001';
    RAISE EXCEPTION 'DAH-131: verified upload without KMS key was accepted';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;
  BEGIN
    UPDATE original_upload
       SET status='verified',
           storage_version_id='bad-version',
           encryption_algorithm='aws:kms',
           kms_key_id='arn:aws:kms:us-east-1:285527663773:key/baf88381-c321-4bdb-8936-a91e28384a50',
           object_lock_mode='GOVERNANCE',
           retention_until='2026-07-13T12:46:58Z',
           verified_at=now(),
           last_error_code=NULL
     WHERE id='00000000-0000-0000-0000-000000131001';
    RAISE EXCEPTION 'DAH-131: non-COMPLIANCE verified upload was accepted';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;
  BEGIN
    UPDATE original_upload
       SET status='verified',
           storage_version_id='bad-version',
           encryption_algorithm='aws:kms',
           kms_key_id='arn:aws:kms:us-east-1:285527663773:key/baf88381-c321-4bdb-8936-a91e28384a50',
           object_lock_mode='COMPLIANCE',
           retention_until=now() - interval '1 second',
           verified_at=now(),
           last_error_code=NULL
     WHERE id='00000000-0000-0000-0000-000000131001';
    RAISE EXCEPTION 'DAH-131: expired retention verified upload was accepted';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;
  BEGIN
    UPDATE original_upload
       SET status='verified',
           storage_version_id='bad-version',
           encryption_algorithm='aws:kms',
           kms_key_id='arn:aws:kms:us-east-1:285527663773:key/baf88381-c321-4bdb-8936-a91e28384a50',
           object_lock_mode='COMPLIANCE',
           retention_until=now() + interval '1 day',
           verified_at=now(),
           last_error_code='media_hash_mismatch'
     WHERE id='00000000-0000-0000-0000-000000131001';
    RAISE EXCEPTION 'DAH-131: verified upload with stale error was accepted';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;
END $$;

UPDATE original_upload
   SET status='failed', verification_attempts=verification_attempts+1,
       last_error_code='media_hash_mismatch'
 WHERE id='00000000-0000-0000-0000-000000131001';

DO $$
DECLARE
  attempts integer;
BEGIN
  SELECT verification_attempts INTO attempts
    FROM original_upload
   WHERE id='00000000-0000-0000-0000-000000131001';
  IF attempts <> 1 THEN
    RAISE EXCEPTION 'DAH-131: failure attempts were not recorded';
  END IF;
END $$;

UPDATE original_upload
   SET status='verified',
       storage_version_id='XzwsAtm7xwUJjzhijF57MmEsff6VuLqV',
       etag='opaque-etag-not-a-hash',
       encryption_algorithm='aws:kms',
       kms_key_id='arn:aws:kms:us-east-1:285527663773:key/baf88381-c321-4bdb-8936-a91e28384a50',
       object_lock_mode='COMPLIANCE',
       retention_until=now() + interval '1 day',
       legal_hold_status=NULL,
       last_error_code=NULL,
       verified_at=now()
 WHERE id='00000000-0000-0000-0000-000000131001';

ROLLBACK;
