<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# UX-20–UX-24 Evidence — Persistent Scene Operational Status

## Scope

This evidence covers:

- UX-20 reusable `SceneStatusHeader`.
- UX-21 scene freshness, object count, scene rate, camera health, and MQTT state.
- UX-22 LIVE / DEGRADED / STALE/OFFLINE state semantics.
- UX-23 explicit Unknown handling.
- UX-24 status persistence across Scene Workspace subviews.

## Implementation

New files:

- `modern-ui/src/ux/sceneStatus.ts`
- `modern-ui/src/ux/SceneStatusHeader.tsx`

The status model is intentionally pure and testable. It does not infer data that
is not present.

Overall-state rules:

- `STALE/OFFLINE` when the current scene observation is stale.
- `DEGRADED` when MQTT reports an explicit non-connected state, or when
  per-camera rate data is available and fewer cameras are healthy than are
  configured.
- `LIVE` when the scene is fresh and no explicit degradation is known.

Unknown MQTT/camera health is displayed as Unknown rather than treated as a
numeric zero.

Camera health uses existing `live.rate` data and therefore adds no camera
polling.

The existing overview endpoint is refreshed every 5 seconds while the Scene
Workspace is mounted. The interval is cleaned up on unmount/scene change.

## Unit test evidence

Command:

```bash
cd modern-ui
npm run test:ux
```

Result:

```text
tests 7
pass 7
fail 0
```

The new status unit test covers:

- healthy LIVE scene
- disconnected MQTT → DEGRADED
- partial camera rates → DEGRADED
- stale scene → STALE/OFFLINE
- unknown camera/MQTT health remaining explicit
- deterministic latest-observation age calculation

## Integration/integrity evidence

Repository-state integrity checks after commit:

- reusable status component exists
- all three operational states exist
- Unknown camera health is preserved
- camera-health field is rendered
- MQTT state is rendered
- latest-observation age is rendered
- status header is rendered before primary navigation, so it remains visible
  across subviews
- runtime refresh interval is bounded and cleaned up
- status unit test is present
- responsive status CSS is present

Result: **10 / 10 checks passed**.

## Commits

- `3e578cb0fe17d49ac84934ac3ba55c08adab87b6` — pure status model.
- `41a715abe9428dfe19858ce5dbf23cdb86f2870f` — reusable status header.
- `7d746e967bce24ce38d81c80471f58ff3f138e5a` — status semantics tests.
- `c75256b8abed5a326cd57680f1d0bc1fcb659c17` — persistent workspace integration.
- `b63a443477c81f0d0a1eb4bf0513805112f1c10c` — status styling/responsiveness.

## Verification boundary

This evidence covers deterministic unit, integration-structure, and regression
checks. Full production build and live browser smoke remain explicit final
gates UX-90 and UX-93–UX-98.
