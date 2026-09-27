# BT-15 Evidence — Multimodal BLE + Vision Fusion

## Status

**SOFTWARE IMPLEMENTED; COMPLETION BLOCKED BY BT-13 DEPENDENCY**

Fusion is implemented as opt-in software with privacy and ambiguity guardrails. Completion remains blocked until false-association/continuity behavior is measured using BT-13-qualified real-site data.

## Software readiness delivered

- scene/time/distance/category gating;
- confidence-based BLE/vision association;
- ambiguity preservation instead of forced fusion;
- association hysteresis;
- constituent source IDs and provenance retention;
- identity revision handling;
- source-quality rejection for bad BLE fixes;
- fusion disabled by default;
- no biometric identity inference;
- operator-visible fusion confidence/provenance.

## Implementation commits

- `f8e0425c9d0e` — privacy-preserving BLE/vision fusion.
- `12045a8af465` — optional live-scene fusion integration.
- `1a2df093ef40` — ambiguity, identity and dropout tests.
- `86580f7f3197` — operator fusion provenance/confidence.
- `dd26e6b769e3` — inspector provenance regression.

## Software tests

`control-api/tests/test_bluetooth_fusion.py` covers:

- strong one-to-one association;
- no named identity from visual appearance;
- category mismatch;
- ambiguous crossing tracks;
- association hysteresis;
- assignment/identity revision changes;
- camera/BLE dropout behavior;
- bad BLE fix rejection.

## Remaining acceptance work

- quantify continuity improvement;
- quantify false-association rate;
- exercise qualified occlusion/crossing scenarios from BT-13;
- capture final E2E screenshots and privacy/redaction evidence.

## Rollback

Disable fusion; original BLE and vision observations remain separate and queryable.
