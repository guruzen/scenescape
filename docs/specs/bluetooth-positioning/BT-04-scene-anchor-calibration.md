# BT-04 — Scene Anchor Calibration

**Status:** IN_PROGRESS  
**Dependencies:** BT-02, BT-03  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective

Place anchors precisely in SceneScape metres using versioned calibration and geometry validation.

## User stories

- Installer clicks map, sets height/orientation, saves.
- Installer sees weak geometry.
- Support restores prior revision.

## Scope / functional requirements

1. Scene-specific revisions.
2. Map click -> scene metres.
3. x/y/z/orientation and z provenance.
4. Render anchors.
5. Warn duplicate/near-duplicate/collinear geometry.
6. Draft then publish.
7. Revision history/rollback.

## Implementation design

- Reuse existing map transforms.
- Calibration separate from hardware identity.
- Advanced GDOP/bias deferred BT-11.
- Define child-scene transforms.

## API, data and events

- Calibration profile/revision endpoints.

## UX / operational behavior

- Show serial/coords/height/orientation + geometry warnings.
- Never use map pixels directly.

## Security, privacy and failure handling

- Privileged/audited change.
- Server validates coordinates.

## Required tests

- [ ] Pixel-to-scene transform.
- [ ] Revision/rollback.
- [ ] E2E placement.
- [ ] Geometry warnings.
- [ ] Child-scene behavior.

## Evidence required

- [ ] Calibration screenshots.
- [ ] Stored calibration sample.
- [ ] Tests.

## Acceptance criteria

- [ ] Four anchors reload identically.
- [ ] Solver gets metres.
- [ ] Active revision explicit/reversible.

## Out of scope

- Survey bias/coverage.
- Ranging.

## Rollback / disable strategy

Reactivate previous calibration or disable anchors.

## Implementation record

- Implementation commit: _not yet recorded_
- Evidence: _not yet recorded_
- Known deviations: BT-04 computes immediate-parent projection for local child scenes as provenance, while authoritative stored coordinates remain in the selected scene local metre frame. Advanced GDOP/bias modelling remains BT-11.

## Continuation prompt

> Implement BT-04 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-04, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-04:`.
