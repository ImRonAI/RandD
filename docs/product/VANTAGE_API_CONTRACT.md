# Vantage v1 API and Event Contract

All authenticated operations derive `user_id`, active `org_id`, and roles from the session. Client-supplied tenant identifiers are rejected. Retryable writes accept `Idempotency-Key`; created domain records also accept stable, non-empty opaque client IDs.

## Authentication

- `POST /api/auth/code/request` `{email}`
- `POST /api/auth/code/verify` `{email, code}`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `POST /api/auth/active-organization` `{organizationId}`
- `POST /api/auth/ws-token`

## Onboarding and inventory

- `GET /api/room-types`
- `GET|POST /api/homes/{homeId}/rooms`
- `PATCH|DELETE /api/rooms/{roomId}` (`DELETE` archives)
- `GET|POST /api/rooms/{roomId}/assets`
- `PATCH /api/assets/{assetId}` (including authorized room move)
- `POST /api/assets/duplicates/search`
- `POST /api/inspections` `{homeId, type: onboarding|turnover, clientId}`. `type` maps to the canonical physical field `inspection_type` in both databases.
- `GET /api/inspections/{inspectionId}`
- `POST /api/inspections/{inspectionId}/sync`
- `POST /api/inspections/{inspectionId}/complete`

## Calendar, Places, and navigation

- `GET /api/calendar/connections`
- `POST /api/calendar/connect`
- `POST /api/calendar/sync`
- `GET /api/calendar/day?date=YYYY-MM-DD`
- `GET /api/places/autocomplete?input=...&sessionToken=...`
- `POST /api/places/resolve` `{placeId, sessionToken}`
- `GET /api/navigation/day-route?date=YYYY-MM-DD`
- `POST /api/navigation/day-route/reorder` `{orderedTaskIds}`
- `GET /api/navigation/legs/{legId}`

Calendar events link to Vantage through private extended properties but all linked identifiers are re-authorized. Place resolution stores only requested fields: place ID, formatted address, display name, latitude, and longitude. Route responses include ordered stops, legs, distance/duration, path/polyline, traffic-aware ETA, and step instructions plus a Google Maps navigation URL.

## Original media

- `POST /api/media/uploads` creates an upload record and signed/resumable target.
- `POST /api/media/uploads/{uploadId}/complete` verifies size, MIME, object existence, and SHA-256 before association.
- `GET /api/media/{mediaId}` returns authorized metadata and a short-lived original/derivative URL.

An asset has `completionStatus: draft|complete`; only a verified original can produce `complete`.

The asset-upload endpoint creates purpose `asset_original`; other frozen purposes are `inspection_evidence`, `maintenance_before`, `maintenance_after`, and `owner_report`. Original object keys are server-owned and have the exact shape `{organization_id}/{home_id}/originals/{media_id}.{extension}`, matching `EvidenceStorage`.

## Turnover checklist results

The normalized result contract uses the exact 38 keys in `VANTAGE_SCHEMA_MAPPING.md`. A result is `PASS`, `FAIL`, or `NA`; later observations append a version linked through `supersedes_result_id`. Each result may link multiple verified original photos through `result_photo`.

Historical House Keeping reports remain raw compatibility records. Their `state.items[].id` values map to checklist keys, while `checked` remains a boolean and is never inferred as PASS/FAIL/NA. Historical reports do not create or imply room inventory.

For every client-ID-scoped create, an exact retry returns the existing record. Reusing the same scoped client ID with a different payload returns `idempotency_payload_conflict` (HTTP 409), never stale values from the first request.

## Error envelope

```json
{
  "error": {
    "code": "stable_machine_code",
    "message": "Human-readable explanation",
    "retryable": false,
    "fields": {"field": "problem"},
    "currentVersion": 3
  }
}
```

## WebSocket approval events

- Server: `approval_requested` `{approvalId, inspectionId, itemId?, resultId?, assetId?, proposedVerdict?, rationale, mediaId, expiresAt}`
- Client: `approval_resolved` `{approvalId, decision: approve|reshoot|cancel, feedback?, inputMode?: text|voice}`
- Server: `approval_completed|approval_expired|approval_cancelled`

On approval, the server atomically associates the verified original and verdict with the referenced item/asset, then emits `approval_completed` with the resulting record IDs. On reshoot, feedback is appended to the agent conversation and returned to the waiting capture tool as the next composition instruction.

Approval IDs are scoped to the authenticated WebSocket session and persisted inspection; ordinary chat text cannot resolve them.
