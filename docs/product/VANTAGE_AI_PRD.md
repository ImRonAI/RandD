# Vantage AI Product Requirements — v1

**Status:** implementation source of truth  
**Supersedes:** earlier STR QC product plans where they conflict  
**Updated:** 2026-07-10

## Product summary

Vantage AI is a mobile, agent-assisted short-term-rental quality-control and property-operations platform. Its defining v1 experience is a low-effort property walkthrough: the user shows the agent each room and asset, the agent organizes and captures the information, and the user confirms only when necessary. The result is a tenant-safe digital twin and an immutable photographic condition baseline.

## Problem statement

Turnover inspection and new-home onboarding are repetitive, time-sensitive, and poorly structured. Operators need reliable room/asset inventories, defensible original evidence, resumable field workflows, and consistent coordination without forcing inspectors or homeowners to complete long forms while walking a property.

## Users and roles

- **Org Admin:** organizations, portfolios, memberships, room types, integrations, retention settings.
- **Property Manager:** homes, tasks, work orders, reports, assignments, owner access.
- **Inspector:** onboarding and turnover inspections, evidence approval, repairs, sign-off.
- **Housekeeper:** assigned work, checklists, issue/photo reporting.
- **Facilities:** assigned work orders and maintenance evidence.
- **Office / Dispatch:** schedules, routing, exceptions, coordination.
- **Owner:** read-only access to explicitly linked homes' approved reports and evidence.

All permissions are evaluated inside the active organization.

## Goals

- Onboard a typical home in under 60 minutes through a live walkthrough.
- Persist rooms and assets directly into the home's normal inventory.
- Preserve at least one original, unmodified source photo for every completed asset.
- Complete and resume onboarding during poor connectivity without duplication or data loss.
- Preserve the canonical 38-item turnover workflow using room-oriented sections.
- Prevent cross-tenant access through APIs, agent tools, jobs, memory, and media.

## Non-goals

- Native iOS/Android applications.
- Autonomous Airbnb/Vrbo claim filing.
- Dynamic pricing, payroll, cleaner marketplace, or guest messaging.
- Full insurance appraisal, advanced CV research platform, or complete CMMS.
- Escapia write-back and non-Escapia PMS integrations in v1.

## Core user journeys

1. Sign in by email magic code and choose an organization.
2. Open My Day, which combines the assigned Google Calendar schedule with a Places-validated, house-to-house Google Maps route.
3. Follow the current turn-by-turn route leg to the next home without leaving the persistent agent UI.
4. Open a home and start/resume an assessment from the same agent frame.
5. Walk the home room by room while the agent proposes structure and captures originals.
4. Correct, rename, move, or archive records with visible autosave state.
5. Review completeness and finish onboarding.
6. Later run room-oriented turnover inspections against the established twin/baseline.
9. Review reports, comparisons, work orders, and claim evidence within role permissions.

## Daily navigation and calendar

Google Calendar and Google Maps are core field-work infrastructure, not optional utilities.

- My Day reads the authenticated inspector's configured Google Calendar and merges linked events with Vantage tasks.
- Calendar events use private extended properties for Vantage organization, home, task, and inspection identifiers; those identifiers are re-authorized server-side.
- Full sync stores the Calendar sync token; incremental sync handles pagination and performs a new full sync after Google returns an expired-token response.
- Every active home stores a validated Google Place ID, formatted address, latitude, and longitude. Address entry uses Places Autocomplete sessions and selected Place Details fields.
- The day route contains an origin, ordered home waypoints, route legs, traffic-aware duration, distance, encoded path, and step-level driving instructions.
- Users can keep the in-app turn list visible or hand the current/remaining route to Google Maps navigation.
- Completing, skipping, delaying, or reordering a stop recomputes remaining route legs and updates the agent's next-stop context.
- Calendar, route, Places, and navigation failures are explicit and retryable; cached last-known data remains labeled with its freshness.

## Persistent agent interaction frame

The agent is the primary application frame across My Day, navigation, onboarding, turnover, photo/video capture, and approvals. Text/voice input and text/voice output are modality choices within one continuous session, not separate screens.

