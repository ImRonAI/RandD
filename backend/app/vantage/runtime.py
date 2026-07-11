"""Canonical Vantage runtime wiring for the deployed FastAPI application.

External Google/Gmail services fail explicitly when credentials are absent.
The SQLite connection is an additive local/legacy compatibility store; the
production schema and RLS policy live in ``backend/migrations`` for RDS.
"""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from fastapi import Cookie, HTTPException, Request, status

from .auth import MagicCodeService, TokenService
from .auth_store import SqlChallengeStore, SqlReplayStore
from .context import TenantContext
from .domain import VantageRepository
from .google_day import GoogleCalendarService, GoogleNavigationService, GooglePlacesService
from .google_http_clients import GoogleCalendarHttpClient, GooglePlacesHttpClient, GoogleRoutesHttpClient
from .schema import install_sqlite_schema

_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ORG_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "vantage:organization:big-bear"))
DEFAULT_PORTFOLIO_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "vantage:portfolio:big-bear"))
COOKIE_NAME = "vantage_session"


class GmailCodeSender:
    """Send authentication codes through the configured Google OAuth gateway."""

    def send_code(self, email: str, code: str) -> str:
        from strands_google.use_google import use_google

        message = EmailMessage()
        message["To"] = email
        message["Subject"] = f"{code} is your Vantage sign-in code"
        message.set_content(
            f"Your Vantage sign-in code is {code}. It expires in 10 minutes. "
            "If you did not request it, ignore this message."
        )
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = use_google(
            credential_type="oauth",
            service="gmail",
            version="v1",
            resource="users.messages",
            method="send",
            parameters={"userId": "me", "body": {"raw": raw}},
            label="Send Vantage authentication code",
        )
        if result.get("status") != "success":
            raise RuntimeError("Gmail did not accept the authentication message")
        try:
            text = result["content"][0]["text"]
            payload = json.loads(text.split("Response:\n", 1)[1])
            return str(payload.get("id") or "gmail-sent")
        except Exception:
            return "gmail-sent"


