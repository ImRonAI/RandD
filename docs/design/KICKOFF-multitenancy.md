# KICKOFF PROMPT — Multi-Tenancy & Auth (fresh context)

> Copy everything below the line into the new agent session as the first message.
> It is self-contained: it names the authoritative spec, the branch, the guardrails,
> and the order of work. Do not paraphrase the spec into the prompt — point at it.

---

You are implementing **multi-tenancy, authentication, and tenant onboarding** for the STR QC platform.

## Your single source of truth

Read and follow **`docs/design/IMPLEMENTATION-multitenancy-and-auth.md`** exactly. It is a
verified, evidence-backed spec (the migration was already executed and proven on a copy of the
live database). **Do not re-derive, re-plan, or "improve" the design.** Where the spec gives
verbatim SQL, endpoint lists, file paths, or line numbers, treat them as authoritative. If you
believe something in the spec is wrong, STOP and surface it to the user before deviating —
do not silently change the approach.

You are already on branch **`feat/multitenancy-and-auth`**. Do all work here. Do not touch `main`.

## Prime directive (from the spec)

**Do not disrupt anything currently working.** The platform is live and deployed
(`https://44-193-208-77.sslip.io`). Every behavior in the spec's §2 regression contract must work
identically afterward. New capabilities are additive and default-on for the existing tenant
(`tenant_id = 1`, "RandD Tradesmen").

## Non-negotiable guardrails (spec §12 — internalize these)

1. Canonical stack is **`backend/` (FastAPI) + `frontend/` (React 19 + Vite 7)**. **Do NOT** touch,
   import from, or sync `apps/*` or `packages/*` (abandoned rewrite) — except keep their existing
   59 tests green.
2. **Never migrate the live DB without a backup first.** The migration is ledger-guarded; a bare
   re-run corrupts via duplicate-column error. Always go through `app.migrate_runtime`.
3. **Never** change an existing `/api/*` response shape or field name — the frontend depends on them.
4. **Never** leave an `/api/*` route or `/ws` unauthenticated; **never** run an unscoped query
   against a tenant-owned table.
5. **Never** commit or log `STRQC_SESSION_SECRET`, passwords, tokens, door codes, or wifi passwords.
6. **Do NOT** change audio/PCM sample rates, camera facing-mode logic, persona/guardrails, or the
   Slack `files_upload_v2` path — out of scope.
7. Keep it lean. Build the two new screens from the **already-vendored** shadcn primitives listed in
   §8. Do not add a component library or a router unless the spec's simplest path requires it
   (it does not — gate at the root).

## Scaling / simplicity intent (why the design is shaped this way)

- Tenancy is enforced by a **single mechanical rule**: every tenant-owned table has `tenant_id`, and
  every query against those tables is scoped `WHERE tenant_id = ?` using `current_user["tenant_id"]`.
  There are only **3 DB-touching HTTP endpoints + `/ws`** and only **2 DB modules**
  (`properties.py`, `report_db.py`) — the surface is finite and named in §6.1. Keep it that way:
  no ORM, no per-tenant databases, no dynamic schema. One SQLite file, one `tenant_id` column,
  one scoping rule. This is what makes it scale without complexity.
- Auth is a signed HTTP-only cookie + a short-lived WS token. No external identity provider, no
  session store — stateless verification against `STRQC_SESSION_SECRET`. Don't add more.
- The CSV importer already exists (`scripts/migrate_phase1.py`). **Reuse its parsing/validation** —
  thread `tenant_id` through it; do not rewrite column handling.

## Order of work (follow the spec's sections; commit after each green milestone)

1. **Migration** — write `sql/0003_multitenancy.sql` verbatim (§3.3) and the ledger runner
   `backend/app/migrate_runtime.py` (§3.4). Prove §3.5 assertions on a **copy** of `./str_qc.sqlite`.
2. **Config/deps** — additive `requirements.txt` entries (§4.1); populate `STRQC_SESSION_SECRET`
   locally (§4.2); tighten CORS off `*` (§4.3).
3. **Auth backend** — `backend/app/auth.py` + auth endpoints (§5); `scripts/seed_auth.py` (§5.3).
4. **Tenant scoping** — thread `tenant_id` into `properties.py` / `report_db.py` and guard all 8
   `/api/*` routes with `Depends(current_user)` (§6).
5. **WS + agent binding** — WS token validation + `state={"tenant_id": …}` into `create_agent`/
   `agent.run` (§7).
6. **Frontend** — auth gate wrapping `<App/>` unchanged, login screen, `credentials:"include"` on
   existing fetches, WS-token fetch before connect, onboarding CSV screen, super-admin panel (§8).
7. **CSV import backend** — `POST /api/import/roster|master`, tenant-scoped, reusing the importer (§9).
8. **Deploy step** — backup → ledger-migrate → restart in `setup_remote_ec2.sh` (§10).
9. **Tests** — `backend/tests/`: migration, auth, and the **negative tenant-isolation tests** (§11).
   These are the merge gate. Also confirm the existing 59 tests still pass.

## Definition of done

The spec's §13. In short: migration applied via ledger with §3.5 passing; all `/api/*` + `/ws`
authed and tenant-scoped; login/logout/me/ws-token/admin endpoints working; frontend login gate +
onboarding working with the existing app unchanged for RandD; **negative isolation tests pass** and
the existing 59 tests still pass; deploy auto-backs-up + migrates; secrets set and never committed.

## How to work

- Validate continuously: run the relevant tests after each milestone; never mark a step done on
  intent alone. For anything user-facing or runtime (auth flow, WS token, isolation), **prove it with
  a real run/test**, not reasoning — this project has been burned by unverified assumptions.
- Before the first production rollout, follow §10.2 exactly (manual backup → set secret → deploy →
  seed_auth → verify §2 + §11 against the live URL).
- Keep commits scoped per milestone with clear messages. Do not commit `str_qc.sqlite`
  (runtime artifact, gitignored pattern; revert any incidental changes to it).

Start with milestone 1 (the migration + ledger runner) and prove §3.5 on a copy before proceeding.
