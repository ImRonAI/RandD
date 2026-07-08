# Implementation Spec — Multi-Tenancy, Authentication & Tenant Onboarding

**Status:** Ready to implement · **Date:** 2026-07-08
**Audience:** the code agent that will write the `.py` / `.ts` / `.sql` (this spec author is restricted to `.md`).
**Target stack (canonical, live, deployed):** `backend/` (FastAPI) + `frontend/` (React 19 + Vite 7). **NOT** `apps/*` / `packages/*` (abandoned rewrite — see §1.3).
**Prime directive:** **Do not disrupt anything currently working.** Every existing behavior in §2 must still work identically after these changes. When in doubt, make the new thing additive and default-on for the existing tenant.

> Everything in this spec was verified against the live codebase and the live `str_qc.sqlite` (96 properties, 65 tasks, 5 stakeholders, 97 stakeholder_role, 11 clusters, 51 inspection_reports). The migration was executed on a **copy** and proven: counts preserved, integrity ok, FK clean, per-tenant uniqueness demonstrated. Do not re-derive; follow exactly.

---

## 0. TL;DR of the whole job

1. Add a `tenant` table; claim **all existing data for tenant_id = 1 = "RandD Tradesmen"**.
2. Add `tenant_id` to every tenant-owned table; make `property.unit_code` and `cluster.name` unique **per tenant** instead of globally.
3. Add `app_user` (login), password hashing, cookie sessions, a short-lived WS token.
4. Gate the **3 DB-touching HTTP endpoints + `/ws`** behind auth; scope their queries by the caller's `tenant_id`.
5. Thread `tenant_id` into the `BidiAgent` session so future DB-backed agent tools stay tenant-scoped.
6. Build a **login screen** and a **CSV onboarding screen** (roster + master checklist upload) for new tenants, using already-vendored UI primitives.
7. Wire a **backup → ledger-guarded migrate → restart** step into deployment. Never auto-migrate without a backup.

---

## 1. Ground truth you must not violate

### 1.1 The database
- The backend opens **one** SQLite file: `STRQC_DB_PATH=./str_qc.sqlite` (resolved to repo root in `backend/app/properties.py:20-22` and `backend/app/report_db.py:24-26`).
- The live DB is on the **phase-1 schema** (`sql/phase1_schema.sql`). It has **no** `escapia_pmc_id` and **no** `schema_migration` ledger. (Verified.)
- The `packages/db` migrations `0001`/`0002` were **never applied** to production. Do not assume they exist. Author the tenancy migration against the phase-1 shape.

### 1.2 Existing data = RandD Tradesmen, and only them
- All current rows belong to the original client. The migration claims them for **tenant_id = 1, name "RandD Tradesmen", slug "randd-tradesmen"**.
- New tenants start **empty** and load their own data via the CSV onboarding UI (§7).

### 1.3 Two stacks — build in the right one
- `backend/` + `frontend/` is the **live** stack (root `package.json` dev scripts run these; the deployed nginx serves `frontend/dist`).
- `apps/*` + `packages/*` is an **abandoned** parallel rewrite. **Do not** modify it, import from it, or keep it in sync. All work here lands in `backend/` and `frontend/`.

### 1.4 Deployment shape (must keep working)
- `scripts/deploy_ec2.py`: builds `frontend`, rsyncs repo to `/var/www/strqc`, uploads a path-rewritten `.env`, runs `scripts/setup_remote_ec2.sh`.
- `scripts/setup_remote_ec2.sh`: builds venv, configures nginx (HTTPS at `44-193-208-77.sslip.io`), writes systemd `strqc-backend.service` (uvicorn on 127.0.0.1:8000, `EnvironmentFile=/var/www/strqc/.env`).
- **The deploy does NOT run any DB migration today.** The `.sqlite` is rsync'd as-is. (Verified: no sqlite/migrate step in either script.)
- nginx already proxies `/ws` with `Upgrade`/`Connection` headers and 86400s timeouts (`setup_remote_ec2.sh:69-80`). **No nginx change is required** for WS auth via query param.

