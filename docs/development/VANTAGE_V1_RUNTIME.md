# Vantage V1 Runtime Configuration

The canonical runtime is `backend/` (FastAPI) plus `frontend/` (React/Vite). The parallel `apps/*` and `packages/*` tree remains reference-only.

## Required configuration

- `VANTAGE_SESSION_SECRET`: at least 32 random bytes for HTTP sessions and one-use WebSocket tokens.
- `VANTAGE_ALLOWED_EMAILS`: comma-separated bootstrap users for local development.
- Google OAuth credentials used by `strands-google` to deliver single-use Gmail authentication codes.
- `GOOGLE_CALENDAR_ACCESS_TOKEN` and `GOOGLE_CALENDAR_ID`: Calendar event sync for the active user.
- `GOOGLE_MAPS_API_KEY`: authorized for Places API (New) and Routes API.

The UI does not synthesize routes, Calendar events, Places validation, approvals, or upload success when a provider is missing. APIs return structured errors and the field UI exposes retry and recovery states.

## Google day contract

Calendar events link to Vantage with private extended properties: `vantageOrgId`, `vantageTaskId`, and `vantageHomeId`. Every link is re-authorized in the active tenant. Synchronization paginates, stores the terminal sync token, and restarts a full sync after HTTP 410.

Property addresses use one Autocomplete session followed by Place Details with the same session token. Vantage stores the stable Place ID, formatted address, coordinates, and validation time. Routes return house-to-house legs, maneuver steps, traffic-aware duration, encoded polyline, and a Google Maps navigation handoff. Reordering authorized stops triggers a server recomputation.

## Agent camera and approval contract

The authenticated WebSocket is `/ws?token=…`; its token is short lived and single use. Camera frames and capture mailboxes use the connection's server-derived session ID.

The client sends `camera_capture` containing the original image. The agent returns `approval_requested` with the inspection, exact checklist item or asset, proposed verdict, rationale, and media reference. The user sends `approval_resolved` with `approve`, `reshoot`, or `cancel`. Reshoot requires voice or text guidance that becomes the next capture instruction. The server may report approval complete only after evidence association and verdict are atomically persisted.

## External production dependencies

- AWS RDS PostgreSQL with the checked-in migration and RLS enabled.
- An S3 bucket created with Object Lock, versioning, seven-year retention, abandoned-multipart cleanup, and signed tenant-authorized reads.
- Google Workspace OAuth and Gmail sender credentials.
- Google Calendar, Places API (New), and Routes API quotas and billing.
- Slack and Gmail report-delivery credentials, separate from the Gmail authentication sender.
- Escapia PMC credentials and an operator-specific housekeeping-status map.

These external accounts cannot be provisioned or validated from repository code without cloud authority. Staging must pass tenant-isolation, concurrency, migration-snapshot, retention, and provider-delivery gates before rollout.
