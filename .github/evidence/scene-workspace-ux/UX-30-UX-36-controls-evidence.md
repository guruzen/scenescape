<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# UX-30–UX-36 Evidence — Contextual Scene View Controls

## Scope

This evidence covers:

- UX-30 replacement of the flat live-view checkbox row.
- UX-31 common layer controls.
- UX-32 2D-only controls.
- UX-33 3D-only controls.
- UX-34 renderer-specific visibility.
- UX-35 explicit data-availability messaging.
- UX-36 preservation of fullscreen and 3D camera/light controls.

## Implementation

The live scene toolbar is now grouped into:

- **Layers** — Objects, Trails, Heatmap, Velocity, Spatial overlays.
- **Diagnostics** — Telemetry with live/stale state.
- **2D view** — Labels.
- **3D view** — Floor plane, camera frames, selected camera view, camera
  opacity, and lighting.
- **Actions** — Clear trails and Fullscreen.

The 2D Labels control is wired into `Map2D`; labels are no longer always on.

Velocity reports `available / total` vectors directly in the control, so a
checked control with no velocity data is no longer silent.

## Unit test evidence

Command:

```bash
cd modern-ui
npm run test:ux
```

Result:

```text
tests 9
pass 9
fail 0
```

New unit checks:

- 2D exposes Labels and excludes 3D-only controls.
- 3D excludes Labels and exposes floor/camera/light controls.
- Common Layers/Diagnostics exist in both renderers.
- Live-object availability correctly counts valid velocity vectors.
- Empty live data reports unavailable trails/heatmap/velocity without
  fabricating values.

## Integration/integrity evidence

Repository-state checks after commit:

- grouped toolbar present
- Layers group present
- Diagnostics group present
- 2D-only Labels control wired to Map2D
- 3D-only view group present
- velocity coverage messaging present
- stale/live diagnostic messaging present
- renderer control contract matches implementation
- contextual control tests present
- responsive toolbar CSS present

Result: **11 / 11 checks passed**.

## Commits

- `90f0c364ce54af47ba5e24ebbe73ec068f591fda` — control model.
- `718efbc3244345b0bc783e450b42015e3b667779` — control model tests.
- `492b0cce7570e64c8eff6d2b910cdff146cad824` — grouped toolbar and 2D Labels wiring.
- `23ea0b7335d04c42c3d0bcbd528fb08f0485121f` — contextual control styling.

## Verification boundary

The deterministic unit/integrity/regression checks pass. Full production build
and live browser smoke remain final gates UX-90 and UX-93–UX-98.
