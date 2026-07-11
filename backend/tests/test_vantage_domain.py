from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.vantage.domain import ConflictError, DomainError, VantageRepository
from app.vantage.schema import install_sqlite_schema


@pytest.fixture()
def repo(tmp_path: Path) -> VantageRepository:
    db = tmp_path / "vantage.sqlite"
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    install_sqlite_schema(connection)
    repository = VantageRepository(lambda: sqlite3.connect(db))
    repository.bootstrap_organization(
        organization_id="org-a", name="Alpha", portfolio_id="portfolio-a"
    )
    repository.bootstrap_organization(
        organization_id="org-b", name="Beta", portfolio_id="portfolio-b"
    )
    repository.bootstrap_user(
        user_id="user-a", email="a@example.com", organization_id="org-a", role="INSPECTOR"
    )
    repository.bootstrap_user(
        user_id="user-b", email="b@example.com", organization_id="org-b", role="INSPECTOR"
    )
    repository.create_home(
        organization_id="org-a", portfolio_id="portfolio-a", home_id="home-a", name="Alpha Home"
    )
    repository.create_home(
        organization_id="org-b", portfolio_id="portfolio-b", home_id="home-b", name="Beta Home"
    )
    return repository


def test_blank_onboarding_has_no_precreated_rooms(repo: VantageRepository) -> None:
    inspection = repo.start_inspection("org-a", "user-a", "home-a", "onboarding", "client-i")
    assert inspection["rooms"] == []


def test_rooms_persist_to_home_allow_repeated_types_and_are_idempotent(repo: VantageRepository) -> None:
    inspection = repo.start_inspection("org-a", "user-a", "home-a", "onboarding", "client-i")
    room_type = repo.list_room_types("org-a")[0]
    first = repo.create_room(
        "org-a", "user-a", "home-a", inspection["id"], room_type["id"], "Bedroom 1", "room-client-1"
    )
    retried = repo.create_room(
        "org-a", "user-a", "home-a", inspection["id"], room_type["id"], "Bedroom 1", "room-client-1"
    )
    second = repo.create_room(
        "org-a", "user-a", "home-a", inspection["id"], room_type["id"], "Bedroom 2", "room-client-2"
    )
    assert first["id"] == retried["id"]
    assert first["room_type_id"] == second["room_type_id"]
    assert [r["name"] for r in repo.list_rooms("org-a", "home-a")] == ["Bedroom 1", "Bedroom 2"]


def test_asset_is_idempotent_and_only_complete_with_verified_original(repo: VantageRepository) -> None:
    inspection = repo.start_inspection("org-a", "user-a", "home-a", "onboarding", "client-i")
    room = repo.create_room(
        "org-a", "user-a", "home-a", inspection["id"], repo.list_room_types("org-a")[0]["id"],
        "Kitchen", "room-client"
    )
    asset = repo.create_asset(
        "org-a", "user-a", room["id"], inspection["id"], "Appliance", "Refrigerator", "asset-client"
    )
    retried = repo.create_asset(
        "org-a", "user-a", room["id"], inspection["id"], "Appliance", "Refrigerator", "asset-client"
    )
    assert asset["id"] == retried["id"]
    assert asset["completion_status"] == "draft"
    failed = repo.create_photo_upload("org-a", "user-a", "home-a", room["id"], asset["id"], inspection["id"], "photo-failed")
    repo.fail_photo_upload("org-a", failed["id"], "network")
    assert repo.get_asset("org-a", asset["id"])["completion_status"] == "draft"
    original = repo.create_photo_upload("org-a", "user-a", "home-a", room["id"], asset["id"], inspection["id"], "photo-ok")
    repo.complete_photo_upload("org-a", original["id"], "originals/org-a/a.jpg", "a" * 64, 123, "image/jpeg")
    assert repo.get_asset("org-a", asset["id"])["completion_status"] == "complete"


def test_cross_tenant_access_and_relationship_spoofing_are_rejected(repo: VantageRepository) -> None:
    inspection = repo.start_inspection("org-a", "user-a", "home-a", "onboarding", "client-i")
    with pytest.raises(DomainError) as hidden:
        repo.get_inspection("org-b", inspection["id"])
    assert hidden.value.code == "not_found"
    with pytest.raises(DomainError) as forbidden:
        repo.create_room("org-b", "user-b", "home-a", inspection["id"], "anything", "Attack", "attack")
    assert forbidden.value.code == "not_found"


