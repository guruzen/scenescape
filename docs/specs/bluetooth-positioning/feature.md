# Feature — Bluetooth High-Accuracy Positioning

## Problem
Camera positioning can lose moving people/assets through occlusion, lighting, coverage gaps, privacy constraints and industrial obstacles. SceneScape needs a second positioning modality based on mobile Bluetooth tags and fixed calibrated anchors.

## Outcome
Bluetooth positioning becomes a first-class SceneScape modality. Anchors range tags; SceneScape solves positions in scene coordinates and uses them in Live 2D/3D, history, trails, velocity, regions, tripwires and incidents. BLE/vision fusion is deferred to BT-15.

## Personas and user stories
### Installer
- Commission anchors/tags and identify them by serial number.
- Place anchors on the floor map in real scene coordinates.
- Validate geometry, calibration and ranging visibility.
### Administrator
- Manage lifecycle, provider, capabilities, activation and assignment.
- Assign tag to person/asset/vehicle/tool with audit history.
- See battery/device metadata when available.
### Operator
- See tag coordinate, source, uncertainty, freshness, anchors used, speed and battery.
- See degraded/offline states instead of misleading precision.
### Support engineer
- Diagnose raw measurements, rejection reasons, residuals, geometry/GDOP, provider health and latency.

## Functional requirements
1. Anchor lifecycle: serial, manufacturer/model/firmware, scene, x/y/z, orientation, capabilities, state and last seen.
2. Tag lifecycle: serial, state, capabilities, battery, last seen and positioning state.
3. Versioned tag-to-entity assignment.
4. Versioned scene calibration and rollback.
5. Vendor-neutral range/RSSI/AoA observations.
6. Robust 2D/2.5D/3D positioning with outlier/NLOS handling and uncertainty.
7. Temporal tracking, velocity, bounded prediction and stale state.
8. 2D/3D layers for Bluetooth tags, anchors, uncertainty, trails and diagnostics.
9. Operational health for battery/offline/provider/geometry issues.
10. Spatial analytics/history/incidents consume quality-gated Bluetooth positions.
11. Later BLE + vision fusion preserves source provenance.

## Accuracy semantics
Accuracy is an empirical release property, not a protocol claim.
Initial BT-13 targets:
- High-quality LOS Channel Sounding: target P95 horizontal error <= 0.50 m.
- Representative mixed indoor conditions: target P95 horizontal error <= 1.00 m.
- RSSI-only is best-effort/proximity and never receives a high-accuracy badge.
- Configurable update target 1–10 Hz where hardware/provider capacity permits.
- Default live stale threshold proposal: 2 seconds.
Targets may be revised based on measured evidence.

## Non-functional requirements
- Existing camera/sensor/scene behavior remains compatible.
- High-rate processing does not block FastAPI request handlers.
- UTC at rest; source and ingestion timestamps preserved.
- Raw and solved retention independently configurable.
- Browser OIDC and provider service authentication separated.
- Precise person history follows least privilege and audit.
- Predicted/synthetic data never masquerades as measured truth.
- Helm can disable the subsystem without deleting control-plane config.

## Out of scope
Emergency/life-safety certification, biometrics, indoor route planning, tag firmware ownership, guaranteed centimeter positioning without qualification.
