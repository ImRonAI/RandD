"""Guardrail policy + hook interception."""

from __future__ import annotations

from types import SimpleNamespace

from strqc_agent.guardrails import ConfirmationGuardrail, requires_confirmation


def _event(name: str, tool_input: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        tool_use={"name": name, "toolUseId": "t1", "input": tool_input or {}},
        cancel_tool=False,
    )


def test_policy_flags_the_right_tools():
    assert requires_confirmation("deliver_report") is True
    assert requires_confirmation("open_work_order", {"priority": "URGENT"}) is True
    assert requires_confirmation("open_work_order", {"priority": "urgent"}) is True
    assert requires_confirmation("open_work_order", {"priority": "MEDIUM"}) is False
    assert requires_confirmation("open_work_order") is False
    assert requires_confirmation("advance_stage", {"stage_key": "DONE"}) is True
    assert requires_confirmation("advance_stage", {"stage_key": "REPORT"}) is True
    assert requires_confirmation("advance_stage", {"stage_key": "CLN"}) is False
    assert requires_confirmation("record_checklist_result", {"result": "FAIL"}) is False
    assert requires_confirmation("capture_photo") is False


def test_hook_cancels_unconfirmed_consequential_call():
    guard = ConfirmationGuardrail()
    event = _event("deliver_report", {"report_path": "/tmp/r.pdf"})
    guard.check(event)
    assert event.cancel_tool
    assert "confirmation" in str(event.cancel_tool)


def test_hook_allows_non_consequential_call():
    guard = ConfirmationGuardrail()
    event = _event("record_checklist_result", {"item_id": 1, "result": "PASS"})
    guard.check(event)
    assert event.cancel_tool is False


def test_grant_is_one_shot():
    guard = ConfirmationGuardrail()
    guard.grant("deliver_report")

    first = _event("deliver_report")
    guard.check(first)
    assert first.cancel_tool is False

    second = _event("deliver_report")
    guard.check(second)
    assert second.cancel_tool  # grant consumed


def test_revoke():
    guard = ConfirmationGuardrail()
    guard.grant("advance_stage")
    guard.revoke("advance_stage")
    event = _event("advance_stage", {"stage_key": "DONE"})
    guard.check(event)
    assert event.cancel_tool
