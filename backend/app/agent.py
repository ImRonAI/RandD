import os
from typing import Any

from app import _vendor  # noqa: F401  (must run before strands.experimental.bidi imports)
from strands.experimental.bidi.agent import BidiAgent
from strands_tools import batch, editor, environment, http_request, image_reader, load_tool, mcp_client, shell
from strands_tools.graph import graph
from strands_tools.swarm import swarm
from strands_tools.use_agent import use_agent
from strands_tools.workflow import workflow

from strands_google.google_auth import google_auth
from strands_google.gmail_helpers import gmail_reply, gmail_send
from strands_google.use_google import use_google

from app.camera_control import control_camera
from app.approval_tools import request_photo_approval
from app.capture_tools import take_photo, take_video
from app.gmail_attachments import gmail_send_with_attachments
from app.kb_archive import archive_inspection_report, save_site_memory
from app.memory import memory_tools
from app.prompts import SYSTEM_PROMPT
from app.walkthrough_videos import list_walkthrough_videos
from app.qc_journal import (
    attach_item_photo,
    list_checklist_items,
    record_checklist_result,
    record_section_note,
)
from app.tool_libraries import list_library_tools
from app.vision_tools import yolo_vision

# Default matches the vendored strands-py BidiGeminiLiveModel (this repo's agent).
# Override with GEMINI_LIVE_MODEL if needed.
DEFAULT_MODEL_ID = "gemini-3.1-flash-live-preview"

DEFAULT_PROVIDER = os.getenv("STRQC_BIDI_PROVIDER", "gemini")

# The inspector's input device is ALWAYS the browser microphone, which streams
# PCM16 at this rate (frontend MIC_SAMPLE_RATE in use-live-agent.ts). Every bidi
# model must be told this is the input rate so it decodes the samples correctly.
# Gemini/Nova already default to 16 kHz; OpenAI Realtime defaults to 24 kHz and
# ignores the per-chunk sample_rate, so without this it misreads the mic (audio
# sounds sped-up/garbled to the model) and comprehension/tool-use degrades.
BROWSER_MIC_RATE = 16000

# The three vended bidi providers (strands-py/src/strands/experimental/bidi/models).
# Each entry drives the frontend model picker and the per-provider voice list.
# "enabled" gates the picker and /ws.
PROVIDERS: dict[str, dict[str, Any]] = {
    "gemini": {
        "name": "Gemini Live",
        "vendor": "Google",
        "model_id": os.getenv("GEMINI_LIVE_MODEL", DEFAULT_MODEL_ID),
        "default_voice": "Puck",
        "description": "Native multimodal realtime (gemini-3.1-flash-live-preview).",
        "enabled": True,
    },
    "openai": {
        "name": "GPT-Realtime-2",
        "vendor": "OpenAI",
        "model_id": os.getenv("OPENAI_MODEL", "gpt-realtime-2"),
        "default_voice": "alloy",
        "description": "OpenAI Realtime over WebSocket — default field agent model.",
        "enabled": True,
    },
    "nova": {
        "name": "Nova Sonic 2",
        "vendor": "Amazon",
        "model_id": os.getenv("STRQC_NOVA_MODEL_ID", "amazon.nova-2-sonic-v1:0"),
        "default_voice": "matthew",
        "description": "Amazon Bedrock bidirectional speech (us-east-1).",
        "enabled": True,
    },
}

# Baseline registry: only the native meta-tooling primitives are always on.
# Everything else (QC journal, camera/capture, vision, KB, formations, Google,
# image_reader, list_library_tools) is discovered and hot-loaded on demand with
# the native `load_tool` tool — see the tool registry in app/prompts.py. This
# keeps the live tool declarations sent to the model small (context window).
# Session-scoped tools that cannot be file-loaded (native browser, perplexity,
# inventory/onboarding, tenant Slack, Smarty MCP, long-term memory) are still
# injected per connection in app/main.py.
TOOLS = [
    editor.editor,
    shell.shell,
    load_tool.load_tool,
    mcp_client.mcp_client,
    http_request,
    environment,
]

