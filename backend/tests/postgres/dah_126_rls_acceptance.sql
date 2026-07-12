\set ON_ERROR_STOP on

-- This suite runs after dah_124_acceptance.sql has seeded two organizations and
-- after 0003 has installed the real capability roles and policies.

INSERT INTO organization_membership(organization_id,user_id,role) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000011','INSPECTOR'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000012','INSPECTOR');
INSERT INTO home_grant(organization_id,home_id,user_id,permission) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000031','00000000-0000-0000-0000-000000000011','manage'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000032','00000000-0000-0000-0000-000000000012','manage');
INSERT INTO google_calendar_connection(organization_id,user_id,calendar_id) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000011','calendar-a'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000012','calendar-b');
INSERT INTO field_task(organization_id,id,home_id,arrival_date) VALUES
  ('00000000-0000-0000-0000-000000000001','task-a','00000000-0000-0000-0000-000000000031',CURRENT_DATE),
  ('00000000-0000-0000-0000-000000000002','task-b','00000000-0000-0000-0000-000000000032',CURRENT_DATE);
INSERT INTO google_calendar_event(organization_id,user_id,calendar_id,event_id,task_id,home_id) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000011','calendar-a','event-a','task-a','00000000-0000-0000-0000-000000000031'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000012','calendar-b','event-b','task-b','00000000-0000-0000-0000-000000000032');

INSERT INTO asset(organization_id,id,home_id,room_id,asset_type,name,created_by,creating_inspection_id,client_id) VALUES
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000072','00000000-0000-0000-0000-000000000032','00000000-0000-0000-0000-000000000062','Appliance','Refrigerator','00000000-0000-0000-0000-000000000012','00000000-0000-0000-0000-000000000052','asset-b');
INSERT INTO photo(organization_id,id,home_id,room_id,asset_id,inspection_id,uploader_id,client_id,purpose,upload_status,original_object_key,sha256,byte_size,mime_type) VALUES
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000082','00000000-0000-0000-0000-000000000032','00000000-0000-0000-0000-000000000062','00000000-0000-0000-0000-000000000072','00000000-0000-0000-0000-000000000052','00000000-0000-0000-0000-000000000012','photo-b','asset_original','verified','00000000-0000-0000-0000-000000000002/00000000-0000-0000-0000-000000000032/originals/00000000-0000-0000-0000-000000000092.jpg',repeat('b',64),100,'image/jpeg');
INSERT INTO photo_derivative(organization_id,id,photo_id,kind,object_key) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-0000000000b1','00000000-0000-0000-0000-000000000081','thumbnail','a/thumb.jpg'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-0000000000b2','00000000-0000-0000-0000-000000000082','thumbnail','b/thumb.jpg');
INSERT INTO inspection_item_result(organization_id,id,home_id,inspection_id,item_key,result,recorded_by,client_id) VALUES
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-0000000000a2','00000000-0000-0000-0000-000000000032','00000000-0000-0000-0000-000000000052','housekeeping.kitchen.oven_clean','PASS','00000000-0000-0000-0000-000000000012','result-b');
INSERT INTO result_photo(organization_id,home_id,inspection_id,result_id,photo_id) VALUES
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000032','00000000-0000-0000-0000-000000000052','00000000-0000-0000-0000-0000000000a2','00000000-0000-0000-0000-000000000082');
INSERT INTO inspection_inventory_link(organization_id,inspection_id,home_id,entity_type,entity_id,room_id,action) VALUES
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000052','00000000-0000-0000-0000-000000000032','room','00000000-0000-0000-0000-000000000062','00000000-0000-0000-0000-000000000062','created');
INSERT INTO evidence_approval(organization_id,id,home_id,inspection_id,photo_id,item_id,result_id,asset_id,verdict,approved_by) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-0000000000c1','00000000-0000-0000-0000-000000000031','00000000-0000-0000-0000-000000000051','00000000-0000-0000-0000-000000000081','housekeeping.kitchen.oven_clean','00000000-0000-0000-0000-0000000000a1','00000000-0000-0000-0000-000000000071','PASS','00000000-0000-0000-0000-000000000011'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-0000000000c2','00000000-0000-0000-0000-000000000032','00000000-0000-0000-0000-000000000052','00000000-0000-0000-0000-000000000082','housekeeping.kitchen.oven_clean','00000000-0000-0000-0000-0000000000a2','00000000-0000-0000-0000-000000000072','PASS','00000000-0000-0000-0000-000000000012');

