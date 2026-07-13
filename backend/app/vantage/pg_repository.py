"""PostgreSQL repository bound to one caller-owned transaction."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg import sql

from .domain import ConflictError, DomainError
from .schema import INSPECTION_TYPES, PHOTO_PURPOSES


def _value(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date, Decimal)):
        return value
    return value


def _dict(row: dict[str, Any] | None, entity: str = "record") -> dict[str, Any]:
    if row is None:
        raise DomainError("not_found", f"{entity} was not found")
    return {key: _value(value) for key, value in row.items()}


class PostgresVantageRepository:
    """No pool, connection checkout, transaction, or commit is hidden here."""

    def __init__(self, connection: psycopg.Connection):
        self.connection = connection

    def _one(self, query: str, params: tuple[Any, ...], entity: str = "record") -> dict[str, Any]:
        return _dict(self.connection.execute(query, params).fetchone(), entity)

    @staticmethod
    def _client_id(client_id: str) -> str:
        value = client_id.strip()
        if not value:
            raise DomainError("client_id_required", "client_id is required", fields={"clientId": "required"})
        return value

    @staticmethod
    def _replay(existing: dict[str, Any], expected: dict[str, Any]) -> None:
        conflicts = {key: "does not match the original request" for key, value in expected.items()
                     if _value(existing.get(key)) != value}
        if conflicts:
            raise ConflictError("idempotency_payload_conflict", "The client_id was already used with a different payload", fields=conflicts)

    def bootstrap_organization(self, organization_id: str, name: str, portfolio_id: str) -> None:
        self.connection.execute("INSERT INTO organization(id,name) VALUES (%s,%s) ON CONFLICT (id) DO NOTHING", (organization_id, name))
        self.connection.execute("INSERT INTO portfolio(organization_id,id,name) VALUES (%s,%s,%s) ON CONFLICT (organization_id,id) DO NOTHING", (organization_id, portfolio_id, name))

    def bootstrap_user(self, user_id: str, email: str, organization_id: str, role: str) -> None:
        self.connection.execute("INSERT INTO app_user(id,email) VALUES (%s,%s) ON CONFLICT (id) DO NOTHING", (user_id, email.lower()))
        self.connection.execute("INSERT INTO organization_membership(organization_id,user_id,role) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (organization_id, user_id, role))

    def create_home(self, organization_id: str, portfolio_id: str, home_id: str, name: str) -> dict[str, Any]:
        return self._one("INSERT INTO home(organization_id,id,portfolio_id,name) VALUES (%s,%s,%s,%s) RETURNING *", (organization_id, home_id, portfolio_id, name), "home")

    def _home(self, organization_id: str, home_id: str) -> dict[str, Any]:
        return self._one("SELECT * FROM home WHERE organization_id=%s AND id=%s AND lifecycle_state='active'", (organization_id, home_id), "home")

    def list_room_types(self, organization_id: str) -> list[dict[str, Any]]:
        return [_dict(row) for row in self.connection.execute("SELECT * FROM room_type WHERE organization_id=%s AND active ORDER BY display_order,name", (organization_id,)).fetchall()]

    def start_inspection(self, organization_id: str, user_id: str, home_id: str, inspection_type: str, client_id: str) -> dict[str, Any]:
        client_id = self._client_id(client_id)
        if inspection_type not in INSPECTION_TYPES:
            raise DomainError("invalid_inspection_type", "inspection type must be onboarding or turnover")
        self._home(organization_id, home_id)
        existing = self.connection.execute("SELECT * FROM inspection WHERE organization_id=%s AND created_by=%s AND home_id=%s AND client_id=%s", (organization_id, user_id, home_id, client_id)).fetchone()
        if existing is None:
            existing = self.connection.execute("INSERT INTO inspection(organization_id,home_id,inspection_type,client_id,created_by) VALUES (%s,%s,%s,%s,%s) RETURNING *", (organization_id, home_id, inspection_type, client_id, user_id)).fetchone()
        else:
            self._replay(existing, {"inspection_type": inspection_type})
        result = _dict(existing)
        result["rooms"] = self._rooms(organization_id, home_id)
        return result

    def get_inspection(self, organization_id: str, inspection_id: str) -> dict[str, Any]:
        result = self._one("SELECT * FROM inspection WHERE organization_id=%s AND id=%s", (organization_id, inspection_id), "inspection")
        result["rooms"] = self._rooms(organization_id, str(result["home_id"]))
        return result

    def _rooms(self, organization_id: str, home_id: str) -> list[dict[str, Any]]:
        return [_dict(row) for row in self.connection.execute("SELECT * FROM room WHERE organization_id=%s AND home_id=%s AND lifecycle_state='active' ORDER BY display_order,created_at,id", (organization_id, home_id)).fetchall()]

    def list_rooms(self, organization_id: str, home_id: str) -> list[dict[str, Any]]:
        self._home(organization_id, home_id)
        return self._rooms(organization_id, home_id)

    def get_room(self, organization_id: str, room_id: str) -> dict[str, Any]:
        return self._one("SELECT * FROM room WHERE organization_id=%s AND id=%s", (organization_id, room_id), "room")

    def create_room(self, organization_id: str, user_id: str, home_id: str, inspection_id: str | None, room_type_id: str, name: str, client_id: str) -> dict[str, Any]:
        client_id = self._client_id(client_id)
        name = name.strip()
        if not name:
            raise DomainError("validation_error", "room name is required", fields={"name": "required"})
        self._home(organization_id, home_id)
        if self.connection.execute("SELECT 1 FROM room_type WHERE organization_id=%s AND id=%s AND active", (organization_id, room_type_id)).fetchone() is None:
            raise DomainError("not_found", "room type was not found")
        if inspection_id and self.connection.execute("SELECT 1 FROM inspection WHERE organization_id=%s AND id=%s AND home_id=%s", (organization_id, inspection_id, home_id)).fetchone() is None:
            raise DomainError("not_found", "inspection was not found")
        existing = self.connection.execute("SELECT * FROM room WHERE organization_id=%s AND created_by=%s AND home_id=%s AND client_id=%s", (organization_id, user_id, home_id, client_id)).fetchone()
        if existing is None:
            existing = self.connection.execute("INSERT INTO room(organization_id,home_id,room_type_id,name,created_by,creating_inspection_id,client_id) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *", (organization_id, home_id, room_type_id, name, user_id, inspection_id, client_id)).fetchone()
            if inspection_id:
                self.connection.execute("INSERT INTO inspection_inventory_link(organization_id,inspection_id,home_id,entity_type,entity_id,room_id,action) VALUES (%s,%s,%s,'room',%s,%s,'created')", (organization_id, inspection_id, home_id, existing["id"], existing["id"]))
        else:
            self._replay(existing, {"creating_inspection_id": inspection_id, "room_type_id": room_type_id, "name": name})
        return _dict(existing)

    def update_room(self, organization_id: str, user_id: str, room_id: str, **changes: Any) -> dict[str, Any]:
        del user_id
        allowed = {"name", "room_type_id", "floor_area", "notes", "display_order"}
        changes = {key: value for key, value in changes.items() if key in allowed}
        if "name" in changes and not str(changes["name"]).strip():
            raise DomainError("validation_error", "room name is required", fields={"name": "required"})
        self._one("SELECT * FROM room WHERE organization_id=%s AND id=%s AND lifecycle_state='active' FOR UPDATE", (organization_id, room_id), "room")
        if changes:
            assignments = sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(key)) for key in changes)
            self.connection.execute(sql.SQL("UPDATE room SET {},updated_at=now() WHERE organization_id=%s AND id=%s").format(assignments), (*changes.values(), organization_id, room_id))
        return self.get_room(organization_id, room_id)

    def archive_room(self, organization_id: str, user_id: str, room_id: str) -> dict[str, Any]:
        del user_id
        self._one("SELECT * FROM room WHERE organization_id=%s AND id=%s AND lifecycle_state='active' FOR UPDATE", (organization_id, room_id), "room")
        count = self.connection.execute("SELECT count(*) AS n FROM asset WHERE organization_id=%s AND room_id=%s AND lifecycle_state='active'", (organization_id, room_id)).fetchone()["n"]
        if count:
            raise ConflictError("room_has_assets", "Move or archive active assets before archiving this room", fields={"activeAssets": str(count)})
        self.connection.execute("UPDATE room SET lifecycle_state='archived',updated_at=now() WHERE organization_id=%s AND id=%s", (organization_id, room_id))
        return self.get_room(organization_id, room_id)

    def create_asset(self, organization_id: str, user_id: str, room_id: str, inspection_id: str | None, asset_type: str, name: str, client_id: str) -> dict[str, Any]:
        client_id = self._client_id(client_id)
        room = self._one("SELECT * FROM room WHERE organization_id=%s AND id=%s AND lifecycle_state='active'", (organization_id, room_id), "room")
        if inspection_id and self.connection.execute("SELECT 1 FROM inspection WHERE organization_id=%s AND id=%s AND home_id=%s", (organization_id, inspection_id, room["home_id"])).fetchone() is None:
            raise DomainError("not_found", "inspection was not found")
        existing = self.connection.execute("SELECT * FROM asset WHERE organization_id=%s AND created_by=%s AND room_id=%s AND client_id=%s", (organization_id, user_id, room_id, client_id)).fetchone()
        if existing is None:
            existing = self.connection.execute("INSERT INTO asset(organization_id,home_id,room_id,asset_type,name,created_by,creating_inspection_id,client_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *", (organization_id, room["home_id"], room_id, asset_type.strip(), name.strip(), user_id, inspection_id, client_id)).fetchone()
            if inspection_id:
                self.connection.execute("INSERT INTO inspection_inventory_link(organization_id,inspection_id,home_id,entity_type,entity_id,asset_id,action) VALUES (%s,%s,%s,'asset',%s,%s,'created')", (organization_id, inspection_id, room["home_id"], existing["id"], existing["id"]))
        else:
            self._replay(existing, {"creating_inspection_id": inspection_id, "asset_type": asset_type.strip(), "name": name.strip()})
        return _dict(existing)

    def get_asset(self, organization_id: str, asset_id: str) -> dict[str, Any]:
        return self._one("SELECT * FROM asset WHERE organization_id=%s AND id=%s", (organization_id, asset_id), "asset")

    def list_assets(self, organization_id: str, room_id: str) -> list[dict[str, Any]]:
        self._one("SELECT * FROM room WHERE organization_id=%s AND id=%s AND lifecycle_state='active'", (organization_id, room_id), "room")
        return [_dict(row) for row in self.connection.execute("SELECT * FROM asset WHERE organization_id=%s AND room_id=%s AND lifecycle_state='active' ORDER BY created_at", (organization_id, room_id)).fetchall()]

    def move_asset(self, organization_id: str, user_id: str, asset_id: str, target_room_id: str) -> dict[str, Any]:
        del user_id
        asset = self._one("SELECT * FROM asset WHERE organization_id=%s AND id=%s AND lifecycle_state='active' FOR UPDATE", (organization_id, asset_id), "asset")
        self._one("SELECT * FROM room WHERE organization_id=%s AND id=%s AND home_id=%s AND lifecycle_state='active'", (organization_id, target_room_id, asset["home_id"]), "target room")
        self.connection.execute("UPDATE asset SET room_id=%s,updated_at=now() WHERE organization_id=%s AND id=%s", (target_room_id, organization_id, asset_id))
        return self.get_asset(organization_id, asset_id)

    def update_asset(self, organization_id: str, user_id: str, asset_id: str, **changes: Any) -> dict[str, Any]:
        del user_id
        allowed = {"asset_type", "name", "location_description", "manufacturer", "model_number", "serial_number", "condition", "condition_notes", "notes"}
        changes = {key: value for key, value in changes.items() if key in allowed}
        self._one("SELECT * FROM asset WHERE organization_id=%s AND id=%s FOR UPDATE", (organization_id, asset_id), "asset")
        if changes:
            assignments = sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(key)) for key in changes)
            self.connection.execute(sql.SQL("UPDATE asset SET {},updated_at=now() WHERE organization_id=%s AND id=%s").format(assignments), (*changes.values(), organization_id, asset_id))
        self._refresh_asset_completion(organization_id, asset_id)
        return self.get_asset(organization_id, asset_id)

    def create_photo_upload(self, organization_id: str, user_id: str, home_id: str, room_id: str, asset_id: str, inspection_id: str | None, client_id: str, purpose: str = "asset_original") -> dict[str, Any]:
        client_id = self._client_id(client_id)
        if purpose not in PHOTO_PURPOSES:
            raise DomainError("invalid_photo_purpose", "photo purpose is not supported")
        self._one("SELECT * FROM asset WHERE organization_id=%s AND id=%s AND home_id=%s AND room_id=%s", (organization_id, asset_id, home_id, room_id), "asset")
        existing = self.connection.execute("SELECT * FROM photo WHERE organization_id=%s AND uploader_id=%s AND client_id=%s", (organization_id, user_id, client_id)).fetchone()
        if existing is None:
            existing = self.connection.execute("INSERT INTO photo(organization_id,home_id,room_id,asset_id,inspection_id,uploader_id,client_id,purpose) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *", (organization_id, home_id, room_id, asset_id, inspection_id, user_id, client_id, purpose)).fetchone()
        else:
            self._replay(existing, {"home_id": home_id, "room_id": room_id, "asset_id": asset_id, "inspection_id": inspection_id, "purpose": purpose})
        return _dict(existing)

    def complete_photo_upload(self, organization_id: str, photo_id: str, object_key: str, sha256: str, byte_size: int, mime_type: str) -> dict[str, Any]:
        photo = self._one("SELECT * FROM photo WHERE organization_id=%s AND id=%s FOR UPDATE", (organization_id, photo_id), "photo upload")
        pattern = rf"^{re.escape(organization_id)}/{re.escape(str(photo['home_id']))}/originals/[0-9a-fA-F-]{{36}}\.[A-Za-z0-9]+$"
        if not re.fullmatch(pattern, object_key) or not re.fullmatch(r"[0-9a-fA-F]{64}", sha256) or byte_size <= 0 or not mime_type.startswith("image/"):
            raise DomainError("invalid_original", "original metadata failed verification")
        self.connection.execute("UPDATE photo SET upload_status='verified',original_object_key=%s,sha256=%s,byte_size=%s,mime_type=%s,failure_reason=NULL WHERE organization_id=%s AND id=%s", (object_key, sha256.lower(), byte_size, mime_type, organization_id, photo_id))
        if photo.get("asset_id"):
            self._refresh_asset_completion(organization_id, str(photo["asset_id"]))
        return self._one("SELECT * FROM photo WHERE organization_id=%s AND id=%s", (organization_id, photo_id), "photo")

    def _refresh_asset_completion(self, organization_id: str, asset_id: str) -> None:
        self.connection.execute("""UPDATE asset SET completion_status=CASE WHEN btrim(asset_type)<>'' AND btrim(name)<>'' AND room_id IS NOT NULL AND EXISTS (SELECT 1 FROM photo WHERE organization_id=%s AND asset_id=%s AND upload_status='verified' AND purpose='asset_original') THEN 'complete' ELSE 'draft' END WHERE organization_id=%s AND id=%s""", (organization_id, asset_id, organization_id, asset_id))

    def complete_onboarding(self, organization_id: str, user_id: str, inspection_id: str) -> dict[str, Any]:
        del user_id
        inspection = self._one("SELECT * FROM inspection WHERE organization_id=%s AND id=%s AND inspection_type='onboarding' FOR UPDATE", (organization_id, inspection_id), "onboarding inspection")
        counts = self.connection.execute("""SELECT (SELECT count(*) FROM room WHERE organization_id=%s AND home_id=%s AND lifecycle_state='active') AS rooms,(SELECT count(*) FROM asset WHERE organization_id=%s AND home_id=%s AND lifecycle_state='active' AND completion_status<>'complete') AS incomplete,(SELECT count(*) FROM photo WHERE organization_id=%s AND inspection_id=%s AND upload_status<>'verified') AS pending""", (organization_id, inspection["home_id"], organization_id, inspection["home_id"], organization_id, inspection_id)).fetchone()
        if not counts["rooms"] or counts["incomplete"] or counts["pending"]:
            raise ConflictError("onboarding_incomplete", "Complete required rooms, assets, and original uploads before finishing", fields={"rooms": str(counts["rooms"]), "incompleteAssets": str(counts["incomplete"]), "pendingUploads": str(counts["pending"])})
        return self._one("UPDATE inspection SET status='completed',completed_at=now() WHERE organization_id=%s AND id=%s RETURNING *", (organization_id, inspection_id), "inspection")
