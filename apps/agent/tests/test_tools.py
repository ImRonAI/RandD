"""Tool behavior against a real (tmp) migrated+seeded database."""

from __future__ import annotations

import hashlib
import json

import pytest
from strqc_db.connection import connect

from strqc_agent.tools.journal import list_checklist_items, record_checklist_result
from strqc_agent.tools.property_info import get_property_brief
from strqc_agent.tools.stages import advance_stage
from strqc_agent.tools.work_orders import list_open_work_orders, open_work_order


def test_list_checklist_items(ctx):
    items = list_checklist_items()
    assert len(items) == 12
    assert items[0]["category"] == "Hot Tub"
    assert {"item_id", "category", "text", "required_photo"} <= set(items[0])
    assert items[0]["required_photo"] is True


def test_record_checklist_result_writes_row_and_starts_inspection(ctx):
    out = record_checklist_result(item_id=1, result="fail", notes="water cloudy")
    assert out["result"] == "FAIL"
    assert ctx.inspection_id == out["inspection_id"]

    conn = connect(ctx.db_path)
    try:
        row = conn.execute(
            "SELECT * FROM inspection_item_result WHERE inspection_item_result_id = ?",
            (out["inspection_item_result_id"],),
        ).fetchone()
        insp = conn.execute(
            "SELECT * FROM inspection WHERE inspection_id = ?", (out["inspection_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row["result"] == "FAIL"
    assert row["notes"] == "water cloudy"
    assert insp["task_id"] == 1
    assert insp["inspector_stakeholder_id"] == 5

    # Second result reuses the same inspection.
    out2 = record_checklist_result(item_id=2, result="PASS")
    assert out2["inspection_id"] == out["inspection_id"]


def test_record_checklist_result_rejects_bad_verdict(ctx):
    with pytest.raises(ValueError):
        record_checklist_result(item_id=1, result="MAYBE")


def test_capture_photo_inserts_row_with_hash(ctx, fake_camera):
    from strqc_agent.tools.camera import capture_photo

    out = capture_photo(caption="hot tub water", purpose="damage", include_in_report=True)
    expected_hash = hashlib.sha256(b"fake-image-bytes").hexdigest()
    assert out["content_hash"] == expected_hash
    assert fake_camera.calls == [{"caption": "hot tub water", "purpose": "damage"}]

    conn = connect(ctx.db_path)
    try:
        row = conn.execute(
            "SELECT * FROM photo_memory WHERE photo_memory_id = ?", (out["photo_memory_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row["content_hash"] == expected_hash
    assert row["include_in_report"] == 1
    assert row["property_id"] == 1
    assert row["task_id"] == 1
    assert json.loads(row["metadata_json"])["purpose"] == "damage"


def test_default_file_backend_creates_placeholder(ctx):
    from strqc_agent.tools.camera import capture_photo

    out = capture_photo(caption="deck")
    assert out["uri"].startswith(ctx.photo_dir)


def test_open_work_order_links_source_items(ctx):
    r1 = record_checklist_result(item_id=9, result="FAIL", notes="CO detector missing")
    wo = open_work_order(
        details="Replace CO detector in hallway",
        priority="high",
        source_item_result_ids=[r1["inspection_item_result_id"]],
    )
    assert wo["priority"] == "HIGH"

    conn = connect(ctx.db_path)
    try:
        link = conn.execute(
            "SELECT * FROM work_order_source_item WHERE work_order_id = ?", (wo["work_order_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert link["inspection_item_result_id"] == r1["inspection_item_result_id"]

    open_wos = list_open_work_orders()
    assert [w["work_order_id"] for w in open_wos] == [wo["work_order_id"]]
    assert open_wos[0]["status"] == "NEW"


def test_advance_stage_updates_task_and_records_event(ctx):
    out = advance_stage("CLN")
    assert out == {"task_id": 1, "stage_key": "CLN"}

    conn = connect(ctx.db_path)
    try:
        task = conn.execute("SELECT * FROM task WHERE task_id = 1").fetchone()
        stage = conn.execute(
            "SELECT stage_key FROM stage_definition WHERE stage_definition_id = ?",
            (task["current_stage_definition_id"],),
        ).fetchone()
        event = conn.execute(
            "SELECT * FROM task_stage_event WHERE task_id = 1 AND stage_definition_id = ?",
            (task["current_stage_definition_id"],),
        ).fetchone()
    finally:
        conn.close()
    assert stage["stage_key"] == "CLN"
    assert event["is_complete"] == 1
    assert event["completed_by_stakeholder_id"] == 5


def test_advance_stage_rejects_unknown_key(ctx):
    with pytest.raises(ValueError):
        advance_stage("NOPE")


def test_property_brief_masks_secrets(ctx):
    # Store a fake ciphertext directly (never plaintext).
    ciphertext = "v1.bm9uY2U=.Y2lwaGVydGV4dA=="
    conn = connect(ctx.db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE property SET wifi_ssid = 'GrizzlyGuest', "
                "wifi_password_ciphertext = ?, door_code_ciphertext = ? WHERE property_id = 1",
                (ciphertext, ciphertext),
            )
    finally:
        conn.close()

    brief = get_property_brief()
    dumped = json.dumps(brief)
    assert ciphertext not in dumped
    assert "ciphertext" not in dumped
    assert brief["wifi_password"].startswith("••••")
    assert brief["door_code"].startswith("••••")
    assert brief["unit_code"] == "BBL-014"
    assert "Hot tub cover straps" in brief["standing_instructions"]
    assert any(f["feature"] for f in brief["features"])