class RuntimeAuthorization:
    def __init__(self, connect, calendar_id: str | None) -> None:
        self.connect = connect
        self.calendar_id = calendar_id

    def calendar_connection(self, context: TenantContext) -> dict[str, Any] | None:
        # The environment-token bridge is intentionally limited to the local
        # Big Bear bootstrap tenant. External tenants require their own
        # encrypted OAuth connection record before Calendar can be enabled.
        if not self.calendar_id or context.organization_id != DEFAULT_ORG_ID:
            return None
        return {"calendarId": self.calendar_id, "status": "connected"}

    def authorize_calendar_link(self, context: TenantContext, properties: dict[str, str]) -> dict[str, Any] | None:
        if properties.get("vantageOrgId") != context.organization_id:
            return None
        task_id = properties.get("vantageTaskId")
        home_id = properties.get("vantageHomeId")
        if not task_id and not home_id:
            return None
        with self.connect() as connection:
            if context.has_role("OWNER") and (not home_id or home_id not in context.home_grants):
                return None
            if home_id and connection.execute(
                "SELECT 1 FROM home WHERE organization_id=? AND id=?",
                (context.organization_id, home_id),
            ).fetchone() is None:
                return None
        return {"taskId": task_id, "homeId": home_id}

    def day_stops(self, context: TenantContext, day: date) -> list[dict[str, Any]]:
        with self.connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT h.id AS home_id,h.name,h.unit_code,h.formatted_address,h.google_place_id,
                       h.latitude,h.longitude,t.id AS task_id,t.arrival_date,t.stage_name
                  FROM home h
                  LEFT JOIN field_task t ON t.organization_id=h.organization_id AND t.home_id=h.id
                 WHERE h.organization_id=? AND h.lifecycle_state='active'
                   AND h.latitude IS NOT NULL AND h.longitude IS NOT NULL
                   AND (t.arrival_date IS NULL OR t.arrival_date=?)
                 ORDER BY (t.arrival_date IS NULL),h.name
                """,
                (context.organization_id, day.isoformat()),
            ).fetchall()
        if context.has_role("OWNER"):
            rows = [row for row in rows if row["home_id"] in context.home_grants]
        return [
            {
                "id": str(row["task_id"] or f"home:{row['home_id']}"),
                "taskId": str(row["task_id"] or f"home:{row['home_id']}"),
                "homeId": row["home_id"],
                "home": {
                    "id": row["home_id"], "name": row["name"], "unitCode": row["unit_code"] or "",
                    "address": row["formatted_address"] or "",
                },
                "stage": row["stage_name"] or "Scheduled",
                "timeLabel": row["arrival_date"] or "Today",
                "latitude": row["latitude"], "longitude": row["longitude"], "placeId": row["google_place_id"],
                "place": {
                    "status": "validated" if row["google_place_id"] else "unverified",
                    "formattedAddress": row["formatted_address"],
                },
            }
            for row in rows
        ]

    def authorize_task_ids(self, context: TenantContext, day: date, task_ids: list[str]) -> list[dict[str, Any]]:
        allowed = {stop["taskId"]: stop for stop in self.day_stops(context, day)}
        return [allowed[task_id] for task_id in task_ids if task_id in allowed]

    def save_home_place(self, context: TenantContext, home_id: str, place: dict[str, Any]) -> dict[str, Any]:
        if not place.get("placeId") or place.get("latitude") is None or place.get("longitude") is None:
            raise HTTPException(status_code=422, detail="Google Place Details did not include a routable location")
        with self.connect() as connection:
            cursor = connection.execute(
                """UPDATE home SET google_place_id=?,formatted_address=?,latitude=?,longitude=?,
                          places_validated_at=CURRENT_TIMESTAMP
                     WHERE organization_id=? AND id=?""",
                (place["placeId"], place.get("formattedAddress"), place["latitude"], place["longitude"],
                 context.organization_id, home_id),
            )
            if cursor.rowcount != 1:
                raise HTTPException(status_code=404, detail="Home was not found")
        return {**place, "homeId": home_id, "status": "validated"}


@dataclass
class VantageRuntime:
    repository: VantageRepository
    token_service: TokenService | None
    magic_codes: MagicCodeService | None
    authorization: RuntimeAuthorization
    calendar: GoogleCalendarService
    places: GooglePlacesService
    navigation: GoogleNavigationService
    connect: Any

    def memberships(self, email: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        with self.connect() as connection:
            connection.row_factory = sqlite3.Row
            user = connection.execute("SELECT * FROM app_user WHERE lower(email)=lower(?) AND active=1", (email,)).fetchone()
            if user is None:
                return None, []
            memberships = connection.execute(
                """SELECT om.organization_id,o.name,om.role FROM organization_membership om
                     JOIN organization o ON o.id=om.organization_id
                    WHERE om.user_id=? AND om.active=1 ORDER BY o.name""",
                (user["id"],),
            ).fetchall()
        return dict(user), [dict(row) for row in memberships]

    def context_from_token(self, token: str | None) -> TenantContext:
        if not token or self.token_service is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        try:
            claims = self.token_service.verify_session(token)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is invalid") from exc
        return self.context_from_claims(claims)

    def context_from_claims(self, claims: dict[str, Any]) -> TenantContext:
        with self.connect() as connection:
            roles = [row[0] for row in connection.execute(
                "SELECT role FROM organization_membership WHERE organization_id=? AND user_id=? AND active=1",
                (claims["org_id"], claims["sub"]),
            )]
            grants = [row[0] for row in connection.execute(
                "SELECT home_id FROM home_grant WHERE organization_id=? AND user_id=?",
                (claims["org_id"], claims["sub"]),
            )]
        if not roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization access is not active")
        return TenantContext(str(claims["sub"]), str(claims["org_id"]), frozenset(roles), frozenset(grants))


def build_runtime() -> VantageRuntime:
    raw_path = Path(os.getenv("VANTAGE_DB_PATH", "backend/workspace/vantage-v1.sqlite"))
    db_path = raw_path if raw_path.is_absolute() else _ROOT / raw_path
    legacy_raw = Path(os.getenv("STRQC_DB_PATH", "./str_qc.sqlite"))
    legacy_path = legacy_raw if legacy_raw.is_absolute() else _ROOT / legacy_raw

    def connect() -> sqlite3.Connection:
        connection = sqlite3.connect(db_path)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    with connect() as connection:
        install_sqlite_schema(connection)
    repository = VantageRepository(connect)
    repository.bootstrap_organization(DEFAULT_ORG_ID, "Big Bear Operations", DEFAULT_PORTFOLIO_ID)
    _sync_legacy_homes(connect, legacy_path)
    for email in [item.strip().lower() for item in os.getenv("VANTAGE_ALLOWED_EMAILS", "").split(",") if item.strip()]:
        user_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"vantage:user:{email}"))
        repository.bootstrap_user(user_id, email, DEFAULT_ORG_ID, "ORG_ADMIN")

    secret = os.getenv("VANTAGE_SESSION_SECRET", "").encode()
    token_service = TokenService(secret, SqlReplayStore(connect)) if len(secret) >= 32 else None
    magic_codes = MagicCodeService(secret, GmailCodeSender(), store=SqlChallengeStore(connect)) if len(secret) >= 32 else None
    authorization = RuntimeAuthorization(connect, os.getenv("GOOGLE_CALENDAR_ID"))
    calendar_client = GoogleCalendarHttpClient(os.environ["GOOGLE_CALENDAR_ACCESS_TOKEN"]) if os.getenv("GOOGLE_CALENDAR_ACCESS_TOKEN") else None
    maps_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    places_client = GooglePlacesHttpClient(maps_key) if maps_key else None
    routes_client = GoogleRoutesHttpClient(maps_key) if maps_key else None
    return VantageRuntime(
        repository, token_service, magic_codes, authorization,
        GoogleCalendarService(calendar_client, authorization),
        GooglePlacesService(places_client), GoogleNavigationService(routes_client, authorization), connect,
    )


def _sync_legacy_homes(connect, legacy_path: Path) -> None:
    if not legacy_path.exists():
        return
    source = sqlite3.connect(f"file:{legacy_path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "property" not in tables:
        source.close()
        return
    with connect() as connection:
        legacy_home_ids: dict[str, str] = {}
        for row in source.execute(
            "SELECT property_id,unit_code,display_name,address_line_1 FROM property WHERE roster_active=1"
        ):
            home_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"vantage:legacy-property:{row['property_id']}"))
            legacy_home_ids[str(row["property_id"])] = home_id
            connection.execute(
                """INSERT OR IGNORE INTO home
                   (organization_id,id,portfolio_id,name,unit_code,legacy_property_id,formatted_address)
                   VALUES (?,?,?,?,?,?,?)""",
                (DEFAULT_ORG_ID, home_id, DEFAULT_PORTFOLIO_ID,
                 (row["display_name"] or row["unit_code"] or "Home").strip(), row["unit_code"],
                 str(row["property_id"]), (row["address_line_1"] or "").strip()),
            )
        if "task" in tables:
            stage_names = {
                str(row["stage_definition_id"]): row["stage_name"]
                for row in source.execute("SELECT stage_definition_id,stage_name FROM stage_definition")
            } if "stage_definition" in tables else {}
            for row in source.execute(
                "SELECT task_id,property_id,arrival_date,current_stage_definition_id FROM task"
            ):
                home_id = legacy_home_ids.get(str(row["property_id"]))
                if not home_id:
                    continue
                connection.execute(
                    """INSERT OR REPLACE INTO field_task
                       (organization_id,id,home_id,arrival_date,stage_name) VALUES (?,?,?,?,?)""",
                    (DEFAULT_ORG_ID, str(row["task_id"]), home_id, row["arrival_date"],
                     stage_names.get(str(row["current_stage_definition_id"]), "Scheduled")),
                )
    source.close()