# ── Discoverable tool catalog, baked into load_tool's own description ─────────
# The agent is a meta-tooling agent: only the six primitives above are registered
# up front. Every other tool is hot-loaded on demand with the native `load_tool`
# tool. So the model knows WHAT it can load and from WHERE, we generate a catalog
# (tool name -> exact load_tool call) and append it to load_tool's model-facing
# description. The native `load_tool` schema and function are untouched — only its
# description gains the map. Session-scoped tools that cannot be file-loaded
# (browser, perplexity, inventory/onboarding, tenant Slack, Smarty, memory) are
# not in the catalog; they are injected per connection in app/main.py.
import ast as _ast
import importlib.util as _import_util
import pkgutil as _pkgutil
from pathlib import Path as _Path

_APP_DIR = _Path(__file__).resolve().parent

# App @tool files removed from the baseline; each is loadable by file path. A
# single file can define several tools (e.g. qc_journal.py), so entries are
# (tool_name, module_filename).
_APP_LOADABLE: list[tuple[str, str]] = [
    ("control_camera", "camera_control.py"),
    ("take_photo", "capture_tools.py"),
    ("take_video", "capture_tools.py"),
    ("yolo_vision", "vision_tools.py"),
    ("list_checklist_items", "qc_journal.py"),
    ("record_checklist_result", "qc_journal.py"),
    ("record_section_note", "qc_journal.py"),
    ("attach_item_photo", "qc_journal.py"),
    ("archive_inspection_report", "kb_archive.py"),
    ("save_site_memory", "kb_archive.py"),
    ("list_walkthrough_videos", "walkthrough_videos.py"),
    ("gmail_send_with_attachments", "gmail_attachments.py"),
    ("request_photo_approval", "approval_tools.py"),
]

# Provider/class-based or non-tool modules that cannot be load_tool'd by file
# path (they need instantiation), plus the primitives already registered.
_SKIP_LIBRARY_MODULES = {
    "a2a_client", "agent_core_memory", "browser", "code_interpreter", "utils",
    "load_tool", "editor", "shell", "mcp_client", "http_request", "environment",
}


def _tool_names_in_file(path: _Path) -> list[str]:
    """Actual tool names in a file (``@tool`` functions and ``TOOL_SPEC`` name),
    read via AST so no module is imported (fast, and safe for optional deps)."""
    try:
        tree = _ast.parse(path.read_text())
    except Exception:
        return []
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                target = dec.func if isinstance(dec, _ast.Call) else dec
                dec_name = target.attr if isinstance(target, _ast.Attribute) else getattr(target, "id", None)
                if dec_name == "tool":
                    names.append(node.name)
                    break
        elif isinstance(node, _ast.Assign) and any(
            isinstance(t, _ast.Name) and t.id == "TOOL_SPEC" for t in node.targets
        ):
            if isinstance(node.value, _ast.Dict):
                for key, value in zip(node.value.keys, node.value.values):
                    if (
                        isinstance(key, _ast.Constant) and key.value == "name"
                        and isinstance(value, _ast.Constant) and isinstance(value.value, str)
                    ):
                        names.append(value.value)
    return names


def _package_loadable(package: str) -> list[tuple[str, str]]:
    spec = _import_util.find_spec(package)
    if spec is None or not spec.submodule_search_locations:
        return []
    base = _Path(list(spec.submodule_search_locations)[0])
    entries: list[tuple[str, str]] = []
    for info in _pkgutil.iter_modules([str(base)]):
        if info.name.startswith("_") or info.name in _SKIP_LIBRARY_MODULES or info.ispkg:
            continue
        path = base / f"{info.name}.py"
        for name in _tool_names_in_file(path):
            entries.append((name, str(path)))
    return entries


