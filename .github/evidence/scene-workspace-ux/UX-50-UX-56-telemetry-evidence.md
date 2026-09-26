<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# UX-50–UX-56 Evidence — Scene Telemetry Redesign

## Scope

This evidence covers:

- UX-50 dedicated reusable Scene telemetry HUD.
- UX-51 scene rate and object count.
- UX-52 per-camera FPS from the live scene rate map.
- UX-53 feed freshness and observation age.
- UX-54 rich object persistent data moved to the inspector.
- UX-55 Camera Feeds telemetry terminology aligned with the scene HUD.
- UX-56 telemetry state reset on scene changes.

## Implementation

New telemetry model/component:

- `modern-ui/src/ux/sceneTelemetry.ts`
- `modern-ui/src/ux/SceneTelemetryHud.tsx`

The old duplicated 2D and 3D HUD implementations were removed. Both renderers
now use exactly one shared telemetry HUD.

### Unknown versus zero

The telemetry model treats missing values as unknown:

- Missing `scene_rate` → `Unknown`, not `0.0 Hz`.
- Missing per-camera rate data → `Camera FPS: Unknown`.
- Missing camera-feed FPS/detection count → `Unknown`, not zero.

A real numeric zero remains a real zero.

### Feed freshness

The HUD exposes:

- Receiving / Stale / Unknown.
- Latest observation age when available.

### Object telemetry

The map keeps concise per-object telemetry (ID, velocity, dwell) when enabled.
Rich `persistent_data` was removed from map labels and remains available in
the contextual inspector.

### Cross-scene integrity

When the active scene changes, SceneWorkspace resets:

- live scene state
- trails
- runtime overview
- selection/inspector state

before new scene data arrives. This prevents telemetry from the previous scene
being displayed under the new scene name.

## Unit/regression test evidence

Command executed:

```bash
cd /tmp/scenescape-ux/modern-ui
npm run test:ux
```

Result:

```text
tests 14
pass 14
fail 0
cancelled 0
skipped 0
todo 0
```

New coverage verifies:

- scene rate remains null when unavailable
- object count
- Receiving/Stale freshness
- deterministic observation age
- stable per-camera FPS ordering and numeric conversion
- no-camera-rate case
- fresh object instances for scene-reset state

## Integration/integrity evidence

Post-commit repository checks:

- exactly one `SceneTelemetryHud` is rendered
- HUD derives data through the pure telemetry model
- missing scene rate displays Unknown
- freshness is rendered
- camera rates are rendered only when present
- scene change resets live/trail/runtime state
- Map2D no longer renders `persistent_data`
- inspector still owns `persistent_data`
- camera feed no longer converts missing FPS/detections to zero
- Camera Feed uses Receiving / Stale / Waiting terminology
- telemetry model tests are present
- SPDX headers present on new telemetry/test files

Result: **14 / 14 checks passed**.

## Commits

- `1f4b2c19c138327e62b0dace3e976d7a02b98d32` — telemetry model.
- `2622bf2085a16c059f5948daa573e3d16f869776` — telemetry unit/regression tests.
- `bb99f66e4f8a68e3872e98f4ba80db1819268628` — reusable telemetry HUD.
- `6f5ebf02417f54b06810348c9dc138be7d17d6d9` — Scene Workspace telemetry integration/reset.
- `3349ffb72be52a7a640d2e7dc2bbf99d1aac7620` — telemetry visual-language alignment.

## Verification boundary

The zero-dependency UX test suite and repository integrity checks passed.
Production TypeScript/Vite build and live browser smoke remain explicit final
gates UX-90 and UX-93–UX-98.