- Opening the camera compresses or slides the upper conversation region downward to reveal the live preview while preserving visible agent state and recent guidance.
- Agent guidance overlays or sits adjacent to the live preview without blocking the subject.
- After capture, one proposed image embeds in the conversation frame with the proposed verdict, rationale, and exact destination line item.
- **Approve** writes a correlated approval event, persists the accepted original and verdict to the exact inspection item, and adds a visible approval message to the conversation.
- **Take Again** keeps the proposed image for context and opens an in-place voice/text instruction control. The user's feedback becomes the next capture instruction before the agent recomposes.
- The flow supports repeated re-shoots, cancellation, disconnect/resume, expiry, and prevents a different session from resolving the approval.

## Onboarding-assessment workflow

- A new onboarding inspection begins with zero room instances and a clear **Start property walkthrough** / **Add first room** state.
- The user or agent adds rooms from the inspection itself. Creating a room persists a normal home inventory record immediately.
- Multiple rooms may share a type; type and user-facing name are separate.
- Rooms can be renamed, reordered, edited, and safely archived. Referenced historical rooms are never hard-deleted.
- Assets are created inside rooms and likewise become normal inventory records immediately.
- Draft progress continuously autosaves and can resume after browser restart or connection loss.
- Stable client IDs and idempotency keys prevent duplicates during retries.
- Completion presents the generated inventory and validates only v1-required data.

## Inspection-form requirements

- **Onboarding:** blank, dynamic, room-based canvas.
- **Turnover:** exact 38-item canonical checklist from `backend/app/qc_journal.py`, displayed through actual room instances where applicable.
- Results persist as PASS, FAIL, or NA with notes, evidence, rationale, and human approval.
- Repairs Needed, signature, section video, pause/resume, and sign-off remain supported.
- Saving, saved, queued, failed, and conflict states are always visible.

## Room requirements

Initial types: Bedroom, Bathroom, Common Area, Game Room, Dock Area, Pool, Casita / Guest House, Basement, Kitchen, and Other. The catalog is organization-scoped and extensible.

A room stores stable ID, organization, home, exactly one room type, distinct name, optional floor/area and notes, display order, lifecycle state, timestamps, creator/source, and optional creating inspection.

## Asset requirements

An asset belongs to exactly one room and remains traceable to its home and organization through enforced relationships.

Required for **completion**, not draft creation:

1. Asset Type
2. Asset Name
3. Asset Location (room)
4. At least one successfully persisted original photo

Optional fields include manufacturer, model, serial, quantity, condition, dates, costs, warranty, dimensions, finish, service data, documents, manuals, identifiers, research source/confidence, notes, tags, and a more specific location description. Optional research never blocks save or completion.

## Agent-assisted walkthrough requirements

The agent can start/end/pause/resume a walkthrough; recognize a room transition; suggest room type/name; create or update confirmed rooms; identify and deduplicate assets; capture originals; accept voice descriptions; associate media correctly; ask only for missing required information; mark uncertainty; and show captured state. The provider boundary must remain replaceable, and unavailable external capabilities must be reported honestly.

## Agent tools

Required operations: list room types, create/update/archive/list rooms, create/update/move assets, attach originals, find duplicates, identify an asset from view, look up product information, record sourced research, mark low confidence, retrieve inspection state, save progress, and complete onboarding.

Tools derive organization/user context from the authenticated invocation, validate every referenced ID, use structured errors, support idempotency, preserve provenance, and never silently overwrite confirmed values.

## Data model

Organization -> Portfolio -> Home -> Room -> Asset. Home also owns tasks, inspections, work orders, reports, baselines, and damage incidents. Media references organization, home, room/asset when applicable, inspection, uploader/source, immutable original, derivatives, and approval/provenance. Completed onboarding links to every inventory record it created or reviewed.

## Multi-tenancy and authorization

PostgreSQL row-level security and tenant-aware composite relationships enforce the organization boundary. Tenant identity is never trusted from a request payload. HTTP sessions, WebSockets, background jobs, media access, memory search, agent tools, and delivery jobs all carry server-derived organization context. Owners receive explicit home grants only.

## Media and photo requirements

