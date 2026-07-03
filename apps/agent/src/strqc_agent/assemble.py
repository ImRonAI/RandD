"""Agent assembly — build the STR QC BidiAgent (TASKS.md M2.1).

Constructible without network: the Gemini Live connection is only opened on
``agent.start()``. Inject a model/delivery/capture backend for tests.
"""

from __future__ import annotations

from typing import Any

from strands.experimental.bidi import BidiAgent
from strands.tools.executors import SequentialToolExecutor
from strqc_shared.config import get_settings

from .context import AgentRunContext, set_context
from .guardrails import ConfirmationGuardrail
from .persona import build_system_prompt
from .tools import ALL_TOOLS
from .tools.camera import CaptureBackend, FileCaptureBackend, set_capture_backend
from .tools.slack_delivery import DeliveryAdapter, make_delivery_adapter, set_delivery_adapter


PROVIDERS = ("gemini", "openai", "nova")


def build_model(provider: str | None = None, provider_config: dict | None = None) -> Any:
    """Construct the BidiModel for a provider: gemini (default) | openai | nova.

    Falls back to ``Settings.strqc_bidi_provider`` when ``provider`` is None.
    All three vended models share the (model_id, provider_config, client_config)
    constructor shape.
    """
    settings = get_settings()
    name = (provider or settings.strqc_bidi_provider or "gemini").strip().lower()

    if name == "gemini":
        from strands.experimental.bidi.models.gemini_live import BidiGeminiLiveModel

        client_config = {"api_key": settings.google_api_key} if settings.google_api_key else None
        return BidiGeminiLiveModel(
            model_id=settings.strqc_gemini_model_id,
            provider_config=provider_config,
            client_config=client_config,
        )

    if name == "openai":
        from strands.experimental.bidi.models.openai_realtime import BidiOpenAIRealtimeModel

        client_config: dict[str, Any] = {}
        if settings.openai_api_key:
            client_config["api_key"] = settings.openai_api_key
        if settings.openai_organization:
            client_config["organization"] = settings.openai_organization
        if settings.openai_project:
            client_config["project"] = settings.openai_project
        return BidiOpenAIRealtimeModel(
            model_id=settings.openai_model,
            provider_config=provider_config,
            client_config=client_config or None,
        )

    if name == "nova":
        from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel

        return BidiNovaSonicModel(
            model_id=settings.strqc_nova_model_id,
            provider_config=provider_config,
            client_config={"region": settings.aws_region},
        )

    raise ValueError(f"Unknown BIDI provider {name!r}; expected one of {PROVIDERS}")


def _load_property_context(ctx: AgentRunContext) -> str | None:
    """Non-secret property brief appended to the system prompt."""
    if ctx.property_id is None:
        return None
    conn = ctx.get_conn()
    try:
        row = conn.execute(
            "SELECT unit_code, display_name, standing_instructions FROM property WHERE property_id = ?",
            (ctx.property_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    parts = [f"Property: {row['unit_code']} — {row['display_name']}"]
    if row["standing_instructions"]:
        parts.append(f"Standing instructions: {row['standing_instructions']}")
    return "\n".join(parts)


def build_agent(
    ctx: AgentRunContext,
    model: Any = None,
    *,
    provider: str | None = None,
    delivery: DeliveryAdapter | None = None,
    capture_backend: CaptureBackend | None = None,
    guardrail: ConfirmationGuardrail | None = None,
    provider_config: dict | None = None,
) -> BidiAgent:
    """Assemble the field-companion agent for one run context.

    Args:
        ctx: Run scope (db, task, property, inspector, photo dir).
        model: Injected BidiModel (tests); defaults to the provider's vended model.
        provider: BIDI provider — gemini | openai | nova (default: Settings).
        delivery: Report delivery adapter; defaults to Slack or dry-run per Settings.
        capture_backend: Photo capture backend; defaults to FileCaptureBackend.
        guardrail: Confirmation guardrail; a fresh one is created if omitted.
        provider_config: Optional provider config forwarded to the model.
    """
    set_context(ctx)
    set_capture_backend(capture_backend or FileCaptureBackend(ctx.photo_dir))
    set_delivery_adapter(delivery or make_delivery_adapter())

    if model is None:
        model = build_model(provider, provider_config)

    return BidiAgent(
        model=model,
        tools=list(ALL_TOOLS),
        system_prompt=build_system_prompt(_load_property_context(ctx)),
        hooks=[guardrail or ConfirmationGuardrail()],
        # Field workflows chain tools (take_photo → yolo_vision → journal);
        # order matters, so tools from one turn run sequentially.
        tool_executor=SequentialToolExecutor(),
        name="the Keeper",
        description="STR turnover quality-control field companion",
    )
