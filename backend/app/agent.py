import importlib.util
import os
from pathlib import Path
from typing import Any

from app import _vendor  # noqa: F401  (must run before strands.experimental.bidi imports)
from strands.experimental.bidi.agent import BidiAgent
from strands_tools import editor, environment, http_request, load_tool, mcp_client, shell

from app.memory import memory_tools
from app.prompts import SYSTEM_PROMPT
from app.qc_journal import record_checklist_result
from app.tool_libraries import list_library_tools

# Default matches the vendored strands-py BidiGeminiLiveModel (this repo's agent).
# Override with GEMINI_LIVE_MODEL if needed.
DEFAULT_MODEL_ID = "gemini-3.1-flash-live-preview"

DEFAULT_PROVIDER = "openai"

# The three vended bidi providers (strands-py/src/strands/experimental/bidi/models).
# Each entry drives the frontend model picker and the per-provider voice list.
# "enabled" gates the picker and /ws — Gemini is off until a funded AI Studio
# key or Vertex allowlisting exists (1011/1008 as of 2026-07-03).
PROVIDERS: dict[str, dict[str, Any]] = {
    "gemini": {
        "name": "Gemini Live",
        "vendor": "Google",
        "model_id": os.getenv("GEMINI_LIVE_MODEL", DEFAULT_MODEL_ID),
        "default_voice": "Puck",
        "description": "Native multimodal realtime — disabled pending billing.",
        "enabled": False,
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

def _fun_tool_paths(*module_names: str) -> list[str]:
    """File paths of strands_fun_tools modules, loadable without importing the
    package __init__ (it pulls in pyautogui, which dies headless)."""
    spec = importlib.util.find_spec("strands_fun_tools")
    if spec is None or not spec.submodule_search_locations:
        return []
    base = Path(next(iter(spec.submodule_search_locations)))
    return [str(base / f"{name}.py") for name in module_names if (base / f"{name}.py").exists()]


TOOLS = [
    editor.editor,
    shell.shell,
    load_tool.load_tool,
    list_library_tools,
    mcp_client.mcp_client,
    http_request,  # module-based tool (TOOL_SPEC + function)
    environment,  # module-based tool (TOOL_SPEC + function)
    # QC turnover inspection journal (routes to the live checklist form)
    record_checklist_result,
    # QC vision tools, always loaded (by file path — see _fun_tool_paths)
    *_fun_tool_paths("take_photo", "yolo_vision"),
]


def build_model(provider: str, mode: str, voice: str) -> Any:
    """Build the vended bidi model for one provider (imported lazily per session)."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}; expected one of {sorted(PROVIDERS)}")

    provider_config: dict[str, Any] = {"audio": {"voice": voice}}

    if provider == "gemini":
        from strands.experimental.bidi.models.gemini_live import BidiGeminiLiveModel

        if mode == "text":
            provider_config["inference"] = {"response_modalities": ["TEXT"]}
        # Vertex AI (service-account auth via GOOGLE_APPLICATION_CREDENTIALS) when
        # enabled; otherwise AI Studio via GOOGLE_API_KEY. google-genai supports both.
        client_config: dict[str, Any] | None
        if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes"):
            client_config = {
                "vertexai": True,
                "project": os.getenv("GOOGLE_CLOUD_PROJECT", ""),
                "location": os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            }
        else:
            api_key = os.getenv("GOOGLE_API_KEY")
            client_config = {"api_key": api_key} if api_key else None
        return BidiGeminiLiveModel(
            model_id=PROVIDERS["gemini"]["model_id"],
            provider_config=provider_config,
            client_config=client_config,
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


def create_agent(mode: str, voice: str, provider: str = DEFAULT_PROVIDER) -> BidiAgent:
    """Create one BidiAgent per connection, on the requested vended provider."""
    model = build_model(provider, mode, voice)
    return BidiAgent(
        model=model,
        tools=TOOLS + memory_tools(),
        system_prompt=SYSTEM_PROMPT,
        name="RandD Live",
        description="Real-time Gemini Live meta-tooling agent (editor, shell, load_tool).",
    )
