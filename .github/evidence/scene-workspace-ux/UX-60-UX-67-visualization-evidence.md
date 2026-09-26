<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# UX-60–UX-67 Evidence — Heatmap and Velocity Refinement

## Scope

This evidence covers:

- UX-60 heatmap styling and legend.
- UX-61 consistent heatmap behavior in 2D and 3D.
- UX-62 heatmap opacity control.
- UX-63 historical ranges only when backed by an appropriate data contract.
- UX-64 bounded 2D velocity arrows.
- UX-65 bounded 3D velocity arrows.
- UX-66 numeric speed/velocity in the object inspector.
- UX-67 explicit velocity-vector availability count.

## Implementation

New pure visualization contract:

- `modern-ui/src/ux/sceneVisualization.ts`

New shared legend:

- `modern-ui/src/ux/SceneVisualizationLegend.tsx`

### Heatmap

Both 2D and 3D use the same operator-controlled opacity setting. The UI exposes
a Current-range legend with lower/higher relative intensity and the number of
current tracked positions.

Historical 5/30/60-minute choices were intentionally **not** exposed. The
current native history endpoint stores real observations, but it does not expose
a bounded density-aggregation contract. Fetching an arbitrary history window
and synthesizing density client-side would introduce unpredictable cost and a
new analytical behavior without a stable API contract. The UX therefore
advertises only `Current`; no historical visualization is fabricated.

### Velocity

2D arrow geometry is derived by a tested helper:

- invalid/zero vectors are not drawn
- minimum displayed length: 0.4 scene metres
- maximum displayed length: 2.5 scene metres

3D arrows use a tested bounded length:

- minimum displayed length: 0.5
- maximum displayed length: 4.0

The actual direction remains derived from the reported vector.

The object inspector already exposes numeric velocity and speed. The Layers
control and visualization legend expose `available / total` vector counts.

## Unit test evidence

Command executed:

```bash
cd /tmp/scenescape-ux/modern-ui
npm run test:ux
```

Final result:

```text
tests 16
pass 16
fail 0
cancelled 0
skipped 0
todo 0
```

An earlier run caught a strict numeric edge case where a horizontal vector
produced JavaScript `-0` for its Y delta. The helper was corrected to normalize
zero components and the complete suite was rerun successfully. This failure was
not ignored or weakened.

## Integration/integrity evidence

Post-commit checks verify:

- only Current heatmap range is advertised
- opacity is bounded between 10% and 100%
- 2D vector length is bounded
- 3D vector length is bounded
- Map2D uses the tested velocity helper
- one shared visualization legend is rendered
- legend explains lower/higher heat intensity
- 3D uses the tested velocity helper
- 2D and 3D consume the same heatmap opacity state
- object inspector exposes speed
- vector availability count is visible
- visualization unit tests are present
- new files contain SPDX headers

Result: **15 / 15 checks passed**.

## Commits

- `8ec1bd44fd9d6a66f0247af736527f08d340532c` — visualization helper model.
- `6374e9b4ea88579f6a7f5fc9386d28347eb40e6b` — visualization tests.
- `311d8c9a3a07edf69c5dba2b5012929e62b4a95d` — normalize zero arrow components after the first unit run exposed `-0`.
- `502903898cc0e25bcbb519c0dc358d13d1b79186` — shared heatmap/velocity legend.
- `3847772956ff66a35fbb147e2ff24afee9561cf0` — shared controls/2D integration.
- `6b4df17b300680ff7e0abcbf21ccdba5e37fccdd` — bounded 3D velocity and heatmap opacity.
- `5d48a7a7b67a6807e57aa18040a47a0d46d47c84` — visualization legend/control styling.

## Verification boundary

The zero-dependency UX suite and repository integrity checks pass. Production
TypeScript/Vite build and live browser smoke remain explicit final gates
UX-90 and UX-93–UX-98.
