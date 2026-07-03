"""Tests for migrations, seeds, and repositories against a temp database."""

from __future__ import annotations

import pytest

from strqc_db import migrate as migrate_mod
from strqc_db import repositories as repo
from strqc_db.connection import connect
from strqc_db.seed import seed


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "test.sqlite"
    ran = migrate_mod.migrate(path)
    assert ran, "expected at least the baseline migration to apply"
    seed(path)
    conn = connect(path)
    yield conn
    conn.close()


def test_migrations_are_idempotent(tmp_path):
    path = tmp_path / "idem.sqlite"
    first = migrate_mod.migrate(path)
    second = migrate_mod.migrate(path)
    assert first and not second


def test_addendum_columns_exist(db):
    report_cols = {r["name"] for r in db.execute("PRAGMA table_info(report)")}
    assert {"delivery_channel", "delivered_at", "delivery_status"} <= report_cols

    photo_cols = {r["name"] for r in db.execute("PRAGMA table_info(photo_memory)")}
    assert "include_in_report" in photo_cols

    prop_cols = {r["name"] for r in db.execute("PRAGMA table_info(property)")}
    assert {"escapia_unit_native_pms_id", "escapia_pmc_id"} <= prop_cols

    tables = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"sync_cursor", "housekeeping_status_map"} <= tables


def test_seeded_property_and_features(db):
    prop = repo.get_property(db, "BBL-014")
    assert prop is not None and prop["display_name"] == "Grizzly Pines"
    features = repo.property_features(db, prop["property_id"])
    assert any(f["feature_key"] == "HOT_TUB" for f in features)


def test_stage_transition_records_event(db):
    repo.set_task_stage(db, 1, "CLN", completed_by=1)
    row = db.execute(
        "SELECT sd.stage_key FROM task t JOIN stage_definition sd "
        "ON sd.stage_definition_id = t.current_stage_definition_id WHERE t.task_id = 1"
    ).fetchone()
    assert row["stage_key"] == "CLN"
    events = db.execute("SELECT * FROM task_stage_event WHERE task_id = 1").fetchall()
    assert len(events) == 1 and events[0]["is_complete"] == 1


def test_inspection_flow_and_work_order(db):
    insp = repo.start_inspection(db, task_id=1, checklist_template_id=1, inspector_id=5)
    items = repo.checklist_items(db, 1)
    assert len(items) == 12

    fail_id = repo.record_item_result(
        db, insp, items[0]["checklist_item_template_id"], "FAIL",
        notes="Water at 96°F — heater fault", inspector_id=5,
    )
    wo = repo.create_work_order(
        db, property_id=1, task_id=1, details="Hot tub heater fault",
        priority="URGENT", source_item_result_ids=[fail_id],
    )
    link = db.execute(
        "SELECT * FROM work_order_source_item WHERE work_order_id = ?", (wo,)
    ).fetchone()
    assert link["inspection_item_result_id"] == fail_id


def test_invalid_result_rejected(db):
    with pytest.raises(ValueError):
        repo.record_item_result(db, 1, 1, "MAYBE")


def test_sync_cursor_upsert(db):
    repo.upsert_sync_cursor(db, "PMC1", "RESERVATIONS", start_version=42)
    repo.upsert_sync_cursor(db, "PMC1", "RESERVATIONS", start_version=43)
    cur = repo.get_sync_cursor(db, "PMC1", "RESERVATIONS")
    assert cur["start_version"] == 43
