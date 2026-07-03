# Agentic STR Quality-Control Platform

An AI-native quality-control platform for short-term rental operations — a strands-based field agent powered by **Gemini Live** (`gemini-3.1-flash-live-preview`) that guides photo-verified turnovers, opens work orders, and delivers signed-off readiness reports.

- **Requirements / PRD:** [AGENTS.md](AGENTS.md)
- **Delivery plan & status:** [TASKS.md](TASKS.md)
- **Frontend design contract:** [DESIGN.md](DESIGN.md)

## Workspace layout

| Path | Package | What |
| --- | --- | --- |
| `apps/agent` | `strqc-agent` | The field agent (Strands BIDI + Gemini Live, tools, persona) |
| `apps/api` | `strqc-api` | HTTP API + realtime voice bridge (FastAPI) |
| `apps/web` | — | Next.js mobile-first PWA (shadcn/ui + AI Elements) |
| `packages/shared` | `strqc-shared` | Config (pydantic-settings) + secret envelope encryption |
| `packages/db` | `strqc-db` | Versioned SQL migrations, repositories, dev seeds |
| `harness-sdk/` | — | Vendored Strands SDK monorepo (editable install; git-ignored) |
| `Escapia/` | — | Escapia HSAPI OpenAPI specs (integration contract) |
| `sql/`, `scripts/`, `docs/` | — | Phase-1 artifacts (baseline schema, CSV migration, architecture) |

## Quickstart

Requires Python 3.12+, Node 20+, pnpm.

```bash
cp .env.example .env            # fill in keys (see comments in the file)
make install                    # Python packages (editable) + Strands SDK
make install-web                # Next.js dependencies
make migrate                    # apply DB migrations  (DB_PATH=./str_qc.sqlite)
make seed                       # load Big Bear dev fixtures
make test                       # run all Python unit tests
```

Run the stack (separate shells):

```bash
make api                        # FastAPI on :8000
make web                        # Next.js dev server on :3000
make agent                      # agent console harness (text mode)
```

`make help` lists all targets.

## Legacy Phase-1 artifacts

The original kickoff schema/migration live in `sql/phase1_schema.sql` and `scripts/migrate_phase1.py` (CSV import of the Master/roster sheets). The live schema is now owned by `packages/db/src/strqc_db/migrations/`.

### Migration usage

```bash
python scripts/migrate_phase1.py \
  --master-csv /absolute/path/master.csv \
  --roster-csv /absolute/path/roster.csv \
  --db-path /absolute/path/str_qc.sqlite \
  --fail-on-error
```

Notes:

- The migration enables `PRAGMA foreign_keys=ON` on its connection and the schema also declares it.
- Plaintext secrets found in CSV inputs (for example WiFi password/door code) are surfaced as migration issues and are not stored as raw values.