INSERT INTO asset_document(organization_id,id,asset_id,kind,object_key) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-0000000000d1','00000000-0000-0000-0000-000000000071','manual','a/manual.pdf'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-0000000000d2','00000000-0000-0000-0000-000000000072','manual','b/manual.pdf');
INSERT INTO asset_research_value(organization_id,id,asset_id,field_name,value,provenance) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-0000000000e1','00000000-0000-0000-0000-000000000071','model','"A"','user_entered'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-0000000000e2','00000000-0000-0000-0000-000000000072','model','"B"','user_entered');
INSERT INTO baseline_version(organization_id,id,home_id,inspection_id,version,created_by) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-0000000000f1','00000000-0000-0000-0000-000000000031','00000000-0000-0000-0000-000000000051',1,'00000000-0000-0000-0000-000000000011'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-0000000000f2','00000000-0000-0000-0000-000000000032','00000000-0000-0000-0000-000000000052',1,'00000000-0000-0000-0000-000000000012');
INSERT INTO baseline_photo(organization_id,baseline_id,photo_id) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-0000000000f1','00000000-0000-0000-0000-000000000081'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-0000000000f2','00000000-0000-0000-0000-000000000082');
INSERT INTO comparison(organization_id,id,home_id,baseline_id,inspection_id,result) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000101','00000000-0000-0000-0000-000000000031','00000000-0000-0000-0000-0000000000f1','00000000-0000-0000-0000-000000000051','{}'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000102','00000000-0000-0000-0000-000000000032','00000000-0000-0000-0000-0000000000f2','00000000-0000-0000-0000-000000000052','{}');
INSERT INTO damage_incident(organization_id,id,home_id,comparison_id,status) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000111','00000000-0000-0000-0000-000000000031','00000000-0000-0000-0000-000000000101','draft'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000112','00000000-0000-0000-0000-000000000032','00000000-0000-0000-0000-000000000102','draft');
INSERT INTO claim_export(organization_id,id,incident_id,object_key,manifest_sha256,created_by) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000121','00000000-0000-0000-0000-000000000111','a/claim.zip',repeat('a',64),'00000000-0000-0000-0000-000000000011'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000122','00000000-0000-0000-0000-000000000112','b/claim.zip',repeat('b',64),'00000000-0000-0000-0000-000000000012');
INSERT INTO video(organization_id,id,home_id,inspection_id,room_id,uploader_id,raw_object_key) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000131','00000000-0000-0000-0000-000000000031','00000000-0000-0000-0000-000000000051','00000000-0000-0000-0000-000000000061','00000000-0000-0000-0000-000000000011','a/raw.webm'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000132','00000000-0000-0000-0000-000000000032','00000000-0000-0000-0000-000000000052','00000000-0000-0000-0000-000000000062','00000000-0000-0000-0000-000000000012','b/raw.webm');
INSERT INTO audit_event(organization_id,id,actor_user_id,action) VALUES
  ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000141','00000000-0000-0000-0000-000000000011','job.queued'),
  ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000142','00000000-0000-0000-0000-000000000012','job.queued');

