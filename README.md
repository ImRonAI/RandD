# Agentic STR Quality-Control Platform

> Product source of truth: [Vantage AI v1 PRD](docs/product/VANTAGE_AI_PRD.md)
> Implementation audit: [Vantage v1 gap analysis](docs/audit/VANTAGE_V1_GAP_ANALYSIS.md)
> API contract: [Vantage v1 API and event contract](docs/product/VANTAGE_API_CONTRACT.md)
> Runtime setup: [Vantage v1 runtime configuration](docs/development/VANTAGE_V1_RUNTIME.md)

An AI-native quality-control platform for short-term rental operations — a strands-based field agent powered by **Gemini Live** (`gemini-3.1-flash-live-preview`) that guides photo-verified turnovers, opens work orders, and delivers signed-off readiness reports.

## AI Chat (Gemini Live) — AI Elements frontend + Strands bidi backend

Live text + voice chat UI built entirely from [Vercel AI Elements](https://github.com/vercel/ai-elements)
components, driven by the repo-vendored Strands bidi agent (`strands-py/`) running
**gemini-3.1-flash-live-preview** with exactly three tools: `editor`, `shell`, `load_tool`
(meta-tooling: the agent creates new tools with the editor and hot-loads them with `load_tool`).
See `DESIGN.md` for the full component plan and architecture.

### Run

Backend (needs a real `GOOGLE_API_KEY` for Gemini Live):

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export GOOGLE_API_KEY=your-key
.venv/bin/uvicorn app.main:app --port 8000
```

Frontend (proxies `/api`, `/ws`, `/workspace` to the backend):

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

### Test

1. Open http://localhost:5173, pick a voice (VoiceSelector) and mic (MicSelector), press **Connect**.
2. Voice: click **Mic** and speak — persona animates, transcripts stream, model audio plays and is
   replayable per turn via the AudioPlayer.
3. Text: type in the prompt input (attach images by drag-drop/paste); responses stream as markdown.
4. Meta-tooling: say/type *"create a tool that reverses text, then use it on 'hello'"* — watch
   Chain of Thought, Tool, Sandbox (shell), the Agent panel tool list, and the workspace
   artifacts/web-preview update from live events. Toggle **Workflow** for the live session graph.
5. Frontend build check: `cd frontend && npm run build`. Backend import check:
   `cd backend && GOOGLE_API_KEY=dummy .venv/bin/python -c "from app.main import app"`.

Sync vendored AI Elements from upstream (or a fork) at any time:

```bash
./scripts/sync-ai-elements.sh                 # vercel/ai-elements@main
AI_ELEMENTS_REPO=ImRonAI/ai-elements ./scripts/sync-ai-elements.sh
```

## Phase 1 STR QC artifacts

Phase 1 STR QC kickoff artifacts:

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
