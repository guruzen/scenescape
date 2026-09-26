# BT-13 — Accuracy Qualification

**Status:** PLANNED  
**Dependencies:** BT-12  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective

Establish evidence-backed accuracy, availability, latency and robustness envelopes using ground truth.

## User stories

- Product owner gets defensible claims.
- Installer gets deployment guidance.
- Engineer sees percentile failure modes.

## Scope / functional requirements

1. Surveyed static points and dynamic paths.
2. Floor edges/interior.
3. Walking/asset trajectories.
4. LOS/body-block/NLOS/multipath/anchor-loss variants.
5. Report horizontal/vertical P50/P90/P95/P99, CDF, availability, update rate, latency.
6. Compare raw vs tracked.
7. Measure calibration/geometry effects.
8. Record environment/hardware/config.

## Implementation design

- Qualification harness aligns truth with outputs.
- Clock alignment documented.
- No cherry-picking.
- Report accuracy when good separately from availability of good fixes.

## API, data and events

- No runtime API required; export/report tooling allowed.

## UX / operational behavior

- Optional report view; primary artifact is evidence.

## Security, privacy and failure handling

- Consent/minimized identifiers for human trials.
- Secure qualification logs.

## Required tests

- [ ] Simulator benchmark rerun.
- [ ] Static real-site.
- [ ] Dynamic path.
- [ ] NLOS/anchor failure.
- [ ] Repeatability.
- [ ] Latency/update rate.

## Evidence required

- [ ] Formal report + CSV/plots.
- [ ] Raw anonymized artifacts where policy allows.
- [ ] Exact commit/config/hardware versions.

## Acceptance criteria

- [ ] Targets supported or revised transparently.
- [ ] Poor conditions documented.
- [ ] Accuracy and availability separated.
- [ ] Release claims trace to evidence.

## Out of scope

- Marketing/life-safety certification.

## Rollback / disable strategy

If targets fail, retain experimental status and iterate calibration/solver/provider.

## Implementation record

- Implementation commit: _not yet recorded_
- Evidence: _not yet recorded_
- Known deviations: _none at planning baseline_

## Continuation prompt

> Implement BT-13 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-13, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-13:`.
