from __future__ import annotations

import json
import mimetypes
import re
import sqlite3
import uuid
from collections.abc import Callable
from typing import Any

from .schema import INSPECTION_RESULTS, INSPECTION_TYPES, LEGACY_CHECKLIST_ID_TO_KEY, PHOTO_PURPOSES, ROOM_TYPES


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

    @staticmethod
    def _require_client_id(client_id: str) -> str:
        value = client_id.strip()
        if not value:
            raise DomainError("client_id_required", "client_id is required", fields={"clientId": "required"})
        return value

    @staticmethod
    def _reject_conflicting_replay(existing: sqlite3.Row, expected: dict[str, Any]) -> None:
        conflicts = {
            key: "does not match the original request"
            for key, value in expected.items()
            if existing[key] != value
        }
        if conflicts:
            raise ConflictError(
                "idempotency_payload_conflict",
                "The client_id was already used with a different payload",
                fields=conflicts,
            )

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
        client_id = self._require_client_id(client_id)
        if inspection_type not in INSPECTION_TYPES:
            raise DomainError("invalid_inspection_type", "inspection type must be onboarding or turnover")
        with self._connection() as c:
            self._home(c, organization_id, home_id)
            existing = c.execute("SELECT * FROM inspection WHERE organization_id=? AND created_by=? AND home_id=? AND client_id=?", (organization_id, user_id, home_id, client_id)).fetchone()
            if existing is None:
                inspection_id = str(uuid.uuid4())
                c.execute("INSERT INTO inspection(organization_id,id,home_id,inspection_type,client_id,created_by) VALUES (?,?,?,?,?,?)", (organization_id, inspection_id, home_id, inspection_type, client_id, user_id))
                existing = c.execute("SELECT * FROM inspection WHERE organization_id=? AND id=?", (organization_id, inspection_id)).fetchone()
            else:
                self._reject_conflicting_replay(existing, {"inspection_type": inspection_type})
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
        return [dict(r) for r in c.execute("SELECT * FROM room WHERE organization_id=? AND home_id=? AND lifecycle_state='active' ORDER BY display_order,created_at,rowid", (organization_id, home_id))]

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
        client_id = self._require_client_id(client_id)
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
                    c.execute(
                        """INSERT INTO inspection_inventory_link(
                             organization_id,inspection_id,home_id,entity_type,entity_id,room_id,action)
                           VALUES (?,?,?,?,?,?,?)""",
                        (organization_id, inspection_id, home_id, "room", room_id, room_id, "created"),
                    )
                existing = c.execute("SELECT * FROM room WHERE organization_id=? AND id=?", (organization_id, room_id)).fetchone()
            else:
                self._reject_conflicting_replay(existing, {
                    "creating_inspection_id": inspection_id,
                    "room_type_id": room_type_id,
                    "name": name.strip(),
                })
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
        client_id = self._require_client_id(client_id)
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
                    c.execute(
                        """INSERT INTO inspection_inventory_link(
                             organization_id,inspection_id,home_id,entity_type,entity_id,asset_id,action)
                           VALUES (?,?,?,?,?,?,?)""",
                        (organization_id, inspection_id, room["home_id"], "asset", asset_id, asset_id, "created"),
                    )
                existing = c.execute("SELECT * FROM asset WHERE organization_id=? AND id=?", (organization_id, asset_id)).fetchone()
            else:
                self._reject_conflicting_replay(existing, {
                    "creating_inspection_id": inspection_id,
                    "asset_type": asset_type.strip(),
                    "name": name.strip(),
                })
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

    def create_photo_upload(self, organization_id: str, user_id: str, home_id: str, room_id: str,
                            asset_id: str, inspection_id: str | None, client_id: str,
                            purpose: str = "asset_original") -> dict[str, Any]:
        client_id = self._require_client_id(client_id)
        if purpose not in PHOTO_PURPOSES:
            raise DomainError("invalid_photo_purpose", "photo purpose is not supported")
        with self._connection() as c:
            asset = c.execute("SELECT * FROM asset WHERE organization_id=? AND id=? AND home_id=? AND room_id=?", (organization_id, asset_id, home_id, room_id)).fetchone()
            if asset is None:
                raise DomainError("not_found", "asset was not found")
            if inspection_id and c.execute(
                "SELECT 1 FROM inspection WHERE organization_id=? AND id=? AND home_id=?",
                (organization_id, inspection_id, home_id),
            ).fetchone() is None:
                raise DomainError("not_found", "inspection was not found")
            existing = c.execute("SELECT * FROM photo WHERE organization_id=? AND uploader_id=? AND client_id=?", (organization_id, user_id, client_id)).fetchone()
            if existing is None:
                photo_id = str(uuid.uuid4())
                c.execute("INSERT INTO photo(organization_id,id,home_id,room_id,asset_id,inspection_id,uploader_id,client_id,purpose) VALUES (?,?,?,?,?,?,?,?,?)", (organization_id, photo_id, home_id, room_id, asset_id, inspection_id, user_id, client_id, purpose))
                existing = c.execute("SELECT * FROM photo WHERE organization_id=? AND id=?", (organization_id, photo_id)).fetchone()
            else:
                self._reject_conflicting_replay(existing, {
                    "home_id": home_id,
                    "room_id": room_id,
                    "asset_id": asset_id,
                    "inspection_id": inspection_id,
                    "purpose": purpose,
                })
            return dict(existing)

    def initiate_original_upload(
        self, organization_id: str, user_id: str, *, home_id: str, room_id: str,
        asset_id: str, inspection_id: str | None, client_id: str, storage_bucket: str,
        filename: str, mime_type: str, byte_size: int, sha256: str,
        purpose: str = "asset_original",
    ) -> dict[str, Any]:
        """Atomically create one PENDING photo and its server-owned upload capability."""
        client_id = self._require_client_id(client_id)
        normalized_mime = mime_type.split(";", 1)[0].strip().lower()
        normalized_sha = sha256.strip().lower()
        if (purpose not in PHOTO_PURPOSES
                or normalized_mime not in {"image/jpeg", "image/png", "image/heic", "image/heif"}
                or byte_size < 1 or byte_size > 50 * 1024 * 1024
                or not re.fullmatch(r"[0-9a-f]{64}", normalized_sha)
                or not storage_bucket.strip()):
            raise DomainError("invalid_original_declaration", "Original upload constraints are invalid")
        suffix = __import__("pathlib").Path(filename).suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix or ""):
            suffix = mimetypes.guess_extension(normalized_mime) or ".bin"
        with self._connection() as c:
            asset = c.execute(
                """SELECT * FROM asset WHERE organization_id=? AND id=? AND home_id=?
                   AND room_id=? AND lifecycle_state='active'""",
                (organization_id, asset_id, home_id, room_id),
            ).fetchone()
            if asset is None:
                raise DomainError("not_found", "asset was not found")
            if inspection_id and c.execute(
                "SELECT 1 FROM inspection WHERE organization_id=? AND id=? AND home_id=?",
                (organization_id, inspection_id, home_id),
            ).fetchone() is None:
                raise DomainError("not_found", "inspection was not found")
            photo = c.execute(
                "SELECT * FROM photo WHERE organization_id=? AND uploader_id=? AND client_id=?",
                (organization_id, user_id, client_id),
            ).fetchone()
            if photo is not None:
                upload = c.execute(
                    "SELECT * FROM original_upload WHERE organization_id=? AND photo_id=?",
                    (organization_id, photo["id"]),
                ).fetchone()
                if upload is None:
                    raise ConflictError("upload_state_conflict", "Photo exists without its upload capability")
                self._reject_conflicting_replay(photo, {
                    "home_id": home_id, "room_id": room_id, "asset_id": asset_id,
                    "inspection_id": inspection_id, "purpose": purpose,
                })
                self._reject_conflicting_replay(upload, {
                    "storage_bucket": storage_bucket, "expected_byte_size": byte_size,
                    "expected_sha256": normalized_sha, "expected_mime_type": normalized_mime,
                })
                return {**dict(upload), "photo_id": photo["id"], "upload_id": upload["id"]}
            photo_id, upload_id = str(uuid.uuid4()), str(uuid.uuid4())
            object_key = f"{organization_id}/{home_id}/originals/{photo_id}{suffix}"
            c.execute(
                """INSERT INTO photo(
                     organization_id,id,home_id,room_id,asset_id,inspection_id,uploader_id,
                     client_id,purpose,upload_status,original_object_key)
                   VALUES (?,?,?,?,?,?,?,?,?,'pending',?)""",
                (organization_id, photo_id, home_id, room_id, asset_id, inspection_id,
                 user_id, client_id, purpose, object_key),
            )
            c.execute(
                """INSERT INTO original_upload(
                     organization_id,id,home_id,photo_id,storage_bucket,object_key,
                     expected_byte_size,expected_sha256,expected_mime_type)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (organization_id, upload_id, home_id, photo_id, storage_bucket, object_key,
                 byte_size, normalized_sha, normalized_mime),
            )
            return dict(c.execute(
                "SELECT *,id AS upload_id FROM original_upload WHERE organization_id=? AND id=?",
                (organization_id, upload_id),
            ).fetchone())

    def get_original_upload(self, organization_id: str, upload_id: str) -> dict[str, Any]:
        with self._connection() as c:
            return self._dict(c.execute(
                """SELECT u.*,u.id AS upload_id,p.room_id,p.asset_id,p.inspection_id,p.uploader_id,
                          p.upload_status AS photo_status
                     FROM original_upload u JOIN photo p
                       ON p.organization_id=u.organization_id AND p.id=u.photo_id
                    WHERE u.organization_id=? AND u.id=?""",
                (organization_id, upload_id),
            ).fetchone(), "original upload")

    def record_original_upload_failure(self, organization_id: str, upload_id: str, error_code: str) -> None:
        with self._connection() as c:
            upload = c.execute(
                """SELECT u.*,p.asset_id
                     FROM original_upload u JOIN photo p
                       ON p.organization_id=u.organization_id AND p.id=u.photo_id
                    WHERE u.organization_id=? AND u.id=?""",
                (organization_id, upload_id),
            ).fetchone()
            if upload is None:
                raise DomainError("not_found", "original upload was not found")
            if upload["status"] != "verified":
                c.execute(
                    """UPDATE original_upload
                          SET status='failed',verification_attempts=verification_attempts+1,
                              last_error_code=?,updated_at=CURRENT_TIMESTAMP
                        WHERE organization_id=? AND id=? AND status IN ('pending','failed')""",
                    (error_code, organization_id, upload_id),
                )
                c.execute(
                    """UPDATE photo SET upload_status='failed',failure_reason=?
                        WHERE organization_id=? AND id=? AND upload_status IN ('pending','failed')""",
                    (error_code, organization_id, upload["photo_id"]),
                )
                if upload["asset_id"]:
                    self._refresh_asset_completion(c, organization_id, upload["asset_id"])

    def complete_photo_upload(self, organization_id: str, photo_id: str, object_key: str, sha256: str, byte_size: int, mime_type: str) -> dict[str, Any]:
        del organization_id, photo_id, object_key, sha256, byte_size, mime_type
        raise DomainError(
            "server_verification_required",
            "Only the trusted storage finalizer can mark an original as verified",
        )

    def _finalize_original_from_storage(self, organization_id: str, upload_id: str,
                                        facts: dict[str, Any]) -> dict[str, Any]:
        """Persist trusted immutable storage facts; callers must be the finalizer service."""
        with self._connection() as c:
            upload = c.execute(
                "SELECT * FROM original_upload WHERE organization_id=? AND id=?",
                (organization_id, upload_id),
            ).fetchone()
            if upload is None:
                raise DomainError("not_found", "original upload was not found")
            expected = {
                "storage_bucket": upload["storage_bucket"], "object_key": upload["object_key"],
                "byte_size": upload["expected_byte_size"], "sha256": upload["expected_sha256"],
                "mime_type": upload["expected_mime_type"],
            }
            for key, value in expected.items():
                if facts.get(key) != value:
                    raise ConflictError("storage_verification_conflict", f"Stored original {key} does not match")
            required = ("storage_version_id", "encryption_algorithm", "kms_key_id", "object_lock_mode", "retention_until")
            if any(not facts.get(key) for key in required):
                raise DomainError("storage_retention_unverified", "Immutable storage facts are incomplete")
            if facts["encryption_algorithm"] != "aws:kms" or facts["object_lock_mode"] != "COMPLIANCE":
                raise DomainError("storage_retention_unverified", "Immutable storage facts are incomplete")
            if upload["status"] == "verified":
                self._reject_conflicting_replay(upload, {
                    "storage_version_id": facts["storage_version_id"],
                    "etag": facts.get("etag"), "encryption_algorithm": facts["encryption_algorithm"],
                    "kms_key_id": facts.get("kms_key_id"), "object_lock_mode": facts["object_lock_mode"],
                    "retention_until": facts["retention_until"],
                    "legal_hold_status": facts.get("legal_hold_status"),
                })
            else:
                c.execute(
                    """UPDATE original_upload SET status='verified',storage_version_id=?,etag=?,
                         encryption_algorithm=?,kms_key_id=?,object_lock_mode=?,retention_until=?,
                         legal_hold_status=?,verification_attempts=verification_attempts+1,
                         last_error_code=NULL,verified_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                       WHERE organization_id=? AND id=? AND status IN ('pending','failed')""",
                    (facts["storage_version_id"], facts.get("etag"), facts["encryption_algorithm"],
                     facts.get("kms_key_id"), facts["object_lock_mode"], facts["retention_until"],
                     facts.get("legal_hold_status"), organization_id, upload_id),
                )
                if c.execute("SELECT changes()").fetchone()[0] != 1:
                    raise ConflictError("upload_state_conflict", "Original upload cannot be finalized")
                c.execute(
                    """UPDATE photo SET upload_status='verified',sha256=?,byte_size=?,mime_type=?,
                         failure_reason=NULL WHERE organization_id=? AND id=? AND upload_status IN ('pending','failed')""",
                    (facts["sha256"], facts["byte_size"], facts["mime_type"],
                     organization_id, upload["photo_id"]),
                )
                photo = c.execute(
                    "SELECT * FROM photo WHERE organization_id=? AND id=?",
                    (organization_id, upload["photo_id"]),
                ).fetchone()
                if photo and photo["asset_id"]:
                    self._refresh_asset_completion(c, organization_id, photo["asset_id"])
            return dict(c.execute(
                """SELECT u.*,u.id AS upload_id,p.room_id,p.asset_id,p.inspection_id,p.uploader_id,
                          p.upload_status AS photo_status
                     FROM original_upload u JOIN photo p
                       ON p.organization_id=u.organization_id AND p.id=u.photo_id
                    WHERE u.organization_id=? AND u.id=?""",
                (organization_id, upload_id),
            ).fetchone())

    def record_inspection_item_result(self, organization_id: str, user_id: str, *, inspection_id: str,
                                      item_key: str, result: str, note: str, client_id: str) -> dict[str, Any]:
        """Append a normalized checklist result revision; exact client replays are safe."""
        client_id = self._require_client_id(client_id)
        result = result.strip().upper()
        if result not in INSPECTION_RESULTS:
            raise DomainError("invalid_inspection_result", "result must be PASS, FAIL, or NA")
        with self._connection() as c:
            inspection = c.execute(
                "SELECT * FROM inspection WHERE organization_id=? AND id=?",
                (organization_id, inspection_id),
            ).fetchone()
            if inspection is None:
                raise DomainError("not_found", "inspection was not found")
            if c.execute("SELECT 1 FROM checklist_item WHERE item_key=? AND active=1", (item_key,)).fetchone() is None:
                raise DomainError("invalid_checklist_item", "checklist item key is not supported")
            existing = c.execute(
                "SELECT * FROM inspection_item_result WHERE organization_id=? AND recorded_by=? AND inspection_id=? AND client_id=?",
                (organization_id, user_id, inspection_id, client_id),
            ).fetchone()
            if existing is not None:
                self._reject_conflicting_replay(existing, {"item_key": item_key, "result": result, "note": note})
                return dict(existing)
            previous = c.execute(
                "SELECT * FROM inspection_item_result WHERE organization_id=? AND inspection_id=? AND item_key=? ORDER BY version DESC LIMIT 1",
                (organization_id, inspection_id, item_key),
            ).fetchone()
            result_id = str(uuid.uuid4())
            version = int(previous["version"]) + 1 if previous else 1
            c.execute(
                """INSERT INTO inspection_item_result(
                     organization_id,id,home_id,inspection_id,item_key,result,note,version,
                     supersedes_result_id,recorded_by,client_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (organization_id, result_id, inspection["home_id"], inspection_id, item_key, result,
                 note, version, previous["id"] if previous else None, user_id, client_id),
            )
            return self._dict(c.execute(
                "SELECT * FROM inspection_item_result WHERE organization_id=? AND id=?",
                (organization_id, result_id),
            ).fetchone(), "inspection item result")

    def attach_result_photo(self, organization_id: str, *, result_id: str, photo_id: str,
                            display_order: int = 0) -> dict[str, Any]:
        """Attach one of multiple verified originals without weakening org/home/inspection scope."""
        with self._connection() as c:
            result = c.execute(
                "SELECT * FROM inspection_item_result WHERE organization_id=? AND id=?",
                (organization_id, result_id),
            ).fetchone()
            if result is None:
                raise DomainError("not_found", "inspection item result was not found")
            photo = c.execute(
                """SELECT * FROM photo WHERE organization_id=? AND id=? AND home_id=?
                   AND inspection_id=? AND upload_status='verified'""",
                (organization_id, photo_id, result["home_id"], result["inspection_id"]),
            ).fetchone()
            if photo is None:
                raise DomainError("result_photo_mismatch", "photo is not verified for this inspection")
            existing = c.execute(
                "SELECT * FROM result_photo WHERE organization_id=? AND result_id=? AND photo_id=?",
                (organization_id, result_id, photo_id),
            ).fetchone()
            if existing is not None:
                if existing["display_order"] != display_order:
                    raise ConflictError("idempotency_payload_conflict", "photo is already attached at another display_order")
                return dict(existing)
            try:
                c.execute(
                    "INSERT INTO result_photo(organization_id,home_id,inspection_id,result_id,photo_id,display_order) VALUES (?,?,?,?,?,?)",
                    (organization_id, result["home_id"], result["inspection_id"], result_id, photo_id, display_order),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("result_photo_order_conflict", "display_order is already used for this result") from exc
            return self._dict(c.execute(
                "SELECT * FROM result_photo WHERE organization_id=? AND result_id=? AND photo_id=?",
                (organization_id, result_id, photo_id),
            ).fetchone(), "result photo")

    def inspection_result_history(self, organization_id: str, inspection_id: str, item_key: str) -> list[dict[str, Any]]:
        with self._connection() as c:
            if c.execute("SELECT 1 FROM inspection WHERE organization_id=? AND id=?", (organization_id, inspection_id)).fetchone() is None:
                raise DomainError("not_found", "inspection was not found")
            return [dict(row) for row in c.execute(
                "SELECT * FROM inspection_item_result WHERE organization_id=? AND inspection_id=? AND item_key=? ORDER BY version",
                (organization_id, inspection_id, item_key),
            )]

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
                                    photo_id: str, item_id: str | None, result_id: str | None,
                                    asset_id: str | None,
                                    verdict: str | None) -> dict[str, str]:
        """Atomically attach a verified original and its human verdict."""
        if not item_id and not asset_id:
            raise DomainError("approval_destination_required", "An inspection item or asset is required")
        if verdict is not None and verdict not in {*INSPECTION_RESULTS, "REVIEW"}:
            raise DomainError("invalid_approval_verdict", "verdict must be PASS, FAIL, NA, or REVIEW")
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
            if item_id:
                if not result_id:
                    raise DomainError("approval_result_required", "The exact checklist result revision is required")
                item_result = c.execute(
                    """SELECT * FROM inspection_item_result WHERE organization_id=? AND inspection_id=?
                       AND item_key=? AND id=?""",
                    (organization_id, inspection_id, item_id, result_id),
                ).fetchone()
                if item_result is None:
                    raise DomainError("approval_result_mismatch", "The checklist result revision does not match the approval")
            elif result_id:
                raise DomainError("approval_item_required", "item_id is required when result_id is supplied")
            row = c.execute(
                """SELECT id FROM evidence_approval WHERE organization_id=? AND inspection_id=?
                   AND photo_id=? AND result_id IS ? AND asset_id IS ?""",
                (organization_id, inspection_id, photo_id, result_id, asset_id),
            ).fetchone()
            if row is None:
                approval_id = str(uuid.uuid4())
                c.execute(
                    """INSERT INTO evidence_approval(
                         organization_id,id,home_id,inspection_id,photo_id,item_id,result_id,
                         asset_id,verdict,approved_by) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (organization_id, approval_id, photo["home_id"], inspection_id, photo_id,
                     item_id, result_id, asset_id, verdict, user_id),
                )
                row = c.execute(
                    "SELECT id FROM evidence_approval WHERE organization_id=? AND id=?",
                    (organization_id, approval_id),
                ).fetchone()
            else:
                c.execute(
                    """UPDATE evidence_approval SET verdict=?,approved_by=?,approved_at=CURRENT_TIMESTAMP
                       WHERE organization_id=? AND id=?""",
                    (verdict, user_id, organization_id, row["id"]),
                )
            return {"approvalId": str(row["id"]), "photoId": photo_id,
                    "inspectionId": inspection_id, "itemId": item_id or "", "assetId": asset_id or ""}

    def record_legacy_report(self, organization_id: str, report_id: str,
                             property_name: str, state_json: str) -> None:
        with self._connection() as c:
            c.execute(
                """INSERT OR REPLACE INTO legacy_inspection_report(
                     organization_id,id,property,state_json) VALUES (?,?,?,?)""",
                (organization_id, report_id, property_name, state_json),
            )

    def get_legacy_report(self, organization_id: str, report_id: str) -> dict[str, Any]:
        with self._connection() as c:
            report = self._dict(c.execute(
                "SELECT * FROM legacy_inspection_report WHERE organization_id=? AND id=?",
                (organization_id, report_id),
            ).fetchone(), "legacy report")
            state = json.loads(report["state_json"])
            # Historical reports stored only `checked`; it is not equivalent to
            # PASS/FAIL/NA. Route by stable item id because exported labels can
            # contain photo/note decorations. Never synthesize Room inventory.
            report["legacy_item_states"] = [
                {
                    "itemKey": LEGACY_CHECKLIST_ID_TO_KEY.get(str(item.get("id", ""))),
                    "legacyItemId": item.get("id"),
                    "checked": bool(item.get("checked")),
                }
                for item in state.get("items", [])
            ]
            return report
