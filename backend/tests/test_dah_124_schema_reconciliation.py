from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from app.qc_journal import CHECKLIST_ITEMS
from scripts.audit_legacy_housekeeping import audit
from app.vantage.domain import ConflictError, DomainError, VantageRepository
from app.vantage.schema import (
    LEGACY_CHECKLIST_ID_TO_KEY,
    PHOTO_PURPOSES,
    QC_CHECKLIST_ITEMS,
    install_sqlite_schema,
)


@pytest.fixture()
def store(tmp_path: Path) -> tuple[VantageRepository, Path]:
    path = tmp_path / "dah124.sqlite"
    connection = sqlite3.connect(path)
    install_sqlite_schema(connection)
    repository = VantageRepository(lambda: sqlite3.connect(path))
    repository.bootstrap_organization("org-a", "Alpha", "portfolio-a")
    repository.bootstrap_user("user-a", "a@example.com", "org-a", "INSPECTOR")
    repository.create_home("org-a", "portfolio-a", "home-a", "Alpha Home")
    repository.create_home("org-a", "portfolio-a", "home-a2", "Alpha Home Two")
    return repository, path


def _inventory(repository: VantageRepository, *, home: str = "home-a", suffix: str = "1"):
    inspection = repository.start_inspection("org-a", "user-a", home, "turnover", f"inspection-{suffix}")
    room = repository.create_room(
        "org-a", "user-a", home, inspection["id"], repository.list_room_types("org-a")[0]["id"],
        f"Kitchen {suffix}", f"room-{suffix}",
    )
    asset = repository.create_asset(
        "org-a", "user-a", room["id"], inspection["id"], "Appliance", f"Fridge {suffix}", f"asset-{suffix}",
    )
    return inspection, room, asset


def _verified_photo(repository: VantageRepository, inspection: dict, room: dict, asset: dict,
                    suffix: str, purpose: str = "inspection_evidence") -> dict:
    photo = repository.create_photo_upload(
        "org-a", "user-a", room["home_id"], room["id"], asset["id"], inspection["id"],
        f"photo-{suffix}", purpose,
    )
    repository.complete_photo_upload(
        "org-a", photo["id"], f"org-a/{room['home_id']}/originals/{photo['id']}.jpg",
        suffix[0].encode().hex()[0].ljust(64, "a"), 100, "image/jpeg",
    )
    return photo


def test_exact_qc_journal_catalog_is_seeded_without_label_inference(store) -> None:
    _repository, path = store
    flattened = [(section, label) for section, labels in CHECKLIST_ITEMS.items() for label in labels]
    assert len(flattened) == len(QC_CHECKLIST_ITEMS) == len(LEGACY_CHECKLIST_ID_TO_KEY) == 38
    assert flattened == [(section, label) for _key, section, label in QC_CHECKLIST_ITEMS]
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT item_key,section_name,label FROM checklist_item ORDER BY display_order"
        ).fetchall()
    assert rows == list(QC_CHECKLIST_ITEMS)


def test_defaults_enums_and_required_relationships(store) -> None:
    repository, path = store
    inspection, room, asset = _inventory(repository)
    photo = repository.create_photo_upload(
        "org-a", "user-a", "home-a", room["id"], asset["id"], inspection["id"], "defaults"
    )
    assert inspection["inspection_type"] == "turnover" and inspection["status"] == "draft"
    assert photo["purpose"] == "asset_original" and photo["upload_status"] == "pending"
    assert set(PHOTO_PURPOSES) == {
        "asset_original", "inspection_evidence", "maintenance_before", "maintenance_after", "owner_report"
    }
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE photo SET purpose='unknown' WHERE organization_id='org-a' AND id=?", (photo["id"],)
        )


def test_scoped_client_id_replays_require_identical_payload(store) -> None:
    repository, _path = store
    inspection, room, asset = _inventory(repository)
    with pytest.raises(ConflictError) as inspection_conflict:
        repository.start_inspection("org-a", "user-a", "home-a", "onboarding", "inspection-1")
    assert inspection_conflict.value.code == "idempotency_payload_conflict"
    with pytest.raises(ConflictError):
        repository.create_room(
            "org-a", "user-a", "home-a", inspection["id"], room["room_type_id"], "Changed", "room-1"
        )
    with pytest.raises(ConflictError):
        repository.create_asset(
            "org-a", "user-a", room["id"], inspection["id"], "TV", asset["name"], "asset-1"
        )
    photo = _verified_photo(repository, inspection, room, asset, "replay")
    with pytest.raises(ConflictError):
        repository.create_photo_upload(
            "org-a", "user-a", "home-a", room["id"], asset["id"], inspection["id"],
            "photo-replay", "asset_original",
        )
    with pytest.raises(ConflictError):
        repository.complete_photo_upload(
            "org-a", photo["id"], f"org-a/home-a/originals/{photo['id']}.jpg", "b" * 64, 100, "image/jpeg"
        )


