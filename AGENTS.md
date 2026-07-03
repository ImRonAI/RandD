# Agentic Short-Term Rental Quality Control Platform

## Executive Summary

This document defines the product requirements for an agentic short-term rental (STR) quality control platform focused on operational reliability, multi-stakeholder coordination, and photo-verified inspections across a geographically concentrated portfolio (e.g., Big Bear Lake, CA). The platform is designed around an AI-native, strands-based main agent powered by a reasoning-capable LLM (e.g., Gemini Live) with access to cameras, journals, memory, telephony, email, Slack, and Google tools.

The product's core value is to turn cleaning, inspection, and maintenance work into structured, verifiable operational data, enabling managers, owners, housekeepers, facilities, QC inspectors, property managers, and the office team to maintain guest-ready properties at scale. Market research shows that existing STR operations tools (e.g., Breezeway, Turno, Properly, RapidEye) have strong adoption but still leave gaps around continuous, AI-driven QC, baseline comparison, and agentic orchestration.[1][2][3][4]

## Background and Market Context

### STR Operations Today

Professional STR operators manage day-to-day tasks like cleaning, inspections, maintenance, and guest communication between bookings to keep properties guest-ready. Operations platforms such as Breezeway coordinate task scheduling, guest messaging, maintenance, and inventory tracking across portfolios, with over 270,000 properties in 90+ countries and tens of millions of tasks facilitated. These tools provide:[5][6][1]

- Reservation-driven task scheduling.
- Customizable digital checklists (often per room) with photo documentation.
- Messaging and notifications to cleaners and vendors.
- Preventative maintenance planning and inventory tracking.[6][1]

However, quality control remains an operational bottleneck. Housekeepers and cleaners vary widely in consistency; managers struggle to verify that each turnover hits the same standard and that issues are detected and resolved before the next guest arrives.[7][8]

### AI in STR Operations

Recent work has introduced AI-based inspection and damage detection tools that analyze turnover photos to detect anomalies (e.g., missing items, damage, cleanliness issues). STR-native tools like RapidEye plug into operations platforms (e.g., Breezeway, Guesty, Streamline PropertyCare) to analyze the photos teams already upload, comparing turnovers to per-property baselines. Other solutions (e.g., CheckEasy, Inspector, PropCheckAI) provide AI-assisted anomaly detection and room scoring from structured photo sets.[4][9][10][11]

These tools demonstrate that AI can:

- Identify damage and cleanliness issues faster and more consistently than manual photo review.
- Provide per-room scoring and anomaly flags to support QC decisions.
- Integrate with existing STR ops platforms to avoid workflow change.[10][4]

But current AI layers are typically single-purpose (damage detection or inspection scoring) rather than fully agentic systems that coordinate multi-stakeholder actions end-to-end.

### Opportunity

Market surveys and vendor comparisons show that Breezeway dominates operations management, with many operators layering additional tools for cleaning marketplaces, inspections, and maintenance. Hostaway's reports and Breezeway's analyses highlight that AI adoption in STR operations is accelerating and that operators are seeking more automation across cleaning, maintenance, and guest experience rather than just messaging or pricing.[2][3][12][13][6]

There is room for a focused, AI-native QC platform that:

- Deeply understands per-property standards (room-by-room checklists, required supplies, functional checks).
- Uses agents to orchestrate cleaners, inspectors, facilities, and office staff.
- Provides verifiable, photo-backed evidence that each property is guest-ready.
- Supports geo-concentrated portfolios (e.g., Big Bear, Tahoe) with local nuances and routing.

## Product Vision

Build an agentic STR quality-control platform that acts as the operational "brain" for a cluster of properties, ensuring that every home is cleaned, inspected, and maintained to a defined standard before each guest arrival. The platform will:

- Represent each property ("House") as a structured object with spaces (rooms, outdoor areas), assets (TVs, hot tubs, arcade machines, grills, detectors), supplies, and maintenance plans.
- Coordinate tasks (Housekeeping, QC, B2B handoffs, Cleaning, DONE, OWNER review, Work Orders, REPORT) across stakeholders.
- Use AI agents to analyze photos, checklist data, and task stages, then trigger the right next actions (re-clean, maintenance, owner communication).
- Provide route-aware task lists with integrated Google Maps directions for daily field work.

## Target Users and Stakeholders

### Stakeholder Roles

The platform defines the following core roles, each treated as a stakeholder:

