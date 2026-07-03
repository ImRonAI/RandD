"""Runtime context shared by the agent's tools.

Tools are plain module-level functions (Strands ``@tool``), so they get their
database/task scope from a module-level :class:`AgentRunContext` set by the
assembler (see :mod:`strqc_agent.assemble`) before the agent starts.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from strqc_db.connection import connect


@dataclass
class AgentRunContext:
    """Scope for one agent session: which DB, task, property, and inspector."""

    db_path: str
    photo_dir: str = "./photostore"
    task_id: int | None = None
    property_id: int | None = None
    inspection_id: int | None = None
    checklist_template_id: int = 1
    stakeholder_id: int | None = None
    extra: dict = field(default_factory=dict)

    def get_conn(self) -> sqlite3.Connection:
        """Open a connection to the operational database."""
        return connect(self.db_path)


_current: AgentRunContext | None = None


def set_context(ctx: AgentRunContext) -> None:
    """Install the active run context (called by the assembler / tests)."""
    global _current
    _current = ctx


def get_context() -> AgentRunContext:
    """Return the active run context, or raise with a clear message."""
    if _current is None:
        raise RuntimeError(
            "no AgentRunContext set — call strqc_agent.context.set_context() "
            "(build_agent does this for you)"
        )
    return _current


def clear_context() -> None:
    """Remove the active run context (test teardown)."""
    global _current
    _current = None
