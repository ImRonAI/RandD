# Vantage database migrations

Apply files in lexical order with a migration role that owns the schema. The
runtime role must not own tables, be a superuser, or have `BYPASSRLS`.

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

