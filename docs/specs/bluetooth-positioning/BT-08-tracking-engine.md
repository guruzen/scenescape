# BT-08 — Tracking Engine

**Status:** COMPLETE  
**Dependencies:** BT-07  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective

Stabilize raw solves temporally and produce velocity/freshness with bounded prediction.

## User stories

- Operator sees stable motion.
- Support knows measured vs predicted.
- Apps get velocity/heading/stale.

## Scope / functional requirements

1. Constant-velocity Kalman/EKF.
2. Use solver covariance.
3. Velocity/optional heading.
4. Bound prediction horizon.
5. good/degraded/predicted/stale/unavailable.
6. Reset on scene/calibration change, long gap, impossible jump.
7. Persist tracked provenance.

## Implementation design

- State per scene/tag and evicted.
- Event-time policy.
- Tag-class motion limits configurable.
- No smoothing across identity/assignment changes.

## API, data and events

- Tracked position adds velocity/tracker fields.

## UX / operational behavior

- Predicted/stale later rendered distinctly.

## Security, privacy and failure handling

- Bound memory + reset metrics.

## Required tests

- [x] Constant velocity.
- [x] Stop/start/turn.
- [x] Dropout expiry.
- [x] Out-of-order.
- [x] Impossible jump.
- [x] Calibration revision.
- [x] Large tag count.

## Evidence required

- [x] Raw vs tracked jitter/error.
- [x] Velocity error.
- [x] State timeline.

## Acceptance criteria

- [x] Jitter reduced within latency budget.
- [x] Predictions expire.
- [x] Deterministic state/velocity.

## Out of scope

- Vision fusion.
- Incidents.

## Rollback / disable strategy

Disable tracker; publish raw solves marked raw.

## Implementation record

- Implementation commits: `019b584f8c66`, `311022ef40f8`, `eef4e0f43f37`, `dd0da8afc576`, `dc8940d13644`, `92c5071729f7`, `8ee126874dab`, `7b0ced184d9d`, `92a34d7faacb`, `c08b1062652a`, `276ef568625d`, `09a81d076ea9`, `70b70ef54174`, `5e277c060ccb`, `521060c401ed`, `48f55495eac9`
- Evidence: `.github/evidence/bluetooth-positioning/BT-08-tracking-engine.md`
- Known deviations: Solver v1 exposes horizontal/vertical uncertainty rather than a full covariance matrix; the tracker converts those uncertainty values into a conservative diagonal measurement covariance.

## Continuation prompt

> Implement BT-08 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-08, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-08:`.
