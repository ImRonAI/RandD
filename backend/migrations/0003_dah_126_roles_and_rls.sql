BEGIN;

-- Capability roles are deliberately NOLOGIN. Deployment creates separate
-- credential-bearing login roles and grants exactly one capability role to
-- each login (see docs/security/DAH-126-RLS-QUALIFICATION.md).
DO $roles$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='vantage_migration_owner') THEN
    CREATE ROLE vantage_migration_owner NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='vantage_runtime') THEN
    CREATE ROLE vantage_runtime NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='vantage_auth_bootstrap') THEN
    CREATE ROLE vantage_auth_bootstrap NOLOGIN;
  END IF;
END $roles$;

ALTER ROLE vantage_migration_owner NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
ALTER ROLE vantage_runtime NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
ALTER ROLE vantage_auth_bootstrap NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO vantage_migration_owner;

-- All application objects have one non-runtime owner. FORCE RLS therefore
-- remains defense in depth while catalog checks can prove runtime ownership is
-- impossible.
DO $ownership$
DECLARE object_name text;
BEGIN
  FOREACH object_name IN ARRAY ARRAY[
    'organization','portfolio','app_user','organization_membership','home',
    'google_calendar_connection','google_calendar_event','field_task','home_grant',
    'room_type','inspection','room','asset','photo','photo_derivative',
    'inspection_inventory_link','evidence_approval','asset_document',
    'asset_research_value','baseline_version','baseline_photo','comparison',
    'damage_incident','claim_export','video','magic_code_challenge','revoked_token',
    'audit_event','checklist_item','inspection_item_result','result_photo',
    'legacy_inspection_report'
  ] LOOP
    EXECUTE format('ALTER TABLE public.%I OWNER TO vantage_migration_owner', object_name);
  END LOOP;
END $ownership$;

ALTER FUNCTION public.app_org_id() OWNER TO vantage_migration_owner;
ALTER FUNCTION public.app_user_id() OWNER TO vantage_migration_owner;
ALTER FUNCTION public.app_org_id() SET search_path = pg_catalog;
ALTER FUNCTION public.app_user_id() SET search_path = pg_catalog;
REVOKE ALL ON FUNCTION public.app_org_id() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.app_user_id() FROM PUBLIC;

-- Replace the broad ALL policies with operation-specific contracts. UPDATE
-- intentionally has both USING (old row) and WITH CHECK (new row).
DO $policies$
DECLARE object_name text;
DECLARE tenant_column text;
BEGIN
  FOREACH object_name IN ARRAY ARRAY[
    'organization','portfolio','organization_membership','home','home_grant',
    'google_calendar_connection','google_calendar_event','field_task','room_type',
    'inspection','room','asset','photo','photo_derivative',
    'inspection_inventory_link','evidence_approval','asset_document',
    'asset_research_value','baseline_version','baseline_photo','comparison',
    'damage_incident','claim_export','video','audit_event',
    'inspection_item_result','result_photo','legacy_inspection_report'
  ] LOOP
    tenant_column := CASE WHEN object_name='organization' THEN 'id' ELSE 'organization_id' END;
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', object_name);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', object_name);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON public.%I', object_name);
    EXECUTE format('DROP POLICY IF EXISTS tenant_select ON public.%I', object_name);
    EXECUTE format('DROP POLICY IF EXISTS tenant_insert ON public.%I', object_name);
    EXECUTE format('DROP POLICY IF EXISTS tenant_update ON public.%I', object_name);
    EXECUTE format('DROP POLICY IF EXISTS tenant_delete ON public.%I', object_name);
    EXECUTE format('CREATE POLICY tenant_select ON public.%I FOR SELECT USING (%I=public.app_org_id() AND public.app_user_id() IS NOT NULL)', object_name, tenant_column);
    EXECUTE format('CREATE POLICY tenant_insert ON public.%I FOR INSERT WITH CHECK (%I=public.app_org_id() AND public.app_user_id() IS NOT NULL)', object_name, tenant_column);
    EXECUTE format('CREATE POLICY tenant_update ON public.%I FOR UPDATE USING (%I=public.app_org_id() AND public.app_user_id() IS NOT NULL) WITH CHECK (%I=public.app_org_id() AND public.app_user_id() IS NOT NULL)', object_name, tenant_column, tenant_column);
    EXECUTE format('CREATE POLICY tenant_delete ON public.%I FOR DELETE USING (%I=public.app_org_id() AND public.app_user_id() IS NOT NULL)', object_name, tenant_column);
  END LOOP;
END $policies$;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM vantage_runtime, vantage_auth_bootstrap;
GRANT USAGE ON SCHEMA public TO vantage_runtime, vantage_auth_bootstrap;
GRANT EXECUTE ON FUNCTION public.app_org_id() TO vantage_runtime;
GRANT EXECUTE ON FUNCTION public.app_user_id() TO vantage_runtime;

DO $runtime_grants$
DECLARE object_name text;
BEGIN
  FOREACH object_name IN ARRAY ARRAY[
    'organization','portfolio','organization_membership','home','home_grant',
    'google_calendar_connection','google_calendar_event','field_task','room_type',
    'inspection','room','asset','photo','photo_derivative',
    'inspection_inventory_link','evidence_approval','asset_document',
    'asset_research_value','baseline_version','baseline_photo','comparison',
    'damage_incident','claim_export','video','audit_event',
    'inspection_item_result','result_photo','legacy_inspection_report'
  ] LOOP
    EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.%I TO vantage_runtime', object_name);
  END LOOP;
END $runtime_grants$;
GRANT SELECT ON TABLE public.checklist_item TO vantage_runtime;

-- Unauthenticated login discovery is kept behind fixed-search-path,
-- column-limited functions. The bootstrap role has no direct tenant-table
-- privilege and cannot read homes, inventory, evidence, Calendar, or reports.
CREATE OR REPLACE FUNCTION public.auth_user_by_email(lookup_email text)
RETURNS TABLE(id uuid, email text, active boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $function$
  SELECT u.id,u.email,u.active
    FROM public.app_user AS u
   WHERE lower(u.email)=lower(lookup_email)
$function$;

CREATE OR REPLACE FUNCTION public.auth_active_memberships(lookup_user_id uuid)
RETURNS TABLE(organization_id uuid, organization_name text, role public.vantage_role)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $function$
  SELECT m.organization_id,o.name,m.role
    FROM public.organization_membership AS m
    JOIN public.organization AS o ON o.id=m.organization_id
   WHERE m.user_id=lookup_user_id AND m.active
$function$;

ALTER FUNCTION public.auth_user_by_email(text) OWNER TO vantage_migration_owner;
ALTER FUNCTION public.auth_active_memberships(uuid) OWNER TO vantage_migration_owner;
REVOKE ALL ON FUNCTION public.auth_user_by_email(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.auth_active_memberships(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.auth_user_by_email(text) TO vantage_auth_bootstrap;
GRANT EXECUTE ON FUNCTION public.auth_active_memberships(uuid) TO vantage_auth_bootstrap;
GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.magic_code_challenge TO vantage_auth_bootstrap;
GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.revoked_token TO vantage_auth_bootstrap;

ALTER DEFAULT PRIVILEGES FOR ROLE vantage_migration_owner IN SCHEMA public
  REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE vantage_migration_owner IN SCHEMA public
  REVOKE ALL ON FUNCTIONS FROM PUBLIC;

COMMIT;
