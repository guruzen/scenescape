# BT-03 — Bluetooth Management UI

**Status:** COMPLETE  
**Dependencies:** BT-02  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective

Add React management workspace for anchors, tags, assignment and health.

## User stories

- Admin manages anchor serial/state.
- Admin registers tags/assignments.
- Operator identifies offline/low-battery/unassigned devices.

## Scope / functional requirements

1. Configuration > Bluetooth Positioning.
2. Anchors/Tags/Diagnostics tabs; Calibration placeholder.
3. Tables show serial/scene/state/capabilities/provider/last-seen.
4. Tag assignment/battery/position state.
5. Validated dialogs + confirmations.
6. Search/filters.
7. Loading/empty/error/forbidden/conflict states.

## Implementation design

- Reuse native inventory patterns.
- Central API client/types.
- Never fabricate telemetry.
- Optimistic edits only with conflict recovery.

## API, data and events

- Consume BT-02 only.

## UX / operational behavior

- Liquid Glass/theme compatible.
- Keyboard accessible.
- Unknown battery says Unknown.
- Text/icon plus color.

## Security, privacy and failure handling

- Permission-gated controls.
- Avoid sensitive identity in logs/URLs.

## Required tests

- [x] Typecheck/build/lint.
- [x] Component contracts.
- [x] Integrated CRUD E2E.
- [x] Accessibility.
- [x] Existing nav regression.

## Evidence required

- [x] Screenshots.
- [x] Build/test output.
- [x] E2E output.

## Acceptance criteria

- [x] Admin can complete control-plane workflow in UI.
- [x] Unknown/offline/conflict truthful.
- [x] No nav/theme regression.

## Out of scope

- Map calibration.
- Live positioning.

## Rollback / disable strategy

Remove/disable navigation; backend remains.

## Implementation record

- Implementation commits: `2a34112b8883` (management UI/API client), `d96f962ac7ab` (final inventory context and keyboard coverage)
- Validated implementation head: `d96f962ac7ab`
- Evidence: `.github/evidence/bluetooth-positioning/BT-03-management-ui.md`
- Known deviations: The BT-03 tag workspace remains administrator-only because BT-02 intentionally has no static tag-to-scene binding. Battery and last-seen values are displayed read-only and remain `Unknown` until provider telemetry is implemented in BT-10.

## Continuation prompt

> BT-03 is complete. Continue with BT-04 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md`, BT-03 and BT-04 first. Verify dependencies and the current branch, implement only BT-04, add required tests/evidence, update status/checklists, and commit with a message beginning `BT-04:`.
