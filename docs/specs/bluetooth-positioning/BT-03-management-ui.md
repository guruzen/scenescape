# BT-03 — Bluetooth Management UI

**Status:** IN_PROGRESS  
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

- [ ] Typecheck/build/lint.
- [ ] Component contracts.
- [ ] Integrated CRUD E2E.
- [ ] Accessibility.
- [ ] Existing nav regression.

## Evidence required

- [ ] Screenshots.
- [ ] Build/test output.
- [ ] E2E output.

## Acceptance criteria

- [ ] Admin can complete control-plane workflow in UI.
- [ ] Unknown/offline/conflict truthful.
- [ ] No nav/theme regression.

## Out of scope

- Map calibration.
- Live positioning.

## Rollback / disable strategy

Remove/disable navigation; backend remains.

## Implementation record

- Implementation commit: _not yet recorded_
- Evidence: _not yet recorded_
- Known deviations: The BT-03 tag workspace remains administrator-only because BT-02 intentionally has no static tag-to-scene binding. Battery and last-seen values are displayed read-only and remain `Unknown` until provider telemetry is implemented in BT-10.

## Continuation prompt

> Implement BT-03 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-03, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-03:`.