CREATE TEMP TABLE expected_tenant_table(table_name text PRIMARY KEY, tenant_column text NOT NULL) ON COMMIT PRESERVE ROWS;
INSERT INTO expected_tenant_table VALUES
 ('organization','id'),('portfolio','organization_id'),('organization_membership','organization_id'),
 ('home','organization_id'),('home_grant','organization_id'),('google_calendar_connection','organization_id'),
 ('google_calendar_event','organization_id'),('field_task','organization_id'),('room_type','organization_id'),
 ('inspection','organization_id'),('room','organization_id'),('asset','organization_id'),('photo','organization_id'),
 ('photo_derivative','organization_id'),('inspection_inventory_link','organization_id'),
 ('evidence_approval','organization_id'),('asset_document','organization_id'),
 ('asset_research_value','organization_id'),('baseline_version','organization_id'),
 ('baseline_photo','organization_id'),('comparison','organization_id'),('damage_incident','organization_id'),
 ('claim_export','organization_id'),('video','organization_id'),('audit_event','organization_id'),
 ('inspection_item_result','organization_id'),('result_photo','organization_id'),
 ('legacy_inspection_report','organization_id');

DO $catalog$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='vantage_runtime'
    AND (rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolinherit)) THEN
    RAISE EXCEPTION 'vantage_runtime has unsafe attributes';
  END IF;
  IF EXISTS (SELECT 1 FROM expected_tenant_table e JOIN pg_class c ON c.relname=e.table_name
    AND c.relnamespace='public'::regnamespace WHERE NOT c.relrowsecurity OR NOT c.relforcerowsecurity) THEN
    RAISE EXCEPTION 'tenant table is missing ENABLE/FORCE RLS';
  END IF;
  IF EXISTS (SELECT 1 FROM expected_tenant_table e JOIN pg_class c ON c.relname=e.table_name
    AND c.relnamespace='public'::regnamespace JOIN pg_roles r ON r.oid=c.relowner
    WHERE r.rolname<>'vantage_migration_owner') THEN
    RAISE EXCEPTION 'tenant table owner is not migration owner';
  END IF;
  IF EXISTS (SELECT 1 FROM expected_tenant_table e WHERE
    (SELECT count(*) FROM pg_policies p WHERE p.schemaname='public' AND p.tablename=e.table_name)<>4) THEN
    RAISE EXCEPTION 'tenant table does not have four operation policies';
  END IF;
  IF EXISTS (SELECT 1 FROM expected_tenant_table e JOIN pg_policies p
    ON p.schemaname='public' AND p.tablename=e.table_name
    WHERE (p.cmd IN ('SELECT','DELETE') AND p.qual IS NULL)
       OR (p.cmd='INSERT' AND p.with_check IS NULL)
       OR (p.cmd='UPDATE' AND (p.qual IS NULL OR p.with_check IS NULL))) THEN
    RAISE EXCEPTION 'USING/WITH CHECK policy contract is incomplete';
  END IF;
  IF EXISTS (SELECT 1 FROM expected_tenant_table e
    WHERE has_table_privilege('vantage_auth_bootstrap',format('public.%I',e.table_name),'SELECT')) THEN
    RAISE EXCEPTION 'auth bootstrap has direct tenant-table access';
  END IF;
END $catalog$;

