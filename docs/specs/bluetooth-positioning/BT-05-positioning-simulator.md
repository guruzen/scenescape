# BT-05 — Deterministic Positioning Simulator

**Status:** PLANNED  
**Dependencies:** BT-04  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective
Generate reproducible truth-known trajectories and ranging faults before real hardware.

## User stories
- Engineer replays exact seed.
- Frontend gets moving tags.
- QA injects NLOS/loss/outage/bad calibration.

## Scope / functional requirements
1. Anchors/tags/trajectories.
2. Ideal range + Gaussian noise, bias, NLOS, outliers, packet loss, jitter, out-of-order, anchor outage.
3. Seeded realtime/accelerated modes.
4. Same normalized contract as real provider.
5. Ground truth isolated.
6. Battery/last-seen simulation.

## Implementation design
- Explicit dev/test component.
- Scenario YAML/JSON.
- Canonical static/walk/forklift/edge/NLOS/outage scenarios.
- Version metadata.

## API, data and events
- Emit BT-06 contract via iterator/MQTT/API; truth separate.

## UX / operational behavior
- Synthetic data clearly marked.

## Security, privacy and failure handling
- Cannot accidentally enable in production.

## Required tests
- [ ] Seed reproducibility.
- [ ] Noise/loss/NLOS.
- [ ] Truth interpolation.
- [ ] Scenario validation.

## Evidence required
- [ ] Scenario files.
- [ ] Truth vs noisy range evidence.
- [ ] Tests.

## Acceptance criteria
- [ ] Same seed=same data.
- [ ] All failure modes available.
- [ ] Solver cannot access hidden truth.

## Out of scope
- Real hardware.
- Accuracy certification.

## Rollback / disable strategy
Remove simulator without production impact.

## Implementation record
- Implementation commit: _not yet recorded_
- Evidence: _not yet recorded_
- Known deviations: _none at planning baseline_

## Continuation prompt
> Implement BT-05 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-05, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-05:`.
