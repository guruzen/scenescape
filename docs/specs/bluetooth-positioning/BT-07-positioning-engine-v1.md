# BT-07 — Positioning Engine v1

**Status:** COMPLETE  
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

- [x] Exact geometry.
- [x] Seeded P50/P95 error.
- [x] Outlier/NLOS.
- [x] Insufficient/collinear.
- [x] 2D vs bad 3D.
- [x] NaN/divergence.
- [x] Many-tag performance.

## Evidence required

- [x] Error table.
- [x] Residual/uncertainty samples.
- [x] Performance/tests.

## Acceptance criteria

- [x] Error quantified.
- [x] Quality degrades correctly.
- [x] No invalid numerics serialized.
- [x] Method/version/anchors/uncertainty present.

## Out of scope

- Tracking.
- Real hardware claim.

## Rollback / disable strategy

Disable solver; continue raw collection.

## Implementation record

- Implementation commits: `8dac007e2cf1`, `99a1b9f76a5b`, `8acb21e34e1d`, `f25db632531f`, `bfb1c2671335`, `6ca990e90076`, `f85396a3472f`, `fc127e82f4f5`, `509fe29c2ffd`
- Evidence: `.github/evidence/bluetooth-positioning/BT-07-positioning-engine-v1.md`
- Known deviations: BT-07 persists the canonical raw solve but does not create a separate external publisher; Live/SSE/scene publication is BT-09. 2.5D is represented as constrained-z 2D (`2d_constrained_z`).

## Continuation prompt

> Implement BT-07 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-07, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-07:`.