---

## 2. Behaviors that MUST still work identically after your changes (regression contract)

Do not break any of these. Each has a verification step in §9.

1. **Live voice/text session** over `/ws` (Gemini/OpenAI/Nova) — `backend/app/main.py:241`, `backend/app/agent.py:create_agent`.
2. **Inspection form** live edits + `POST /api/inspection/export` snapshotting — `frontend/src/views/InspectionView.tsx`, `backend/app/main.py:92`.
3. **Walkthrough video upload** `POST /api/inspection/video` — `backend/app/main.py:41`.
4. **Slack report delivery** (`files_upload_v2`) — currently working on EC2 (`auth.test ok`).
5. **Property dropdown** `GET /api/properties` and **inspector picker** `GET /api/inspectors` — `backend/app/properties.py`.
6. **Report persistence** `report_db.upsert_form` on every export — `backend/app/report_db.py`.
7. **Deploy** via `scripts/deploy_ec2.py` end-to-end.
8. **The existing 59 Python tests** (`packages/shared/tests packages/db/tests apps/agent/tests apps/api/tests`) must still pass. (Yes, those live under `packages/`/`apps/` — do not delete them; just keep them green.)

---

## 3. Database migration (SQL) — `sql/0003_multitenancy.sql`

This exact SQL was executed on a copy of the live DB and verified. Reproduce it faithfully. It must be applied through a **ledger** (see §3.3) so it never runs twice.

### 3.1 Tables that get `tenant_id` via `ALTER TABLE ADD COLUMN` (no rebuild)
`stakeholder`, `stakeholder_role`, `task`, `work_order`, `report`, `inspection`, `photo_memory`, `maintenance_check`, `inspection_reports`.

### 3.2 Tables that must be REBUILT (to change a global UNIQUE into a per-tenant UNIQUE)
- `property`: `UNIQUE(unit_code)` → `UNIQUE(tenant_id, unit_code)`.
- `cluster`: `UNIQUE(name)` → `UNIQUE(tenant_id, name)`.

Rebuild pattern (SQLite): create `_new` table with the new constraint, `INSERT … SELECT` copying every column and setting `tenant_id = 1`, `DROP` old, `RENAME`. Run inside a transaction with `PRAGMA foreign_keys=OFF` during the swap, `ON` after.

### 3.3 The migration file (write this verbatim)

