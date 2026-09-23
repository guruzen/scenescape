# BT-08 — Tracking Engine

**Status:** PLANNED  
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
- [ ] Constant velocity.
- [ ] Stop/start/turn.
- [ ] Dropout expiry.
- [ ] Out-of-order.
- [ ] Impossible jump.
- [ ] Calibration revision.
- [ ] Large tag count.

## Evidence required
- [ ] Raw vs tracked jitter/error.
- [ ] Velocity error.
- [ ] State timeline.

## Acceptance criteria
- [ ] Jitter reduced within latency budget.
- [ ] Predictions expire.
- [ ] Deterministic state/velocity.

## Out of scope
- Vision fusion.
- Incidents.

## Rollback / disable strategy
Disable tracker; publish raw solves marked raw.

## Implementation record
- Implementation commit: _not yet recorded_
- Evidence: _not yet recorded_
- Known deviations: _none at planning baseline_

## Continuation prompt
> Implement BT-08 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-08, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-08:`.
