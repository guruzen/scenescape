<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# UX-02 Evidence — Scene Workspace Regression Baseline

## Purpose

Lock the pre-overhaul Scene Workspace capability set and the one-to-one mapping
from the legacy flat tab model to the UX 2.0 information architecture.

## Automated checks

Command:

```bash
cd modern-ui
npm run test:ux
```

Result captured before check-in:

```text
tests 3
pass 3
fail 0
```

The three checks are intentionally separated by purpose:

1. **Unit** — every legacy tab resolves to a valid UX 2.0 destination and an
   unknown tab resolves to null.
2. **Integrity** — all ten legacy destinations are represented exactly once,
   destination keys do not collide, and the only primary modes are Monitor,
   Analyze, and Configure.
3. **Regression** — the pre-overhaul capability baseline is locked and the
   default destination is Monitor → 2D Scene.

## Locked capability baseline

- Live 2D
- Live 3D
- Camera feeds
- Sensor telemetry
- Geometry editor
- Hierarchy editor
- Camera calibration
- Runtime status
- History/replay
- Trends/analytics
- Trails
- Telemetry
- Heatmap
- Velocity
- ROI visualization
- Fullscreen

## Legacy-to-target navigation mapping

| Legacy destination | Primary mode | Secondary view |
| --- | --- | --- |
| Live 2D | Monitor | 2D Scene |
| Live 3D | Monitor | 3D Scene |
| Camera feeds | Monitor | Cameras |
| Sensors & telemetry | Monitor | Sensors |
| Runtime | Analyze | Runtime |
| History & replay | Analyze | History |
| Trends & analytics | Analyze | Trends |
| Geometry | Configure | Geometry |
| Hierarchy | Configure | Hierarchy |
| Camera calibration | Configure | Calibration |

## Evidence quality

This phase does not change runtime rendering or backend behavior, so the
narrowest meaningful executable evidence is the zero-dependency Node contract
suite. Full browser/runtime smoke evidence becomes mandatory when navigation
or rendering behavior changes in later phases.
