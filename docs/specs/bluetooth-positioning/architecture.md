# Architecture — Bluetooth High-Accuracy Positioning

## Decision
Implement Bluetooth positioning as a vendor-neutral subsystem:
1. FastAPI/PostgreSQL control plane.
2. Hardware/provider adapters.
3. MQTT/service-auth ingestion.
4. Asynchronous positioning worker.
5. Temporal tracker/quality layer.
6. Existing SceneScape live/history/2D/3D integration.

Preferred precision provider: Bluetooth Core 6.x Channel Sounding. AoA may be supported by capable providers. RSSI remains a lower-accuracy fallback.

## Flow
```text
React -> FastAPI /api/v2/bluetooth/* -> PostgreSQL config/calibration/assignment
                                          |
Provider/gateway -> normalized MQTT/API measurements
                                          |
                              bluetooth-positioning-worker
                  validate -> align -> robust solve -> covariance
                                          |
                                       tracker
                       filter -> velocity -> expiry -> quality
                                          |
                           solved/tracked position stream/history
                                          |
                     bundle/live/SSE -> 2D/3D -> spatial analytics
```

## Provider abstractions
### RangingProvider
Maps vendor identity to SceneScape IDs, advertises capabilities/capacity, schedules ranging and emits normalized range/direction records.
### DeviceTelemetryProvider
Normalizes Battery Service, Device Information Service or vendor telemetry with source/freshness and bounded polling.
### PositionSolver
Consumes coherent measurements + active anchor calibration; emits raw position, covariance/uncertainty, residuals and accepted/rejected anchors.
### PositionTracker
Produces smoothed position, velocity/heading, prediction and stale state.
### EntityFusionProvider
BT-15 only; associates BLE and vision tracks while retaining both source observations.

## Identity
Do not use BLE MAC as primary identity.
- anchor_id/tag_id: immutable SceneScape IDs.
- serial_number: human-visible hardware identity.
- provider_device_id: vendor stable identity.
- bluetooth_address: optional rotating transport metadata.
- entity_id: optional business assignment.
Assignments are versioned intervals with actor and reason.

## Persistence
Low-rate: anchors, tags, providers, assignments, calibration profiles/revisions.
High-rate: normalized measurements (short retention), raw solves, tracked positions, device telemetry.
Use native Resource for low-rate data where suitable; use purpose-built indexed storage for high-rate paths.

## Positioning
### Dimensionality
- 2D: x/y, fixed/constrained z.
- 2.5D: tag-class constrained z.
- 3D: only when vertical geometry is observable.
### Solver baseline
Weighted nonlinear least squares; robust loss; outlier rejection; NLOS down-weighting; residual RMS; GDOP/geometry metric; covariance/uncertainty; singular geometry detection.
### Tracker baseline
Constant-velocity Kalman/EKF using solver covariance, bounded prediction and reset after long gaps/impossible jumps/calibration revision changes.

## Quality contract
Every position includes good/degraded/predicted/stale/unavailable state, horizontal uncertainty, optional vertical uncertainty, score, anchors visible/used, residual RMS, GDOP, freshness, method and algorithm versions. Channel Sounding method alone never means high accuracy.

## Channel Sounding deployment
Preferred: powered fixed anchor as initiator/gateway side and mobile battery tag as reflector, when hardware supports it. Provider adapter may reverse roles. Provider exposes actual session capacity and achieved update rate; SceneScape assumes no unlimited concurrent ranging.

## Coordinates
Solver coordinates are SceneScape scene-local metres. Map pixels, lat/lon and child-scene coordinates require explicit transforms.

## MQTT
- scenescape/data/bluetooth/range/{scene}/{anchor}/{tag}
- scenescape/data/bluetooth/device/{scene}/{device}
- scenescape/data/bluetooth/position/{scene}/{tag}
- scenescape/event/bluetooth/{scene}/{event}
schema_version is mandatory.

## Security/privacy
Browser uses existing Keycloak/OIDC. Provider gateways use service identity. Scene scope applies to devices/assignment/positions. Person assignment and exact history can require stronger roles. Mutations audited. MQTT ACLs are least privilege. Replay uses timestamps/sequence/session when possible. Secrets/pairing material never enter normal browser resource payloads.

## Failure behavior
Anchor offline => exclude and degrade quality. Tag loss => good/degraded/predicted/stale/unavailable. Skew/out-of-order => policy rejection/down-weighting. Bad calibration => diagnostics + revision rollback. Provider outage => old fix ages out; no fabricated coordinate. Queue/DB pressure => bounded buffering/drop metrics. Solver divergence => unavailable/degraded, never NaN.

## Observability
Measure ingress/rejection rates, lag, active tags/anchors, solver latency percentiles, update rate, uncertainty/residual distribution, stale counts, provider sessions, MQTT drops and battery alerts.

## Deployment
Optional positioning worker/provider config; disabled by default until enabled. Upgrade/rollback must preserve existing SceneScape.
