-- 0006_dah_126_auth_function_rls_fix.sql
-- Fix: auth_active_memberships and auth_user_by_email are SECURITY DEFINER
-- functions owned by vantage_migration_owner (NOBYPASSRLS). When called by
-- vantage_auth_bootstrap without a tenant context (app.org_id is unset),
-- RLS policies on organization_membership and organization filter all rows,
-- so the functions return zero rows. This breaks the login discovery flow.
--
-- Solution: create a dedicated vantage_auth_reader role with BYPASSRLS that
-- owns only these two bootstrap lookup functions. The role has no login --
-- it exists solely so SECURITY DEFINER functions can read tenant tables
-- without RLS filtering during unauthenticated bootstrap (email lookup ->
-- membership discovery -> organization selection). The role is granted
-- SELECT only on the three tables the functions query; it has no other
-- privileges and no direct login access.

BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vantage_auth_reader') THEN
    CREATE ROLE vantage_auth_reader NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS NOLOGIN;
  END IF;
END $$;

-- Enforce attributes even when the role pre-exists (same pattern as 0003):
-- a pre-existing role without BYPASSRLS would silently break login discovery,
-- and one with LOGIN would be a credential-bearing RLS bypass.
ALTER ROLE vantage_auth_reader
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS NOLOGIN;

ALTER FUNCTION public.auth_user_by_email(text) OWNER TO vantage_auth_reader;
ALTER FUNCTION public.auth_active_memberships(uuid) OWNER TO vantage_auth_reader;

-- The new owner needs SELECT on the tables the functions query.
-- app_user has no RLS (global identity table).
-- organization_membership and organization have FORCE RLS, but
-- vantage_auth_reader has BYPASSRLS so the policies are skipped.
GRANT SELECT ON TABLE public.app_user TO vantage_auth_reader;
GRANT SELECT ON TABLE public.organization_membership TO vantage_auth_reader;
GRANT SELECT ON TABLE public.organization TO vantage_auth_reader;

-- Preserve the explicit grant chain: only vantage_auth_bootstrap may call these.
REVOKE ALL ON FUNCTION public.auth_user_by_email(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.auth_active_memberships(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.auth_user_by_email(text) TO vantage_auth_bootstrap;
GRANT EXECUTE ON FUNCTION public.auth_active_memberships(uuid) TO vantage_auth_bootstrap;

COMMIT;
