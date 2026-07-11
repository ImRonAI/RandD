import json
import os
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from strands.tools.registry import ToolRegistry

from app.agent import DEFAULT_MODEL_ID, DEFAULT_PROVIDER, PROVIDERS, TOOLS, create_agent
from app import browser_camera
from app.io import BidiWebSocketInput, BidiWebSocketOutput
from app.memory import memory_tools
from app.prompts import SYSTEM_PROMPT
from app.transcribe import compress_clip, measure_loudness, transcribe_audio
from app.approval_registry import ApprovalRegistry, ApprovalResolution
from app.approval_tools import approval_scope
from app.vantage.api import create_vantage_router
from app.vantage.auth_api import create_auth_router, session_context
from app.vantage.google_day_api import create_google_day_router
from app.vantage.runtime import build_runtime

os.environ.setdefault("STRANDS_NON_INTERACTIVE", "true")
os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")

WORKSPACE_DIR = Path(__file__).resolve().parent.parent / "workspace"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Vantage AI Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("VANTAGE_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/workspace", StaticFiles(directory=WORKSPACE_DIR), name="workspace")

VANTAGE = build_runtime()
_session_dependency = session_context(VANTAGE)


@app.middleware("http")
async def protect_tenant_surfaces(request: Request, call_next):
    """Keep legacy field/media routes behind the same verified session.

    New Vantage routers also authorize entity access; this middleware closes
    the older unscoped HTTP entry points while they are incrementally ported.
    """
    public = {"/api/auth/code/request", "/api/auth/code/verify"}
    protected = request.url.path.startswith((
        "/api/field", "/api/inspection", "/api/properties", "/api/inspectors",
        "/api/workspace", "/workspace",
    ))
    if protected and request.url.path not in public:
        try:
            VANTAGE.context_from_token(request.cookies.get("vantage_session"))
        except Exception:
            return JSONResponse(status_code=401, content={"error": {
                "code": "not_authenticated", "message": "A valid Vantage session is required",
                "retryable": False, "fields": {},
            }})
    return await call_next(request)

app.include_router(create_auth_router(VANTAGE))
app.include_router(create_vantage_router(VANTAGE.repository, _session_dependency))
app.include_router(create_google_day_router(
    calendar=VANTAGE.calendar,
    places=VANTAGE.places,
    navigation=VANTAGE.navigation,
    context_dependency=_session_dependency,
))

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
        registry.process_tools(TOOLS)
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
        "name": "Vantage AI",
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


@app.get("/api/properties")
async def get_properties() -> dict[str, Any]:
    """Active homes for the inspection form's property dropdown."""
    from app.properties import list_properties

    return {"properties": await run_in_threadpool(list_properties)}


@app.get("/api/inspectors")
async def get_inspectors() -> dict[str, Any]:
    """QC inspectors who can sign off an inspection."""
    from app.properties import list_inspectors

    return {"inspectors": await run_in_threadpool(list_inspectors)}


# ── Field app (Vantage mobile) read endpoints — real data, additive only ─────


@app.get("/api/field/clusters")
async def field_clusters() -> dict[str, Any]:
    from app.field_api import list_clusters

    return {"clusters": await run_in_threadpool(list_clusters)}


@app.get("/api/field/day")
async def field_day(cluster: int | None = Query(default=None)) -> dict[str, Any]:
    from app.field_api import list_day

    return {"tasks": await run_in_threadpool(list_day, cluster)}


@app.get("/api/field/property/{property_id}")
async def field_property(property_id: int) -> dict[str, Any]:
    from app.field_api import property_detail

    detail = await run_in_threadpool(property_detail, property_id)
    return detail or {}


@app.get("/api/field/checklist")
async def field_checklist() -> dict[str, Any]:
    from app.field_api import checklist

    return {"sections": await run_in_threadpool(checklist)}


@app.get("/api/field/notifications")
async def field_notifications() -> dict[str, Any]:
    from app.field_api import list_notifications

    return {"notifications": await run_in_threadpool(list_notifications)}


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
    token: str = Query(...),
    mode: str = Query("audio", pattern="^(audio|text)$"),
    voice: str = Query("Puck"),
    provider: str = Query(DEFAULT_PROVIDER, pattern="^(gemini|openai|nova)$"),
) -> None:
    """Drive one live session with the vendored bidi harness loop.

    ``BidiAgent.run`` owns the whole lifecycle: it starts the agent loop,
    supervises input/output tasks in the harness task group, executes tools
    concurrently, and tears everything down via ``stop_all``.
    """
    if VANTAGE.token_service is None:
        await websocket.close(code=1013, reason="Vantage authentication is not configured")
        return
    try:
        claims = VANTAGE.token_service.consume_ws_token(token)
        context = VANTAGE.context_from_claims(claims)
    except Exception:
        await websocket.close(code=4401, reason="Invalid or replayed WebSocket token")
        return
    session_id = str(claims["jti"])
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
        def emit_approval(event: dict[str, Any]) -> None:
            __import__("asyncio").create_task(websocket.send_text(json.dumps(event, default=str)))

        def associate_approval(request, resolution) -> dict[str, str]:
            return VANTAGE.repository.associate_approved_evidence(
                context.organization_id, context.user_id,
                inspection_id=request.inspection_id, photo_id=request.media_id,
                item_id=request.item_id, asset_id=request.asset_id,
                verdict=request.proposed_verdict,
            )

        registry = ApprovalRegistry(event_sink=emit_approval, associate_approval=associate_approval,
                                    conversation_sink=emit_approval)

        async def resolve_approval(payload: dict[str, Any]) -> None:
            try:
                registry.resolve(
                    session_id=session_id,
                    resolution=ApprovalResolution(
                        approval_id=str(payload.get("approvalId") or ""),
                        decision=str(payload.get("decision") or ""),
                        feedback=payload.get("feedback"),
                        input_mode=payload.get("inputMode"),
                    ),
                )
            except Exception as exc:
                await websocket.send_text(json.dumps({
                    "type": "approval_error", "approvalId": payload.get("approvalId"),
                    "error": str(exc),
                }))

        privileged = context.has_role("ORG_ADMIN") and os.getenv("VANTAGE_PLATFORM_ADMIN_TOOLS", "false").lower() in {"1", "true", "yes"}
        agent = create_agent(mode=mode, voice=voice, provider=provider, privileged=privileged)
        with browser_camera.session_scope(session_id), approval_scope(session_id, registry):
            try:
                await agent.run(
                    inputs=[BidiWebSocketInput(websocket, approval_resolver=resolve_approval)],
                    outputs=[BidiWebSocketOutput(websocket)],
                )
            finally:
                browser_camera.discard_session(session_id)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_text(json.dumps({"type": "bidi_error", "error": str(exc)}))
        except Exception:
            pass


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
