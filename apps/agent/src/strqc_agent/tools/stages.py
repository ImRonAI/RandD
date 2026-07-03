"""Stage tool — advance the active task through the turnover pipeline (AGENTS.md §2)."""

from __future__ import annotations

from strands import tool
from strqc_db import repositories

from ..context import get_context

STAGE_KEYS = ("QC", "B2B", "CLN", "DONE", "OWN", "WO", "DONE_WO", "REPORT")


@tool
def advance_stage(stage_key: str) -> dict:
    """Advance the active task to a pipeline stage and record the stage event.

    Args:
        stage_key: One of QC, B2B, CLN, DONE, OWN, WO, DONE_WO, REPORT.

    Returns:
        The task id and the stage it now sits at.
    """
    ctx = get_context()
    if ctx.task_id is None:
        raise RuntimeError("no active task — cannot advance stage")
    key = stage_key.strip().upper()
    conn = ctx.get_conn()
    try:
        repositories.set_task_stage(conn, ctx.task_id, key, completed_by=ctx.stakeholder_id)
    finally:
        conn.close()
    return {"task_id": ctx.task_id, "stage_key": key}
