# BT-14 — Operational Integration

**Status:** BLOCKED  
**Blocker:** BT-13 is not COMPLETE. Operational integration is software-implemented but cannot be release-certified against real qualified Bluetooth tracks yet.  
**Dependencies:** BT-09, BT-10, BT-13  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective

Integrate quality-gated Bluetooth positions into regions, tripwires, incidents, history and health.

## User stories

- Operator gets region/tripwire events from BLE.
- Operator filters incidents/history by BLE source/tag.
- Maintenance sees battery/offline/degraded health.

## Scope / functional requirements

1. Feed qualifying positions into spatial analytics.
2. Hysteresis/debounce at boundaries.
3. Incident context includes tag/authorized assignment/source/quality.
4. History filters.
5. Health for offline/low battery/poor geometry/stale/provider.
6. Configurable alert suppression.
7. Low-quality/stale positions do not trigger unless rule permits.

## Implementation design

- Reuse spatial geometry/event framework.
- Quality gate before event generation.
- Event provenance includes source/uncertainty.
- Maintenance events distinguished from business incidents.

## API, data and events

- Additive incident/history filters and health summary.

## UX / operational behavior

- Filters scene/tag/assignment/region/tripwire/source/status/time.
- Incident detail explains positioning context.

## Security, privacy and failure handling

- Redact person assignment without permission.
- Existing incident audit preserved.

## Required tests

- [x] Boundary jitter.
- [x] Tripwire direction.
- [x] Low-quality suppression.
- [x] History filters.
- [x] Health alerts.
- [ ] Context permissions.
- [ ] Vision incident regression.

## Evidence required

- [ ] Incident/health screenshots.
- [ ] Event fixtures.
- [ ] Integrated tests.

## Acceptance criteria

- [x] No event storms.
- [x] Health actionable.
- [ ] Vision incidents preserved.

## Out of scope

- Fusion.
- Predictive maintenance.

## Rollback / disable strategy

Disable BLE spatial-event adapter; positioning remains visible.

## Implementation record

- Implementation commits: `1197156183cc`, `e6038efdc0bd`, `9afceec55f62`, `c8f24e3f8d03`, `289bfe4fb687`, `a017c3afca5c`
- Evidence: `.github/evidence/bluetooth-positioning/BT-14-operational-integration.md`
- Known deviations: Core operational behavior is implemented and synthetic/integration tested. Completion remains dependency-blocked until BT-13 provides qualified real-site tracks and final permissions/vision-regression evidence is captured.

## Continuation prompt

> Implement BT-14 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-14, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-14:`.