- **Owner**: Property owner, concerned with safety, asset preservation, and guest experience.
- **Housekeeper**: Primary cleaning staff responsible for turnovers.
- **Facilities / Maintenance**: Handles repairs, preventative maintenance, and utilities issues.
- **QC Inspector**: Performs structured inspections after cleaning, validating readiness.
- **Property Manager**: Oversees bookings, revenue, and overall operations.
- **Office / Dispatch**: Coordinates scheduling, routing, and communication.
- **Guest (indirect)**: Receives the outcome of QC via cleanliness and readiness.

These roles are consistent with patterns in existing operations platforms and inspection tools, which manage cleaners, inspectors, owners, and maintenance vendors as distinct actor types.[8][1][2]

### Primary User Personas

1. **Local Operations Manager (Big Bear / Tahoe)**
   - Manages 30–150 homes.
   - Uses PMS plus operations software but lacks reliable QC and inspection intelligence.
   - Pain points: inconsistent cleans, missed damage, last-minute scrambling before arrivals.

2. **Cleaning Team Lead**
   - Coordinates multiple housekeepers (e.g., Maribel, Bertha, Gabriella) across daily tasks.
   - Needs clear schedules, driving directions, and photo-based verification of work.

3. **Facilities Lead**
   - Responds to work orders and preventative maintenance plans.
   - Requires task prioritization (e.g., urgent vs. medium), asset-level context (which hot tub, which TV), and status tracking.

4. **Owner / Asset Manager**
   - Wants evidence that the property is cared for: photos, reports, and reduced damage.
   - Evaluates operators partly on QC reliability and responsiveness to repairs.[6][8]

## Scope and Use Cases

### In-Scope (Phase 1)