def _load_tool_catalog() -> str:
    lines = [
        "## DISCOVERABLE TOOL CATALOG",
        "These tools are NOT pre-registered. Hot-load any of them on demand with",
        "an exact call below, then invoke it. Always prefer loading an existing",
        "tool over creating a new one, and load what you expect to need early.",
        "",
    ]

    def section(title: str, entries: list[tuple[str, str]]) -> None:
        if not entries:
            return
        lines.append(f"### {title}")
        for name, path in sorted(set(entries)):
            lines.append(f'- {name}: load_tool(name="{name}", path="{path}")')
        lines.append("")

    section("App tools", [(name, str(_APP_DIR / fname)) for name, fname in _APP_LOADABLE])
    for pkg in ("strands_tools", "strands_fun_tools", "strands_google"):
        try:
            section(pkg, _package_loadable(pkg))
        except Exception:
            pass
    return "\n".join(lines).rstrip()


# Append (idempotently) the catalog to the native load_tool tool's description.
_MARKER = "\n\n## DISCOVERABLE TOOL CATALOG"
_base_desc = load_tool.load_tool.tool_spec["description"].split(_MARKER)[0].rstrip()
load_tool.load_tool.tool_spec["description"] = _base_desc + "\n\n" + _load_tool_catalog()


def build_model(provider: str, mode: str, voice: str) -> Any:
    """Build the vended bidi model for one provider (imported lazily per session)."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}; expected one of {sorted(PROVIDERS)}")

    # input_rate matches the browser mic (16 kHz) for every provider; output_rate
    # is left at each model's native rate — the frontend plays back at whatever
    # sample_rate the model stamps on bidi_audio_stream (use-live-agent.ts).
    provider_config: dict[str, Any] = {"audio": {"voice": voice, "input_rate": BROWSER_MIC_RATE}}

    if provider == "gemini":
        from strands.experimental.bidi.models.gemini_live import BidiGeminiLiveModel

        # SDK-default config: AUDIO responses with input/output transcription.
        # gemini-3.1-flash-live-preview rejects TEXT-only response modalities,
        # so text-mode sessions ride the same audio session and read transcripts.
        api_key = os.getenv("GOOGLE_API_KEY")

        thinking_level = os.getenv("GEMINI_THINKING_LEVEL") or os.getenv("STRQC_GEMINI_THINKING_LEVEL", "HIGH")

        inference_config = {}
        if thinking_level:
            inference_config["thinking_config"] = {"thinking_level": thinking_level}
        provider_config["inference"] = inference_config

        return BidiGeminiLiveModel(
            model_id=PROVIDERS["gemini"]["model_id"],
            provider_config=provider_config,
            client_config={"api_key": api_key} if api_key else None,
        )

    if provider == "openai":
        from strands.experimental.bidi.models.openai_realtime import BidiOpenAIRealtimeModel

        client_config: dict[str, Any] = {}
        for key, env in (
            ("api_key", "OPENAI_API_KEY"),
            ("organization", "OPENAI_ORGANIZATION"),
            ("project", "OPENAI_PROJECT"),
        ):
            if os.getenv(env):
                client_config[key] = os.environ[env]
        return BidiOpenAIRealtimeModel(
            model_id=PROVIDERS["openai"]["model_id"],
            provider_config=provider_config,
            client_config=client_config or None,
        )

    # nova — credentials come from the standard AWS chain
    from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel

    return BidiNovaSonicModel(
        model_id=PROVIDERS["nova"]["model_id"],
        provider_config=provider_config,
        client_config={"region": os.getenv("AWS_REGION", "us-east-1")},
    )


def create_agent(
    mode: str,
    voice: str,
    provider: str = DEFAULT_PROVIDER,
    *,
    session_tools: list[Any] | None = None,
) -> BidiAgent:
    """Create one BidiAgent per connection, on the requested vended provider."""
    model = build_model(provider, mode, voice)
    return BidiAgent(
        model=model,
        tools=TOOLS + list(session_tools or ()) + memory_tools(),
        system_prompt=SYSTEM_PROMPT,
        name="Vantage AI",
        description="Tenant-scoped real-time field operations and property inspection agent.",
    )
