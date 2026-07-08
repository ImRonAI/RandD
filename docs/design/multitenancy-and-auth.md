# Multi-Tenancy, Authentication & Tenant Onboarding — Design Doc

**Status:** Draft for review · **Date:** 2026-07-08 · **Author:** Kilo (grounded, read-only analysis + verified DB inspection)
**Target stack:** `backend/` (FastAPI) + `frontend/` (React/Vite) — the **live, deployed** stack.
**Scope:** Turn the current single-tenant STR QC app into a multi-tenant platform with login/authorization and a UI for onboarding new tenants' houses/schedules via CSV upload.

> This doc is a plan. **No production code or the live database has been modified.** Every claim about current state below was verified by reading files and querying the live `str_qc.sqlite`; command outputs are cited inline.

---

## 0. Verified current state (ground truth, not assumptions)

| Fact | Evidence |
|---|---|
| **No auth anywhere.** API fully open, CORS `*`, no `Depends()` guards, no user table. | `backend/app/main.py:27-33`; grep found zero inbound-auth code |
| **Single tenant, no tenant column.** Core tables have no tenant/account/org FK. | `sql/phase1_schema.sql`; live DB `PRAGMA table_info(property)` shows no tenant col |
| **Live DB is on the phase-1 schema, NOT the `packages/db` migrations.** No `escapia_pmc_id`, no `schema_migration` ledger. | Live query: `no such column: escapia_pmc_id`, `no such table: schema_migration` |
| **The `apps/*` + `packages/*` tree is NOT what runs.** It's a parallel, unused rewrite. | root `package.json:5-8` runs `backend/`+`frontend/`; `apps/web` is a stock Next scaffold (`apps/web/src/app/page.tsx`) |
| **Existing data = RandD Tradesmen (Tenant #1), and only them.** | Live counts: 96 property, 65 task, 5 stakeholder, 97 stakeholder_role, 11 cluster; 0 work_order/report/inspection/photo |
| **`property.unit_code` is globally UNIQUE.** Blocks two tenants reusing a code. | `sql/phase1_schema.sql:26` |
| **Data was loaded via a one-time CSV importer** (roster + master checklist). There is no in-app upload path today. | `scripts/migrate_phase1.py` |
| **`STRQC_SESSION_SECRET` exists but is empty.** Reserved for session signing. | `.env:78`, `packages/shared/.../config.py:59` |
| **Deploy = SQLite file per host, uvicorn behind nginx, `.env` via systemd `EnvironmentFile`; `/ws` proxied with Upgrade headers.** | `scripts/deploy_ec2.py`, `scripts/setup_remote_ec2.sh:69-80,136-155` |

**Two honest risks up front:**
1. The migration chain in `packages/db` assumes a DB that does not exist in production. Tenancy must be authored against the **live phase-1 schema**, not that chain.
2. Backfill/constraint-tightening runs against **32 MB of real RandD data on the EC2 host**. Must be backup-first, validated on a copy, before touching the server.

---

## 1. Tenancy model

- **New table `tenant`** — the isolation boundary.
  - `tenant_id INTEGER PK`, `name TEXT`, `slug TEXT UNIQUE`, `is_active INTEGER`, `created_at TEXT`.
  - **Row 1 = RandD Tradesmen** (existing client). All current data is claimed for it.
- **Add `tenant_id` to every tenant-owned table**: `property`, `task`, `stakeholder`, `cluster`, `work_order`, `report`, `inspection`, `photo_memory`, `stakeholder_role`, `maintenance_check`, `inspection_reports`.
- **`unit_code` uniqueness becomes per-tenant**: drop global `UNIQUE(unit_code)`, add `UNIQUE(tenant_id, unit_code)`. (SQLite → table rebuild inside a transaction.)
- **Isolation rule:** RandD's rows are never visible to any other tenant. New tenants start with **zero** houses/tasks/stakeholders and load their own.

---

## 2. Authentication & authorization

- **New table `app_user`**: `user_id`, `tenant_id` (FK, nullable only for platform super-admin), `email UNIQUE`, `password_hash` (argon2 or bcrypt), `is_platform_admin INTEGER`, `stakeholder_id` (nullable FK — links a login to an operational person), `is_active`, `created_at`.
- **Reuse existing role model** (`role` / `stakeholder_role`, `phase1_schema.sql:18-65`) for in-tenant authorization scopes (QC_INSPECTOR, PROPERTY_MANAGER, etc.). No new RBAC vocabulary invented.
- **Sessions:** JWT (or signed cookie) signed with `STRQC_SESSION_SECRET` (must be populated — currently empty). Claims carry `user_id`, `tenant_id`, `is_platform_admin`.
- **Who creates tenants/users:** **platform super-admin only** (per decision). Super-admin creates a tenant + its first admin user; that tenant admin then manages their own users. No public self-signup.

### HTTP enforcement
- Add `Depends(current_user)` to every `/api/*` route in `backend/app/main.py` (today: **none**).
- Tighten CORS from `*` to the real origin `https://44-193-208-77.sslip.io` (`main.py:29`).

### WebSocket enforcement (`/ws`, `main.py:241`)
- Browsers can't set WS headers → pass token as query param: `wss://…/ws?token=<JWT>`.
- Validate at `websocket.accept()`; reject/close on failure.
- **Bind resolved `tenant_id` into the `BidiAgent` session** so every agent tool (property lookup, work-order creation, journal) is tenant-scoped. nginx already forwards `/ws` with Upgrade headers (`setup_remote_ec2.sh:69-80`) — no infra change.

---

## 3. Tenant-scoped data access (the safety-critical part)

SQLite has **no row-level security**, so isolation is enforced in code:
- **A tenant-scoped connection/repository wrapper**: all reads/writes require an explicit `tenant_id` and inject `WHERE tenant_id = ?` — no ambient/global query is allowed. Refactor `backend/app/properties.py`, `report_db.py`, and any future repos through it.
- **Secrets** (`packages/shared/.../crypto.py`) already support AAD binding (currently unit code); extend AAD to include `tenant_id` so ciphertext is bound to its tenant.
- **Negative boundary tests (required):** tests that log in as Tenant B and attempt to read Tenant A's (RandD's) houses/door codes and assert **empty/403**. A green suite without these tests does not prove isolation.

