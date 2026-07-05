import json
import os
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from strands.tools.registry import ToolRegistry

from app.agent import DEFAULT_MODEL_ID, DEFAULT_PROVIDER, PROVIDERS, TOOLS, create_agent
from app import browser_camera
from app.io import BidiWebSocketInput, BidiWebSocketOutput
from app.memory import memory_tools
from app.prompts import SYSTEM_PROMPT
from app.transcribe import compress_clip, measure_loudness, transcribe_audio

os.environ.setdefault("STRANDS_NON_INTERACTIVE", "true")
os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")

WORKSPACE_DIR = Path(__file__).resolve().parent.parent / "workspace"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="RandD Live Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/workspace", StaticFiles(directory=WORKSPACE_DIR), name="workspace")

REPORTS_DIR = WORKSPACE_DIR / "reports"
LATEST_REPORT = REPORTS_DIR / "inspection-report-latest.html"
CAPTURES_DIR = WORKSPACE_DIR / "captures"


@app.post("/api/inspection/video")
async def inspection_video(
    request: Request,
    section: str = Query(default=""),
    duration: float = Query(default=0.0),
) -> dict[str, Any]:
    """Receive a browser-recorded walkthrough clip (webm with mic audio).

    The frontend records with MediaRecorder when the agent calls take_video,
    then uploads the blob here. We save it, transcribe the audio (so the agent
    can fold speech + visuals into the section note), and wake the take_video
    tool that is blocking on the clip mailbox.
    """
    data = await request.body()
    if not data:
        return {"error": "empty body"}
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    import re as _re
    import time as _time

    # iOS Safari records video/mp4; Chrome/Android record video/webm.
    mime = (request.headers.get("content-type") or "video/webm").split(";")[0].strip()
    ext = ".mp4" if "mp4" in mime else ".webm"
    slug = _re.sub(r"[^a-zA-Z0-9-]+", "-", section).strip("-").lower() or "walkthrough"
    filename = f"video-{int(_time.time())}-{slug}{ext}"
    path = CAPTURES_DIR / filename
    path.write_bytes(data)

    transcript = await run_in_threadpool(transcribe_audio, path, mime)
    max_db = await run_in_threadpool(measure_loudness, path)
    # Compact web MP4 for the form embed — the raw recording bloats exports
    # (~3.5 MB per 10 s clip baked in as base64) and webm won't play on iOS.
    compact = await run_in_threadpool(compress_clip, path)
    serve = compact or path
    info = {
        "path": str(serve),
        "url": f"/workspace/captures/{serve.name}",
        "original_path": str(path),
        "section": section,
        "duration": duration,
        "size": serve.stat().st_size,
        "transcript": transcript,
        # Surfaced so the agent can tell the inspector the mic was dead
        # (max below about -50 dBFS means the track carried no real speech).
        "audio_max_db": max_db,
        "audio_ok": max_db is not None and max_db > -50,
    }
    browser_camera.deliver_clip(info)
    return info


@app.post("/api/inspection/export")
async def inspection_export(request: Request) -> dict[str, str]:
    """Receive the self-contained interactive inspection-form snapshot.

    The frontend posts the full HTML export (state + media baked in) whenever
    the form changes; the agent ships the latest file to Slack via
    files_upload_v2. Signed-off snapshots are additionally archived into the
    knowledge-base S3 bucket (best-effort) so past inspections become
    searchable memory.
    """
    html = (await request.body()).decode("utf-8", errors="replace")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_REPORT.write_text(html, encoding="utf-8")
    result = {"path": str(LATEST_REPORT), "url": "/workspace/reports/inspection-report-latest.html"}
    try:
        from app.kb_archive import archive_report, extract_state
        from app.report_db import upsert_form

        state = extract_state(html)
        # Live persistence: every export updates the form's row (keyed by the
        # form's own UUID), so the database tracks the inspection as it is
        # filled out — not just at archive time.
        form_id = await run_in_threadpool(upsert_form, state, len(html.encode("utf-8")))
        if form_id:
            result["form_uuid"] = form_id
        if state and state.get("signedOff") and os.getenv("BEDROCK_KB_S3_BUCKET"):
            archived = await run_in_threadpool(archive_report, html, "auto-archived on sign-off")
            result["archived"] = archived["summary_uri"]
    except Exception:
        pass  # persistence/archiving must never break the export path
    return result