```sql
-- sql/0003_multitenancy.sql
-- Convert single-tenant phase-1 schema to multi-tenant.
-- All existing rows belong to ONE client: RandD Tradesmen (tenant_id = 1).
-- Verified on a copy of the live DB: row counts preserved, integrity ok, FK clean.
-- MUST be applied via a schema_migration ledger (see runner in §3.4) so it never runs twice
-- (a bare re-run errors "duplicate column name" — proven).

PRAGMA foreign_keys = OFF;
BEGIN;

CREATE TABLE IF NOT EXISTS tenant (
  tenant_id  INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  slug       TEXT NOT NULL UNIQUE,
  is_active  INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO tenant (tenant_id, name, slug)
VALUES (1, 'RandD Tradesmen', 'randd-tradesmen');

CREATE TABLE IF NOT EXISTS app_user (
  user_id           INTEGER PRIMARY KEY,
  tenant_id         INTEGER,                 -- NULL only for platform super-admin
  email             TEXT NOT NULL UNIQUE,
  password_hash     TEXT,
  is_platform_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_platform_admin IN (0,1)),
  stakeholder_id    INTEGER,
  is_active         INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  created_at        TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (tenant_id) REFERENCES tenant(tenant_id) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (stakeholder_id) REFERENCES stakeholder(stakeholder_id) ON DELETE SET NULL ON UPDATE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_app_user_tenant ON app_user(tenant_id);

ALTER TABLE stakeholder        ADD COLUMN tenant_id INTEGER REFERENCES tenant(tenant_id);
ALTER TABLE stakeholder_role   ADD COLUMN tenant_id INTEGER REFERENCES tenant(tenant_id);
ALTER TABLE task               ADD COLUMN tenant_id INTEGER REFERENCES tenant(tenant_id);
ALTER TABLE work_order         ADD COLUMN tenant_id INTEGER REFERENCES tenant(tenant_id);
ALTER TABLE report             ADD COLUMN tenant_id INTEGER REFERENCES tenant(tenant_id);
ALTER TABLE inspection         ADD COLUMN tenant_id INTEGER REFERENCES tenant(tenant_id);
ALTER TABLE photo_memory       ADD COLUMN tenant_id INTEGER REFERENCES tenant(tenant_id);
ALTER TABLE maintenance_check  ADD COLUMN tenant_id INTEGER REFERENCES tenant(tenant_id);
ALTER TABLE inspection_reports ADD COLUMN tenant_id INTEGER REFERENCES tenant(tenant_id);

-- property rebuild: UNIQUE(unit_code) -> UNIQUE(tenant_id, unit_code)
CREATE TABLE property_new (
  property_id INTEGER PRIMARY KEY,
  tenant_id INTEGER NOT NULL DEFAULT 1,
  unit_code TEXT NOT NULL,
  display_name TEXT, address_line_1 TEXT, city TEXT, state_province TEXT, postal_code TEXT,
  wifi_ssid TEXT, wifi_password_ciphertext TEXT, wifi_password_secret_ref TEXT,
  door_code_ciphertext TEXT, door_code_secret_ref TEXT,
  qc_assignee_stakeholder_id INTEGER, standing_instructions TEXT, cluster_id INTEGER,
  roster_active INTEGER NOT NULL DEFAULT 1 CHECK (roster_active IN (0,1)),
  source_system TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (tenant_id, unit_code),
  FOREIGN KEY (tenant_id) REFERENCES tenant(tenant_id) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (cluster_id) REFERENCES cluster(cluster_id) ON DELETE SET NULL ON UPDATE CASCADE,
  FOREIGN KEY (qc_assignee_stakeholder_id) REFERENCES stakeholder(stakeholder_id) ON DELETE SET NULL ON UPDATE CASCADE
);
INSERT INTO property_new (
  property_id, tenant_id, unit_code, display_name, address_line_1, city, state_province,
  postal_code, wifi_ssid, wifi_password_ciphertext, wifi_password_secret_ref,
  door_code_ciphertext, door_code_secret_ref, qc_assignee_stakeholder_id,
  standing_instructions, cluster_id, roster_active, source_system, created_at, updated_at)
SELECT
  property_id, 1, unit_code, display_name, address_line_1, city, state_province,
  postal_code, wifi_ssid, wifi_password_ciphertext, wifi_password_secret_ref,
  door_code_ciphertext, door_code_secret_ref, qc_assignee_stakeholder_id,
  standing_instructions, cluster_id, roster_active, source_system, created_at, updated_at
FROM property;
DROP TABLE property;
ALTER TABLE property_new RENAME TO property;

-- cluster rebuild: UNIQUE(name) -> UNIQUE(tenant_id, name)
CREATE TABLE cluster_new (
  cluster_id INTEGER PRIMARY KEY,
  tenant_id INTEGER NOT NULL DEFAULT 1,
  name TEXT NOT NULL,
  description TEXT,
  UNIQUE (tenant_id, name),
  FOREIGN KEY (tenant_id) REFERENCES tenant(tenant_id) ON DELETE CASCADE ON UPDATE CASCADE
);
INSERT INTO cluster_new (cluster_id, tenant_id, name, description)
SELECT cluster_id, 1, name, description FROM cluster;
DROP TABLE cluster;
ALTER TABLE cluster_new RENAME TO cluster;

-- backfill tenant_id = 1 on the ADD COLUMN tables (property/cluster already set via SELECT)
UPDATE stakeholder        SET tenant_id = 1 WHERE tenant_id IS NULL;
UPDATE stakeholder_role   SET tenant_id = 1 WHERE tenant_id IS NULL;
UPDATE task               SET tenant_id = 1 WHERE tenant_id IS NULL;
UPDATE work_order         SET tenant_id = 1 WHERE tenant_id IS NULL;
UPDATE report             SET tenant_id = 1 WHERE tenant_id IS NULL;
UPDATE inspection         SET tenant_id = 1 WHERE tenant_id IS NULL;
UPDATE photo_memory       SET tenant_id = 1 WHERE tenant_id IS NULL;
UPDATE maintenance_check  SET tenant_id = 1 WHERE tenant_id IS NULL;
UPDATE inspection_reports SET tenant_id = 1 WHERE tenant_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_property_tenant           ON property(tenant_id);
CREATE INDEX IF NOT EXISTS idx_task_tenant               ON task(tenant_id);
CREATE INDEX IF NOT EXISTS idx_stakeholder_tenant        ON stakeholder(tenant_id);
CREATE INDEX IF NOT EXISTS idx_work_order_tenant         ON work_order(tenant_id);
CREATE INDEX IF NOT EXISTS idx_report_tenant             ON report(tenant_id);
CREATE INDEX IF NOT EXISTS idx_cluster_tenant            ON cluster(tenant_id);
CREATE INDEX IF NOT EXISTS idx_inspection_reports_tenant ON inspection_reports(tenant_id);

COMMIT;
PRAGMA foreign_keys = ON;
```

