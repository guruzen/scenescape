# BT-13 Evidence — Accuracy Qualification

## Status

**BLOCKED ON BT-12 REAL CHANNEL SOUNDING HIL**

The BT-13 qualification harness is implemented and simulator-qualified, but BT-13 cannot be marked COMPLETE until a real Channel Sounding stack from BT-12 produces ground-truth-aligned site data.

## Software readiness delivered

- deterministic one-to-one truth/fix timestamp alignment;
- configurable alignment tolerance;
- horizontal, vertical and 3D P50/P90/P95/P99/mean/max;
- accepted-fix availability separated from accuracy-when-accepted;
- update-rate and latency statistics;
- raw-versus-tracked comparison;
- scenario matrix preserving poor-condition results;
- CSV export without person/display-name fields;
- environment/system metadata for commit, hardware and configuration traceability;
- anti-cherry-picking behavior when samples fall outside alignment tolerance.

## Implementation commits

- `0192162ea66d` — ground-truth qualification harness.
- `6e03f42b1a02` — deterministic qualification harness tests.

## Software tests

`control-api/tests/test_bluetooth_qualification.py` covers:

- deterministic percentile reporting;
- separation of accuracy from availability;
- configurable good/degraded acceptance;
- alignment tolerance / no sample borrowing;
- raw versus tracked comparison;
- privacy-minimized CSV output;
- LOS versus NLOS scenario matrix.

These tests validate the qualification machinery, not a real-site accuracy claim.

## Missing release evidence

BT-13 still requires real BT-12 data for:

1. surveyed static points;
2. dynamic walking/asset paths;
3. LOS and floor-edge cases;
4. body block / NLOS / multipath;
5. anchor-loss conditions;
6. repeatability;
7. measured update rate and latency;
8. exact hardware, firmware, SDK, adapter build and commit metadata;
9. formal report plus raw anonymized artifacts where policy permits.

## Claim guardrail

No real-site P95 target is currently proven. Accuracy claims remain blocked until the above evidence exists.

## Rollback

The qualification harness is offline/report tooling and does not alter the runtime positioning path.
