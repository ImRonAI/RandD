from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable
from typing import Any

from .schema import ROOM_TYPES


class DomainError(RuntimeError):
    def __init__(self, code: str, message: str, *, fields: dict[str, str] | None = None, retryable: bool = False):
        super().__init__(message)
        self.code, self.fields, self.retryable = code, fields or {}, retryable


class ConflictError(DomainError):
    pass


class VantageRepository:
    """Small transaction boundary shared by HTTP and agent adapters.

    Every public tenant-owned operation requires an organization ID supplied
    by authenticated server context. Queries intentionally return not_found
    for foreign-tenant identifiers to avoid identifier disclosure.
    """

    def __init__(self, connect: Callable[[], sqlite3.Connection]):
        self._connect = connect

    def _connection(self) -> sqlite3.Connection:
        connection = self._connect()
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _dict(row: sqlite3.Row | None, entity: str = "record") -> dict[str, Any]:
        if row is None:
            raise DomainError("not_found", f"{entity} was not found")
        return dict(row)

    def bootstrap_organization(self, organization_id: str, name: str, portfolio_id: str) -> None:
        with self._connection() as c:
            c.execute("INSERT OR IGNORE INTO organization(id,name) VALUES (?,?)", (organization_id, name))
            c.execute("INSERT OR IGNORE INTO portfolio(organization_id,id,name) VALUES (?,?,?)", (organization_id, portfolio_id, name))
            for index, room_name in enumerate(ROOM_TYPES):
                room_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"vantage:{organization_id}:room-type:{room_name}"))
                c.execute("INSERT OR IGNORE INTO room_type(organization_id,id,name) VALUES (?,?,?)", (organization_id, room_id, room_name))

    def bootstrap_user(self, user_id: str, email: str, organization_id: str, role: str) -> None:
        with self._connection() as c:
            c.execute("INSERT OR IGNORE INTO app_user(id,email) VALUES (?,?)", (user_id, email.lower()))
            c.execute("INSERT OR IGNORE INTO organization_membership(organization_id,user_id,role) VALUES (?,?,?)", (organization_id, user_id, role))

    def create_home(self, organization_id: str, portfolio_id: str, home_id: str, name: str) -> dict[str, Any]:
        with self._connection() as c:
            c.execute("INSERT INTO home(organization_id,id,portfolio_id,name) VALUES (?,?,?,?)", (organization_id, home_id, portfolio_id, name))
            return self._dict(c.execute("SELECT * FROM home WHERE organization_id=? AND id=?", (organization_id, home_id)).fetchone(), "home")

    def _home(self, c: sqlite3.Connection, organization_id: str, home_id: str) -> sqlite3.Row:
        row = c.execute("SELECT * FROM home WHERE organization_id=? AND id=? AND lifecycle_state='active'", (organization_id, home_id)).fetchone()
        if row is None:
            raise DomainError("not_found", "home was not found")
        return row

    def list_room_types(self, organization_id: str) -> list[dict[str, Any]]:
        with self._connection() as c:
            return [dict(r) for r in c.execute("SELECT * FROM room_type WHERE organization_id=? AND active=1 ORDER BY name", (organization_id,))]

    def start_inspection(self, organization_id: str, user_id: str, home_id: str, inspection_type: str, client_id: str) -> dict[str, Any]:
        if inspection_type not in {"onboarding", "turnover"}:
            raise DomainError("invalid_inspection_type", "inspection type must be onboarding or turnover")
        with self._connection() as c:
            self._home(c, organization_id, home_id)
            existing = c.execute("SELECT * FROM inspection WHERE organization_id=? AND created_by=? AND home_id=? AND client_id=?", (organization_id, user_id, home_id, client_id)).fetchone()
            if existing is None:
                inspection_id = str(uuid.uuid4())
                c.execute("INSERT INTO inspection(organization_id,id,home_id,inspection_type,client_id,created_by) VALUES (?,?,?,?,?,?)", (organization_id, inspection_id, home_id, inspection_type, client_id, user_id))
                existing = c.execute("SELECT * FROM inspection WHERE organization_id=? AND id=?", (organization_id, inspection_id)).fetchone()
            result = dict(existing)
            result["rooms"] = self._rooms(c, organization_id, home_id)
            return result

    def get_inspection(self, organization_id: str, inspection_id: str) -> dict[str, Any]:
        with self._connection() as c:
            row = c.execute("SELECT * FROM inspection WHERE organization_id=? AND id=?", (organization_id, inspection_id)).fetchone()
            result = self._dict(row, "inspection")
            result["rooms"] = self._rooms(c, organization_id, result["home_id"])
            return result

    def _rooms(self, c: sqlite3.Connection, organization_id: str, home_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in c.execute("SELECT * FROM room WHERE organization_id=? AND home_id=? AND lifecycle_state='active' ORDER BY display_order,created_at", (organization_id, home_id))]

    def list_rooms(self, organization_id: str, home_id: str) -> list[dict[str, Any]]:
        with self._connection() as c:
            self._home(c, organization_id, home_id)
            return self._rooms(c, organization_id, home_id)

    def get_room(self, organization_id: str, room_id: str) -> dict[str, Any]:
        with self._connection() as c:
            return self._dict(c.execute(
                "SELECT * FROM room WHERE organization_id=? AND id=?",
                (organization_id, room_id),
            ).fetchone(), "room")

    def create_room(self, organization_id: str, user_id: str, home_id: str, inspection_id: str | None, room_type_id: str, name: str, client_id: str) -> dict[str, Any]:
        if not name.strip():
            raise DomainError("validation_error", "room name is required", fields={"name": "required"})
        with self._connection() as c:
            self._home(c, organization_id, home_id)
            if c.execute("SELECT 1 FROM room_type WHERE organization_id=? AND id=? AND active=1", (organization_id, room_type_id)).fetchone() is None:
                raise DomainError("not_found", "room type was not found")
            if inspection_id and c.execute("SELECT 1 FROM inspection WHERE organization_id=? AND id=? AND home_id=?", (organization_id, inspection_id, home_id)).fetchone() is None:
                raise DomainError("not_found", "inspection was not found")
            existing = c.execute("SELECT * FROM room WHERE organization_id=? AND created_by=? AND home_id=? AND client_id=?", (organization_id, user_id, home_id, client_id)).fetchone()
            if existing is None:
                room_id = str(uuid.uuid4())
                c.execute("INSERT INTO room(organization_id,id,home_id,room_type_id,name,created_by,creating_inspection_id,client_id) VALUES (?,?,?,?,?,?,?,?)", (organization_id, room_id, home_id, room_type_id, name.strip(), user_id, inspection_id, client_id))
                if inspection_id:
                    c.execute("INSERT INTO inspection_inventory_link VALUES (?,?,?,?,?)", (organization_id, inspection_id, "room", room_id, "created"))
                existing = c.execute("SELECT * FROM room WHERE organization_id=? AND id=?", (organization_id, room_id)).fetchone()
            return dict(existing)

    def update_room(self, organization_id: str, user_id: str, room_id: str, **changes: Any) -> dict[str, Any]:
        allowed = {"name", "room_type_id", "floor_area", "notes", "display_order"}
        changes = {key: value for key, value in changes.items() if key in allowed}
        if "name" in changes and not str(changes["name"]).strip():
            raise DomainError("validation_error", "room name is required", fields={"name": "required"})
        with self._connection() as c:
            room = c.execute(
                "SELECT * FROM room WHERE organization_id=? AND id=? AND lifecycle_state='active'",
                (organization_id, room_id),
            ).fetchone()
            if room is None:
                raise DomainError("not_found", "room was not found")
            if "room_type_id" in changes and c.execute(
                "SELECT 1 FROM room_type WHERE organization_id=? AND id=? AND active=1",
                (organization_id, changes["room_type_id"]),
            ).fetchone() is None:
                raise DomainError("not_found", "room type was not found")
            if changes:
                values = list(changes.values()) + [organization_id, room_id]
                c.execute(
                    f"UPDATE room SET {','.join(f'{key}=?' for key in changes)}, updated_at=CURRENT_TIMESTAMP "
                    "WHERE organization_id=? AND id=?",
                    values,
                )
            return self._dict(
                c.execute("SELECT * FROM room WHERE organization_id=? AND id=?", (organization_id, room_id)).fetchone(),
                "room",
            )

    def archive_room(self, organization_id: str, user_id: str, room_id: str) -> dict[str, Any]:
        with self._connection() as c:
            room = c.execute(
                "SELECT * FROM room WHERE organization_id=? AND id=? AND lifecycle_state='active'",
                (organization_id, room_id),
            ).fetchone()
            if room is None:
                raise DomainError("not_found", "room was not found")
            active_assets = c.execute(
                "SELECT COUNT(*) FROM asset WHERE organization_id=? AND room_id=? AND lifecycle_state='active'",
                (organization_id, room_id),
            ).fetchone()[0]
            if active_assets:
                raise ConflictError(
                    "room_has_assets",
                    "Move or archive active assets before archiving this room",
                    fields={"activeAssets": str(active_assets)},
                )
            c.execute(
                "UPDATE room SET lifecycle_state='archived',updated_at=CURRENT_TIMESTAMP WHERE organization_id=? AND id=?",
                (organization_id, room_id),
            )
            return self._dict(
                c.execute("SELECT * FROM room WHERE organization_id=? AND id=?", (organization_id, room_id)).fetchone(),
                "room",
            )

    def create_asset(self, organization_id: str, user_id: str, room_id: str, inspection_id: str | None, asset_type: str, name: str, client_id: str) -> dict[str, Any]:
        with self._connection() as c:
            room = c.execute("SELECT * FROM room WHERE organization_id=? AND id=? AND lifecycle_state='active'", (organization_id, room_id)).fetchone()
            if room is None:
                raise DomainError("not_found", "room was not found")
            if inspection_id and c.execute("SELECT 1 FROM inspection WHERE organization_id=? AND id=? AND home_id=?", (organization_id, inspection_id, room["home_id"])).fetchone() is None:
                raise DomainError("not_found", "inspection was not found")
            existing = c.execute("SELECT * FROM asset WHERE organization_id=? AND created_by=? AND room_id=? AND client_id=?", (organization_id, user_id, room_id, client_id)).fetchone()
            if existing is None:
                asset_id = str(uuid.uuid4())
                c.execute("INSERT INTO asset(organization_id,id,home_id,room_id,asset_type,name,created_by,creating_inspection_id,client_id) VALUES (?,?,?,?,?,?,?,?,?)", (organization_id, asset_id, room["home_id"], room_id, asset_type.strip(), name.strip(), user_id, inspection_id, client_id))
                if inspection_id:
                    c.execute("INSERT INTO inspection_inventory_link VALUES (?,?,?,?,?)", (organization_id, inspection_id, "asset", asset_id, "created"))
                existing = c.execute("SELECT * FROM asset WHERE organization_id=? AND id=?", (organization_id, asset_id)).fetchone()
            return dict(existing)

    def get_asset(self, organization_id: str, asset_id: str) -> dict[str, Any]:
        with self._connection() as c:
            return self._dict(c.execute("SELECT * FROM asset WHERE organization_id=? AND id=?", (organization_id, asset_id)).fetchone(), "asset")

    def list_assets(self, organization_id: str, room_id: str) -> list[dict[str, Any]]:
        with self._connection() as c:
            if c.execute(
                "SELECT 1 FROM room WHERE organization_id=? AND id=? AND lifecycle_state='active'",
                (organization_id, room_id),
            ).fetchone() is None:
                raise DomainError("not_found", "room was not found")
            return [dict(row) for row in c.execute(
                "SELECT * FROM asset WHERE organization_id=? AND room_id=? AND lifecycle_state='active' ORDER BY created_at",
                (organization_id, room_id),
            )]

    def move_asset(self, organization_id: str, user_id: str, asset_id: str, target_room_id: str) -> dict[str, Any]:
        with self._connection() as c:
            asset = c.execute(
                "SELECT * FROM asset WHERE organization_id=? AND id=? AND lifecycle_state='active'",
                (organization_id, asset_id),
            ).fetchone()
            if asset is None:
                raise DomainError("not_found", "asset was not found")
            room = c.execute(
                "SELECT * FROM room WHERE organization_id=? AND id=? AND home_id=? AND lifecycle_state='active'",
                (organization_id, target_room_id, asset["home_id"]),
            ).fetchone()
            if room is None:
                raise DomainError("not_found", "target room was not found in this home")
            c.execute(
                "UPDATE asset SET room_id=?,updated_at=CURRENT_TIMESTAMP WHERE organization_id=? AND id=?",
                (target_room_id, organization_id, asset_id),
            )
            return self._dict(
                c.execute("SELECT * FROM asset WHERE organization_id=? AND id=?", (organization_id, asset_id)).fetchone(),
                "asset",
            )

    def update_asset(self, organization_id: str, user_id: str, asset_id: str, **changes: Any) -> dict[str, Any]:
        allowed = {"asset_type", "name", "location_description", "manufacturer", "model_number", "serial_number", "condition", "condition_notes", "notes"}
        changes = {key: value for key, value in changes.items() if key in allowed}
        with self._connection() as c:
            if c.execute("SELECT 1 FROM asset WHERE organization_id=? AND id=?", (organization_id, asset_id)).fetchone() is None:
                raise DomainError("not_found", "asset was not found")
            if changes:
                values = list(changes.values()) + [organization_id, asset_id]
                c.execute(f"UPDATE asset SET {','.join(f'{key}=?' for key in changes)}, updated_at=CURRENT_TIMESTAMP WHERE organization_id=? AND id=?", values)
            self._refresh_asset_completion(c, organization_id, asset_id)
            return self._dict(c.execute("SELECT * FROM asset WHERE organization_id=? AND id=?", (organization_id, asset_id)).fetchone(), "asset")

    def create_photo_upload(self, organization_id: str, user_id: str, home_id: str, room_id: str, asset_id: str, inspection_id: str | None, client_id: str) -> dict[str, Any]:
        with self._connection() as c:
            asset = c.execute("SELECT * FROM asset WHERE organization_id=? AND id=? AND home_id=? AND room_id=?", (organization_id, asset_id, home_id, room_id)).fetchone()
            if asset is None:
                raise DomainError("not_found", "asset was not found")
            existing = c.execute("SELECT * FROM photo WHERE organization_id=? AND uploader_id=? AND client_id=?", (organization_id, user_id, client_id)).fetchone()
            if existing is None:
                photo_id = str(uuid.uuid4())
                c.execute("INSERT INTO photo(organization_id,id,home_id,room_id,asset_id,inspection_id,uploader_id,client_id) VALUES (?,?,?,?,?,?,?,?)", (organization_id, photo_id, home_id, room_id, asset_id, inspection_id, user_id, client_id))
                existing = c.execute("SELECT * FROM photo WHERE organization_id=? AND id=?", (organization_id, photo_id)).fetchone()
            return dict(existing)

    def complete_photo_upload(self, organization_id: str, photo_id: str, object_key: str, sha256: str, byte_size: int, mime_type: str) -> dict[str, Any]:
        if not object_key.startswith(f"originals/{organization_id}/") or len(sha256) != 64 or byte_size <= 0 or not mime_type.startswith("image/"):
            raise DomainError("invalid_original", "original metadata failed verification")
        with self._connection() as c:
            photo = c.execute("SELECT * FROM photo WHERE organization_id=? AND id=?", (organization_id, photo_id)).fetchone()
            if photo is None:
                raise DomainError("not_found", "photo upload was not found")
            c.execute("UPDATE photo SET upload_status='verified',original_object_key=?,sha256=?,byte_size=?,mime_type=?,failure_reason=NULL WHERE organization_id=? AND id=?", (object_key, sha256, byte_size, mime_type, organization_id, photo_id))
            if photo["asset_id"]:
                self._refresh_asset_completion(c, organization_id, photo["asset_id"])
            return self._dict(c.execute("SELECT * FROM photo WHERE organization_id=? AND id=?", (organization_id, photo_id)).fetchone(), "photo")

    def fail_photo_upload(self, organization_id: str, photo_id: str, reason: str) -> None:
        with self._connection() as c:
            photo = c.execute("SELECT * FROM photo WHERE organization_id=? AND id=?", (organization_id, photo_id)).fetchone()
            if photo is None:
                raise DomainError("not_found", "photo upload was not found")
            c.execute("UPDATE photo SET upload_status='failed',failure_reason=? WHERE organization_id=? AND id=?", (reason, organization_id, photo_id))
            if photo["asset_id"]:
                self._refresh_asset_completion(c, organization_id, photo["asset_id"])

    def _refresh_asset_completion(self, c: sqlite3.Connection, organization_id: str, asset_id: str) -> None:
        asset = c.execute("SELECT * FROM asset WHERE organization_id=? AND id=?", (organization_id, asset_id)).fetchone()
        verified = c.execute("SELECT 1 FROM photo WHERE organization_id=? AND asset_id=? AND upload_status='verified' AND purpose='asset_original' LIMIT 1", (organization_id, asset_id)).fetchone()
        complete = bool(asset and asset["asset_type"].strip() and asset["name"].strip() and asset["room_id"] and verified)
        c.execute("UPDATE asset SET completion_status=? WHERE organization_id=? AND id=?", ("complete" if complete else "draft", organization_id, asset_id))

    def complete_onboarding(self, organization_id: str, user_id: str, inspection_id: str) -> dict[str, Any]:
        with self._connection() as c:
            inspection = c.execute("SELECT * FROM inspection WHERE organization_id=? AND id=? AND inspection_type='onboarding'", (organization_id, inspection_id)).fetchone()
            if inspection is None:
                raise DomainError("not_found", "onboarding inspection was not found")
            room_count = c.execute("SELECT COUNT(*) FROM room WHERE organization_id=? AND home_id=? AND lifecycle_state='active'", (organization_id, inspection["home_id"])).fetchone()[0]
            incomplete = c.execute("SELECT COUNT(*) FROM asset WHERE organization_id=? AND home_id=? AND lifecycle_state='active' AND completion_status!='complete'", (organization_id, inspection["home_id"])).fetchone()[0]
            pending = c.execute("SELECT COUNT(*) FROM photo WHERE organization_id=? AND inspection_id=? AND upload_status!='verified'", (organization_id, inspection_id)).fetchone()[0]
            if not room_count or incomplete or pending:
                raise ConflictError("onboarding_incomplete", "Complete required rooms, assets, and original uploads before finishing", fields={"rooms": str(room_count), "incompleteAssets": str(incomplete), "pendingUploads": str(pending)})
            c.execute("UPDATE inspection SET status='completed',completed_at=CURRENT_TIMESTAMP WHERE organization_id=? AND id=?", (organization_id, inspection_id))
            return self._dict(c.execute("SELECT * FROM inspection WHERE organization_id=? AND id=?", (organization_id, inspection_id)).fetchone(), "inspection")

    def associate_approved_evidence(self, organization_id: str, user_id: str, *, inspection_id: str,
                                    photo_id: str, item_id: str | None, asset_id: str | None,
                                    verdict: str | None) -> dict[str, str]:
        """Atomically attach a verified original and its human verdict."""
        if not item_id and not asset_id:
            raise DomainError("approval_destination_required", "An inspection item or asset is required")
        with self._connection() as c:
            photo = c.execute(
                "SELECT * FROM photo WHERE organization_id=? AND id=? AND inspection_id=? AND upload_status='verified'",
                (organization_id, photo_id, inspection_id),
            ).fetchone()
            if photo is None:
                raise DomainError("original_not_verified", "The original photo is not verified for this inspection")
            if asset_id and (photo["asset_id"] != asset_id or c.execute(
                "SELECT 1 FROM asset WHERE organization_id=? AND id=? AND home_id=?",
                (organization_id, asset_id, photo["home_id"]),
            ).fetchone() is None):
                raise DomainError("approval_destination_mismatch", "The asset and original do not belong together")
            approval_id = str(uuid.uuid4())
            c.execute(
                """INSERT INTO evidence_approval(organization_id,id,inspection_id,photo_id,item_id,asset_id,verdict,approved_by)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(organization_id,inspection_id,photo_id,item_id,asset_id) DO UPDATE SET
                     verdict=excluded.verdict,approved_by=excluded.approved_by,approved_at=CURRENT_TIMESTAMP""",
                (organization_id, approval_id, inspection_id, photo_id, item_id, asset_id, verdict, user_id),
            )
            row = c.execute(
                "SELECT id FROM evidence_approval WHERE organization_id=? AND inspection_id=? AND photo_id=? AND item_id IS ? AND asset_id IS ?",
                (organization_id, inspection_id, photo_id, item_id, asset_id),
            ).fetchone()
            return {"approvalId": str(row["id"]), "photoId": photo_id,
                    "inspectionId": inspection_id, "itemId": item_id or "", "assetId": asset_id or ""}

    def record_legacy_report(self, report_id: str, property_name: str, state_json: str) -> None:
        with self._connection() as c:
            c.execute("INSERT OR REPLACE INTO legacy_inspection_report(id,property,state_json) VALUES (?,?,?)", (report_id, property_name, state_json))

    def get_legacy_report(self, report_id: str) -> dict[str, Any]:
        with self._connection() as c:
            return self._dict(c.execute("SELECT * FROM legacy_inspection_report WHERE id=?", (report_id,)).fetchone(), "legacy report")
