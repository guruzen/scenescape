# BT-14 Evidence — Operational Integration

## Status

**SOFTWARE IMPLEMENTED; COMPLETION BLOCKED BY BT-13 DEPENDENCY**

The operational adapter is implemented and tested against synthetic/tracked inputs. The feature cannot be certified COMPLETE under the program Definition of Done while BT-13 remains blocked.

## Software readiness delivered

- quality-gated BLE positions into region/tripwire processing;
- region hysteresis and transition confirmation;
- event debounce;
- tripwire crossing direction;
- low-quality/stale/predicted suppression;
- Bluetooth incident context and source provenance;
- incident/source filters;
- operational health summary covering low battery, unknown battery, stale/degraded tags, offline anchors and inactive providers;
- configurable telemetry staleness.

## Implementation commits

- `1197156183cc` — quality-gated spatial event adapter.
- `e6038efdc0bd` — event-time debounce behavior.
- `9afceec55f62` — configurable telemetry staleness.
- `c8f24e3f8d03` — incident context and filters.
- `289bfe4fb687` — operational health.
- `a017c3afca5c` — health and incident regression tests.
- `c59883efb6d3` — incident regression cleanup.

## Software tests

`control-api/tests/test_bluetooth_pipeline.py` includes BT-14 coverage for:

- region hysteresis into the shared incident model;
- low-quality suppression;
- tripwire direction and duplicate-event debounce;
- Bluetooth versus vision incident filtering;
- actionable health summary.

## Remaining acceptance work

- certify behavior against BT-13-qualified real-site tracks;
- capture integrated incident/health screenshots;
- explicitly re-run permission/redaction and vision-incident regression in the final release gate.

## Rollback

Disable the BLE spatial-event adapter; Bluetooth live positioning remains available and existing vision incident processing is unchanged.
