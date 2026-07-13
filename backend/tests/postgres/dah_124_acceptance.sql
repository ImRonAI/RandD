\set ON_ERROR_STOP on

CREATE OR REPLACE FUNCTION pg_temp.expect_sqlstate(statement text, accepted_states text[])
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN
    EXECUTE statement;
  EXCEPTION WHEN OTHERS THEN
    IF SQLSTATE = ANY(accepted_states) THEN
      RETURN;
    END IF;
    RAISE;
  END;
  RAISE EXCEPTION 'expected statement to fail with one of %, but it succeeded', accepted_states;
END
$$;

INSERT INTO organization(id,name) VALUES
  ('00000000-0000-0000-0000-000000000001','Alpha'),
  ('00000000-0000-0000-0000-000000000002','Beta');
INSERT INTO portfolio(organization_id,id,name) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000021','Alpha'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000022','Beta');
INSERT INTO app_user(id,email) VALUES
  ('00000000-0000-0000-0000-000000000011','a@example.com'),
  ('00000000-0000-0000-0000-000000000012','b@example.com');
INSERT INTO home(organization_id,id,portfolio_id,name,unit_code) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000031','00000000-0000-0000-0000-000000000021','Alpha Home','A'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000032','00000000-0000-0000-0000-000000000022','Beta Home','B');
INSERT INTO room_type(organization_id,id,name) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000041','Kitchen'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000042','Kitchen');
INSERT INTO inspection(organization_id,id,home_id,inspection_type,client_id,created_by) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000051','00000000-0000-0000-0000-000000000031','turnover','inspection-a','00000000-0000-0000-0000-000000000011'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000052','00000000-0000-0000-0000-000000000032','turnover','inspection-b','00000000-0000-0000-0000-000000000012');
INSERT INTO room(organization_id,id,home_id,room_type_id,name,created_by,creating_inspection_id,client_id) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000061','00000000-0000-0000-0000-000000000031','00000000-0000-0000-0000-000000000041','Kitchen','00000000-0000-0000-0000-000000000011','00000000-0000-0000-0000-000000000051','room-a'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000062','00000000-0000-0000-0000-000000000032','00000000-0000-0000-0000-000000000042','Kitchen','00000000-0000-0000-0000-000000000012','00000000-0000-0000-0000-000000000052','room-b');
INSERT INTO asset(organization_id,id,home_id,room_id,asset_type,name,created_by,creating_inspection_id,client_id) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000071','00000000-0000-0000-0000-000000000031','00000000-0000-0000-0000-000000000061','Appliance','Refrigerator','00000000-0000-0000-0000-000000000011','00000000-0000-0000-0000-000000000051','asset-a');
INSERT INTO photo(
  organization_id,id,home_id,room_id,asset_id,inspection_id,uploader_id,client_id,
  purpose,upload_status,original_object_key,sha256,byte_size,mime_type
) VALUES (
  '00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000081',
  '00000000-0000-0000-0000-000000000031','00000000-0000-0000-0000-000000000061',
  '00000000-0000-0000-0000-000000000071','00000000-0000-0000-0000-000000000051',
  '00000000-0000-0000-0000-000000000011','photo-a','asset_original','verified',
  '00000000-0000-0000-0000-000000000001/00000000-0000-0000-0000-000000000031/originals/00000000-0000-0000-0000-000000000091.jpg',
  repeat('a',64),100,'image/jpeg'
);
INSERT INTO inspection_item_result(
  organization_id,id,home_id,inspection_id,item_key,result,recorded_by,client_id
) VALUES (
  '00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-0000000000a1',
  '00000000-0000-0000-0000-000000000031','00000000-0000-0000-0000-000000000051',
  'housekeeping.kitchen.oven_clean','PASS','00000000-0000-0000-0000-000000000011','result-a'
);
INSERT INTO result_photo(organization_id,home_id,inspection_id,result_id,photo_id) VALUES (
  '00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000031',
  '00000000-0000-0000-0000-000000000051','00000000-0000-0000-0000-0000000000a1',
  '00000000-0000-0000-0000-000000000081'
);
INSERT INTO inspection_inventory_link(
  organization_id,inspection_id,home_id,entity_type,entity_id,room_id,action
) VALUES (
  '00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000051',
  '00000000-0000-0000-0000-000000000031','room','00000000-0000-0000-0000-000000000061',
  '00000000-0000-0000-0000-000000000061','created'
);
INSERT INTO legacy_inspection_report(organization_id,id,property,state_json) VALUES
  ('00000000-0000-0000-0000-000000000001','legacy-1','Alpha','{"items":[]}'),
  ('00000000-0000-0000-0000-000000000002','legacy-1','Beta','{"items":[]}');

