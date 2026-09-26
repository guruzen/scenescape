<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# UX-10–UX-15 Evidence — Scene Workspace Navigation Foundation

## Scope

This evidence covers the information-architecture foundation:

- UX-10 Primary Monitor / Analyze / Configure navigation.
- UX-11 Monitor secondary navigation.
- UX-12 Analyze secondary navigation.
- UX-13 Configure secondary navigation.
- UX-14 Removal of the legacy single long tab row.
- UX-15 Preservation of direct-entry and default navigation behavior.

## Implementation

The Scene Workspace now uses an explicit navigation contract in
`modern-ui/src/ux/sceneWorkspaceContract.ts`.

Primary modes:

- Monitor
- Analyze
- Configure

Secondary views:

- Monitor: 2D Scene, 3D Scene, Cameras, Sensors
- Analyze: History, Trends, Runtime
- Configure: Scene, Cameras, Sensors, Geometry, Hierarchy, Calibration

Configure → Scene/Cameras/Sensors intentionally route to the existing native
inventory pages until those editors are composed directly into the scene
workspace. Geometry, Hierarchy, and Calibration stay scene-local.

The old ten-item peer tab row was removed.

## Unit test evidence

Command:

```bash
cd modern-ui
npm run test:ux
```

Result:

```text
tests 6
pass 6
fail 0
```

Covered behavior:

1. Legacy destination ↔ UX 2.0 destination round-trip.
2. Stable primary-mode defaults.
3. Direct scene route suffix mapping for geometry/hierarchy/default entry.
4. One-to-one destination integrity.
5. Explicit route-out destinations for configuration inventory.
6. Locked pre-overhaul capability regression baseline.

## Integration/integrity evidence

A repository-state integrity check was run after the implementation commits.

Passed checks:

- Primary navigation exists.
- Secondary navigation exists.
- Legacy flat tab row is absent.
- Legacy `setTab` state mutation is absent.
- Mode defaults are driven by the tested navigation contract.
- Direct geometry/hierarchy route entry uses the tested route helper.
- Monitor views match the specification.
- Analyze views match the specification.
- Configure views match the specification.
- Configure route-out targets are explicit.
- Responsive navigation CSS exists.

Result: **12 / 12 checks passed**.

## Regression evidence

The regression contract continues to lock all migrated Scene Workspace
capabilities:

- Live 2D / Live 3D
- Camera feeds
- Sensor telemetry
- Geometry
- Hierarchy
- Camera calibration
- Runtime
- History/replay
- Trends/analytics
- Trails
- Telemetry
- Heatmap
- Velocity
- ROI visualization
- Fullscreen

No capability was removed by the navigation refactor.

## Commits

Implementation sequence:

- `b9eaadc8f00c4be2593d09ea9cac91465f17f44d` — mode navigation in SceneWorkspace.
- `d65f195c7ed518bc08e3de5f2844e752eed4bb76` — expanded navigation contract.
- `591b98bbba87179f2ec8c2300f90be8ca21e25c7` — navigation contract tests.
- `62032c6bfb08c654b74c81ad29f399c794185a58` — navigation styling.
- `1d70b214048621f6aa9dd6cebe09a2f313fc7378` — direct-entry route helper.
- `8e27a1c749a4598dcf5ce127eb18f8e86d6a3f21` — route compatibility tests.
- `e5b8b39e9b2450828c6d589650e92bcf99cd7f63` — App wiring to tested route helper.

## Verification boundary

This increment has executable unit/integrity/regression evidence. Full
production TypeScript/Vite build and live browser smoke are still retained as
explicit final gates UX-90 and UX-93–UX-98; those are not claimed by this
evidence file.
