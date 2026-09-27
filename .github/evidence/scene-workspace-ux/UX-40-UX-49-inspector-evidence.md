<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# UX-40–UX-49 Evidence — Contextual Scene Inspector

## Scope

This evidence covers:

- UX-40 selection state and inspector shell.
- UX-41 tracked-object selection in 2D.
- UX-42 tracked-object selection in 3D.
- UX-43 tracked-object inspector fields.
- UX-44 camera selection and inspector.
- UX-45 sensor selection and inspector.
- UX-46 region selection and inspector.
- UX-47 tripwire selection and inspector.
- UX-48 clear/collapse behavior.
- UX-49 honest missing-data handling.

## Implementation

New reusable inspector model/component:

- `modern-ui/src/ux/sceneInspector.ts`
- `modern-ui/src/ux/SceneInspector.tsx`

### Selection

2D supports direct selection of:

- tracked objects
- cameras
- sensors
- regions
- tripwires

3D supports tracked-object selection through Three.js raycasting.

Selected 2D entities receive a visible selected style. Selected 3D tracked
objects receive a ground selection ring.

### Live object freshness

The inspector does not freeze the tracked-object payload captured at click
time. `refreshObjectSelection` resolves the selected object against the latest
live scene observation on every render when the object is still present.

### Inspector data

Tracked objects expose:

- category
- position
- velocity
- speed
- regions
- dwell
- visible cameras
- persistent data

Cameras expose configured identity plus live telemetry when available.

Sensors expose configured identity plus latest retained telemetry.

Regions/tripwires expose geometry and configured operational fields.

Unavailable optional values are rendered as **Unknown** rather than guessed.

### Runtime fetch behavior

Only a selected camera or sensor triggers additional telemetry retrieval.
The selected resource is refreshed every 3 seconds and the interval is cleaned
up on selection change/unmount.

## Unit/regression test evidence

Command:

```bash
cd modern-ui
npm run test:ux
```

Result:

```text
tests 12
pass 12
fail 0
```

New checks cover:

- object speed derivation from an explicit velocity vector
- dwell extraction
- camera visibility list
- persistent data
- Unknown semantics for missing camera/sensor telemetry
- selected live object refresh from the latest scene observation
- retention of last selected payload if the object is temporarily absent

## Integration/integrity evidence

Post-commit repository-state checks:

- 2D object selection present
- 2D camera selection present
- 2D sensor selection present
- 2D region selection present
- 2D tripwire selection present
- 3D object raycast selection present
- 3D selected-object highlight present
- inspector wired into monitor layout
- collapse and clear behavior present
- camera telemetry retrieval present
- sensor telemetry retrieval present
- explicit Unknown semantics present
- live selected-object refresh present
- inspector tests present
- responsive inspector fallback present

Result: **15 / 15 checks passed**.

## Commits

- `9fbfa412358e9315e76e69f5c07941b2e27fb89f` — inspector model.
- `136129fcdff77db4ea40c167ef36513c4bcfba5c` — inspector component.
- `edb4d708f934a3c4d5e99b1d16d672c7224639e4` — inspector tests.
- `9b224873b9243b275c71f67952a8c87f7bc5ab34` — 2D selections and inspector integration.
- `368d4d35f0e841a9b77abf3c6af66752fc618713` — 3D tracked-object selection/highlight.
- `d464a752999151d106dbf1de20033b2ef8cbae72` — inspector/selection styling.

## Verification boundary

This evidence covers deterministic unit, integration-structure, and regression
checks. Full production build and live browser interaction remain final gates
UX-90 and UX-93–UX-98.
