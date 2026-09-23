# BT-06 — Measurement Ingestion and Normalization

**Status:** PLANNED  
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
- [ ] Simulator E2E.
- [ ] Malformed/NaN/oversized.
- [ ] Duplicate/out-of-order.
- [ ] Cross-scene spoof.
- [ ] Retention.
- [ ] Burst/backpressure.

## Evidence required
- [ ] Metrics sample.
- [ ] Retention sample.
- [ ] Throughput/tests.

## Acceptance criteria
- [ ] One normalized contract for sim+real.
- [ ] Malformed never reaches solver.
- [ ] Ingress independent of request path.

## Out of scope
- Solving.
- Vendor SDK.

## Rollback / disable strategy
Disable subscriptions/API; TTL cleans raw data.

## Implementation record
- Implementation commit: _not yet recorded_
- Evidence: _not yet recorded_
- Known deviations: _none at planning baseline_

## Continuation prompt
> Implement BT-06 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-06, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-06:`.
