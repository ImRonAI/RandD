"""STR QC field agent — Gemini Live via Strands BIDI (assembled in M2/M3)."""

from .assemble import build_agent
from .context import AgentRunContext
from .guardrails import ConfirmationGuardrail, requires_confirmation
from .persona import PERSONA_VERSION, SYSTEM_PROMPT, build_system_prompt

__all__ = [
    "PERSONA_VERSION",
    "SYSTEM_PROMPT",
    "AgentRunContext",
    "ConfirmationGuardrail",
    "build_agent",
    "build_system_prompt",
    "requires_confirmation",
]
