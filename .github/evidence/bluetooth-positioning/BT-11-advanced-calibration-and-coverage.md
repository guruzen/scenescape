# BT-11 Evidence — Advanced Calibration and Coverage

## Status

**COMPLETE**

## Scope delivered

BT-11 adds survey-driven Bluetooth calibration diagnostics and revisioned bias
correction without rewriting raw range observations.

Delivered behavior:

- known XYZ survey points with repeated range samples;
- bounded raw survey sample storage;
- robust per-anchor bias/variance estimation using median/MAD rejection;
- explicit sample/accepted/rejected quality counts;
- draft bias-corrected calibration revisions;
- explicit publish/activate and prior-revision restore;
- deterministic 2D range GDOP grid;
- separate observed RF survey diagnostics;
- bounded coverage grid;
- calibration UI overlays for survey points, theoretical GDOP and survey-anchor links;
- per-anchor bias quality readouts and bias-corrected draft creation.

## Implementation commits

Backend:

- `f6536bb57fe3` — survey bias and coverage diagnostics.
- `1b1d746bf384` — survey/bias/coverage APIs.
- `a23222195462` — synthetic bias, coverage and rollback tests.

UI:

- `5c71e2d5cf90` — survey/coverage client contracts.
- `484700302cdc` — survey coverage in calibration workspace.
- `72340d05096f` — bias/coverage controls and overlays.
- `104a23ec04da` — calibration coverage UI contract.
- `5ffa8648864e` — integrated survey coverage E2E.
- `23158265e279` — focused BT-11 backend/UI gate.

## Bias-recovery quality report

The deterministic survey fixture uses four anchors and four known survey points,
with five repeated measurements per anchor/point.

Injected anchor range biases:

| Anchor | Injected bias | Recovery requirement | Outlier evidence |
| --- | ---: | ---: | --- |
| a1 | +0.35 m | recovered within ±0.03 m | normal samples |
| a2 | -0.18 m | recovered within ±0.03 m | normal samples |
| a3 | +0.24 m | recovered within ±0.03 m | one +4.0 m bad survey sample rejected |
| a4 | -0.12 m | recovered within ±0.03 m | normal samples |

The estimator records:

- total sample count;
- accepted sample count;
- rejected sample count;
- robust bias;
- standard deviation;
- median;
- MAD;
- outlier threshold.

The a3 regression explicitly requires at least one rejected sample.

## Before/after validation error

A separate truth point at `(4.2, 6.1, 1.0)` is solved using the injected
anchor biases.

| Validation mode | Calibration metadata | Result |
| --- | --- | --- |
| Before correction | no per-anchor range bias | non-zero biased horizontal solution |
| After correction | recovered `range_bias_m` and `range_stddev_m` | horizontal error is lower than the uncorrected result and < 0.08 m |

The acceptance regression therefore proves improvement on a validation point
that is not one of the survey-point coordinates.

BT-11 does not claim this synthetic software result as real-site Bluetooth
accuracy; hardware/site qualification remains BT-12/BT-13.

## Revision / rollback evidence

`create_bias_calibration_revisions()` creates new **draft** revisions instead
of mutating the active calibration.

The regression verifies:

1. four draft revisions are created;
2. the a1 draft is revision 2 and contains the recovered bias;
3. publishing revision 2 makes it active and retires revision 1;
4. reactivating revision 1 restores it;
5. the formerly active revision 2 becomes retired.

This provides an explicit rollback path.

## Theoretical geometry vs observed RF

`coverage_diagnostics()` returns two intentionally separate datasets.

### Theoretical geometry

- model: `2d-range-gdop`;
- active anchor geometry only;
- fixed-z plane;
- per-cell GDOP;
- per-cell state: good/degraded/poor/unavailable.

The deterministic regression uses a 0..10 m grid in x/y at 5 m spacing and
requires exactly 9 cells from four active anchors.

### Observed RF

- source: `survey_samples`;
- known survey-point coordinates;
- sample-derived quality/statistics.

The same regression requires four observed survey points and explicitly checks
that the theoretical model and observed RF source remain distinct.

## Bounds / abuse resistance

Tests verify:

- per-survey-point sample count is bounded by
  `BLUETOOTH_SURVEY_MAX_SAMPLES_PER_POINT`;
- an attempted sample beyond the configured bound is rejected;
- coverage grids larger than 10,000 cells are rejected;
- survey coordinates and measurements must be finite;
- surveys require an existing scene/anchor relationship.

## UI evidence

The calibration workspace exposes:

- survey points on the scene map;
- **Theoretical GDOP** toggle;
- **Observed RF surveys** toggle;
- **Survey-anchor links** toggle;
- per-anchor robust bias/sample quality;
- **Create bias-corrected drafts** action.

The integrated BT-11 browser test provisions four anchors and active
calibrations through the real API, creates a survey point and repeated biased
samples, opens the calibration UI, verifies survey/bias controls, renders GDOP
cells and survey-anchor links, and captures the coverage screenshot.

## CI evidence

Focused GitHub Actions run:

`https://github.com/guruzen/scenescape/actions/runs/36292346801`

Backend:

```text
5 passed in 1.79s
```

Integrated Playwright:

```text
1 passed (6.1s)
```

Scenario:

`BT-11 integrated survey diagnostics render observed RF and theoretical GDOP`

The same UI job passed TypeScript typecheck and production build.

## Coverage screenshot artifact

Generated screenshot:

- `bt11-survey-coverage.png`

GitHub Actions artifact:

- name: `bt11-survey-coverage-evidence`
- artifact ID: `10922606788`
- size: 235,647 bytes
- SHA-256: `64fac82d12ba373b915bad2223108872e541f3e144b524cc1e343fb4876f16ba`
- expires: 2026-10-27

## Acceptance evidence

- [x] Known synthetic bias is recovered within tolerance.
- [x] Bad survey outlier is rejected robustly.
- [x] Bias correction improves a held-out validation solve.
- [x] Coverage/GDOP output is deterministic.
- [x] Weak geometry is represented by GDOP geometry state.
- [x] Draft -> publish -> revert works.
- [x] Theoretical geometry and observed RF are separate datasets.
- [x] UI overlay is exercised through integrated Playwright.
- [x] Before/after validation evidence is recorded.
- [x] Coverage screenshot is captured.
- [x] Calibration quality/sample report is recorded.

## Known limitations / deferred items

- BT-11 is a software/survey calibration capability, not a hardware accuracy
  certification.
- Coverage geometry is 2D range GDOP on a selected fixed-z plane.
- Observed RF coverage is only as representative as the collected survey
  points.
- Real Channel Sounding provider integration belongs to BT-12; real-site
  accuracy qualification belongs to BT-13.

## Rollback

Reactivate the previous calibration revision. Raw survey samples and raw range
measurements remain unchanged, so calibration rollback is non-destructive.