VOICES: dict[str, list[dict[str, str]]] = {
    "gemini": [
        {"id": "Puck", "name": "Puck", "gender": "male", "accent": "American", "age": "adult", "description": "Upbeat male voice."},
        {"id": "Charon", "name": "Charon", "gender": "male", "accent": "American", "age": "adult", "description": "Informative, deep male voice."},
        {"id": "Kore", "name": "Kore", "gender": "female", "accent": "American", "age": "adult", "description": "Firm female voice."},
        {"id": "Fenrir", "name": "Fenrir", "gender": "male", "accent": "American", "age": "adult", "description": "Excitable male voice."},
        {"id": "Aoede", "name": "Aoede", "gender": "female", "accent": "American", "age": "adult", "description": "Breezy female voice."},
        {"id": "Leda", "name": "Leda", "gender": "female", "accent": "American", "age": "youthful", "description": "Youthful female voice."},
        {"id": "Orus", "name": "Orus", "gender": "male", "accent": "American", "age": "adult", "description": "Firm male voice."},
        {"id": "Zephyr", "name": "Zephyr", "gender": "female", "accent": "American", "age": "adult", "description": "Bright female voice."},
    ],
    "openai": [
        {"id": "alloy", "name": "Alloy", "gender": "neutral", "accent": "American", "age": "adult", "description": "Balanced neutral voice."},
        {"id": "ash", "name": "Ash", "gender": "male", "accent": "American", "age": "adult", "description": "Warm male voice."},
        {"id": "coral", "name": "Coral", "gender": "female", "accent": "American", "age": "adult", "description": "Bright female voice."},
        {"id": "echo", "name": "Echo", "gender": "male", "accent": "American", "age": "adult", "description": "Resonant male voice."},
        {"id": "sage", "name": "Sage", "gender": "female", "accent": "American", "age": "adult", "description": "Calm female voice."},
        {"id": "shimmer", "name": "Shimmer", "gender": "female", "accent": "American", "age": "adult", "description": "Crisp female voice."},
        {"id": "verse", "name": "Verse", "gender": "male", "accent": "American", "age": "adult", "description": "Expressive male voice."},
        {"id": "marin", "name": "Marin", "gender": "female", "accent": "American", "age": "adult", "description": "Natural conversational voice."},
        {"id": "cedar", "name": "Cedar", "gender": "male", "accent": "American", "age": "adult", "description": "Grounded male voice."},
    ],
    "nova": [
        {"id": "matthew", "name": "Matthew", "gender": "male", "accent": "American", "age": "adult", "description": "Default American male voice."},
        {"id": "tiffany", "name": "Tiffany", "gender": "female", "accent": "American", "age": "adult", "description": "American female voice."},
        {"id": "amy", "name": "Amy", "gender": "female", "accent": "British", "age": "adult", "description": "British female voice."},
    ],
}


@app.on_event("startup")
async def startup() -> None:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(WORKSPACE_DIR)


_tool_list_cache: list[dict[str, str]] | None = None


def tool_list() -> list[dict[str, str]]:
    """Every tool registered on the live agent (same registry BidiAgent builds)."""
    global _tool_list_cache
    if _tool_list_cache is None:
        registry = ToolRegistry()
        registry.process_tools(TOOLS + memory_tools())
        tools = []
        for spec in registry.get_all_tool_specs():
            description = str(spec.get("description", ""))
            if len(description) > 200:
                description = description[:197].rstrip() + "..."
            tools.append({"name": str(spec["name"]), "description": description})
        _tool_list_cache = sorted(tools, key=lambda tool: tool["name"])
    return _tool_list_cache


@app.get("/api/agent")
async def get_agent() -> dict[str, Any]:
    return {
        "name": "RandD Live",
        "model": os.getenv("GEMINI_LIVE_MODEL", DEFAULT_MODEL_ID),
        "instructions": SYSTEM_PROMPT,
        "tools": tool_list(),
    }


@app.get("/api/models")
async def get_models() -> dict[str, Any]:
    """The enabled vended bidi providers, for the frontend model picker."""
    return {
        "default": DEFAULT_PROVIDER,
        "models": [
            {
                "id": provider_id,
                "name": info["name"],
                "vendor": info["vendor"],
                "modelId": info["model_id"],
                "defaultVoice": info["default_voice"],
                "description": info["description"],
            }
            for provider_id, info in PROVIDERS.items()
            if info.get("enabled", True)
        ],
    }


@app.get("/api/voices")
async def get_voices(provider: str = Query(DEFAULT_PROVIDER, pattern="^(gemini|openai|nova)$")) -> dict[str, Any]:
    return {"voices": VOICES[provider]}


@app.get("/api/workspace")
async def get_workspace() -> dict[str, Any]:
    files = [
        str(path.relative_to(WORKSPACE_DIR))
        for path in WORKSPACE_DIR.rglob("*")
        if path.is_file() and not any(part.startswith(".") for part in path.relative_to(WORKSPACE_DIR).parts)
    ]
    return {"files": sorted(files)}


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    mode: str = Query("audio", pattern="^(audio|text)$"),
    voice: str = Query("Puck"),
    provider: str = Query(DEFAULT_PROVIDER, pattern="^(gemini|openai|nova)$"),
) -> None:
    """Drive one live session with the vendored bidi harness loop.

    ``BidiAgent.run`` owns the whole lifecycle: it starts the agent loop,
    supervises input/output tasks in the harness task group, executes tools
    concurrently, and tears everything down via ``stop_all``.
    """
    await websocket.accept()
    if not PROVIDERS.get(provider, {}).get("enabled", True):
        await websocket.send_text(
            json.dumps({"type": "bidi_error", "error": f"provider {provider!r} is disabled"})
        )
        await websocket.close()
        return
    try:
        # Inside the try so construction failures (missing credentials, model
        # deps) reach the browser as bidi_error instead of a dead socket.
        agent = create_agent(mode=mode, voice=voice, provider=provider)
        await agent.run(
            inputs=[BidiWebSocketInput(websocket)],
            outputs=[BidiWebSocketOutput(websocket)],
        )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_text(json.dumps({"type": "bidi_error", "error": str(exc)}))
        except Exception:
            pass


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
