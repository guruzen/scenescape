# BT-11 — Advanced Calibration and Coverage

**Status:** PLANNED  
**Dependencies:** BT-07  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective
Add survey points, per-anchor bias estimation, geometry/GDOP and coverage diagnostics.

## User stories
- Installer estimates anchor bias from known points.
- Installer sees weak geometry before acceptance.
- Support compares revisions.

## Scope / functional requirements
1. Survey known x/y/z with repeated measurements.
2. Robust per-anchor bias/variance estimation.
3. GDOP grid.
4. Observed/theoretical coverage.
5. Calibration quality residuals/sample count.
6. Explicit publish revision.
7. Compare/revert.

## Implementation design
- Bias is metadata, not raw rewrite.
- Retain bounded raw survey data.
- Separate theoretical geometry from observed RF.

## API, data and events
- Survey/calibration/coverage diagnostics APIs.

## UX / operational behavior
- Map overlays for links/GDOP/coverage/survey points.
- Label geometry vs RF problems.

## Security, privacy and failure handling
- Privileged/audited; no person data required.

## Required tests
- [ ] Recover known synthetic bias.
- [ ] Bad survey outlier.
- [ ] Coverage/GDOP deterministic.
- [ ] Publish/revert.
- [ ] UI overlay.

## Evidence required
- [ ] Before/after error tables.
- [ ] Coverage screenshots.
- [ ] Quality report.

## Acceptance criteria
- [ ] Bias correction improves validation set.
- [ ] Weak geometry visible.
- [ ] Rollback works.
- [ ] Observed/theoretical not conflated.

## Out of scope
- Real hardware qualification.

## Rollback / disable strategy
Reactivate prior calibration revision.

## Implementation record
- Implementation commit: _not yet recorded_
- Evidence: _not yet recorded_
- Known deviations: _none at planning baseline_

## Continuation prompt
> Implement BT-11 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-11, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-11:`.