def test_completion_requires_room_and_complete_assets_but_not_optional_metadata(repo: VantageRepository) -> None:
    inspection = repo.start_inspection("org-a", "user-a", "home-a", "onboarding", "client-i")
    with pytest.raises(ConflictError) as empty:
        repo.complete_onboarding("org-a", "user-a", inspection["id"])
    assert empty.value.code == "onboarding_incomplete"
    room = repo.create_room(
        "org-a", "user-a", "home-a", inspection["id"], repo.list_room_types("org-a")[0]["id"],
        "Kitchen", "room-client"
    )
    asset = repo.create_asset("org-a", "user-a", room["id"], inspection["id"], "", "", "asset-client")
    with pytest.raises(ConflictError):
        repo.complete_onboarding("org-a", "user-a", inspection["id"])
    repo.update_asset("org-a", "user-a", asset["id"], asset_type="Appliance", name="Fridge")
    photo = repo.create_photo_upload("org-a", "user-a", "home-a", room["id"], asset["id"], inspection["id"], "photo")
    repo.complete_photo_upload("org-a", photo["id"], "originals/org-a/a.jpg", "b" * 64, 20, "image/jpeg")
    completed = repo.complete_onboarding("org-a", "user-a", inspection["id"])
    assert completed["status"] == "completed"
    assert repo.get_asset("org-a", asset["id"])["manufacturer"] is None


def test_historical_reports_remain_readable(repo: VantageRepository) -> None:
    repo.record_legacy_report("legacy-1", "Old House Keeping", '{"items": [{"checked": true}]}')
    report = repo.get_legacy_report("legacy-1")
    assert report["property"] == "Old House Keeping"


def test_room_with_active_assets_cannot_be_archived_and_asset_move_is_tenant_safe(repo: VantageRepository) -> None:
    inspection = repo.start_inspection("org-a", "user-a", "home-a", "onboarding", "client-i")
    room_type = repo.list_room_types("org-a")[0]["id"]
    source = repo.create_room("org-a", "user-a", "home-a", inspection["id"], room_type, "Source", "source")
    target = repo.create_room("org-a", "user-a", "home-a", inspection["id"], room_type, "Target", "target")
    asset = repo.create_asset("org-a", "user-a", source["id"], inspection["id"], "TV", "TV", "asset")
    with pytest.raises(ConflictError) as active:
        repo.archive_room("org-a", "user-a", source["id"])
    assert active.value.code == "room_has_assets"
    moved = repo.move_asset("org-a", "user-a", asset["id"], target["id"])
    assert moved["room_id"] == target["id"]
    assert repo.archive_room("org-a", "user-a", source["id"])["lifecycle_state"] == "archived"
    with pytest.raises(DomainError):
        repo.move_asset("org-a", "user-a", asset["id"], "home-b")


def test_photo_approval_persists_exact_verified_destination(repo: VantageRepository) -> None:
    inspection = repo.start_inspection("org-a", "user-a", "home-a", "onboarding", "approval-i")
    room = repo.create_room("org-a", "user-a", "home-a", inspection["id"],
                            repo.list_room_types("org-a")[0]["id"], "Kitchen", "approval-room")
    asset = repo.create_asset("org-a", "user-a", room["id"], inspection["id"],
                              "Appliance", "Refrigerator", "approval-asset")
    photo = repo.create_photo_upload("org-a", "user-a", "home-a", room["id"], asset["id"],
                                     inspection["id"], "approval-photo")
    repo.complete_photo_upload("org-a", photo["id"], "originals/org-a/photo.jpg", "c" * 64, 20, "image/jpeg")
    result = repo.associate_approved_evidence(
        "org-a", "user-a", inspection_id=inspection["id"], photo_id=photo["id"],
        item_id="kitchen.refrigerator", asset_id=asset["id"], verdict="PASS",
    )
    assert result["photoId"] == photo["id"] and result["itemId"] == "kitchen.refrigerator"
    with pytest.raises(DomainError) as foreign:
        repo.associate_approved_evidence(
            "org-b", "user-b", inspection_id=inspection["id"], photo_id=photo["id"],
            item_id="kitchen.refrigerator", asset_id=asset["id"], verdict="PASS",
        )
    assert foreign.value.code == "original_not_verified"
