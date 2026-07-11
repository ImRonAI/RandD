# Vantage AI Backend

Requires **Python 3.12+** (the Nova Sonic bidi provider refuses to import on older interpreters).

```bash
cd backend
python3.12 -m venv .backend-venv
. .backend-venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in real credentials — .env is gitignored, never commit it
uvicorn app.main:app --reload --reload-dir app --port 8000   # --reload-dir keeps agent-written workspace files from restarting the server
```

The server exposes `/api/agent`, `/api/voices`, `/api/workspace`, static workspace files at `/workspace/*`, and the live bridge at `/ws?mode=audio|text&voice=Puck`.

## Long-term memory (AWS Bedrock Knowledge Base)

The agent has cross-session memory implemented with the [Strands memory framework](https://strandsagents.com/docs/user-guide/concepts/memory/overview/): a `BedrockKnowledgeBaseStore` (`strands.vended_memory_stores`) registered through a `MemoryManager` (`strands.memory`), targeting the managed knowledge base `knowledge-base-quick-start-fu4ig` (ID `LAJ1DYSVHG`). The manager's `search_memory` / `add_memory` tools are registered on the bidi agent (the vendored `BidiAgent` has no `memory_manager` plugin slot, so tools are the integration point).

Credentials come from the standard AWS credential chain via `backend/.env` (see `.env.example`). With only `BEDROCK_KB_ID` the store is read-only (search only); set `BEDROCK_KB_DATA_SOURCE_ID` plus `BEDROCK_KB_S3_BUCKET` (S3 data source) to enable `add_memory` writes. Ingestion is eventually consistent.

## Tool libraries (load_tool)

Three Strands tool libraries are installed and accessible to the agent at runtime through `load_tool`:

- [`strands-agents-tools`](https://pypi.org/project/strands-agents-tools/) (`strands_tools`) — calculator, python_repl, file ops, AWS, and more
- [`strands-fun-tools`](https://github.com/cagataycali/strands-fun-tools) (`strands_fun_tools`) — chess, clipboard, template, utility, dialog, and more (headless-safe extras installed; hardware-bound tools such as cursor/vision/audio/bluetooth report as UNAVAILABLE unless their extras are installed)
- [`strands-google`](https://github.com/cagataycali/strands-google) (`strands_google`) — `use_google` (200+ Google APIs), `google_auth`, `gmail_send`, `gmail_reply`

The agent discovers them with the baseline `list_library_tools` tool (`app/tool_libraries.py`), which returns the exact `load_tool(name=..., path=...)` arguments for every loadable tool. Note that `load_tools_from_directory=True` on the bidi agent is only a file watcher over `./tools/`, and the live connection receives tool declarations at connection (re)start — so `load_tool` is the supported dynamic-loading path, and tools should be loaded as early in a session as possible.
