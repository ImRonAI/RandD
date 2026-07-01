# RandD — Strands Bidi Agent with Gemini Live

A fully-featured [Strands](https://strandsagents.com) **`BidiAgent`** powered by
Google's **Gemini Live API** using the **`gemini-3.1-flash-live-preview`** model.

It provides real-time, bidirectional (two-way) streaming conversations with
audio and text, concurrent tool execution, automatic interruption handling
(barge-in), automatic connection restarts, lifecycle hooks, and optional session
persistence.

This project **composes the Strands SDK components directly** (model, agent,
I/O, hooks, session manager) — it does not wrap or hide their APIs. You keep full
access to the underlying `BidiAgent` (`start` / `send` / `receive` / `run` /
`stop`).

## Features

| Capability | How it's implemented |
| --- | --- |
| **Multimodal streaming** | `BidiGeminiLiveModel` + `BidiAudioIO` / `BidiTextIO` for audio & text |
| **Bidirectional interaction** | Persistent connection via `agent.run()` / `send()` / `receive()` |
| **Interruptibility (barge-in)** | Automatic `BidiInterruptionEvent` handling; audio buffer cleared on interrupt |
| **Tool use & function calling** | `calculator`, `current_time`, custom `get_weather`, plus `stop` / `end_session` |
| **Session management** | Optional `FileSessionManager` (see caveats for Gemini Live) |
| **Connection restart** | Automatic on model timeout via Gemini session resumption; monitored by hooks |
| **Hooks** | Logging, analytics, interruption tracking, connection monitoring |
| **Secure auth** | `GOOGLE_API_KEY` via env or `client_config` |

## Project layout

```
src/gemini_bidi_agent/
├── config.py       # Environment-driven configuration (AppConfig, load_config)
├── model.py        # build_model() -> BidiGeminiLiveModel (gemini-3.1-flash-live-preview)
├── tools.py        # default_tools(): calculator, current_time, get_weather, stop, end_session
├── hooks.py        # ConversationLogger, InterruptionTracker, ConnectionMonitor, ConversationAnalytics
├── io_console.py   # ConsoleOutput: BidiOutput channel that renders events to the terminal
├── session.py      # build_session_manager() -> optional FileSessionManager
├── agent.py        # build_agent(): wires model + tools + hooks + session into a BidiAgent
└── app.py          # CLI entrypoint (voice or text)
examples/
├── voice_assistant.py    # Microphone + speakers with console transcripts
├── text_chat.py          # Terminal text chat
├── manual_lifecycle.py   # Explicit start/send/receive/stop
└── websocket_server.py   # FastAPI WebSocket server (client-side audio)
tests/
└── test_smoke.py         # Import & construction tests (no network required)
```

## Installation

Requires Python 3.10+.

```bash
# Core agent + Gemini Live provider
pip install -r requirements.txt

# For local microphone/speaker + terminal I/O (BidiAudioIO / BidiTextIO)
pip install "strands-agents[bidi-io]"
```

`bidi-io` pulls in [PyAudio](https://pypi.org/project/PyAudio/), which needs the
system PortAudio library:

- **macOS:** `brew install portaudio`
- **Linux (Ubuntu/Debian):** `sudo apt-get install portaudio19-dev python3-pyaudio`
- **Windows:** PyAudio typically installs without extra steps.

You can also install this project as a package (exposes the `gemini-bidi-agent`
console script):

```bash
pip install -e ".[io,server,dev]"
```

## Configuration

Copy `.env.example` to `.env` and set your Google AI Studio API key
(obtain one at <https://aistudio.google.com/app/apikey>):

```bash
cp .env.example .env
# edit .env and set GOOGLE_API_KEY=...
```

All settings have sensible defaults; only `GOOGLE_API_KEY` is required. See
`.env.example` for the full list (model id, voice, sample rates, temperature,
system prompt, session id/dir, log level).

## Usage

### CLI

```bash
# Voice conversation (microphone + speakers, transcripts printed to console)
python -m gemini_bidi_agent.app

# Text chat in the terminal
python -m gemini_bidi_agent.app --text

# Print token-usage updates too
python -m gemini_bidi_agent.app --usage
```

Say **"stop conversation"** (handled by the `stop` tool) or press **Ctrl+C** to
exit.

### Programmatic

```python
import asyncio
from strands.experimental.bidi.io import BidiAudioIO
from gemini_bidi_agent import build_agent
from gemini_bidi_agent.io_console import ConsoleOutput

async def main():
    agent = build_agent()               # Gemini Live model + tools + hooks + session
    audio_io = BidiAudioIO()
    await agent.run(
        inputs=[audio_io.input()],
        outputs=[audio_io.output(), ConsoleOutput()],
    )

asyncio.run(main())
```

### Manual lifecycle

```python
import asyncio
from strands.experimental.bidi.types.events import (
    BidiResponseCompleteEvent, BidiTranscriptStreamEvent,
)
from gemini_bidi_agent import build_agent

async def main():
    agent = build_agent(use_session=False)
    await agent.start()
    try:
        await agent.send("What is the Gemini Live API?")
        async for event in agent.receive():
            if isinstance(event, BidiTranscriptStreamEvent) and event.is_final:
                print(f"{event.role}: {event.current_transcript or event.text}")
            elif isinstance(event, BidiResponseCompleteEvent):
                break
    finally:
        await agent.stop()

asyncio.run(main())
```

### WebSocket server

```bash
pip install -e ".[server]"
uvicorn examples.websocket_server:app --reload
```

Clients send JSON input events (e.g. `{"type": "bidi_text_input", "text": "hi"}`)
and read streaming output events.

## Tools

`default_tools()` wires:

- `calculator`, `current_time` — from `strands-agents-tools`
- `get_weather(location)` — a custom example tool (replace with a real API)
- `stop` — lets the user verbally end the conversation
- `end_session` — a custom graceful-shutdown tool that sets
  `request_state["stop_event_loop"] = True`

Tools run concurrently during the conversation without blocking streaming.

## Hooks

Registered by default via `default_hooks()`:

- **`ConversationLogger`** — logs init / connection / message lifecycle
- **`InterruptionTracker`** — counts and records barge-in interruptions
- **`ConnectionMonitor`** — tracks connection restarts and failures
- **`ConversationAnalytics`** — aggregates message/tool/interruption metrics

> `BidiAgentInitializedEvent` is dispatched **synchronously** during construction,
> so its callback is synchronous; every other hook callback is `async` and runs
> in the streaming loop without blocking it.

## Session management

Set `SESSION_ID` (and optionally `SESSION_STORAGE_DIR`) to enable a
`FileSessionManager`.

> **Gemini Live caveat:** Gemini Live does not yet produce a full message history,
> so cross-restart persistence is best-effort. Within a single session, Gemini's
> own [session resumption](https://ai.google.dev/gemini-api/docs/live-session)
> handles connection restarts (connections persist up to 24 hours).

## Development

```bash
pip install -e ".[dev]"
pytest
```

The smoke tests construct the model and agent without opening a network
connection (that only happens on `agent.start()`), so no real API key is needed.

## References

- [Strands Bidirectional Streaming](https://strandsagents.com/docs/user-guide/concepts/bidirectional-streaming/agent/)
- [Gemini Live model provider](https://strandsagents.com/docs/user-guide/concepts/bidirectional-streaming/models/gemini_live/)
- [Gemini Live API](https://ai.google.dev/gemini-api/docs/live)

---

## Phase 1 STR QC artifacts

This repository also contains Phase 1 STR QC kickoff artifacts:

- Schema: `/home/runner/work/RandD/RandD/sql/phase1_schema.sql`
- Architecture diagrams (ERD + state machine): `/home/runner/work/RandD/RandD/docs/phase1_architecture.md`
- Migration script: `/home/runner/work/RandD/RandD/scripts/migrate_phase1.py`

## Migration usage

```bash
python /home/runner/work/RandD/RandD/scripts/migrate_phase1.py \
  --master-csv /absolute/path/master.csv \
  --roster-csv /absolute/path/roster.csv \
  --db-path /absolute/path/str_qc.sqlite \
  --fail-on-error
```

Notes:
- The migration enables `PRAGMA foreign_keys=ON` on its connection and the schema also declares it.
- Plaintext secrets found in CSV inputs (for example WiFi password/door code) are surfaced as migration issues and are not stored as raw values.
