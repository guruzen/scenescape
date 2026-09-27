# BT-06 — Measurement Ingestion and Normalization

**Status:** COMPLETE  
**Dependencies:** BT-01, BT-05  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective

Accept simulated/future provider measurements, validate/normalize them and provide bounded high-rate storage/streaming.

## User stories

- Provider publishes one schema.
- Support knows rejection reasons.
- Solver consumes vendor-independent records.

## Scope / functional requirements

1. Bluetooth MQTT subscriptions.
2. Optional service-auth POST.
3. Validate commissioned IDs/scene.
4. Reject invalid numerics/impossible range/oversized metadata.
5. Duplicate/out-of-order/skew policy.
6. Preserve source+ingest time.
7. Raw retention.
8. Ingress/rejection/lag metrics.

## Implementation design

- Dedicated ingest path; no blocking API.
- Idempotency provider/session/sequence.
- Normalize units at adapter boundary.
- Bound queue/provider_details.

## API, data and events

- Service-auth /measurements if needed; no browser write.
- MQTT ACL.

## UX / operational behavior

- Diagnostics aggregate rates/rejections.

## Security, privacy and failure handling

- Provider scope.
- Replay window.
- Topic IDs cross-checked with payload/config.

## Required tests

- [x] Simulator E2E.
- [x] Malformed/NaN/oversized.
- [x] Duplicate/out-of-order.
- [x] Cross-scene spoof.
- [x] Retention.
- [x] Burst/backpressure.

## Evidence required

- [x] Metrics sample.
- [x] Retention sample.
- [x] Throughput/tests.

## Acceptance criteria

- [x] One normalized contract for sim+real.
- [x] Malformed never reaches solver.
- [x] Ingress independent of request path.

## Out of scope

- Solving.
- Vendor SDK.

## Rollback / disable strategy

Disable subscriptions/API; TTL cleans raw data.

## Implementation record

- Implementation commits: `03c240f4ac60`, `71413b9da721`, `365bbfe342c2`, `9e00203f9091`, `271d0ccd5f24`, `ca9ca9db6cbf`, `302167baf50c`, `c48363fef3ea`, `770e47a1b084`, `fc17f3434ace`, `95fc9ec4179b`
- Evidence: `.github/evidence/bluetooth-positioning/BT-06-measurement-ingestion.md`
- Known deviations: BT-06 establishes bounded functional backpressure and retention evidence but does not declare a production throughput support envelope; measured production capacity is deferred to BT-16.

## Continuation prompt

> Implement BT-06 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-06, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-06:`.
