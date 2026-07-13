# Vantage database migrations

Apply files in lexical order with a migration role that owns the schema. The
runtime role must not own tables, be a superuser, or have `BYPASSRLS`.
Vantage targets PostgreSQL 16 for local, CI, staging, and production so catalog,
constraint, and row-security behavior is consistent across environments.

Every request transaction must set tenant context before issuing tenant-owned
queries:

```sql
BEGIN;
SET LOCAL app.org_id = '00000000-0000-0000-0000-000000000001';
SET LOCAL app.user_id = '00000000-0000-0000-0000-000000000002';
-- queries
COMMIT;
```

`0001_vantage_v1_foundation.sql` is additive. Legacy SQLite tables are not
dropped or rewritten. Run `scripts/import_legacy_sqlite.py` against staging,
verify its JSON summary and source counts, then cut over application reads.
Historical House Keeping reports remain legacy records; the importer never
invents room mappings. Rollback is application cutback to SQLite plus removal
of the new PostgreSQL schema before production writes begin.

`0006_dah_126_auth_function_rls_fix.sql` adds `vantage_auth_reader` (NOLOGIN,
BYPASSRLS) as the owner of the two unauthenticated login-discovery functions
(`auth_user_by_email`, `auth_active_memberships`). That role has SELECT only on
`app_user`, `organization`, and `organization_membership`. Runtime and
bootstrap login roles must not receive BYPASSRLS; only EXECUTE on those
functions is granted to `vantage_auth_bootstrap`.
