# BT-04 — Scene Anchor Calibration

**Status:** COMPLETE  
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

- [x] Pixel-to-scene transform.
- [x] Revision/rollback.
- [x] E2E placement.
- [x] Geometry warnings.
- [x] Child-scene behavior.

## Evidence required

- [x] Calibration screenshots.
- [x] Stored calibration sample.
- [x] Tests.

## Acceptance criteria

- [x] Four anchors reload identically.
- [x] Solver gets metres.
- [x] Active revision explicit/reversible.

## Out of scope

- Survey bias/coverage.
- Ranging.

## Rollback / disable strategy

Reactivate previous calibration or disable anchors.

## Implementation record

- Implementation commits: `defd07a5f44f`, `be2ccfe1b1f4`, `5365d9616d13`, `a2b155fd6f09`, `d6330bc58c53`, `2207fd662e71`, `048db9c569b3`
- Validated implementation head: `048db9c569b3`
- Evidence: `.github/evidence/bluetooth-positioning/BT-04-scene-anchor-calibration.md`
- Known deviations: BT-04 computes immediate-parent projection for local child scenes as provenance, while authoritative stored coordinates remain in the selected scene local metre frame. Advanced GDOP/bias modelling remains BT-11.

## Continuation prompt

> BT-04 is complete. Continue with BT-05 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md`, BT-04 and BT-05 first. Verify dependencies and the current branch, implement only BT-05, add required tests/evidence, update status/checklists, and commit with a message beginning `BT-05:`.
