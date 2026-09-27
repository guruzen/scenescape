# BT-11 — Advanced Calibration and Coverage

**Status:** COMPLETE  
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

- [x] Recover known synthetic bias.
- [x] Bad survey outlier.
- [x] Coverage/GDOP deterministic.
- [x] Publish/revert.
- [x] UI overlay.

## Evidence required

- [x] Before/after error tables.
- [x] Coverage screenshots.
- [x] Quality report.

## Acceptance criteria

- [x] Bias correction improves validation set.
- [x] Weak geometry visible.
- [x] Rollback works.
- [x] Observed/theoretical not conflated.

## Out of scope

- Real hardware qualification.

## Rollback / disable strategy

Reactivate prior calibration revision.

## Implementation record

- Implementation commits: `f6536bb57fe3`, `1b1d746bf384`, `a23222195462`, `5c71e2d5cf90`, `484700302cdc`, `72340d05096f`, `104a23ec04da`, `5ffa8648864e`, `23158265e279`
- Evidence: `.github/evidence/bluetooth-positioning/BT-11-advanced-calibration-and-coverage.md`
- Known deviations: The theoretical coverage model is 2D range GDOP on a fixed-z plane. Real hardware/site accuracy qualification is intentionally deferred to BT-12/BT-13.

## Continuation prompt

> Implement BT-11 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-11, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-11:`.
