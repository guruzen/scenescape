# UX-100–UX-107 Incident Intelligence Evidence

Date: 2026-09-20

## Scope

This follow-up closes the usability gap where retained analytics incidents were displayed as generic rows such as `Scene event · objects` even though the underlying retained Event already carried scene, region/tripwire, event, timestamp, and object context.

## Completed work

- **UX-100 — Preserve retained analytics event context in incident API responses**
  - Incident responses are enriched from their linked `Event` through the existing `event_id`.
  - No database migration was required.
  - Existing retained incidents are enriched at read time.

- **UX-101 — Distinguish region and tripwire incidents**
  - Region and tripwire type/id/name are derived from the authoritative SceneScape MQTT event topic and payload.
  - New incident titles are operationally meaningful, including:
    - `Tripwire crossed · <name>`
    - `Entered region · <name>`
    - `Exited region · <name>`
    - `Region count changed · <name>`
    - `Region activity · <name>`

- **UX-102 — Expose incident object context**
  - API returns object types, object IDs, retained counts, entered/exited collections, event type, action, scene name, rule name, topic, and timestamp.

- **UX-103 — Add server-side incident filters**
  - Supported query filters:
    - scene
    - rule type
    - rule id
    - event type
    - object type
    - status
    - free-text search
    - from/to timestamps
    - result limit
  - Existing scene-scope authorization remains applied before filtering.

- **UX-104 — Add operator filters to React Incidents**
  - Search
  - Scene
  - Rule type
  - Region / tripwire
  - Event
  - Object type
  - Status
  - Time window
  - Clear filters and visible result count

- **UX-105 — Improve incident list and detail context**
  - Rows show meaningful title, scene/rule context, timestamp, status, and object type.
  - Detail view shows scene, rule, rule type, semantic event/action, object types, and object IDs alongside the existing status/assignee/notes/audit workflow.

- **UX-106 — Preserve camera semantics**
  - No camera filter was added because scene-level analytics events do not currently carry a reliable single source-camera identity.
  - Camera filtering should only be introduced after source-camera provenance is explicitly retained/derived.

- **UX-107 — Regression and integration validation**
  - Added backend regression covering region/tripwire enrichment and filters.
  - Added frontend contract coverage for all incident filter controls and enriched context.
  - Hardened previously formatting-sensitive accessibility source checks so Prettier formatting does not create false failures.

## Validation

### Focused incident verification

Workflow run: `35495287728`

Validated implementation head: `6ee4389c240f308e7ac08d73cc0ab813cb8c3a9a`

Passed:

- focused incident API regressions
  - incident action/audit
  - incident enrichment/filtering
  - scene-scope authorization
- Modern UI UX contract tests
- TypeScript typecheck
- production build

### Full Scene Workspace gate

Workflow run: `35495291350`

Passed:

- focused native API integrity regression
- Modern UI regression and production build
- Scene Workspace browser smoke
- integrated native UI/API browser smoke
- evidence upload

## Key implementation commits

- `68ae1a1507cc5076957838a54d8e5e1d239fd21d` — enrich new analytics incident titles
- `4f78b86c8ccb31d074563fc99342bb1767a1d02d` — enrich/filter native incident API
- `a1aa66e4bcea25eaeebe869d2ce7fbcef548d167` — normalize incident filter timestamps
- `0fb19d6b181ee72205be759443c623a8e6d5acd6` — backend enrichment/filter regression
- `fcdecef946d307cf290cc4c86c1184c6cbed0343` — incident context and operational filters
- `7f36f174da6e9ae697a4238eb6dd0b08e331b18b` — incident workspace styling
- `07c5dd0e1786e2d77f247594f64e4d510a0ab91d` — frontend incident contract coverage

## Result

The Incidents page now answers the operator questions:

1. What happened?
2. In which scene?
3. Which region or tripwire caused it?
4. Which object type / object IDs were involved?
5. When did it happen?
6. What is its operational status?

Camera provenance remains an explicit future capability rather than a fabricated filter.
