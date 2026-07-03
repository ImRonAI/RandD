"""Long-term memory for the Gemini Live bidi agent via the Strands memory framework.

Follows https://strandsagents.com/docs/user-guide/concepts/memory/overview/:
a ``BedrockKnowledgeBaseStore`` (``strands.vended_memory_stores``) plugged into a
``MemoryManager`` (``strands.memory``). The store targets the managed Bedrock
Knowledge Base ``knowledge-base-quick-start-fu4ig`` (ID ``LAJ1DYSVHG``) and reaches
Bedrock through the standard AWS credential chain (populate ``backend/.env`` — see
``.env.example``; credentials are never hardcoded or committed).

The vendored ``BidiAgent`` has no ``memory_manager`` plugin slot (that belongs to the
standard ``Agent``), so we register the manager's own ``search_memory`` /
``add_memory`` tools (``MemoryManager.tools``) on the bidi agent's tool registry.

Writability follows the framework rules: with only a knowledge base ID the store is
read-only. Set ``BEDROCK_KB_DATA_SOURCE_ID`` (plus ``BEDROCK_KB_S3_BUCKET`` for the
S3 data source) to enable writes through ``add_memory``.
"""

import os
from functools import lru_cache
from typing import Any

from strands.memory import MemoryManager

DEFAULT_KNOWLEDGE_BASE_ID = "LAJ1DYSVHG"
DEFAULT_KNOWLEDGE_BASE_TYPE = "MANAGED"


def _build_store() -> Any:
    from strands.vended_memory_stores import BedrockKnowledgeBaseStore

    config: dict[str, Any] = {
        "knowledge_base_id": os.getenv("BEDROCK_KB_ID", DEFAULT_KNOWLEDGE_BASE_ID),
    }

    # Skips the GetKnowledgeBase detection call; unset BEDROCK_KB_TYPE to auto-detect.
    kb_type = os.getenv("BEDROCK_KB_TYPE", DEFAULT_KNOWLEDGE_BASE_TYPE)
    if kb_type:
        config["knowledge_base_type"] = kb_type

    writable = False
    data_source_id = os.getenv("BEDROCK_KB_DATA_SOURCE_ID")
    if data_source_id:
        data_source_type = os.getenv("BEDROCK_KB_DATA_SOURCE_TYPE", "S3")
        config["data_source_id"] = data_source_id
        config["data_source_type"] = data_source_type
        if data_source_type == "S3":
            bucket = os.getenv("BEDROCK_KB_S3_BUCKET")
            if bucket:
                config["s3"] = {
                    "bucket": bucket,
                    "prefix": os.getenv("BEDROCK_KB_S3_PREFIX", "memories/"),
                }
                writable = True
        else:
            writable = True

    store_config: dict[str, Any] = {
        "name": "memories",
        "description": "Durable user preferences, decisions, and facts from prior sessions.",
        "writable": writable,
        "config": config,
    }
    scope = os.getenv("BEDROCK_KB_SCOPE")
    if scope:
        store_config["scope"] = scope

    return BedrockKnowledgeBaseStore(**store_config)


@lru_cache(maxsize=1)
def get_memory_manager() -> MemoryManager:
    """Shared MemoryManager over the Bedrock Knowledge Base store.

    Injection/extraction are ``Agent``-plugin behaviors, so they stay disabled here;
    the bidi agent gets memory through the manager's search/add tools instead.
    """
    store = _build_store()
    return MemoryManager(
        stores=[store],
        search_tool_config=True,
        add_tool_config=store.writable,
        injection=False,
    )


def memory_tools() -> list[Any]:
    """The framework's ``search_memory`` / ``add_memory`` AgentTools for the bidi agent."""
    return list(get_memory_manager().tools)
