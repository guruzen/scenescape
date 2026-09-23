# BT-15 — Multimodal BLE + Vision Fusion

**Status:** PLANNED  
**Dependencies:** BT-09, BT-13  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective

Associate BLE tags and camera tracks into one logical entity while retaining source provenance and privacy.

## User stories

- Operator avoids duplicate objects when association is confident.
- BLE bridges camera occlusion.
- Support sees fusion rationale/confidence.

## Scope / functional requirements

1. Fusion default off initially.
2. Gate candidates by scene/time/distance/category/assignment.
3. Score/probabilistic association.
4. Hysteresis against fuse/split oscillation.
5. Retain constituent source IDs.
6. Source-quality selection/fusion.
7. Never infer named identity from anonymous visual appearance; explicit tag assignment governs identity.
8. Expose fusion confidence.
9. Split on divergence/assignment change.

## Implementation design

- EntityFusionProvider consumes tracks without mutating originals.
- Start with gated nearest-neighbor/JPDA-like approach if sufficient.
- Document fused covariance/source selection.
- No biometrics.

## API, data and events

- Fused object includes source IDs/confidence; originals queryable.

## UX / operational behavior

- Vision + Bluetooth source chips; low-confidence candidates remain separate.

## Security, privacy and failure handling

- Identity privacy guardrails.
- Names only from authorized assignment.
- Audit assignment changes affecting identity.

## Required tests

- [ ] One tag/track.
- [ ] Ambiguous close tracks.
- [ ] Crossing.
- [ ] Camera dropout.
- [ ] Bad BLE fix.
- [ ] Assignment change.
- [ ] False-fusion metrics.
- [ ] Redaction.

## Evidence required

- [ ] False-association/continuity table.
- [ ] Occlusion evidence.
- [ ] E2E screenshots.

## Acceptance criteria

- [ ] Continuity improves within documented false-association threshold.
- [ ] Low confidence remains separate.
- [ ] Provenance recoverable.
- [ ] No biometric identity inference.

## Out of scope

- Face recognition.
- Cross-site person tracking.

## Rollback / disable strategy

Feature flag disables fusion; source observations unchanged.

## Implementation record

- Implementation commit: _not yet recorded_
- Evidence: _not yet recorded_
- Known deviations: _none at planning baseline_

## Continuation prompt

> Implement BT-15 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-15, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-15:`.
