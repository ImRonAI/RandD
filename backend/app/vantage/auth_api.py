from __future__ import annotations

import os
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel

from .auth import AuthError
from .context import TenantContext
from .runtime import COOKIE_NAME, VantageRuntime


class EmailBody(BaseModel):
    email: str


class VerifyBody(EmailBody):
    code: str


class OrganizationBody(BaseModel):
    organizationId: str


def session_context(runtime: VantageRuntime):
    def dependency(vantage_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None) -> TenantContext:
        return runtime.context_from_token(vantage_session)
    return dependency


def create_auth_router(runtime: VantageRuntime) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["vantage-auth"])

    context = session_context(runtime)

    @router.post("/code/request")
    def request_code(payload: EmailBody) -> dict:
        if runtime.magic_codes is None:
            raise HTTPException(status_code=503, detail={"error": {"code": "auth_not_configured", "message": "Vantage authentication is not configured", "retryable": False, "fields": {}}})
        user, memberships = runtime.memberships(payload.email.strip().lower())
        if user is None or not memberships:
            # Do not use the Gmail sender as an open relay and do not disclose
            # whether an address is enrolled.
            return {"expiresAt": None, "accepted": True}
        try:
            challenge = runtime.magic_codes.request(payload.email)
            return {"expiresAt": challenge.expires_at}
        except AuthError as error:
            code = 503 if error.code == "delivery_failed" else (429 if error.code == "resend_throttled" else 422)
            raise HTTPException(status_code=code, detail={"error": {"code": error.code, "message": str(error), "retryable": error.code in {"delivery_failed", "resend_throttled"}, "fields": {}}}) from error

    @router.post("/code/verify")
    def verify_code(payload: VerifyBody, response: Response) -> dict:
        if runtime.magic_codes is None or runtime.token_service is None:
            raise HTTPException(status_code=503, detail="Authentication is not configured")
        try:
            challenge = runtime.magic_codes.verify(payload.email, payload.code)
        except AuthError as error:
            raise HTTPException(status_code=401, detail={"error": {"code": error.code, "message": str(error), "retryable": False, "fields": {}}}) from error
        user, memberships = runtime.memberships(challenge.email)
        if user is None or not memberships:
            raise HTTPException(status_code=403, detail="This email does not have Vantage access")
        active_org = memberships[0]["organization_id"]
        roles = [item["role"] for item in memberships if item["organization_id"] == active_org]
        token = runtime.token_service.issue_session(str(user["id"]), str(active_org), roles, ttl=timedelta(hours=12))
        response.set_cookie(COOKIE_NAME, token, httponly=True, secure=os.getenv("VANTAGE_ENV") == "production", samesite="lax", max_age=43200, path="/")
        return _session(user, memberships, active_org)

    @router.get("/me")
    def me(ctx: Annotated[TenantContext, Depends(context)]) -> dict:
        with runtime.connect() as connection:
            connection.row_factory = __import__("sqlite3").Row
            user = dict(connection.execute("SELECT * FROM app_user WHERE id=?", (ctx.user_id,)).fetchone())
        _, memberships = runtime.memberships(user["email"])
        return _session(user, memberships, ctx.organization_id)

    @router.post("/active-organization")
    def choose_organization(payload: OrganizationBody, response: Response, ctx: Annotated[TenantContext, Depends(context)]) -> dict:
        with runtime.connect() as connection:
            roles = [row[0] for row in connection.execute(
                "SELECT role FROM organization_membership WHERE organization_id=? AND user_id=? AND active=1",
                (payload.organizationId, ctx.user_id),
            )]
        if not roles:
            raise HTTPException(status_code=403, detail="Organization access is not active")
        token = runtime.token_service.issue_session(ctx.user_id, payload.organizationId, roles, ttl=timedelta(hours=12))
        response.set_cookie(COOKIE_NAME, token, httponly=True, secure=os.getenv("VANTAGE_ENV") == "production", samesite="lax", max_age=43200, path="/")
        return {"organization": {"id": payload.organizationId, "role": roles[0]}}

    @router.post("/ws-token")
    def ws_token(vantage_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None) -> dict:
        if not vantage_session or runtime.token_service is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        token = runtime.token_service.issue_ws_token(vantage_session, ttl=timedelta(seconds=60))
        return {"token": token, "expiresAt": 60}

    @router.post("/logout")
    def logout(response: Response, vantage_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None) -> None:
        if vantage_session and runtime.token_service is not None:
            try:
                runtime.token_service.revoke_session(vantage_session)
            except AuthError:
                pass
        response.delete_cookie(COOKIE_NAME, path="/")

    return router


def _session(user: dict, memberships: list[dict], active_org: str) -> dict:
    organizations = [
        {"id": row["organization_id"], "name": row["name"], "role": str(row["role"]).lower()}
        for row in memberships
    ]
    return {"id": user["id"], "email": user["email"], "activeOrganizationId": active_org, "organizations": organizations}
