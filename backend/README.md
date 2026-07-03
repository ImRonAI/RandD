# RandD Live Backend

```bash
cd backend
python3 -m venv .backend-venv
. .backend-venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in real credentials — .env is gitignored, never commit it
uvicorn app.main:app --reload --port 8000
```

The server exposes `/api/agent`, `/api/voices`, `/api/workspace`, static workspace files at `/workspace/*`, and the live bridge at `/ws?mode=audio|text&voice=Puck`.

## Long-term memory (AWS Bedrock Knowledge Base)

The agent has cross-session memory implemented with the [Strands memory framework](https://strandsagents.com/docs/user-guide/concepts/memory/overview/): a `BedrockKnowledgeBaseStore` (`strands.vended_memory_stores`) registered through a `MemoryManager` (`strands.memory`), targeting the managed knowledge base `knowledge-base-quick-start-fu4ig` (ID `LAJ1DYSVHG`). The manager's `search_memory` / `add_memory` tools are registered on the bidi agent (the vendored `BidiAgent` has no `memory_manager` plugin slot, so tools are the integration point).

Credentials come from the standard AWS credential chain via `backend/.env` (see `.env.example`). With only `BEDROCK_KB_ID` the store is read-only (search only); set `BEDROCK_KB_DATA_SOURCE_ID` plus `BEDROCK_KB_S3_BUCKET` (S3 data source) to enable `add_memory` writes. Ingestion is eventually consistent.
