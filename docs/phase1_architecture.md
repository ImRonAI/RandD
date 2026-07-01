# Agentic STR QC Platform: Phase 1 Architecture

## Entity-Relationship Diagram

```mermaid
erDiagram
    CLUSTER ||--o{ PROPERTY : groups
    PROPERTY ||--o{ TASK : has
    TASK ||--o{ TASK_STAGE_EVENT : tracks
    STAGE_DEFINITION ||--o{ TASK_STAGE_EVENT : defines
    CHECKLIST_TEMPLATE ||--o{ CHECKLIST_CATEGORY : contains
    CHECKLIST_CATEGORY ||--o{ CHECKLIST_ITEM_TEMPLATE : defines
    TASK ||--o{ INSPECTION : uses
    CHECKLIST_TEMPLATE ||--o{ INSPECTION : versioned_by
    INSPECTION ||--o{ INSPECTION_ITEM_RESULT : records
    CHECKLIST_ITEM_TEMPLATE ||--o{ INSPECTION_ITEM_RESULT : scored_against
    TASK ||--o{ WORK_ORDER : may_spawn
    PROPERTY ||--o{ WORK_ORDER : may_require
    INSPECTION_ITEM_RESULT ||--o{ WORK_ORDER_SOURCE_ITEM : maps
    WORK_ORDER ||--o{ WORK_ORDER_SOURCE_ITEM : aggregates
    TASK ||--o{ REPORT : summarizes
    INSPECTION ||--o{ REPORT : signs_off_from
    PROPERTY ||--o{ REPORT : signs_off
    STAKEHOLDER ||--o{ STAKEHOLDER_ROLE : assigned
    ROLE ||--o{ STAKEHOLDER_ROLE : grants
    PROPERTY ||--o{ STAKEHOLDER_ROLE : scoped_to
    ROLE ||--o{ NOTIFICATION_TRIGGER : default_target
    PROPERTY ||--o{ PROPERTY_FEATURE : inventories
    PROPERTY_FEATURE_TYPE ||--o{ PROPERTY_FEATURE : typed_by
    PROPERTY_FEATURE ||--o{ MAINTENANCE_CHECK : requires
    PHOTO_MEMORY ||--o{ INSPECTION_ITEM_RESULT : evidence_for
```

## Task Pipeline State Machine (Non-Linear / Parallel)

```mermaid
stateDiagram-v2
    [*] --> TaskCreated
    TaskCreated --> QC
    TaskCreated --> B2B
    TaskCreated --> CLN
    TaskCreated --> OWN

    QC --> WO
    B2B --> WO
    CLN --> Done
    OWN --> Report

    WO --> DoneWO

    Done --> Report
    DoneWO --> Report

    state Report {
      [*] --> PendingSignoff
      PendingSignoff --> ReadyForGuests
      PendingSignoff --> NeedsFollowUp
    }

    Report --> [*]

    note right of TaskCreated
      Stage completion is stored per stage event.
      No strict linear dependency is enforced.
      Owner review may complete before cleaning.
    end note
```

## Phase 2 Design (Deferred)

- Add a bidi agent layer (Strands + Gemini Live) after Phase 1 state consistency is proven.
- Add telephony, Slack, and email escalation adapters as notification channels.
- Add camera-driven checklist scoring tied to `inspection_item_result` evidence records.
- Add route optimization from `cluster` + property geocoding.

## Data model notes from review fixes

- Stage keys are now data-driven via `stage_definition` (instead of hard-coded CHECK values).
- Property amenity/facility modeling is multi-instance via `property_feature` + `maintenance_check` (supports many TVs/bathrooms/patios and recurring checks like batteries/devices).
- Sensitive credentials use ciphertext/secret-reference fields; migration flags plaintext CSV secrets instead of persisting raw secret values.
- Reports can reference a specific inspection (`report.inspection_id`) and work orders can aggregate multiple failed items (`work_order_source_item`).
