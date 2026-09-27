# BT-06 Evidence — Measurement Ingestion and Normalization

## Status

**COMPLETE**

## Scope delivered

BT-06 provides one vendor-neutral persisted range-observation contract shared by:

- deterministic BT-05 simulator replay;
- MQTT `scenescape/data/bluetooth/range/{scene}/{anchor}/{tag}`;
- service-authenticated `POST /api/v2/bluetooth/measurements`.

Delivered behavior:

- commissioned provider/anchor/tag validation;
- scene/topic/config cross-checking;
- provider identity scoping;
- finite numeric validation and site maximum range;
- bounded `provider_details`;
- source timestamp + ingestion timestamp preservation;
- replay/future-skew policy;
- provider/session/sequence idempotency;
- explicit out-of-order rejection;
- durable raw measurement persistence;
- bounded solver handoff;
- raw retention purge;
- aggregate accepted/rejected/lag/queue-drop diagnostics;
- browser tokens cannot write measurements.

## Implementation commits

- `03c240f4ac60` — normalized raw measurement persistence.
- `71413b9da721` — transport-neutral validation/normalization/retention.
- `365bbfe342c2` — BT-06 schema migration.
- `9e00203f9091` — MQTT subscription and worker ingest enablement.
- `271d0ccd5f24` — MQTT routing through normalized ingest.
- `ca9ca9db6cbf` — service-auth measurement POST.
- `302167baf50c` — ingestion/security/retention/backpressure tests.
- `6a607e01a78b` — simulator envelope alignment to the same normalized contract.
- `c48363fef3ea` — malformed payload and persisted-backpressure evidence.
- `770e47a1b084` — normalized MQTT schema rejection metrics.
- `fc17f3434ace` — single-cause MQTT rejection accounting.
- `95fc9ec4179b` — truthful rejection-metric assertions.

## Contract evidence

Normalized range rows persist:

- scene, anchor, tag;
- provider, session and sequence;
- source timestamp and ingestion timestamp;
- method;
- distance and distance standard deviation;
- optional RSSI/AoA fields;
- NLOS probability and quality;
- bounded provider details.

A unique database constraint on
`(provider_id, session_id, sequence)` enforces idempotency below the
transport layer.

## Security and abuse evidence

Tests cover:

- service identity must match `provider_id`;
- browser bearer tokens cannot write measurement data;
- anchor scene mismatch is rejected;
- provider/anchor/tag commissioning and lifecycle state are enforced;
- malformed JSON is rejected as `malformed_json`;
- MQTT payloads over 16 KiB are rejected;
- invalid normalized schemas are rejected as `invalid_payload`;
- rejection metrics retain one truthful cause;
- NaN/non-finite values are rejected by schema validation;
- impossible site ranges are rejected;
- oversized `provider_details` are rejected;
- stale replay and excessive future skew are rejected;
- duplicates and older sequence numbers are rejected.

## Backpressure evidence

The ingestion path persists the accepted raw row before offering its ID to the
bounded solver handoff queue.

The BT-06 backpressure regression replaces the handoff with capacity 1,
ingests two valid measurements and proves:

- both raw rows remain persisted;
- only one ID fits in the solver queue;
- the second handoff is dropped rather than growing memory unbounded;
- `solver_queue_drops` increments to 1.

This preserves raw evidence during downstream processing pressure.

## Retention evidence

`purge_measurements()` removes rows based on `ingested_at` and a configurable
`BLUETOOTH_RAW_RETENTION_S` window. The retention test inserts an old and a
recent record and verifies only the old record is removed.

Scheduling/production lifecycle automation is a later production-hardening
concern; BT-06 establishes and tests the retention primitive.

## CI evidence

GitHub Actions run:

`https://github.com/guruzen/scenescape/actions/runs/36287520796`

Python regression result:

```text
121 passed, 2 failed, 1 warning in 11.37s
```

The two failures are outside BT-06:

1. BT-01 test expects an older schema-downgrade error-message string.
2. BT-16 live-disable regression is missing a `select` import.

No `test_bt06_*` test failed. The same run's UI/build and Helm jobs passed.

## Acceptance evidence

- [x] Simulator, MQTT and service-auth POST use the same normalized persisted contract.
- [x] Malformed/invalid observations are rejected before solver handoff.
- [x] Source and ingest timestamps are both retained.
- [x] Duplicate/out-of-order/replay/skew policy is deterministic.
- [x] Raw retention is configurable and tested.
- [x] Backpressure is bounded and does not delete accepted raw evidence.
- [x] Rejection/lag/queue-drop metrics are exposed.
- [x] Browser write access is denied.
- [x] Ingestion normalization/persistence is independent of transport/request path.

## Known limitations / deferred items

- BT-06 intentionally does not solve positions.
- Actual solver scheduling/consumption is BT-07.
- Vendor SDK normalization occurs at provider adapters; BT-06 consumes the
  normalized contract.
- Production throughput/support-envelope qualification is finalized under
  BT-16; BT-06 has no independent numeric throughput target.

## Rollback

Disable Bluetooth range subscriptions/service ingress. Raw rows remain
preserved until the configured retention policy removes them; BT-06 does not
require destructive rollback.
