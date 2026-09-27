<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# UX-80–UX-85 Evidence — Accessibility and Interaction Quality

## Scope

This evidence closes:

- UX-80 keyboard-test primary/secondary navigation.
- UX-81 keyboard-test layer/diagnostic controls.
- UX-82 visible focus styles.
- UX-83 accessible labels/roles for status, inspector, controls, and scene selections.
- UX-84 health status is not color-only.
- UX-85 live updates avoid excessive announcements.

Validated implementation head: `7b7cc29310b20407c084da0edc7a96afd1a17a05`.

Final Scene Workspace UX workflow run: **35490508522**.

## Static/unit accessibility contract

The zero-dependency Scene Workspace contract suite contains explicit coverage for:

- Enter and Space as selectable-entity activation keys.
- Stable ARIA labels such as `Inspect tracked object 42`.
- Explicit live-region policy:
  - scene operational state → `polite`
  - telemetry metrics → `off`
- Primary/secondary navigation remaining native keyboard-operable controls.
- layer controls remaining native input controls.
- selectable 2D scene entities retaining `role="button"` and `tabIndex={0}`.
- source-level preservation of `:focus-visible` treatment.
- status/live-region wiring remaining narrowly scoped.

Final result:

```text
tests 24
pass 24
fail 0
```

## Browser accessibility smoke

The production-checkout Playwright suite contains:

`UX-80–85 Accessibility smoke: keyboard navigation, controls, focus and scoped announcements`

The test performs real Chromium interactions against the React application:

1. Focuses **Analyze** and activates it with Enter.
2. Focuses **Configure** and activates it with Enter.
3. Focuses **Monitor** and activates it with Enter.
4. Switches **3D Scene** and **2D Scene** using keyboard activation.
5. Focuses the **Trails** checkbox and toggles it with Space.
6. Focuses the **Telemetry** checkbox and toggles it with Space.
7. Confirms telemetry uses `aria-live="off"`.
8. Focuses a tracked object and verifies computed focus styling has a visible outline.
9. Opens the object inspector using Space.
10. Confirms the operational state exposes visible text such as **LIVE** and has `role="status"`.
11. Confirms the scene-state live region uses `aria-live="polite"`.

The complete browser suite result was:

```text
Running 7 tests using 1 worker
7 passed (15.2s)
```

## Accessible scene interaction implementation

The Scene Workspace exposes accessible interaction for:

- tracked objects
- cameras
- sensors
- regions
- tripwires

2D entities have keyboard focus and explicit inspection labels. The 3D scene canvas is a focusable region with an accessible description, while tracked-object inspection is additionally available through a native select control so 3D inspection is not pointer-only.

The contextual inspector itself is labelled **Scene inspector**.

## Status semantics

Operational status is communicated with text:

- `LIVE`
- `DEGRADED`
- `STALE/OFFLINE`

Color is supplementary. Unknown health data remains textual `Unknown`.

Rapidly changing scene telemetry is deliberately not a live region. This prevents scene-rate, object-count, camera-rate, and observation-age changes from creating continuous screen-reader announcements.

## Evidence artifacts

Workflow run **35490508522** uploaded:

- `scene-workspace-ux-smoke` — artifact **10598677485**.

The artifact contains the Playwright evidence/screenshots produced by the UX smoke suite, including the accessibility smoke screenshot.

## Verification boundary

This is browser-level keyboard/focus/ARIA verification in Chromium using deterministic native UI fixtures. It does not claim a formal WCAG certification or testing across every browser/screen-reader combination.