### 3.4 Migration runner (ledger-guarded) — `backend/app/migrate_runtime.py`
- Create a `schema_migration(name TEXT PRIMARY KEY, applied_at TEXT DEFAULT (datetime('now')))` table if absent.
- Apply `sql/0003_multitenancy.sql` **only if** `'0003_multitenancy'` is not already in the ledger; then record it.
- Expose `apply_pending(db_path)` callable both as a CLI (`python -m app.migrate_runtime --db-path ./str_qc.sqlite`) and importable.
- **Proven behavior:** a second run skips cleanly; a bare (un-guarded) re-run errors `duplicate column name`. The ledger prevents that.

### 3.5 Verification queries the runner (or a test) MUST assert post-migration
- Row counts unchanged: `property=96, task=65, stakeholder=5, stakeholder_role=97, cluster=11, inspection_reports=51`.
- `SELECT COUNT(*) … WHERE tenant_id IS NULL` = 0 for **every** tenant-owned table.
- `PRAGMA integrity_check` = `ok`; `PRAGMA foreign_key_check` returns no rows.
- Per-tenant uniqueness: inserting a second tenant + reusing an existing `unit_code` under it **succeeds**; reusing it again under tenant 1 **fails** with a UNIQUE error.

---

## 4. Config & dependencies (additive only)

### 4.1 `backend/requirements.txt` — ADD (none of these are present today; verified)
```
passlib[bcrypt]>=1.7.4,<2.0.0     # password hashing (bcrypt backend)
pyjwt>=2.8.0,<3.0.0               # WS short-lived token; sessions may use cookie+itsdangerous instead
```
`cryptography` is already a transitive dep (used by `packages/shared/.../crypto.py:16`) — do not remove.

### 4.2 `.env` — POPULATE the already-declared, currently-empty secret
- `STRQC_SESSION_SECRET` is declared (`config.py:59` / `.env:78`) but **empty** (verified). Generate 32 random bytes base64 and set it locally AND on the EC2 host `.env`.
- Add `STRQC_AUTH_COOKIE_NAME=strqc_session` (optional; default in code).
- **Do not** print or commit the secret. `.env` is gitignored and excluded from rsync (`deploy_ec2.py:211`) — the EC2 `.env` must be updated separately.

### 4.3 CORS — tighten (currently `*`)
- `backend/app/main.py:29` uses `allow_origins=["*"]` with `allow_credentials=True`. For cookie auth this combination is invalid in browsers. Change `allow_origins` to the real origin(s): `["https://44-193-208-77.sslip.io", "http://localhost:5173"]`. Keep `allow_credentials=True`.

---

## 5. Authentication (backend)

