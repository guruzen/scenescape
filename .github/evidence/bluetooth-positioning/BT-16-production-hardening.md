# BT-16 Evidence — Production Hardening and Release

## Status

**SOFTWARE HARDENING IMPLEMENTED IN PART; RELEASE BLOCKED BY BT-12/BT-13**

BT-16 contains substantial runtime/deployment hardening, but production release acceptance cannot close until the real provider and real-site qualification gates are complete and final security/soak/rollback evidence is green.

## Software readiness delivered

- bounded independent retention for measurements, raw positions, tracked positions and telemetry;
- deterministic worker MQTT identity and shared-subscription scale-out ownership;
- worker liveness/readiness distinction;
- fail-closed Helm defaults for Bluetooth;
- retention CronJob with concurrency protection;
- PodDisruptionBudget support;
- unsafe replicated-worker configuration rejected;
- deterministic load benchmark with workload/quality/runtime metrics;
- production runbook;
- threat model;
- evidence-based support matrix;
- non-destructive feature-disable regression.

## Implementation commits

Representative BT-16 commits include:

- `3cfab3416b57` — load benchmark smoke test.
- `0b6980479f7d` — load benchmark in Bluetooth gate.
- `edbf8f2a7e53` — production operations runbook.
- `fe244a5bc655` — Bluetooth threat model.
- `eafa15863bdd` — evidence-based support matrix.
- `c498009dcbe5` — safe Helm render and scale-out.
- `400280e5bea1` — align downgrade-protection regression.
- `b83f56ee769d` — fix disable-path regression import.

## Current gate repair

The previous Bluetooth positioning run reached **131 passed / 2 failed**. Both failures were test-regression defects rather than runtime Bluetooth failures:

1. BT-01 downgrade-protection message had become more specific (`Bluetooth BT-01`) than the test regex.
2. BT-16 disable-path test was missing the SQLAlchemy `select` import.

Both have been patched and the replacement CI run was triggered from `b83f56ee769d`.

## Remaining release blockers

- BT-12 concrete real Channel Sounding adapter/HIL/BOM/security evidence;
- BT-13 real-site static/dynamic/NLOS/repeatability/latency evidence;
- final target-scale load/soak envelope;
- worker/provider/MQTT/DB restart fault injection at release scale;
- demonstrated Helm install/upgrade/rollback;
- migration rollback evidence for the complete release;
- current vulnerability/security scans with no unresolved critical/high issue;
- final privacy and full E2E regression.

## Release rule

Do not mark BT-16 COMPLETE or claim production support until every blocker above is evidenced.

## Rollback

Bluetooth is feature-gated and fail-closed by default. Disable Bluetooth and/or roll back the Helm release while preserving persisted configuration/history according to the documented runbook.
