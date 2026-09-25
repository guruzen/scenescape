# BT-02 — Control Plane API

**Status:** IN_PROGRESS  
**Dependencies:** BT-01  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective

Expose secure APIs for anchor/tag lifecycle, assignment and basic diagnostics.

## User stories

- Admin adds/activates anchor by serial.
- Admin commissions/deactivates/assigns tags.
- Operator reads permitted health without secrets.

## Scope / functional requirements

1. CRUD/list/filter anchors/tags.
2. Explicit state transitions.
3. Assignment create/close/history.
4. Scene scope + role enforcement.
5. Revision conflict handling.
6. Pagination/filtering.
7. Basic diagnostics.

## Implementation design

- Thin handlers over BT-01 services.
- Existing Principal/Keycloak auth.
- Structured duplicate/transition/conflict/scope errors.
- Bound page sizes.

## API, data and events

- Implement /api/v2/bluetooth anchors/tags/assignments baseline.
- Document OpenAPI examples.

## UX / operational behavior

- Errors actionable for BT-03.

## Security, privacy and failure handling

- Management roles enforced.
- Person assignment may need stronger privilege.
- Audit writes.

## Required tests

- [ ] CRUD/filter/lifecycle.
- [ ] Two-scene isolation.
- [ ] Unauthorized browser/service tests.
- [ ] Revision/transition.
- [ ] Oversized input/pagination.

## Evidence required

- [ ] Route/OpenAPI evidence.
- [ ] Focused pytest.
- [ ] Auth denial/conflict examples.

## Acceptance criteria

- [ ] Full lifecycle by API.
- [ ] Cross-scene denied server-side.
- [ ] No secrets returned.
- [ ] Existing endpoints unchanged.

## Out of scope

- React UI.
- Hardware discovery.

## Rollback / disable strategy

Disable routes/feature; preserve resources.

## Implementation record

- Implementation commit: _not yet recorded_
- Evidence: _not yet recorded_
- Known deviations: Tags are intentionally not assigned a permanent scene in BT-02. Until live positioning supplies a trustworthy scene association, full tag inventory and assignment history are administrator-only; scene-scoped non-admin users receive filtered anchor inventory/diagnostics only.

## Continuation prompt

> Implement BT-02 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-02, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-02:`.
