# SceneScape operations-first UX and history architecture

**Design baseline:** 16 September 2026  
**Repository baseline:** `guruzen/scenescape` tag `2026.2.0`, commit `8b1ffafc8cdfbb31f5fa4e18d700bcbfa4a4160e`.

## Product decision

Modernize SceneScape as an operations product, not merely a React replacement for Django forms. The primary information architecture is:

1. **Operations / data plane** — shift overview, live scene, incidents, history/replay, trends, handover, feed/service health.
2. **Configuration / control plane** — sites/floors/scenes, maps, cameras/sensors, calibration, regions/fences/tripwires, alert rules and controlled publication.
3. **Administration** — identity/authorization, retention, audit, integrations and evidence permissions.

The same resource can appear in both planes for different purposes. A camera is configured/calibrated in Configuration and monitored for health/evidence in Operations. A tripwire is authored in Configuration and investigated as an event/incident in Operations.

## Daily operator experience

The landing page should answer: **What needs attention? Where? Can I trust the observations? Who owns the response? What changed during this shift?**

The scene remains the primary context. Incidents, occupancy, flow and source health must share the same scene scope. Missing observations must never be silently interpreted as zero occupancy or an empty area.

### Incident workflow

Core lifecycle: `New -> Acknowledged -> Investigating -> Resolved`, with reopen support and an auditable action history. Detector condition state is distinct from workflow state: acknowledging an event does not clear a physical condition.

Incident detail should retain severity, condition state, source time, rule revision, scene/zone, source/track references, correlated events, assignment, notes, evidence availability and response timing.

### History and replay

SceneScape 2026.2.0 documents PostgreSQL as static-configuration storage and explicitly states that video/object-location data is not stored by the core product. Therefore historical replay and trends need a new durable data layer rather than a new UI tab over existing storage.

Recommended flow:

```text
Scene Controller
      |
      v
Analytics (regulated scene output + region/tripwire events)
      |
      v
Durable collector / retry spool
      |
      +--> Observation + event store
      +--> Incident/action store
      +--> Aggregation jobs
      +--> Configuration revision journal
      |
      v
Authorized history/query API
      |
      v
Operations workspace: replay, trends, handover, evidence
```

Replay must use the scene/map/rule revision active at the historical timestamp. It must expose source coverage, late data and gaps. Metadata replay is not video playback; recorded evidence requires an explicit recorder/integration and independent retention policy.

## Historical data model

Persist at least:

- observation timestamp, received timestamp, scene, object/track identifier, class, position, velocity and relevant attributes;
- immutable region/tripwire analytics events with direction, counts, entered/exited objects and dwell where available;
- feed/collector coverage intervals and quality state;
- incident/action records, assignment, acknowledgement, notes and resolution;
- configuration revisions required to interpret retained history;
- time-bucket aggregates for occupancy, crossings, dwell, throughput and data quality.

Do not equate track IDs with verified identities, crossing events with unique visitors, or missing observations with zero.

## Control-plane authoring

Configuration changes should follow `Draft -> Validate -> Preview -> Publish -> New revision / rollback-by-revision`. Avoid silent mutation of live geometry and rules. Geometry authoring needs map context, coordinate/scale validation, polygon self-intersection checks, explicit tripwire direction and versioned publication.

Alert rules sit above raw geometry. Geometry defines **where**; rules define **when an event deserves attention, severity, owner, schedule, persistence, suppression/escalation and response expectations**.

## Security and API boundary

Keep existing `/api/v1` behavior and machine-token integrations compatible. Introduce Keycloak-aware `/api/v2` endpoints behind server-side authorization. React-side filtering is not authorization.

Proposed API groups:

- `/api/v2/scenes` and `/api/v2/scenes/{id}/snapshot`
- `/api/v2/events`
- `/api/v2/incidents` and `/api/v2/incidents/{id}/actions`
- `/api/v2/history/trajectories`, `/metrics`, `/coverage`
- `/api/v2/configuration/drafts` and publish actions
- `/api/v2/handovers`
- `/api/v2/exports`

Responses should distinguish unauthorized, unavailable, partial coverage and valid no-data states.

## Migration rule

Do not drop advanced native workflows while modernizing. Before replacing a Django route, verify parity for scene create/edit/delete, map/mesh handling, cameras/sensors, manual/automatic calibration, 2D/3D visualization, regions/tripwires, sensor correlation, object properties, supported adapters/models/pipelines and permissions. Where parity is incomplete, retain an explicit authenticated bridge to the legacy UI.

## Acceptance gates

Production claims require tests demonstrating:

- acknowledged incidents survive restart;
- duplicate deliveries do not duplicate counts/incidents;
- historical events replay against historical configuration;
- missing source coverage is visibly degraded rather than represented as zero;
- unauthorized site/scene data cannot be retrieved by API, stream or export;
- concurrent operator actions cannot silently overwrite each other;
- retained evidence availability matches the recorder manifest;
- historian/service failure never renders as a healthy empty screen.

## Source foundation

- `docs/user-guide/index.md` — architecture and persistence boundary.
- `docs/user-guide/how-to-guides/ui-tutorial.md` — existing scene UI and 2D/3D workflow.
- `docs/user-guide/microservices/analytics/analytics.md` — Analytics service responsibilities.
- `docs/user-guide/microservices/analytics/data_formats.md` — regulated scene and region/tripwire event formats.

This document distinguishes documented 2026.2.0 capabilities from proposed operational extensions.