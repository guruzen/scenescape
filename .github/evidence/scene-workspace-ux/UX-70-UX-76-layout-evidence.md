<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# UX-70–UX-76 Evidence — Visual Hierarchy and Responsive Polish

## Scope

This evidence covers:

- UX-70 explicit primary/secondary/tertiary visual hierarchy.
- UX-71 reduced equal-weight borders/chrome.
- UX-72 standardized workspace spacing and control density.
- UX-73 responsive inspector drawer behavior.
- UX-74 desktop/drawer/narrow breakpoint contract.
- UX-75 supported theme contract.
- UX-76 fullscreen behavior after the layout refactor.

## Implementation

New pure layout/theme contract:

- `modern-ui/src/ux/sceneLayout.ts`

The contract defines:

- desktop → width > 1100 px
- drawer → 601–1100 px
- narrow → width <= 600 px
- visual hierarchy: status → primary navigation → secondary navigation →
  controls → visualization → inspector
- supported themes: light, light-air, dark, dark-command

The duplicate scene-summary card row was removed because the persistent status
header already carries scene identity, object/rate/camera/MQTT/freshness state.
This reduces competing card weight before the primary navigation.

At medium/narrow widths, a selected inspector becomes a fixed drawer rather
than forcing the visualization into a stacked desktop layout. An empty
inspector is hidden at those widths.

Fullscreen CSS was corrected to target the actual native 2D classes
(`.map-frame` / `.native-map`) as well as `.three-viewer`. The previous
fullscreen rule referenced `.map-canvas`, which is not used by Map2D.

## Unit/integrity test evidence

Command executed:

```bash
cd /tmp/scenescape-ux/modern-ui
npm run test:ux
```

Result:

```text
tests 18
pass 18
fail 0
cancelled 0
skipped 0
todo 0
```

New checks verify:

- exact breakpoint behavior at boundary values
- explicit visual hierarchy ordering
- exact supported-theme values

## Integration/integrity evidence

Post-commit repository checks verify:

- explicit hierarchy contract exists
- App uses the tested theme contract
- redundant scene-summary row is removed
- primary navigation chrome is visually reduced
- 1100 px drawer breakpoint matches the tested contract
- 600 px narrow breakpoint matches the tested contract
- responsive inspector uses a fixed drawer
- empty responsive inspector is hidden
- 2D fullscreen targets real map classes
- 3D fullscreen remains covered
- layout/theme tests are present
- SPDX header present on the new layout contract

Result: **13 / 13 checks passed**.

## Commits

- `c5d1690b6ebae42feb7de29e711df65d69b7fcce` — layout/theme contract.
- `f97766d90d823b0955044157015ac055fe5adcba` — layout/theme tests.
- `4e17f0142d821cc977dbc8c2f9f3e2ff2be918ca` — App hierarchy/theme integration.
- `d198a225997239673b694e44d707990f758e7ceb` — responsive drawer/fullscreen styling.

The initial combined repository write was rejected by the connector before any
write occurred. The validated change was split into smaller commits; no task was
marked complete until the split commits and post-commit checks passed.

## Verification boundary

Responsive behavior is contract-tested and CSS-integrity-checked here. Actual
browser viewport/theme smoke remains part of the final runtime gate and is not
claimed by this evidence file.
