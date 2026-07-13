import os
from typing import Any

from app import _vendor  # noqa: F401  (must run before strands.experimental.bidi imports)
from strands.experimental.bidi.agent import BidiAgent
from strands_tools import batch, editor, environment, http_request, image_reader, load_tool, mcp_client, shell
from strands_tools.graph import graph
from strands_tools.swarm import swarm
from strands_tools.use_agent import use_agent
from strands_tools.workflow import workflow

from strands_tools.slack import slack, slack_send_message
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
from app.slack_report import send_report_to_slack
from app.walkthrough_videos import list_walkthrough_videos, send_video_to_slack
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

TOOLS = [
    # QC turnover inspection journal (routes to the live checklist form)
    list_checklist_items,
    record_checklist_result,
    record_section_note,
    attach_item_photo,
    # Inspector's browser camera (frontend executes the start/stop/snap)
    control_camera,
    request_photo_approval,
    # Device-camera capture: browser stream first, server hardware fallback
    take_photo,
    take_video,
    # Access session-scoped walkthrough clips after the fact.
    list_walkthrough_videos,
    # YOLO object detection over the device-camera stream
    yolo_vision,
    # Runtime: code, files, environment, dynamic tool discovery, MCP, network
    editor.editor,
    shell.shell,
    load_tool.load_tool,
    list_library_tools,
    mcp_client.mcp_client,
    http_request,
    environment,
    # Visual inspection for screenshots produced by the session's browser tool.
    image_reader,
    # Multi-agent formations
    use_agent,
    batch,
    workflow,
    swarm,
    graph,
    # Delivery and Google integrations
    slack,
    slack_send_message,
    send_report_to_slack,
    use_google,
    google_auth,
    gmail_send,
    gmail_reply,
    gmail_send_with_attachments,
    send_video_to_slack,
    archive_inspection_report,
    save_site_memory,
]

# The generic handoff tool is intentionally not registered: Vantage uses the
# correlated, persisted `request_photo_approval` protocol above.


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
        enable_search_str = os.getenv("GEMINI_ENABLE_SEARCH") or os.getenv("STRQC_GEMINI_ENABLE_SEARCH", "false")
        enable_search = enable_search_str.lower() in ("true", "1", "yes")

        inference_config = {}
        if thinking_level:
            inference_config["thinking_config"] = {"thinking_level": thinking_level}
        inference_config["enable_search"] = enable_search
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
