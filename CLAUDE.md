# CLAUDE.md — Agent working rules for this repository

## 🔒 NONNEGOTIABLE: Do not change the agent tool configuration

**Nobody — human or agent — changes the agent's tool configuration unless the user explicitly asks for that specific change.** This configuration is deliberate. Do not "clean it up," "optimize" it, "fix unused imports," or add tools you think are missing. If you believe a change is needed, stop and ask first.

The tool configuration is:

- **`backend/app/agent.py` → `TOOLS`** — the baseline registry is **exactly six core meta-tooling tools** and nothing else:
  `editor, shell, load_tool, mcp_client, http_request, environment`.
  Do not add, remove, reorder, or wrap these.
- **`backend/app/agent.py` imports** — **all tool imports are intentionally kept**, even though only the six above are registered in `TOOLS`. They stay imported so every tool module remains importable and its file path resolvable for `load_tool`. **Do not remove or trim these imports.**
- **`backend/app/main.py`** — the per-connection session-tool injection (native `browser`, `perplexity_agent`, inventory/onboarding tools, tenant Slack tools, Smarty MCP tools, long-term memory) is deliberate. Do not change what is injected.
- **`backend/app/prompts.py`** — the meta-tooling system prompt. Do not rewrite or overwrite it.

### Why it is built this way (so you don't "helpfully" undo it)

The agent is a **meta-tooling agent**. Only the six core primitives are registered up front to keep the tool declarations sent to the model small (context window). Everything else is discovered and **hot-loaded on demand at runtime via the native `load_tool` tool** (load a tool from its Python file path), and remote tools are reached via the native `mcp_client` tool. This is the standard `strands-agents-tools` meta-tooling pattern. Unattended loading works because `main.py` sets `STRANDS_NON_INTERACTIVE=true` and `BYPASS_TOOL_CONSENT=true`, so `load_tool` does not block on a consent prompt.

Session-scoped tools that cannot be loaded from a file (they close over the live tenant session, or are a per-connection instance / MCP discovery) stay injected per connection in `main.py`.

## General rules

- Prefer native Strands framework functionality; do not build wrappers around functionality that already exists.
- Inspect the installed Strands source before changing native tools; never rewrite native tool input schemas.
- Preserve the dirty worktree. Do not reset, discard, or broadly reformat existing changes.
- No mocks, stubs, fake browsers, fake services, or simulated results. Test through the actual UI.
- Never print credentials or tokens.
- See `AGENTS.md` for product requirements and architecture.
