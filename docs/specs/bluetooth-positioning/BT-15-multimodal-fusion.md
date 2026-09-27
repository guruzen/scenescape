# BT-15 — Multimodal BLE + Vision Fusion

**Status:** BLOCKED  
**Blocker:** BT-13 is not COMPLETE. Fusion software is implemented, but real-site false-association/continuity acceptance cannot be quantified yet.  
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

- [x] One tag/track.
- [x] Ambiguous close tracks.
- [x] Crossing.
- [x] Camera dropout.
- [x] Bad BLE fix.
- [x] Assignment change.
- [ ] False-fusion metrics.
- [ ] Redaction.

## Evidence required

- [ ] False-association/continuity table.
- [ ] Occlusion evidence.
- [ ] E2E screenshots.

## Acceptance criteria

- [ ] Continuity improves within documented false-association threshold.
- [ ] Low confidence remains separate.
- [x] Provenance recoverable.
- [x] No biometric identity inference.

## Out of scope

- Face recognition.
- Cross-site person tracking.

## Rollback / disable strategy

Feature flag disables fusion; source observations unchanged.

## Implementation record

- Implementation commits: `f8e0425c9d0e`, `12045a8af465`, `1a2df093ef40`, `86580f7f3197`, `dd26e6b769e3`
- Evidence: `.github/evidence/bluetooth-positioning/BT-15-multimodal-fusion.md`
- Known deviations: Software ambiguity/privacy/provenance behavior is covered. Quantified false-association and continuity thresholds require BT-13-qualified real-site scenarios.

## Continuation prompt

> Implement BT-15 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-15, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-15:`.
