import os

from app import _vendor  # noqa: F401  (must run before strands.experimental.bidi imports)
from strands.experimental.bidi.agent import BidiAgent
from strands.experimental.bidi.models.gemini_live import BidiGeminiLiveModel
from strands_tools import editor, environment, http_request, load_tool, mcp_client, shell

from app.memory import memory_tools
from app.prompts import SYSTEM_PROMPT

# Default matches the vendored strands-py BidiGeminiLiveModel (this repo's agent).
# Override with GEMINI_LIVE_MODEL if needed.
DEFAULT_MODEL_ID = "gemini-3.1-flash-live-preview"

TOOLS = [
    editor.editor,
    shell.shell,
    load_tool.load_tool,
    mcp_client.mcp_client,
    http_request,  # module-based tool (TOOL_SPEC + function)
    environment,  # module-based tool (TOOL_SPEC + function)
]


def create_agent(mode: str, voice: str) -> BidiAgent:
    """Create one Gemini Live BidiAgent (repo-vendored bidi implementation) per connection."""
    model_id = os.getenv("GEMINI_LIVE_MODEL", DEFAULT_MODEL_ID)
    provider_config = {"audio": {"voice": voice}}

    if mode == "text":
        provider_config["inference"] = {"response_modalities": ["TEXT"]}

    client_config = None
    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        client_config = {"api_key": api_key}

    model = BidiGeminiLiveModel(
        model_id=model_id,
        provider_config=provider_config,
        client_config=client_config,
    )
    return BidiAgent(
        model=model,
        tools=TOOLS + memory_tools(),
        system_prompt=SYSTEM_PROMPT,
        name="RandD Live",
        description="Real-time Gemini Live meta-tooling agent (editor, shell, load_tool).",
    )