DO $$
BEGIN
  IF (SELECT count(*) FROM checklist_item) <> 38 THEN
    RAISE EXCEPTION 'expected exactly 38 checklist items';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='inspection'
      AND column_name='inspection_type' AND udt_name='inspection_type'
  ) THEN RAISE EXCEPTION 'inspection_type contract is not installed'; END IF;
  IF (SELECT column_default FROM information_schema.columns
      WHERE table_schema='public' AND table_name='photo' AND column_name='purpose')
      NOT LIKE '%asset_original%' THEN
    RAISE EXCEPTION 'photo purpose default is missing';
  END IF;
END
$$;

SELECT pg_temp.expect_sqlstate(
  $$INSERT INTO asset(organization_id,id,home_id,room_id,created_by,client_id)
    VALUES ('00000000-0000-0000-0000-000000000001',gen_random_uuid(),
      '00000000-0000-0000-0000-000000000031','00000000-0000-0000-0000-000000000062',
      '00000000-0000-0000-0000-000000000011','cross-home')$$,
  ARRAY['23503']
);
SELECT pg_temp.expect_sqlstate(
  $$INSERT INTO inspection_inventory_link(
      organization_id,inspection_id,home_id,entity_type,entity_id,action)
    VALUES ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000051',
      '00000000-0000-0000-0000-000000000031','room',gen_random_uuid(),'created')$$,
  ARRAY['23514']
);
SELECT pg_temp.expect_sqlstate(
  $$INSERT INTO photo(
      organization_id,id,home_id,uploader_id,client_id,purpose,upload_status,
      original_object_key,sha256,byte_size,mime_type)
    VALUES ('00000000-0000-0000-0000-000000000001',gen_random_uuid(),
      '00000000-0000-0000-0000-000000000031','00000000-0000-0000-0000-000000000011',
      'bad-key','inspection_evidence','verified','wrong/key.jpg',repeat('b',64),10,'image/jpeg')$$,
  ARRAY['23514']
);
SELECT pg_temp.expect_sqlstate(
  $$INSERT INTO inspection_item_result(
      organization_id,home_id,inspection_id,item_key,result,recorded_by,client_id)
    VALUES ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000031',
      '00000000-0000-0000-0000-000000000051','hot_tub.full','REVIEW',
      '00000000-0000-0000-0000-000000000011','invalid-result')$$,
  ARRAY['22P02']
);
SELECT pg_temp.expect_sqlstate(
  $$INSERT INTO evidence_approval(
      organization_id,id,home_id,inspection_id,photo_id,item_id,result_id,asset_id,verdict,approved_by)
    VALUES ('00000000-0000-0000-0000-000000000001',gen_random_uuid(),
      '00000000-0000-0000-0000-000000000031','00000000-0000-0000-0000-000000000051',
      '00000000-0000-0000-0000-000000000081','hot_tub.full',
      '00000000-0000-0000-0000-0000000000a1','00000000-0000-0000-0000-000000000071',
      'PASS','00000000-0000-0000-0000-000000000011')$$,
  ARRAY['23503']
);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vantage_runtime') THEN
    CREATE ROLE vantage_runtime NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END $$;
GRANT USAGE ON SCHEMA public TO vantage_runtime;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO vantage_runtime;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO vantage_runtime;
GRANT EXECUTE ON FUNCTION app_org_id() TO vantage_runtime;
GRANT EXECUTE ON FUNCTION app_user_id() TO vantage_runtime;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='vantage_runtime'
      AND (rolsuper OR rolbypassrls)) THEN
    RAISE EXCEPTION 'runtime role bypasses row security';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_class
    WHERE relnamespace='public'::regnamespace AND relkind='r'
      AND relname IN ('inspection_item_result','result_photo','legacy_inspection_report')
      AND (NOT relrowsecurity OR NOT relforcerowsecurity)
  ) THEN RAISE EXCEPTION 'new tenant tables are missing ENABLE/FORCE RLS'; END IF;
END
$$;

BEGIN;
SET LOCAL ROLE vantage_runtime;
SELECT set_config('app.org_id','00000000-0000-0000-0000-000000000001',true);
SELECT set_config('app.user_id','00000000-0000-0000-0000-000000000011',true);
DO $$
BEGIN
  IF (SELECT count(*) FROM home) <> 1 THEN RAISE EXCEPTION 'RLS leaked another organization home'; END IF;
  IF (SELECT count(*) FROM legacy_inspection_report) <> 1 THEN RAISE EXCEPTION 'RLS leaked legacy history'; END IF;
  BEGIN
    INSERT INTO legacy_inspection_report(organization_id,id,state_json)
    VALUES ('00000000-0000-0000-0000-000000000002','forbidden','{}');
    RAISE EXCEPTION 'cross-tenant insert unexpectedly passed RLS';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;
END
$$;
ROLLBACK;

SELECT 'DAH-124 PostgreSQL acceptance passed' AS result;