- Full-resolution originals are retained without replacement or enhancement.
- Previews, thumbnails, MP4, and report images are separate derivatives.
- Originals store hashes, timestamps, device/lens metadata, uploader/source, and entity relationships.
- Access uses authenticated endpoints or short-lived signed URLs.
- Failed/pending uploads do not satisfy asset completeness.
- Abandoned uploads are cleaned after a documented grace period; retained/legal-hold evidence is excluded.
- Evidence retention defaults to seven years with legal-hold support.

## Research and enrichment

Supported enrichment may use existing multimodal OCR, product identifiers, manufacturer pages, manuals, warranties, specifications, and replacement-cost references. Each value records source, retrieval time, method, confidence, and confirmation status. Low-confidence data is review-only; confirmed data cannot be overwritten implicitly. Research must respect provider terms and access controls.

## Validation rules

- An onboarding assessment needs at least one active room.
- A completed asset needs type, name, room, and a persisted original.
- No required upload may be pending or failed at completion.
- Optional draft or low-confidence values never block completion.
- A room with active assets cannot be archived until assets are moved or archived.
- Cross-home or cross-organization associations are rejected server-side and by database constraints.

## Error handling and recovery

Mutations use stable client IDs and idempotency keys. APIs return machine-readable code, message, field errors, retryability, and current server version. IndexedDB retains ordered operations and media blobs. Sync is replay-safe, resumable, and visibly reports local, queued, syncing, saved, conflict, and failed states.

## Privacy and security

Minimize incidental guest imagery and obtain appropriate audio/video consent. Encrypt access credentials at rest, gate and audit reveals, use least-privilege tool registries, isolate agent sessions, scan uploads, validate MIME/size, and never expose predictable public media paths. Original evidence is never AI-generated or enhanced.

## Analytics and auditability

Measure onboarding duration, rooms/assets captured, baseline completeness, approval taps/reshoots, upload failures, offline recovery, inspection duration, defects, delivery failures, and tenant-isolation events. Audit authentication, organization switches, secret reveals, inventory mutations, agent/research provenance, approvals, completion, evidence access, and legal holds.

## Accessibility and mobile usability

Phone/tablet-first layout, 44px+ targets, safe areas, WCAG AA contrast, visible focus, keyboard access, screen-reader labels and live save-state announcements, reduced motion, progressive disclosure, minimal typing, quick photo capture, and confirmation before destructive actions.

## V1 scope

Magic-code auth; organization tenancy/RBAC; Big Bear migration; Google Calendar schedule sync; Places-validated home destinations; house-to-house Google Maps routing and turn-by-turn directions; persistent agent UI; embedded camera/approval/reshoot flow; onboarding and turnover inspections; rooms/assets/originals; agent-assisted walkthrough; offline resume; work orders; reports; Slack/Gmail delivery; baseline comparison/claim export; read-only Escapia.

## Future considerations

Escapia write-back, Guesty/Hostaway/Track/Streamline, preventive maintenance/CapEx, consumables, multilingual UI, analytics dashboards, bridge/silo tenancy, native apps, and advanced damage detection.

## Acceptance criteria

An authorized user can open a blank onboarding assessment, add multiple named rooms (including repeated types), create assets with required originals, omit optional fields, survive retries/offline restart, review and complete inventory, and later see those rooms/assets on the home. Another tenant cannot read or mutate any related home, room, asset, media, inspection, report, memory, or job. Existing turnover and historical reports remain readable.

## Rollout and migration

Rehearse SQLite-to-PostgreSQL migration on a production snapshot; verify row counts, encrypted data, history, foreign keys, and rollback. Deploy staging RDS/S3 first, run two-tenant concurrency and media isolation tests, pilot Big Bear, then enable the first external tenant. Do not infer room mappings from historical House Keeping sections without human review.

## External dependencies

Production rollout requires provisioned RDS PostgreSQL, an S3 Object Lock bucket, AWS IAM/KMS configuration, a dedicated Google Workspace sender, Slack credentials, Escapia credentials, and Bedrock KB metadata-filter support. Repository code must degrade explicitly when these are absent and must not present placeholders as successful integrations.