### 5.1 New module `backend/app/auth.py`
- **Password hashing:** `passlib.context.CryptContext(schemes=["bcrypt"])`; `hash_password`, `verify_password`.
- **Session token (HTTP):** signed HTTP-only cookie. Payload: `{user_id, tenant_id, is_platform_admin, exp}`. Sign with `STRQC_SESSION_SECRET`. Cookie flags: `HttpOnly`, `Secure` (prod), `SameSite=Lax`, reasonable `Max-Age` (e.g. 12h).
- **WS token (short-lived):** a separate JWT (`pyjwt`), TTL ~60s, minted by an authed HTTP call and passed as `/ws?token=…` (browsers cannot set WS headers — this is required, verified). Validate + immediately consume at `accept()`.
- **`current_user` dependency:** FastAPI `Depends` that reads the cookie, verifies signature+exp, loads the `app_user`, and returns `{user_id, tenant_id, is_platform_admin}`. Raise 401 on any failure.
- **`require_platform_admin` dependency:** wraps `current_user`, 403 unless `is_platform_admin`.

### 5.2 New auth endpoints in `backend/app/main.py`
- `POST /api/auth/login` — body `{email, password}`; verify; set session cookie; return `{user, tenant}`. No auth required.
- `POST /api/auth/logout` — clear cookie. Auth required.
- `GET /api/auth/me` — return current user+tenant. Auth required. (Frontend uses this to decide login vs app.)
- `POST /api/auth/ws-token` — mint the short-lived WS token. Auth required.
- **Platform-admin only:**
  - `POST /api/admin/tenants` — create tenant `{name, slug}`.
  - `POST /api/admin/tenants/{tenant_id}/users` — create that tenant's first admin `{email, password}`.

### 5.3 Seeding the first users (one-time, via a script, not hardcoded)
- Add `scripts/seed_auth.py`: creates the **platform super-admin** (`tenant_id NULL, is_platform_admin=1`) and **RandD's first tenant admin** (`tenant_id=1`). Passwords supplied via env/prompt, hashed with `passlib`. Never store plaintext.

---

## 6. Tenant-scoped data access + endpoint guards (backend)

### 6.1 The complete, finite set of DB touch-points (verified — there are only these)
- `backend/app/properties.py` → `list_properties()`, `list_inspectors()`.
- `backend/app/report_db.py` → `upsert_form()`, `record_archive()`.
- Endpoints in `main.py` that reach them: `GET /api/properties` (216), `GET /api/inspectors` (223), `POST /api/inspection/export` (92). Plus `/ws` (241).
- **The other 5 endpoints** (`/api/agent`, `/api/models`, `/api/voices`, `/api/workspace`, `/api/inspection/video`) do **not** read tenant data. Require login on all of them for consistency, but they need **no** tenant filter.

### 6.2 Scoping rule (apply mechanically, no exceptions)
- Add a required `tenant_id: int` parameter to `list_properties`, `list_inspectors`, `upsert_form`, `record_archive`.
- Every SQL statement in those functions gets `WHERE tenant_id = ?` (and inserts set `tenant_id = ?`). Example: `properties.py` `list_properties` adds `AND p.tenant_id = ?`; `list_inspectors` joins/filter on `s.tenant_id = ?`.
- Callers pass `current_user["tenant_id"]`.
- **Never** run an unscoped query against a tenant-owned table. There is no legitimate cross-tenant read in the app.

### 6.3 Endpoint changes in `main.py`
- Add `user = Depends(current_user)` to **every** `/api/*` route (all 8 HTTP routes) and pass `user["tenant_id"]` into the scoped functions for the 3 DB ones.
- `POST /api/inspection/export`: pass `tenant_id` into `upsert_form(state, html_bytes, tenant_id=…)` and into `archive_report`/`record_archive`.
- Keep every existing response shape identical (the frontend depends on them — §2). Only add auth + the tenant filter; do not rename fields.

### 6.4 `report_db.py` note (do not disrupt)
- `report_db._connect()` idempotently applies `sql/inspection_reports.sql` (`report_db.py:31-34`). After migration, `inspection_reports` has a `tenant_id` column. Update `upsert_form`'s INSERT to include `tenant_id`, and its conflict target stays `form_uuid`. Do not drop the table.

