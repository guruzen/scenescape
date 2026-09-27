# BT-07 Evidence — Positioning Engine v1

## Status

**COMPLETE**

## Scope delivered

BT-07 implements the first robust Bluetooth range positioning engine for
SceneScape.

Delivered behavior:

- coherent source-time solve windows;
- newest observation per anchor within the solve window;
- automatic 2D constrained-z vs observable 3D selection;
- explicit forced 2D and forced 3D modes;
- weighted nonlinear least squares using SciPy `least_squares`;
- robust `soft_l1` loss;
- residual-based outlier rejection;
- quality/NLOS/calibration-uncertainty weighting;
- minimum independent-anchor enforcement;
- singular/ill-conditioned geometry detection;
- residual RMS, GDOP and covariance-derived uncertainty;
- good/degraded/unavailable quality states;
- accepted/rejected anchor diagnostics;
- solver name/version provenance;
- persisted canonical raw solve rows.

## Implementation commits

- `8dac007e2cf1` — raw positioning solve persistence.
- `99a1b9f76a5b` — robust range positioning engine.
- `8acb21e34e1d` — raw solve schema migration.
- `f25db632531f` — raw solve persistence in database lifecycle.
- `bfb1c2671335` — accuracy/geometry/NLOS/performance tests.
- `6ca990e90076` — complete Bluetooth backend gate coverage.
- `f85396a3472f` — coherent-window, degraded-state and persistence tests.
- `fc127e82f4f5` — SQLite UTC assertion portability.
- `509fe29c2ffd` — focused BT-07 positioning gate.

## Deterministic accuracy evidence

The BT-07 solver tests use truth-known range geometry.

| Scenario                                    | Deterministic evidence        |
| ------------------------------------------- | ----------------------------- |
| Exact four-anchor square                    | horizontal error < 0.00001 m  |
| Seeded Gaussian noise, 120 solves, σ=0.06 m | P50 < 0.12 m; P95 < 0.30 m    |
| One +4 m low-quality/high-NLOS outlier      | horizontal error < 0.35 m     |
| Many-tag solver path, 250 solves, σ=0.05 m  | P95 horizontal error < 0.35 m |
| Observable 3D geometry                      | 3D Euclidean error < 0.0001 m |

These are simulator/software results only. They are not a real Bluetooth
hardware accuracy claim; real-site qualification belongs to BT-13.

## Quality and observability evidence

### Good

An exact four-anchor square produces:

- `state=good`;
- `dimension=2d_constrained_z`;
- four anchors used;
- residual RMS < 0.00001 m;
- non-null horizontal uncertainty;
- `method=channel_sounding`;
- solver `robust-wls`, version `1`.

### Degraded

A non-collinear three-anchor constrained-z solve is mathematically supported
but minimally redundant. The explicit BT-07 regression verifies:

- a valid coordinate is returned;
- `state=degraded`;
- three anchors visible/used;
- GDOP and horizontal uncertainty remain present;
- method and solver version remain explicit.

### Unavailable

The solver returns no coordinate for:

- insufficient anchors;
- collinear/singular geometry;
- forced 3D when vertical geometry is unobservable;
- invalid/non-finite ranges;
- divergent/non-finite solutions.

Invalid numerics are never clamped into a plausible map coordinate.

## NLOS/outlier evidence

Input weighting combines:

- measurement distance standard deviation;
- calibration range standard deviation;
- input quality;
- NLOS probability.

A high-NLOS/low-quality measurement therefore receives an inflated effective
sigma. Large residuals are rejected when enough independent anchors remain.
The regression accepts either safe rejection or demonstrable down-weighting and
still constrains horizontal error below 0.35 m.

## Coherent-window evidence

The BT-07 database regression inserts:

- an old stale range outside the 250 ms window;
- two current samples from the same anchor;
- current samples from two additional anchors.

`coherent_measurements()` returns only the current solve epoch and only the
newest sample for each anchor. This prevents stale or duplicate-anchor samples
from contaminating a solve.

## Raw persistence evidence

`persist_raw_solve()` stores:

- scene/tag/source timestamp;
- x/y/z when supportable;
- dimension and quality state;
- horizontal/vertical uncertainty;
- score;
- anchors visible/used;
- residual RMS;
- GDOP;
- positioning method;
- solver name/version;
- accepted/rejected anchor diagnostics;
- geometry/covariance/iteration diagnostics.

The persistence regression reloads the SQL row and verifies these fields.

## Performance evidence

The BT-07 deterministic performance regression executes 250 noisy solves and
requires:

- total elapsed time < 8 seconds on the CI-class test environment;
- P95 horizontal error < 0.35 m.

The focused BT-07 gate completed the entire 11-test file in:

```text
11 passed in 1.78s
```

This is a software solver regression, not a provider/radio capacity claim.

## CI evidence

Focused GitHub Actions run:

`https://github.com/guruzen/scenescape/actions/runs/36287950951`

Result:

```text
11 passed in 1.78s
```

The focused gate compiles `bluetooth_positioning.py` and runs only
`control-api/tests/test_bluetooth_positioning.py`, so later BT features do not
affect BT-07 completion evidence.

## Acceptance evidence

- [x] Exact geometry is correct.
- [x] Seeded P50/P95 error is quantified.
- [x] NLOS/outlier behavior is bounded.
- [x] Insufficient and singular geometry return unavailable.
- [x] Auto mode avoids false 3D precision.
- [x] Observable 3D geometry is supported.
- [x] NaN/non-finite input never serializes an invalid coordinate.
- [x] Minimum supported geometry explicitly degrades quality.
- [x] Coherent solve windows/newest-per-anchor are tested.
- [x] Raw solves persist method/version/anchors/uncertainty/diagnostics.
- [x] Many-solve performance is bounded.

## Known limitations / deferred items

- BT-07 persists the canonical raw solve. External Live/SSE/scene publication
  is owned by BT-09 rather than creating a second BT-07 data-plane path.
- 2.5D is represented as `2d_constrained_z` with an explicit fixed/constrained
  z value.
- Real hardware accuracy is not claimed here; BT-12/BT-13 own provider and
  real-site qualification.
- Temporal smoothing/prediction belongs to BT-08.

## Rollback

Disable the solver consumer while continuing BT-06 raw measurement collection.
Persisted raw solves are additive and can remain for diagnostics/history.