1. **Agent-Orchestrated Daily Task List**
   - Ingest a "Master" task table with columns like Geo, RES, Unit Code, Arrival Date, Housekeeper, QC, B2B, Clean, Done, Owner, Work Order (WO), DONE_WO, Report, with boolean flags per stage.
   - Generate per-stakeholder task views (e.g., Maribel's tasks with directions).

2. **Structured House Object Modeling**
   - Represent each property with:
     - Core metadata (unit code, cabin name, address, Wi-Fi SSID/password, door code, cluster/geo).
     - Spaces (kitchen, bedrooms, bathrooms, living room, outdoors, hot tub area).
     - Assets (TVs, hot tubs, grills, detectors, EV chargers).
     - QC requirements mapped to spaces and assets (e.g., "Hot Tub: Up and Working, Full, Fresh, Clear, 103°F").

3. **Digital Checklists and Inspections**
   - Implement a templated checklist for Housekeeping and QC, including:
     - Kitchen cleanliness and organization.
     - Bathroom cleanliness and supplies.
     - Bedroom bed-making, remotes, closets.
     - Home overall state (smell, surfaces, floors, carpets).
     - Outdoors (walkways, garbage cans, yard, BBQ, outdoor furniture, windows).
     - Utilities check (Gas, Wi-Fi, Power, Water).
     - Gifts and welcome items (coffee, cream, deodorant setup).
     - "Ready for guests" summary and "Repairs Needed" section.
   - Each checklist item supports PASS/FAIL/NA status, notes, and required photos.[14][7][8]

4. **Photo Capture and QC Intelligence**
   - Agent instructs the user to capture structured photos per room and per asset via a camera tool.
   - Store photos with metadata linking them to the property, space, asset, checklist items, and tasks.
   - Use AI to auto-assess certain criteria (e.g., visible clutter, missing towels, dirty surfaces), augmenting manual PASS/FAIL.

5. **Work Order Creation from Inspection Results**
   - Convert failed inspection items into work orders with priority and assignment to Facilities.
   - Track status transitions: NEW → ASSIGNED → IN_PROGRESS → BLOCKED → DONE → CANCELLED.

6. **Report Generation**
   - Produce a per-task "Ready for Guests" report summarizing:
     - Checklist outcomes by category.
     - Photos of key areas.
     - Repairs needed and work order status.
     - Sign-off by QC inspector or property manager.

### Out-of-Scope (Phase 1)

- Direct PMS integration (Airbnb, VRBO, Booking.com or PMS platforms); initial Phase 1 will assume imported CSV or manual entry for reservations and tasks.
- Dynamic pricing, owner statements, and financial accounting.
- Guest messaging, beyond basic templated readiness notifications.

## Product Requirements

### 1. House Object and Relationships

#### House Core

Each **House** object must include:

- `house_id` (internal ID).
- `unit_code` (e.g., LBV, LCV, COOKIE).
- `cabin_name` (e.g., "Lakefront Bay View").
- `address` (full address with city, state, postal code).
- `wifi_ssid`, `wifi_password` (with secure handling).
- `door_code`.
- `cluster`/`geo` (e.g., Boulder Bay, Metcalf Bay, Village, Moonridge, etc.).
- `owner_stakeholder_id` (link to Owner stakeholder).

Source data: Big Bear listings with unit codes, cabin names, addresses, Wi-Fi credentials, door codes, and hot tub/TV/EV flags illustrate the real-world attributes the House object needs to support.[5][14]

#### Spaces

- Each House has multiple **Spaces** (e.g., Kitchen, Bathroom 1, Bathroom 2, Bedroom 1, Living Room, Hot Tub Area, Outdoor Patio, Yard).
- Spaces include:
  - `space_id`.
  - `house_id`.
  - `space_type` (enum).
  - `display_name`.
  - `display_order`.

Industry checklists support room-by-room structure as the standard for cleaning and QC.[15][7][8]

#### Assets

- Assets belong to Houses and optionally to Spaces:
  - `asset_id`.
  - `house_id`.
  - `space_id` (nullable for whole-house assets like Wi-Fi).
  - `asset_type` (e.g., TV, Hot Tub, Grill, Arcade Machine, Smoke Detector, CO Detector, EV Charger).
  - `status` (OK, NEEDS_SERVICE, OUT_OF_ORDER, REMOVED).
  - `notes`.

Assets allow tracking multiple TVs, hot tubs, grills, etc., as separate objects in specific rooms or outdoor areas, reflecting how inspections tools handle per-item conditions.[11][10]

#### Stakeholders and Roles

Stakeholders represent individuals or teams:

- `stakeholder_id`.
- `full_name` (e.g., Maribel, Bertha, Gabriella, Liz n Leo, Dan).
- `contact` (phone, email).

Roles:

- OWNER.
- HOUSEKEEPER.
- FACILITIES.
- QC_INSPECTOR.
- PROPERTY_MANAGER.
- OFFICE_DISPATCH.

Relationships:

- `stakeholder_role` table linking stakeholders to roles globally or per house.

This aligns with existing STR operations tools that manage cleaners, inspectors, owners, and maintenance vendors as separate entities with defined roles.[1][2]

### 2. Task and Stage Management

#### Task Model

A **Task** represents a specific turnover or QC workflow for a House:

- `task_id`.
- `house_id`.
- `arrival_date` (guest arrival date, can be NULL for non-reservation tasks).
- `assigned_housekeeper_id`.
- `current_stage`.
- `created_at`, `updated_at`.

Imported task tables (e.g., listing Geo, RES, Unit Code, Arrival Date, Housekeeper, and a series of stage flags like QC, B2B, CLN, DONE, OWN, WO, DONE_WO, REPORT) provide the initial data source.[14]

#### Stages

Stages represent workflow steps:

- QC (Quality Control inspection).
- B2B (Back-to-back booking or special handling).
- CLN (Cleaning performed).
- DONE (Turnover completed).
- OWN (Owner review).
- WO (Work Order created).
- DONE_WO (Work Orders resolved).
- REPORT (Report generated and signed off).

Each stage is tracked as a `task_stage_event`:

- `task_id`.
- `stage_key`.
- `is_complete`.
- `completed_at`.
- `completed_by_stakeholder_id`.

### 3. Checklist and Inspection System

#### Checklist Templates

- Define **Checklist Templates** for Housekeeping and QC.
- Each template has categories (Hot Tub, Housekeeping/Kitchen, Bathrooms, Bedrooms, Home, Outdoors, Utilities, Gifts, Summary).

Checklist items match the provided example:

- Hot Tub:
  - Up and working.
  - Full.
  - Fresh.
  - Clear.
  - 103°F.
- Kitchen:
  - Dishes, glasses, and silverware clean.
  - Pots and pans clean.
  - Dishwasher empty.
  - Sink cleaned and free from food.
  - Garbage disposal clear and fresh.
  - Refrigerator cold and clean.
  - Oven clean.
- Bathrooms:
  - Towels displayed.
  - Floors mopped.
  - Tub/shower clean.
  - Toilet clean and fresh.
  - Sink and mirrors wiped.
- Bedrooms:
  - Beds made properly with skirts.
  - Remotes in holders.
  - Closets organized.
- Home Overall:
  - House smells normal/fresh.
  - All surfaces cleaned or dusted.
  - Floors vacuumed or mopped.
  - House clean and organized.
  - Home open and welcoming.
  - Carpets look good (no stains).
- Outdoors:
  - Walkways and driveway cleaned.
  - Garbage cans put away.
  - Yard maintained.
  - BBQ cleaned.
  - Outdoor furniture arranged.
  - Windows presentable.
- Utilities:
  - Gas on and safe.
  - Wi-Fi working.
  - Power on.
  - Water running.
- Gifts:
  - Coffee and cream set up.
  - Deodorant or welcome gifts set up.
- Summary:
  - Ready for guests.
  - Repairs needed.

These items line up with published room-by-room cleaning and inspection checklists from major STR operators and guides.[7][8][15]

#### Inspection Execution

An **Inspection** ties a Task, Checklist Template, and Inspector:

- `inspection_id`.
- `task_id`.
- `checklist_template_id`.
- `inspector_stakeholder_id`.
- `started_at`, `submitted_at`.

Each item result:

- `inspection_item_result_id`.
- `inspection_id`.
- `checklist_item_template_id`.
- `space_id` and `asset_id` (where applicable).
- `result` (PASS, FAIL, NA).
- `photo_ids` (via separate Photo objects).
- `notes`.

### 4. Photo and Evidence Management

#### Photo Capture

Given the importance of photo documentation in STR operations (accountability, evidence for owners/guests, and AI analysis), the platform must support structured photo storage:[9][16][10][5]

- `photo_id`.
- `house_id`.
- `space_id`.
- `asset_id`.
- `inspection_item_result_id` or `work_order_id`.
- `capture_uri`.
- `captured_at`.
- `captured_by_stakeholder_id`.
- `purpose` (CLEAN_VERIFICATION, DAMAGE_DOCUMENTATION, MAINTENANCE_BEFORE, MAINTENANCE_AFTER, OWNER_REPORT).

#### AI Analysis

AI agents analyze photos to:

- Detect anomalies (clutter, missing items, visible damage).
- Provide per-room scores.
- Compare against per-house baselines (previous "good" turnovers).

This mirrors how RapidEye and CheckEasy operate on STR photos, using baseline comparison and anomaly detection for damage and cleanliness.[17][4][10]

### 5. Work Orders and Maintenance

#### Work Order Creation

Failed inspection items can generate **Work Orders**:

- `work_order_id`.
- `task_id`.
- `house_id`.
- `inspection_item_result_id`.
- `status` (NEW, ASSIGNED, IN_PROGRESS, BLOCKED, DONE, CANCELLED).
- `priority` (LOW, MEDIUM, HIGH, URGENT).
- `assigned_facilities_stakeholder_id`.
- `opened_at`, `closed_at`.
- `details`.

Facility workflows in STR operations software already emphasize status tracking, prioritization, and integration with task schedules.[2][1]

#### Maintenance Plans (Phase 1 optional, Phase 2 recommended)

Introduce **Maintenance Plans** for recurring checks (e.g., hot tub service, smoke detector battery changes, HVAC filters):[18][6]

- `maintenance_plan_id`.
- `asset_id`.
- `maintenance_type`.
- `frequency_days`.
- `next_due_at`.
- `auto_generate_work_order` flag.

### 6. Reports and Owner Communication

#### Report Generation

A **Report** summarizes the QC outcome for a Task:

- `report_id`.
- `task_id`.
- `house_id`.
- `checklist_template_id`.
- `ready_for_guests` (boolean).
- `signed_off_by_stakeholder_id`.
- `signed_off_at`.
- `export_uri` (PDF, shared link).
- `summary_text`.

Reports will include:

- Category-level summaries of PASS/FAIL.
- Key photos.
- Repairs and work order statuses.

This is similar to how inspection apps and operations platforms generate professional PDF reports for owners.[10][17]

### 7. Agent Architecture and Tools

#### Main Agent

The main agent is a **bi-directional strands agent** running on a reasoning-capable LLM (e.g., Gemini Live), with the following tools:

- **Camera Tool**: Capture room and asset photos.
- **Journal Tool**: Write structured notes, using the checklist template.
- **Memory**: Persist operational context across sessions.
- **Strands-Google Tools**: Access Google Maps (directions), Calendar, Sheets (task imports), Docs (reports).
- **Telephony**: Call cleaners, inspectors, facilities.
- **Email**: Send reports and notifications to owners and staff.
- **Slack (or equivalent)**: Coordinate with office and operations team.

This aligns with modern AI stacks for STR operations, where AI is deeply embedded into communication layers (omnichat) and inspection intelligence.[19][4]

#### Agent Behaviors

- **Daily Planning**: Generate route-aware task lists for housekeepers and inspectors based on Geo, RES, unit codes, arrival dates, and stage statuses.
- **Checklist Guidance**: Walk users through the Master checklist, prompting them to verify each item and capture photos where required.
- **QC Verification**: Analyze photos and checklist responses; mark items PASS/FAIL/NA, then update task stages.
- **Issue Routing**: Create work orders for failed items, assign them to Facilities, and notify Office/Dispatch.
- **Owner Communication**: Generate and send reports when tasks reach REPORT and OWNER stages.

### 8. Integrations (Phase 1 minimal)

In Phase 1, integrations focus on:

- **Google Maps**: For directions to each property in daily task lists.
- **Google Sheets**: For importing task tables similar to the provided CSV-like list.
- **Email & Telephony**: For status notifications and coordination.

Phase 2+ can add:

- PMS integrations (Guesty, Hostaway, Breezeway tasks API).
- Direct integration with AI inspection tools if needed.

## Non-Functional Requirements

- **Security**: Door codes and Wi-Fi passwords must be encrypted in transit and at rest.
- **Performance**: Task list generation and photo analysis should be responsive (< 2–3 seconds) for field usability.
- **Reliability**: Offline-capable capture of checklists and photos for poor connectivity areas (common in mountain/lake geos).[5]
- **Scalability**: Support at least 100–300 houses per cluster with multiple concurrent users.

## Risks and Mitigations

- **Adoption Risk**: Operators may be entrenched in existing platforms like Breezeway; mitigation is positioning this as a QC layer that can export reports and data back to existing systems.[12][2]
- **AI Reliability Risk**: Over-reliance on AI photo analysis could misclassify edge cases; mitigation is hybrid workflows (AI suggestions + human override, clear visual evidence).
- **Data Quality Risk**: Inconsistent photo capture and checklist adherence; mitigation via agent-guided workflows and required photo points.[9][10]

## Roadmap (High-Level)

1. **Phase 1 (MVP)**
   - Implement House object, Spaces, Assets, Stakeholders, Tasks, Stages, Checklist Templates, Inspections, Photos, Work Orders, and Reports.
   - Build main strands agent with Google Maps, camera, journal, email, and Slack tools.
   - Support Big Bear Lake cluster as initial geo.

2. **Phase 2**
   - Add Maintenance Plans and recurring maintenance events.
   - Introduce baseline comparison for photo sets per House.
   - Implement PMS integrations (Guesty, Breezeway).

3. **Phase 3**
   - Extend to multi-cluster deployment (Tahoe, other markets).
   - Add guest-facing safety and readiness summaries.
   - Explore vendor marketplaces for cleaners and maintenance.

***

This PRD aggregates learnings from current STR operations platforms, AI inspection tools, and best practices for cleaning and quality control, tailored to the specific needs and data structures of a Big Bear–style property cluster.[4][1][2][6][5]

---

## Addendum: Checklist Photo Capture, Report Embedding & Slack-First Delivery (Added Requirement)

### 9. Report Photo Embedding and Multi-Channel QC Delivery

**Requirement:** During checklist execution, the BIDI agent shall work through the assigned Checklist Template (Section 3), take structured notes per item via the Journal Tool (Section 7), and capture photos — via the Camera Tool — of areas of interest: any item marked FAIL, any item the inspector flags for visual documentation, and all safety-critical items regardless of PASS/FAIL. Captured photos shall be embedded directly into the generated Report (Section 6), not merely referenced by ID, so the Report is a self-contained artifact when shared outside the platform. On sign-off (`Report.signed_off_at` populated), the platform shall automatically send the Report as a file attachment to the appropriate stakeholder channel. **V1 ships with Slack as the only delivery channel**; the delivery layer shall be built as a swappable adapter so Email and Microsoft Teams can be added in Phase 2 without reworking report generation.

**New/extended data model fields:**
- `Report.delivery_channel` (enum: SLACK, EMAIL, TEAMS — v1 supports SLACK only).
- `Report.delivered_at`, `Report.delivery_status` (PENDING, SENT, FAILED).
- `Photo.include_in_report` (boolean) — extends the existing `Photo.purpose` field so report assembly can pull exactly the photos meant for inclusion.

**Technical grounding — Strands native Slack tooling (confirmed directly against the `strands-agents-tools` source):**

Strands does not need a custom-built Slack integration. The community tools package (PyPI: `strands-agents-tools`; source: `strands_tools/slack.py`) ships a native `slack` tool with two relevant entry points:

- `slack(action, parameters)` — a generic passthrough to any Slack Web API method. This includes `files_upload_v2`, which is the exact method for attaching a file to a channel — the tool's own documentation gives this as a worked example: `slack(action="files_upload_v2", parameters={"channel_id": "...", "file": "...", "title": "..."})`. This is the call the Report-delivery step should use.
- `slack_send_message(channel, text, thread_ts)` — a simplified helper for the plain-text notification that accompanies the attachment (e.g., "Unit LBV — ready for guests, report attached").

Setup requirements are minimal: a Slack app with `chat:write` scope (broader scopes like `channels:history`, `reactions:write`, etc. are only needed if using real-time Socket Mode listening, which this use case doesn't require), and a `SLACK_BOT_TOKEN` environment variable. The heavier `SLACK_APP_TOKEN`/Socket Mode setup described in the tool's docs is for two-way conversational use in Slack, not needed for a one-way "send the report" flow.

**Practical lift:** this is Slack app provisioning (create the app, grant scopes, generate the bot token) plus wiring the Report-delivery step to call the already-open-sourced `slack` tool. It is not a from-scratch Slack API integration.

**Technical grounding — Strands native vision/multimodal tooling:**

Two distinct things are relevant here, worth keeping separate:

1. **Photo understanding is a model-layer capability, not a separate tool.** Gemini Live, and Claude (also a supported Strands model provider), are natively multimodal — they can see and reason over images passed into the conversation directly. The "does the agent understand what's in this hot tub photo" capability comes from the model itself, not from a bolt-on computer-vision tool. No custom vision model needs to be trained or integrated for the agent to reason about a captured photo.
2. **`strands-agents-tools` separately ships an Image Processing tool** for generating and manipulating images programmatically. This is a convenience utility — useful for formatting/composing captured photos for report layout — distinct from the model's native vision reasoning.

**Practical lift:** the "AI photo analysis" described elsewhere in this document (anomaly detection, baseline comparison) is primarily an agent-design and prompting problem, not a model-training problem, since perception is already handled by the underlying multimodal model. Engineering effort concentrates on report assembly — pulling flagged photos and formatting them into the embedded report — not on building or training a vision pipeline.

**Sources (fetched directly):**
- `strands-agents/tools` GitHub repository, `slack.py` source: https://github.com/strands-agents/tools/blob/main/src/strands_tools/slack.py
- `strands-agents-tools` on PyPI: https://pypi.org/project/strands-agents-tools/
- Strands Agents SDK — Community Built Tools documentation: https://strandsagents.com/docs/user-guide/concepts/tools/community-tools-package/

---

## Addendum 2: Escapia PMS Integration (Added v1 Requirement)

**Requirement:** The platform must integrate with Escapia (the HomeAway/Vrbo PMS) as a v1 requirement, not a later phase. V1 scope covers four Escapia HSAPI modules — **Reservations**, **Housekeeping**, **WorkOrders** (Facilities/Maintenance), and **Units** (full property "demographics") — plus stakeholder sync via **Owners** and **Guests**. This section is grounded directly in the four uploaded Escapia files (OpenAPI3 spec, legacy Swagger 2.0 spec, and the consolidated HTML documentation), not assumed from general PMS knowledge.

### Connection & Authentication
- Base URL (REST HSAPI): `https://hsapi.escapia.com/dragomanadapter`.
- Every HSAPI call requires three custom headers alongside the bearer token: `x-homeaway-hasp-api-version`, `x-homeaway-hasp-api-endsystem` (e.g. `EscapiaVRS`), and `x-homeaway-hasp-api-pmcid` (this operator's Property Management Company ID).
- Token flow: `GET /hsapi/auth/token` with `Authorization: Basic base64(clientId:secret)` returns a bearer token, sent thereafter as `Authorization: Bearer <token>`.
- A **separate** GraphQL Gateway API exists (`https://api-gateway.escapia.com/graphql`, its own `/token` OAuth flow) covering rates, fees, taxes, booking restrictions, booking channels, and unit listing content. This is **explicitly out of v1 scope** — none of it falls under Reservations/Housekeeping/Facilities/Units/Stakeholders — flag for Phase 2 if dynamic pricing ever becomes relevant.
- Rate limiting exists (HTTP 429) but Escapia does not publish exact limits ("will not publish the exact limits... will act as an upper bound"). The integration layer needs generic exponential backoff/retry, not a hardcoded request budget.

### V1 Module Scope, Mapped to Platform Entities

| Escapia module | Key endpoints | Maps to (platform) | Sync direction |
|---|---|---|---|
| **Reservations** | `GetReservationChanges` (version-cursor delta), `SearchReservationSummaries`, `GetReservationById`/`GetReservationByNumber`, `UpdateReservationOccupancyStatus` | `Task.arrival_date`, new `Task.reservation_context` | Escapia → Platform (read). `GetReservationChanges` is the **only** endpoint in the entire spec with a delta/version cursor (`startVersion`, begins at 0, advances each call) — this should drive the Reservations sync job specifically. |
| **Housekeeping** | `SearchHousekeepingTasks`, `GetHousekeepingStatusList`, `GetHousekeepingAssigneeList`, `GetUnitHousekeepingStatuses`, `SaveUnitHousekeepingStatus`, `CreateHousekeepingTask`/`UpdateHousekeepingTask` | `Task` scheduling fields; status write-back only | Bi-directional but shallow on the write side. Escapia's `HousekeepingTask` object is an 11-field scheduling/status record (unit, reservation, clean type, assignee, scheduled date, a `cleanStatusID`) with **no checklist-item-level structure**. The platform's `ChecklistInstance`/`ChecklistItemResult` model has no Escapia equivalent and stays the system of record for QC detail; Escapia only needs a status write-back via `SaveUnitHousekeepingStatus` when the platform's checklist reaches Ready, so anyone still looking at the PMS calendar sees accurate status. |
| **WorkOrders** (Facilities/Maintenance) | `SearchWorkOrders`, `GetWorkOrder(s)`, `SaveWorkOrder`, `SaveWorkOrderTask`, `GetWorkOrderVendorList`, `GetWorkOrderInternalAssigneeList`, `GetChargeTemplateList` | `WorkOrder` | Bi-directional. Escapia's `WorkOrder` schema (35 fields: category/subcategory, priority enum `Urgent/High/Medium/Low/None`, vendor vs. internal assignee, cost fields, `workOrderRemovesUnitFromAvailability`) is rich enough to be the real target — a failed safety-critical checklist item should call `SaveWorkOrder` directly rather than only living in the platform's own table, so Facilities isn't split across two systems. |
| **Units** ("house demographics") | `SearchUnitSummaries`, `GetUnitById`/`GetUnitsById`, `UpdateUnitMetadata`, `ListUnitTypes`, `ListUnitLocations`, `ListUnitFeatureGroups` | `Property` (extends House Core) | Escapia → Platform (read), primarily. Escapia's `Unit` object (51 fields) is a genuinely complete property master record: address, lat/long, bedrooms/bathrooms/`bedGroups`/`sleeps`, `featureGroups`, `unitType`, `unitComplex`, `maintenanceNotes`, `owners` (direct linkage array), current housekeeping status, `vacantUntil`/`occupiedUntil`/`nextArrival`. This becomes the authoritative source for `Property` demographic fields; the platform's own additions (`standing_instructions`, combinable-unit relationships) remain platform-only, layered on top, since Escapia's `Unit` schema has no equivalent for either. |
| **Owners** (stakeholders) | `SearchOwners`, `GetOwnerById` | `Stakeholder` (role=OWNER) | Escapia → Platform (read). `ownsUnitNativePMSIDs` gives the owner↔unit linkage directly — no manual mapping needed. |
| **Guests** (stakeholders) | `SearchGuests`, `GetGuestById`, `CreateGuest` | Reservation context / future guest-facing use | Escapia → Platform (read); `CreateGuest` write path exists but isn't needed for v1 since Guest isn't a platform stakeholder role in this document. Includes an `isWarn` flag worth surfacing to Housekeeping/QC later if guest-facing features get built. |

### Sync Strategy — the one real asymmetry to design around
`GetReservationChanges` is the **only** endpoint in the spec with incremental delta support. Units, Owners, Housekeeping tasks, and WorkOrders have **no equivalent changes/delta endpoint** — sync for those has to be a scheduled poll against the relevant `Search*` endpoint, not a subscription. Design the sync layer around this asymmetry explicitly rather than assuming all five modules can be synced the same way.

Housekeeping status values (`cleanStatusID`, `unitHousekeepingStatusType`) are **PMC-configurable lookups**, not a fixed enum — `GetHousekeepingStatusList` must be called per-PMC and the results stored as a mapping table between the platform's own pipeline stages and this operator's specific Escapia status IDs. Don't hardcode status name strings.

### Agent Tooling Implication
There is no pre-built Escapia tool in the Strands ecosystem (unlike the native Slack tool covered in Addendum 1). This has to be built as a custom Strands tool — most efficiently as a thin wrapper around the generic `http_request` tool already in `strands-agents-tools`, using the uploaded OpenAPI3 spec directly as the endpoint/schema contract rather than hand-transcribing it. Given the agent will also carry `strands-google` (200+ Google APIs — Sheets/Maps/Calendar, referenced elsewhere in this document) and `strands-fun-tools` (utility/creative tools — its `utility` module's JSON/YAML handling is incidentally useful for normalizing Escapia's XML/JSON dual-format responses), the Escapia integration is the one piece in this PRD that has to be built from the ground up rather than composed from an existing package.

**New/extended data model fields:**
- `Property.escapia_unit_native_pms_id`, `Property.escapia_pmc_id`.
- `Task.escapia_reservation_native_pms_id`, `Task.escapia_housekeeping_task_native_pms_id`.
- `WorkOrder.escapia_work_order_native_pms_id`.
- `Stakeholder.escapia_owner_native_pms_id` (OWNER-role stakeholders).
- New entity `SyncCursor` (per PMC, per resource type) — stores `startVersion` for the Reservations delta feed and `last_polled_at` for the four poll-based resources.
- New entity `HousekeepingStatusMap` — per-PMC mapping between the platform's pipeline stages and Escapia's PMC-specific `cleanStatusID`/`unitHousekeepingStatusType` values.

**Sources (reviewed directly):** `escapia_openapi3.json`/`.yaml` (81 combined paths: 79 HSAPI + 2 Gateway), `escapia_hsapi_swagger2.json` (79 HSAPI paths, legacy Swagger 2.0 form of the same REST API), `escapia_consolidated_documentation.html`. Endpoint list, schema field counts, auth headers, rate-limit disclosure, and the delta-endpoint asymmetry above are pulled from the spec files themselves.

---

## Addendum 3: Implementation Status & Delivery Plan (Added — living pointer)

> Additive note recording current build state and the companion planning/design docs. This section is a pointer; the PRD above remains the requirements source of truth.

**Companion documents:**
- **[TASKS.md](TASKS.md)** — the remaining work to reach **v1**, organized as milestones `M0–M8` with status, effort, dependencies, and a Definition of Done. Maps every requirement here (including Addenda 1 & 2) to a concrete task.
- **[DESIGN.md](DESIGN.md)** — the frontend design system & interaction contract (brand/art direction, tokens, components, the signature voice console, accessibility, and the Next.js stack).

**Current state (as assessed):**
- ✅ **Gemini Live BIDI integration is implemented in the Strands SDK** — `BidiGeminiLiveModel` defaults to **`gemini-3.1-flash-live-preview`** with audio I/O, transcription, native image input, tool calls/results, usage, session resumption, and interruption handling. This is the "reasoning-capable LLM with cameras/tools" core from §7.
- ✅ **Phase-1 relational schema + CSV migration** exist (properties, stakeholders/roles, tasks + stages, checklist templates, inspections, photos, work orders, reports, maintenance).
- ⬜ **Not yet built:** the STR application agent assembly (system prompt/persona, tool orchestration), the domain tools (camera, journal, memory, Google, email, **Slack `files_upload_v2`**, telephony), the **Escapia** client/tool, report assembly + delivery, the backend API + realtime voice bridge, and the **entire Next.js frontend**.
- 🔧 **Schema extensions required before v1:** Addendum-1 fields (`Report.delivery_channel`/`delivered_at`/`delivery_status`, `Photo.include_in_report`) and Addendum-2 fields (Escapia native IDs, `SyncCursor`, `HousekeepingStatusMap`) are **not yet present** in the live schema. Tracked in TASKS.md `M1`.

**Confirmed frontend stack:** Next.js (App Router) mobile-first **PWA** · **AI Elements** (Vercel, on shadcn/ui) for the bidirectional agent surface · **shadcn/ui** foundation · Vercel AI SDK v5 · editorial "Paper, Ink & Ember" design language (see DESIGN.md).