---

## 7. WebSocket + agent tenant-binding (backend)

**Verified mechanism (do not improvise):**
- `main.py:264` calls `create_agent(...)` then `agent.run(inputs, outputs)`.
- `BidiAgent.__init__` accepts `state: AgentState | dict` (agent.py:74); `agent.run(..., invocation_state=…)` (agent.py:332) forwards it; the tool layer injects `agent=invocation_state["agent"]` (installed `strands/tools/decorator.py:406`, `strands/agent/agent.py:1278`).

**Do this:**
1. `GET /ws` handler (`main.py:241`): add `token: str = Query(...)`. Before `create_agent`, validate the WS token (§5.1). On failure: `await websocket.accept(); send bidi_error; close()` (keep the existing error-to-browser pattern at `main.py:271-275`). Resolve `tenant_id` from the token.
2. Change `create_agent(mode, voice, provider)` → `create_agent(mode, voice, provider, tenant_id)` in `backend/app/agent.py`. Pass `state={"tenant_id": tenant_id}` to `BidiAgent(...)` (line 178).
3. `agent.run(inputs=[…], outputs=[…], invocation_state={"tenant_id": tenant_id})`.
4. **Future DB-backed agent tools** must be declared `@tool(context="ctx")` and read `ctx.agent.state.get("tenant_id")`. The **current** tools in `agent.py:TOOLS` are side-effect-free string returns (verified: `qc_journal.py` does no DB writes; persistence is the frontend + `/api/inspection/export`), so they carry **no cross-tenant risk today** and need no change now.
5. nginx needs **no** change (Upgrade headers + long timeout already present).

---

## 8. Frontend (React 19 + Vite 7)

**Verified UI inventory** — these shadcn primitives already exist in `frontend/src/components/ui/`: `button`, `button-group`, `card`, `dialog`, `hover-card`, `input`, `input-group`, `label`, `select`. Build the new screens from these; do not introduce a component library.

### 8.1 Dependencies to ADD
- `papaparse` (+ `@types/papaparse`) — CSV parsing. **Proven** to parse the exact roster/master columns the backend consumes.
- Router optional. Simplest: no router — gate at the root (§8.2). If you prefer routes, `react-router-dom@7` is React-19 compatible.

### 8.2 Auth gate (one insertion point — do not restructure `App.tsx`)
- `frontend/src/main.tsx` renders `<App/>` inside `<StrictMode>`. Wrap it: `<AuthProvider><Gate/></AuthProvider>` where `Gate` calls `GET /api/auth/me`; if 401 → render `<Login/>`, else render the existing `<App/>` **unchanged**.
- `Login` = `card + label + input + button` posting to `POST /api/auth/login`.
- **All existing `fetch("/api/…")` calls** (in `use-live-agent.ts:102,111,124,134,750`, `InspectionView.tsx:241`) must add `credentials: "include"` so the session cookie is sent. This is the only change to existing fetch calls — do not alter their URLs, methods, or payloads.

### 8.3 WebSocket connect change
- `use-live-agent.ts:48` builds the `/ws` URL. Before connecting, call `POST /api/auth/ws-token` (with `credentials:"include"`), then append `&token=<token>` to the WS URL. Everything else about the socket stays identical.

### 8.4 Tenant onboarding screen (new, platform-admin only)
- New view `frontend/src/views/Onboarding.tsx`, reachable from a header button (add one `Button` in `App.tsx` alongside the existing ones — additive).
- Two file inputs (`input type=file`): **Address Roster CSV** and **Master Checklist CSV**.
- Parse client-side with papaparse; show a preview `table` inside a `dialog`; surface row count + any parse issues.
- On confirm, POST the raw file(s) to the import endpoints (§7 backend below), show the returned `migration_issue`-style warnings/errors.

### 8.5 Super-admin tenant/user creation UI
- A simple admin panel (behind `is_platform_admin`) with forms to `POST /api/admin/tenants` and `POST /api/admin/tenants/{id}/users`. Built from `card + input + label + button`.

