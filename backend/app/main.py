import json
import os
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from strands_tools import editor, environment, http_request, load_tool, mcp_client, shell

from app.agent import DEFAULT_MODEL_ID, create_agent
from app.io import BidiWebSocketInput, BidiWebSocketOutput
from app.memory import memory_tools
from app.prompts import SYSTEM_PROMPT

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

VOICES = [
    {"id": "Puck", "name": "Puck", "gender": "male", "accent": "American", "age": "adult", "description": "Upbeat male voice."},
    {"id": "Charon", "name": "Charon", "gender": "male", "accent": "American", "age": "adult", "description": "Informative, deep male voice."},
    {"id": "Kore", "name": "Kore", "gender": "female", "accent": "American", "age": "adult", "description": "Firm female voice."},
    {"id": "Fenrir", "name": "Fenrir", "gender": "male", "accent": "American", "age": "adult", "description": "Excitable male voice."},
    {"id": "Aoede", "name": "Aoede", "gender": "female", "accent": "American", "age": "adult", "description": "Breezy female voice."},
    {"id": "Leda", "name": "Leda", "gender": "female", "accent": "American", "age": "youthful", "description": "Youthful female voice."},
    {"id": "Orus", "name": "Orus", "gender": "male", "accent": "American", "age": "adult", "description": "Firm male voice."},
    {"id": "Zephyr", "name": "Zephyr", "gender": "female", "accent": "American", "age": "adult", "description": "Bright female voice."},
]


@app.on_event("startup")
async def startup() -> None:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(WORKSPACE_DIR)


def _tool_spec(module: Any, name: str) -> dict[str, Any]:
    spec = getattr(module, "TOOL_SPEC", None)
    if spec is None:
        tool = getattr(module, name)
        spec = getattr(tool, "TOOL_SPEC", None) or getattr(tool, "tool_spec", {})
    description = str(spec.get("description", ""))
    if len(description) > 200:
        description = description[:197].rstrip() + "..."
    return {"name": spec.get("name", name), "description": description}


def tool_list() -> list[dict[str, str]]:
    tools = [
        _tool_spec(editor, "editor"),
        _tool_spec(shell, "shell"),
        _tool_spec(load_tool, "load_tool"),
        _tool_spec(mcp_client, "mcp_client"),
        _tool_spec(http_request, "http_request"),
        _tool_spec(environment, "environment"),
    ]
    for memory_tool in memory_tools():
        spec = memory_tool.tool_spec
        description = str(spec.get("description", ""))
        if len(description) > 200:
            description = description[:197].rstrip() + "..."
        tools.append({"name": spec.get("name", memory_tool.tool_name), "description": description})
    return tools


@app.get("/api/agent")
async def get_agent() -> dict[str, Any]:
    return {
        "name": "RandD Live",
        "model": os.getenv("GEMINI_LIVE_MODEL", DEFAULT_MODEL_ID),
        "instructions": SYSTEM_PROMPT,
        "tools": tool_list(),
    }


@app.get("/api/voices")
async def get_voices() -> dict[str, Any]:
    return {"voices": VOICES}


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
) -> None:
    """Drive one Gemini Live session with the vendored bidi harness loop.

    ``BidiAgent.run`` owns the whole lifecycle: it starts the agent loop,
    supervises input/output tasks in the harness task group, executes tools
    concurrently, and tears everything down via ``stop_all``.
    """
    await websocket.accept()
    agent = create_agent(mode=mode, voice=voice)

    try:
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
