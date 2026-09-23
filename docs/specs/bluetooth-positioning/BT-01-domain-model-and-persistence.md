# BT-01 — Domain Model and Persistence

**Status:** PLANNED  
**Dependencies:** BT-00  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective
Introduce stable anchor/tag/provider/assignment/calibration resources and migrations.

## User stories
- Admin persists anchors/tags with IDs+serials.
- Admin assigns a tag while retaining history.
- Installer stores scene-bound calibration.

## Scope / functional requirements
1. Validated anchor/tag/provider/assignment/calibration models.
2. Serial required; BLE address is mutable metadata.
3. Lifecycle + optimistic revision semantics.
4. Assignment validity intervals/history.
5. Non-destructive reversible migrations.
6. Unknown telemetry represented explicitly.

## Implementation design
- Reuse native Resource for low-rate config when suitable; otherwise justified tables.
- Domain services enforce invariants.
- Indexes for scene/state/serial/provider identity.
- High-rate tables deferred.

## API, data and events
- Internal services first; public API BT-02.

## UX / operational behavior
- No production UI; fixtures allowed.

## Security, privacy and failure handling
- Scene required for calibrated anchor.
- Assignments capture actor/audit.
- No secrets in resource payload.

## Required tests
- [ ] Migration up/down empty+populated DB.
- [ ] CRUD/invariant tests.
- [ ] Revision conflict.
- [ ] Assignment overlap/close.
- [ ] Scene deletion/cascade policy.

## Evidence required
- [ ] Migration/test output.
- [ ] Serialized fixtures.

## Acceptance criteria
- [ ] No existing data deleted.
- [ ] Round-trip correct.
- [ ] Migrations reversible.
- [ ] Invariants enforced below route layer.

## Out of scope
- Public API/UI.
- Ranging.

## Rollback / disable strategy
Downgrade migration or disable feature resources.

## Implementation record
- Implementation commit: _not yet recorded_
- Evidence: _not yet recorded_
- Known deviations: _none at planning baseline_

## Continuation prompt
> Implement BT-01 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-01, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-01:`.