---

## 9. CSV import backend (reuse the proven importer)

- The original loader is `scripts/migrate_phase1.py` (`Migrator`, `ingest_roster`, `ingest_master`). **Reuse its parsing/validation logic** — do not reinvent column handling. Verified column shapes:
  - **Roster:** `Unit Code|Property|House|Code|Unit`, `Address`, `Cluster`, `Display Name`, `Standing Instructions`, `QC Assignee`, `WiFi SSID`, `WiFi Password`, `Door Code`, feature flags (`Hot Tub, TV, EV Charger, Arcade, Patio, Porch, Bathroom, Bedroom`).
  - **Master:** `House|Property|Unit|Code`, `Arrival Date`, `Cleaner|Housekeeper`, stage flags `QC|B2B|CLN|DONE|OWN|WO|DONE_WO|REPORT`.
- New endpoints (platform-admin or tenant-admin, authed):
  - `POST /api/import/roster` (multipart file) → runs roster ingest **scoped to `tenant_id`**.
  - `POST /api/import/master` (multipart file) → runs master ingest **scoped to `tenant_id`**.
- **Critical:** every INSERT the importer does (`property`, `cluster`, `stakeholder`, `stakeholder_role`, `task`, `task_stage_event`, `property_feature`, `migration_issue`) must set `tenant_id` on the tenant-owned tables. Refactor `Migrator` to accept and thread `tenant_id`, or wrap it. Reuse `migration_issue` reporting so the UI shows blank/invalid/duplicate warnings exactly as the CLI did.
- Return the accumulated issues (type, severity, row, message) as JSON for the onboarding UI.

---

## 10. Deployment changes (do not break the existing flow)

### 10.1 Add a backup + migrate step (proven sequence)
Insert into `scripts/setup_remote_ec2.sh` **after** the venv install (step 2) and **before** the systemd restart (step 5):
```bash
echo "=== Backing up and migrating the database ==="
if [ -f /var/www/strqc/str_qc.sqlite ]; then
  cp /var/www/strqc/str_qc.sqlite "/var/www/strqc/str_qc.sqlite.bak-$(date +%s)"
fi
/var/www/strqc/backend/venv/bin/python -m app.migrate_runtime --db-path /var/www/strqc/str_qc.sqlite
```
- The migrate runner is ledger-guarded (§3.4): safe to run on every deploy, applies `0003` once. **Proven** on a copy: backup → migrate → re-run skips → app reads 96 properties → integrity ok.
- Run from `WorkingDirectory=/var/www/strqc/backend` context (the systemd service uses it) so `app.migrate_runtime` imports resolve.

### 10.2 Order of operations for the first production rollout
1. **Back up EC2 `str_qc.sqlite`** manually first (belt-and-suspenders).
2. Set `STRQC_SESSION_SECRET` in the EC2 `.env`.
3. Deploy (`scripts/deploy_ec2.py`) — this now runs the migration on the host.
4. Run `scripts/seed_auth.py` on the host once to create the super-admin + RandD admin.
5. Verify the regression contract (§2) and isolation (§11) against the live URL.

### 10.3 Local dev
- Run `python -m app.migrate_runtime --db-path ./str_qc.sqlite` once locally (after backing up `./str_qc.sqlite`) before starting the backend.

---

## 11. Testing (required — this is the merge gate)

Add tests under `backend/tests/` (create the dir). **Do not** merge without the negative isolation tests.

### 11.1 Migration tests
- Apply `0003` to a fresh copy fixture; assert §3.5 (counts preserved, no NULL tenant_id, integrity ok, FK clean).
- Idempotency: run the runner twice; assert the second run is a no-op and no error.

### 11.2 Auth tests
- Login with correct/incorrect password; cookie set/rejected.
- `current_user` rejects missing/expired/tampered cookie (401).
- `require_platform_admin` rejects a normal tenant user (403).
- WS token: mint, validate, reject expired.

