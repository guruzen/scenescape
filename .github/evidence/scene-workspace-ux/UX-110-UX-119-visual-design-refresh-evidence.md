# UX-110–UX-119 Visual Design System Refresh Evidence

Date: 2026-09-20

## Goal

Move the Modern UI away from a cyan-heavy technical-console aesthetic toward a calm, premium spatial-operations product while preserving SceneScape workflows, semantic visualization colors, accessibility, responsive behavior, and saved theme compatibility.

## Completed work

- **UX-110 — Neutral spatial-operations tokens**
  - Introduced neutral canvas, panel, raised-panel, hover-surface, border, text, muted, accent-soft, semantic status, info, and shadow tokens.
  - Spatial Dark now uses a neutral near-black canvas and slate surfaces rather than blue/cyan-tinted black.

- **UX-111 — Restrained accent usage**
  - Teal/cyan is reserved primarily for selected/active state and product accent.
  - Success, warning, danger, info, tripwire, region, camera, and tracked-object colors remain semantically distinct.

- **UX-112 — Global shell modernization**
  - Sidebar, brand mark, top bar, navigation hover/active states, and spacing hierarchy were refreshed.
  - Active navigation now uses a restrained surface tint plus a 2px accent rail rather than a large saturated block.

- **UX-113 — Typography cleanup**
  - Removed console-oriented global labels such as “Operations · data plane” and “Configuration · control plane”.
  - Global groups are now “Operations”, “Configuration”, and “Administration”.
  - Brand descriptor changed from “Native operations console” to “Spatial operations”.
  - Sidebar typography was refined after visual review:
    - brand title: 15px / 700
    - descriptor: 10.5px / 500
    - section labels: 11px / 650
    - navigation items: 13px / 520 with 1.35 line-height
    - active item: 630 weight
  - Dense Dark keeps compact density but no longer collapses typography to console-sized text.

- **UX-114 — Surface and border hierarchy**
  - Reduced border contrast/density across panels, metrics, tables, status blocks, and controls.
  - Added restrained elevation using tokenized shadows where appropriate.
  - Dense Dark intentionally keeps flatter elevation while sharing the same hierarchy.

- **UX-115 — Shared controls**
  - Buttons, form controls, status pills, focus treatment, selected states, and hover surfaces were aligned to the refreshed token set.

- **UX-116 — Incident workspace**
  - Incident filters and metadata styling were modernized.
  - Incident list now uses the full content width before selection.
  - The list/detail split is activated only after an incident is selected, eliminating the large empty right-hand area.
  - Selected incident rows use a restrained accent rail and soft surface tint.

- **UX-117 — Theme compatibility and responsiveness**
  - Existing persisted theme IDs remain unchanged:
    - `light`
    - `light-air`
    - `dark`
    - `dark-command`
  - Display labels are now:
    - Spatial Light
    - Soft Light
    - Spatial Dark
    - Dense Dark
  - Existing localStorage theme preferences therefore remain valid.
  - Existing responsive breakpoint behavior remains intact.

- **UX-118 — Regression validation**
  - Visual design contract assertions were added for theme labels/tokens and sidebar typography.
  - Repository Prettier formatting was applied using the repository’s own formatter.
  - Required lint gate passed.
  - Modern UI UX tests, TypeScript, production build, browser smoke, focused native API regression, and integrated native UI/API browser smoke passed.

- **UX-119 — Evidence**
  - Final Scene Workspace workflow: `35496097097`.
  - Required lint workflow: `35496100038`.
  - Validated implementation head: `307a181cca914debe79a411f2425f33791de46db`.
  - Browser evidence artifacts:
    - `scene-workspace-ux-smoke` — artifact `10600434477`
    - `scene-workspace-native-integration` — artifact `10601155372`

## Validation result

### Scene Workspace gate — run 35496097097

Passed:

- Modern UI UX contract tests
- TypeScript typecheck
- production build
- Scene Workspace browser smoke
- focused native API integrity regression
- integrated React + FastAPI + SQLite + SSE native browser smoke
- browser/integration evidence upload

### Required lint gate — run 35496100038

Passed:

- Prettier check
- GitHub Actions lint
- Python indentation check

## Design principles retained

The refresh intentionally does **not** flatten semantic visualization colors. Regions, tripwires, cameras, tracked objects, warning states, failures, and live/health states must remain visually distinguishable. The product accent is no longer used as ambient decoration.

The visual direction is:

> Calm, premium, technical spatial operations — not a hacker/NOC console and not a consumer SaaS dashboard.
