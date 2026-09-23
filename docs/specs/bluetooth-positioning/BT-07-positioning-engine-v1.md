# BT-07 — Positioning Engine v1

**Status:** PLANNED  
**Dependencies:** BT-04, BT-06  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective
Compute robust quality-aware 2D/2.5D positions from coherent ranges and calibrated anchors.

## User stories
- Operator gets only supportable coordinates.
- Engineer sees residuals/used-rejected anchors.
- QA quantifies error.

## Scope / functional requirements
1. Time-coherent windows.
2. 2D/constrained-z/3D mode based on observability.
3. Weighted nonlinear least squares + robust loss/outliers.
4. Minimum independent anchors.
5. Residual RMS/GDOP/covariance.
6. good/degraded/unavailable.
7. Persist/publish raw solves.
8. Solver version/config.

## Implementation design
- Stable numerical library.
- Initial guess cannot hide divergence.
- Weights use variance/quality/NLOS.
- Detect singular geometry.
- Never clamp invalid solution into map.

## API, data and events
- Canonical raw position + diagnostics.

## UX / operational behavior
- Diagnostics only; rendering BT-09.

## Security, privacy and failure handling
- Bound state/measurements.
- Treat inputs untrusted.

## Required tests
- [ ] Exact geometry.
- [ ] Seeded P50/P95 error.
- [ ] Outlier/NLOS.
- [ ] Insufficient/collinear.
- [ ] 2D vs bad 3D.
- [ ] NaN/divergence.
- [ ] Many-tag performance.

## Evidence required
- [ ] Error table.
- [ ] Residual/uncertainty samples.
- [ ] Performance/tests.

## Acceptance criteria
- [ ] Error quantified.
- [ ] Quality degrades correctly.
- [ ] No invalid numerics serialized.
- [ ] Method/version/anchors/uncertainty present.

## Out of scope
- Tracking.
- Real hardware claim.

## Rollback / disable strategy
Disable solver; continue raw collection.

## Implementation record
- Implementation commit: _not yet recorded_
- Evidence: _not yet recorded_
- Known deviations: _none at planning baseline_

## Continuation prompt
> Implement BT-07 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-07, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-07:`.