def test_result_history_pass_fail_na_and_multiple_photos(store) -> None:
    repository, _path = store
    inspection, room, asset = _inventory(repository)
    key = "housekeeping.kitchen.oven_clean"
    first = repository.record_inspection_item_result(
        "org-a", "user-a", inspection_id=inspection["id"], item_key=key,
        result="FAIL", note="grease", client_id="result-1",
    )
    replay = repository.record_inspection_item_result(
        "org-a", "user-a", inspection_id=inspection["id"], item_key=key,
        result="FAIL", note="grease", client_id="result-1",
    )
    second = repository.record_inspection_item_result(
        "org-a", "user-a", inspection_id=inspection["id"], item_key=key,
        result="PASS", note="cleaned", client_id="result-2",
    )
    assert replay["id"] == first["id"]
    assert (first["version"], second["version"], second["supersedes_result_id"]) == (1, 2, first["id"])
    assert [row["result"] for row in repository.inspection_result_history("org-a", inspection["id"], key)] == ["FAIL", "PASS"]
    na_result = repository.record_inspection_item_result(
        "org-a", "user-a", inspection_id=inspection["id"], item_key="hot_tub.full",
        result="NA", note="no hot tub", client_id="result-na",
    )
    assert na_result["result"] == "NA" and na_result["version"] == 1
    photos = [_verified_photo(repository, inspection, room, asset, suffix) for suffix in ("one", "two")]
    assert repository.attach_result_photo("org-a", result_id=second["id"], photo_id=photos[0]["id"], display_order=0)
    assert repository.attach_result_photo("org-a", result_id=second["id"], photo_id=photos[1]["id"], display_order=1)
    with pytest.raises(DomainError):
        repository.record_inspection_item_result(
            "org-a", "user-a", inspection_id=inspection["id"], item_key=key,
            result="REVIEW", note="", client_id="result-3",
        )


def test_same_org_cross_home_spoofing_fails_at_physical_fk(store) -> None:
    repository, path = store
    inspection, room, _asset = _inventory(repository, home="home-a", suffix="a")
    _other_inspection, other_room, _other_asset = _inventory(repository, home="home-a2", suffix="b")
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO asset(organization_id,id,home_id,room_id,created_by,client_id)
                   VALUES ('org-a','spoof','home-a',?,'user-a','spoof')""",
                (other_room["id"],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO photo(organization_id,id,home_id,room_id,asset_id,inspection_id,uploader_id,client_id)
                   VALUES ('org-a','spoof-photo','home-a',?,NULL,?,'user-a','spoof-photo')""",
                (room["id"], _other_inspection["id"]),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO inspection_inventory_link(
                     organization_id,inspection_id,home_id,entity_type,entity_id,room_id,action)
                   VALUES ('org-a',?,'home-a','room','missing-room','missing-room','created')""",
                (inspection["id"],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO inspection_inventory_link(
                     organization_id,inspection_id,home_id,entity_type,entity_id,action)
                   VALUES ('org-a',?,'home-a','room','null-room','created')""",
                (inspection["id"],),
            )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_approval_item_and_result_must_identify_the_same_checklist_revision(store) -> None:
    repository, path = store
    inspection, room, asset = _inventory(repository)
    oven = repository.record_inspection_item_result(
        "org-a", "user-a", inspection_id=inspection["id"],
        item_key="housekeeping.kitchen.oven_clean", result="PASS", note="",
        client_id="oven-result",
    )
    photo = _verified_photo(repository, inspection, room, asset, "approval-pair")
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO evidence_approval(
                     organization_id,id,home_id,inspection_id,photo_id,item_id,result_id,
                     asset_id,verdict,approved_by) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                ("org-a", "mismatched-approval", "home-a", inspection["id"], photo["id"],
                 "hot_tub.full", oven["id"], asset["id"], "PASS", "user-a"),
            )


def test_forward_migration_contract_and_checksum_evidence() -> None:
    root = Path(__file__).resolve().parents[2]
    migration = root / "backend/migrations/0002_dah_124_schema_reconciliation.sql"
    evidence = root / "docs/product/VANTAGE_SCHEMA_MAPPING.md"
    sql = migration.read_text()
    text = evidence.read_text()
    digest = hashlib.sha256(migration.read_bytes()).hexdigest()
    assert f"0002_sha256: `{digest}`" in text
    assert "RENAME COLUMN kind TO inspection_type" in sql
    assert sql.count("INSERT INTO checklist_item") == 1
    assert "CREATE TABLE inspection_item_result" in sql
    assert "CREATE TABLE result_photo" in sql
    assert "No room rows are inferred" in sql


def test_checked_in_legacy_history_matches_frozen_id_catalog() -> None:
    database = Path(__file__).resolve().parents[2] / "str_qc.sqlite"
    evidence = audit(database)
    assert evidence == {
        "report_count": 51,
        "distinct_item_ids": 38,
        "photo_count": 215,
        "max_photos_per_item": 3,
        "unknown_item_ids": [],
        "result_semantics": "checked_boolean_only_no_PASS_FAIL_NA_inference",
        "room_inference": "disabled",
    }