### 11.3 Tenant isolation (NEGATIVE — the whole point)
- Seed two tenants (RandD=1 + a test tenant=2) with distinct properties.
- As tenant 2, call `GET /api/properties` → assert it returns **only** tenant 2's rows, **never** RandD's door codes / wifi / addresses.
- As tenant 2, attempt to read/import into tenant 1 → assert impossible (no cross-tenant write).
- Per-tenant unique: tenant 2 may reuse a unit_code RandD uses; tenant 1 cannot duplicate its own. (DB-level version already proven; assert at API level.)

### 11.4 Regression
- The existing 59 tests still pass: `PYTHONPATH=packages/db/src:packages/shared/src:apps/agent/src:apps/api/src:strands-py/src python3 -m pytest packages/shared/tests packages/db/tests apps/agent/tests apps/api/tests -q` → `59 passed`.
- Smoke: `/api/properties` (authed) returns 96 for RandD; `/api/inspection/export` still persists; `/ws` connects with a valid token and refuses without one.

---

## 12. Explicit DO-NOT list (disruption guards)

1. **Do not** touch `apps/*` or `packages/*`.
2. **Do not** run the migration against the live DB without a backup first (§10).
3. **Do not** apply the migration without the ledger guard (bare re-run corrupts via duplicate-column error — proven).
4. **Do not** change any existing `/api/*` response shape or field name (§2/§6.3).
5. **Do not** leave any `/api/*` route or `/ws` unauthenticated.
6. **Do not** leave any tenant-owned query unscoped (§6.2).
7. **Do not** commit or log `STRQC_SESSION_SECRET`, passwords, tokens, door codes, or wifi.
8. **Do not** change the audio/PCM sample rates, camera facing-mode logic, persona/guardrails, or Slack `files_upload_v2` path — none of that is in scope here.
9. **Do not** widen CORS back to `*` with credentials (breaks cookies + is unsafe).
10. **Do not** remove or rewrite `qc_journal.py` tools (they're side-effect-free and correct as-is).

---

## 13. Definition of done

- `0003` migration applied on live DB (post-backup) via ledger; §3.5 assertions pass.
- All 8 `/api/*` routes require login; the 3 DB routes + `/ws` are tenant-scoped.
- Login, logout, `me`, ws-token, admin tenant/user creation endpoints work.
- Frontend: login gate wraps `<App/>`; existing app works unchanged for RandD admin; onboarding CSV screen imports a new tenant's roster+master (tenant-scoped) and shows issues.
- Negative isolation tests (§11.3) pass; existing 59 tests still pass.
- Deploy runs backup+migrate automatically; live URL passes the §2 regression contract.
- Secrets set (session secret), never committed.

---

## Appendix A — Verified evidence backing this spec
- Migration executed on a copy of the live DB: counts preserved (96/65/5/97/11/51), 0 NULL tenant_id, `integrity_check=ok`, `foreign_key_check` empty, per-tenant unique proven (tenant 2 reused code `ADS`; dup within tenant 1 rejected).
- Full prod sequence proven on copy: backup → ledger-migrate → re-run skips → scoped read returns 96 → integrity ok.
- Strands tool-context injection confirmed in installed SDK: `strands/tools/decorator.py:406`, `strands/agent/agent.py:1278`; `BidiAgent.run(invocation_state=)` at `strands-py/.../bidi/agent/agent.py:332`.
- Endpoint inventory: 9 declarations in `main.py`; exactly 3 touch tenant data (`/api/properties`, `/api/inspectors`, `/api/inspection/export`) + `/ws`.
- DB touch-points: only `backend/app/properties.py` and `backend/app/report_db.py`.
- CSV shapes parse into the exact fields `ingest_roster`/`ingest_master` read (papaparse-equivalent verified).
- Auth deps absent from `requirements.txt`; `cryptography` present; `STRQC_SESSION_SECRET` declared but empty.
- Frontend: React 19.2 / Vite 7.3; only runtime dep `class-variance-authority`; vendored UI primitives listed in §8; `main.tsx` renders `<App/>` in `<StrictMode>`.
- Deploy scripts run no migration today; nginx `/ws` already Upgrade-proxied with 86400s timeout.
