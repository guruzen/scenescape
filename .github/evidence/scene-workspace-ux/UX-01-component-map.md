<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# UX-01 Evidence — Scene Workspace Component and State Map

## Scope

This captures the pre-refactor responsibilities and state ownership for the
React Scene Workspace before navigation changes begin.

## Current top-level owner

`SceneWorkspace` in `modern-ui/src/App.tsx` currently owns all scene-local
operational, analytical, and configuration navigation.

### Data lifecycle responsibilities

- Fetch scene bundle from `/api/v2/scenes/{scene}/bundle`.
- Maintain live scene state from SSE `/api/v2/scenes/{scene}/live/stream`.
- Fall back to polling `/api/v2/scenes/{scene}/live` if SSE fails.
- Maintain object trails from successive live observations.
- Fetch history on demand.
- Fetch trends on demand.
- Fetch runtime overview on demand.
- Refresh the scene bundle after configuration changes.

### Navigation responsibility

The current `tab` state selects one of ten peer destinations:

- Live 2D
- Live 3D
- Camera feeds
- Sensors & telemetry
- Geometry
- Hierarchy
- Camera calibration
- Runtime
- History & replay
- Trends & analytics

This flat navigation is the primary target of UX-10 through UX-15.

### View-control state currently owned by SceneWorkspace

| State | Current purpose | Future owner |
| --- | --- | --- |
| `liveView` | Enable live objects | Monitor workspace |
| `showTrails` | Object trails | Layer controls |
| `showTelemetry` | Telemetry HUD/text | Diagnostic controls |
| `showHeatmap` | Position heat overlay | Layer controls |
| `showVelocity` | Velocity vectors | Layer controls |
| `visualizeRois` | Regions/tripwires | Layer controls |
| `showFloor` | 3D floor | 3D view controls |
| `projectCameraFrames` | 3D camera projection | 3D view controls |
| `cameraOpacity` | Camera projection opacity | 3D view controls |
| `selectedCameraId` | Camera selection | Monitor/inspector selection |
| `cameraView` | Selected camera POV | 3D view controls |
| `lightIntensity` | 3D lighting | 3D view controls |
| `runtimeOverview` | MQTT/runtime health | Status header / Analyze |

## Current child components

### Operational rendering

- `Map2D`
  - scene map/media loading
  - region/tripwire/sensor/camera overlays
  - tracked objects
  - trails
  - telemetry text/HUD
  - heatmap and velocity 2D overlays
- `ThreeScene`
  - GLB/3D scene
  - tracked assets
  - spatial overlays
  - cameras and projected frames
  - floor and lighting
  - heatmap and velocity 3D overlays
- `CameraFeeds` / `CameraFeed`
  - live camera snapshot refresh
  - optional per-camera telemetry
- `SceneSensorTelemetry`
  - retained sensor observations

### Analyze

- Inline History & replay panel
- Inline Trends & analytics panel
- `SceneRuntime`

### Configure

- `SpatialEditor`
- `HierarchyEditor`
- `CameraCalibration`

Scene, camera, and sensor inventory editors remain reachable through the broader
application navigation and will be reconciled with Configure mode during the
information-architecture phase without duplicating ownership.

## Candidate reusable UX components

The following extraction boundaries are preferred:

- `ScenePrimaryNav`
- `SceneSecondaryNav`
- `SceneStatusHeader`
- `SceneViewToolbar`
- `LayerControls`
- `DiagnosticControls`
- `SceneTelemetryHud`
- `SceneInspector`
- `MonitorWorkspace`
- `AnalyzeWorkspace`
- `ConfigureWorkspace`

## State ownership decision

No new global state library is required for the first refactor.

Scene-local state remains under `SceneWorkspace` and is passed down through
small components. Selection state introduced by the inspector should also remain
scene-local unless a concrete cross-route requirement appears.

## Guardrails before navigation refactor

1. The ten existing destinations must map one-to-one into the new information
   architecture.
2. Existing live-stream lifecycle and cleanup behavior must not move until a
   feature requires it.
3. Existing scene-scope authorization remains server-side and unchanged.
4. Renderer state that is meaningful only to 3D must not leak into 2D controls.
5. No capability may disappear merely because the flat tab row is removed.