CREATE OR REPLACE FUNCTION pg_temp.assert_rls_matrix(target regclass, tenant_column text)
RETURNS void LANGUAGE plpgsql AS $matrix$
DECLARE visible_count bigint; affected bigint;
DECLARE org_a constant uuid := '00000000-0000-0000-0000-000000000001';
DECLARE org_b constant uuid := '00000000-0000-0000-0000-000000000002';
DECLARE org_spoof constant uuid := '00000000-0000-0000-0000-000000000099';
BEGIN
  EXECUTE format('SELECT count(*) FROM %s',target) INTO visible_count;
  IF visible_count=0 THEN RAISE EXCEPTION '% has no visible Org A qualification row',target; END IF;
  EXECUTE format('SELECT count(*) FROM %s WHERE %I=$1',target,tenant_column) INTO visible_count USING org_b;
  IF visible_count<>0 THEN RAISE EXCEPTION '% leaked Org B SELECT',target; END IF;

  EXECUTE format('UPDATE %s SET %I=%I WHERE %I=$1',target,tenant_column,tenant_column,tenant_column) USING org_b;
  GET DIAGNOSTICS affected=ROW_COUNT;
  IF affected<>0 THEN RAISE EXCEPTION '% mutated Org B UPDATE',target; END IF;
  EXECUTE format('DELETE FROM %s WHERE %I=$1',target,tenant_column) USING org_b;
  GET DIAGNOSTICS affected=ROW_COUNT;
  IF affected<>0 THEN RAISE EXCEPTION '% mutated Org B DELETE',target; END IF;

  BEGIN
    EXECUTE format('UPDATE %s SET %I=$1 WHERE %I=$2',target,tenant_column,tenant_column)
      USING org_spoof,org_a;
    RAISE EXCEPTION '% accepted payload-spoofed tenant UPDATE',target;
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
  BEGIN
    EXECUTE format(
      'INSERT INTO %s SELECT (json_populate_record(NULL::%s,to_jsonb(src)||jsonb_build_object(%L,$1))).* FROM %s src WHERE %I=$2 LIMIT 1',
      target,target,tenant_column,target,tenant_column
    ) USING org_spoof,org_a;
    RAISE EXCEPTION '% accepted payload-spoofed tenant INSERT',target;
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
END $matrix$;

SET ROLE vantage_runtime;
BEGIN;
SELECT set_config('app.org_id','00000000-0000-0000-0000-000000000001',true);
SELECT set_config('app.user_id','00000000-0000-0000-0000-000000000011',true);
DO $all_tables$
DECLARE item record;
BEGIN
  FOR item IN SELECT * FROM expected_tenant_table ORDER BY table_name LOOP
    PERFORM pg_temp.assert_rls_matrix(format('public.%I',item.table_name)::regclass,item.tenant_column);
  END LOOP;
END $all_tables$;
ROLLBACK;

-- Pool checkout simulation: transaction-local state expires at COMMIT. Missing
-- either org or user defaults to no rows; alternating organizations is safe.
BEGIN;
SELECT set_config('app.org_id','00000000-0000-0000-0000-000000000001',true);
SELECT set_config('app.user_id','00000000-0000-0000-0000-000000000011',true);
SELECT CASE WHEN count(*)>0 THEN 1 ELSE 1/0 END FROM home;
COMMIT;
BEGIN;
SELECT CASE WHEN count(*)=0 THEN 1 ELSE 1/0 END FROM home;
ROLLBACK;
BEGIN;
SELECT set_config('app.org_id','00000000-0000-0000-0000-000000000001',true);
SELECT CASE WHEN count(*)=0 THEN 1 ELSE 1/0 END FROM home;
ROLLBACK;
BEGIN;
SELECT set_config('app.org_id','00000000-0000-0000-0000-000000000002',true);
SELECT set_config('app.user_id','00000000-0000-0000-0000-000000000012',true);
SELECT CASE WHEN count(*)>0 AND bool_and(organization_id='00000000-0000-0000-0000-000000000002') THEN 1 ELSE 1/0 END FROM home;
ROLLBACK;

RESET ROLE;
SET ROLE vantage_auth_bootstrap;
SELECT CASE WHEN count(*)=1 THEN 1 ELSE 1/0 END FROM auth_user_by_email('a@example.com');
SELECT CASE WHEN count(*)=1 THEN 1 ELSE 1/0 END FROM auth_active_memberships('00000000-0000-0000-0000-000000000011');
DO $bootstrap_denied$
BEGIN
  BEGIN PERFORM count(*) FROM home;
    RAISE EXCEPTION 'auth bootstrap unexpectedly read homes';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
END $bootstrap_denied$;
RESET ROLE;

SELECT 'DAH-126 PostgreSQL RLS qualification passed' AS result;