---

## 4. Tenant onboarding UI (CSV upload) — per decision

New tenants have no data and must load it themselves. The UI mirrors the **exact** two-file shape the original importer used (`scripts/migrate_phase1.py`), so it's proven, not invented:

1. **Address roster CSV** → properties. Columns (with the importer's aliases): Property/Unit Code, Address, Cluster, Display Name, Standing Instructions, QC Assignee, WiFi SSID/Password, Door Code, feature flags (Hot Tub, TV, EV Charger, Arcade, Patio, Porch, Bathroom, Bedroom). (`migrate_phase1.py:274-341`)
2. **Master checklist CSV** → tasks/schedule. Columns: House/Unit Code, Arrival Date, Cleaner/Housekeeper, stage flags QC/B2B/CLN/DONE/OWN/WO/DONE_WO/REPORT. (`migrate_phase1.py:343-423`)

**Backend work:** new authenticated endpoints (e.g. `POST /api/import/roster`, `POST /api/import/master`) that reuse the existing `Migrator` parsing/validation logic **but scoped to the caller's `tenant_id`**, and surface the existing `migration_issue` warnings/errors back to the UI (blank status, invalid date, duplicate code, plaintext credential, etc.).
**Frontend work:** an admin "Onboarding / Import" screen — upload both files, preview parsed rows, show validation issues, confirm, then commit. Plus (Phase 2) manual add/edit forms for single houses/tasks.

---

## 5. Migration plan (against the LIVE phase-1 DB, backup-first)

Authored as a new SQL migration applied to `./str_qc.sqlite` (the file the backend actually opens):

1. **Backup** `str_qc.sqlite` (local + EC2) and validate every step on a **copy** first.
2. Create `tenant`; insert **Tenant #1 = RandD Tradesmen**.
3. Add `tenant_id` (nullable) to all tenant-owned tables.
4. **Backfill** `tenant_id = 1` on all existing rows (all 96/65/5/97/11 are RandD's).
5. Verify zero NULL `tenant_id` remain (assert counts match pre-migration totals).
6. **Tighten:** `NOT NULL` + FK; rebuild `property` to swap global `UNIQUE(unit_code)` → `UNIQUE(tenant_id, unit_code)`.
7. Create `app_user`; create RandD's first admin + the platform super-admin.
8. Populate `STRQC_SESSION_SECRET`.

**Every step validated by row-count assertions and the existing 59-test suite (verified passing: `59 passed`) before/after, on a copy, before the EC2 host is touched.**

---

## 6. Sequenced deliverables

1. Design review + sign-off on this doc (name for Tenant #1 = "RandD Tradesmen" confirmed).
2. Tenancy migration (backup → add col → backfill → verify → tighten) on a **copy**; show before/after.
3. `app_user` + auth (hashing, JWT via `STRQC_SESSION_SECRET`, `current_user` dependency).
4. Tenant-scoped repository wrapper + refactor existing queries + **negative isolation tests**.
5. HTTP guards on all `/api/*`; CORS tightened; WS token auth + agent tenant binding.
6. CSV import endpoints (reuse `Migrator`, tenant-scoped) + issue reporting.
7. Frontend: login, super-admin tenant/user creation, tenant onboarding/import screen.
8. Deploy: run migration on EC2 (post-backup), rotate `.env`, restart `strqc-backend.service`, verify.

---

## 7. Open decisions needed before coding

- Confirm **Tenant #1 display name/slug** = "RandD Tradesmen".
- Confirm auth token style: **JWT bearer** vs **signed HTTP-only cookie** (cookie is safer for a browser PWA; JWT is simpler for the WS query-param path). Recommendation: cookie for HTTP, short-lived query-param token minted for WS.
- Confirm the `packages/*`/`apps/*` tree is **abandoned** (not to be kept in sync) so tenancy is built only in `backend/`+`frontend/`.
