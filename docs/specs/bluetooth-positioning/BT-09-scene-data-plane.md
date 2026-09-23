# BT-09 — Scene Data-Plane Integration

**Status:** PLANNED  
**Dependencies:** BT-08  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective
Project Bluetooth tracks into existing bundle/live/SSE/history and render 2D/3D with provenance/uncertainty.

## User stories
- Operator sees moving tagged entity.
- Operator toggles tags/anchors/uncertainty/trails.
- Support inspects method/quality.

## Scope / functional requirements
1. Add BLE objects without replacing camera scene observations.
2. Stable bt:{tag_id} ID.
3. Authorized assignment label.
4. Anchor layer.
5. Uncertainty + trail + velocity.
6. Inspector method/state/uncertainty/anchors/freshness/battery.
7. Bluetooth history.
8. No fusion yet.

## Implementation design
- Adapter into existing render object model.
- Guard camera-telemetry isolation regression.
- Bound trail memory.
- Handle weak z honestly.

## API, data and events
- Additive bundle/live/history/SSE fields.

## UX / operational behavior
- Controls: tags, anchors, uncertainty, anchor links.
- Source badge CS/AoA/RSSI.
- Predicted/stale visually distinct.

## Security, privacy and failure handling
- Assignment display permissioned.
- No unauthorized precise history leak.

## Required tests
- [ ] Bundle/live isolation.
- [ ] 2D uncertainty/trails/velocity.
- [ ] 3D.
- [ ] SSE+polling fallback.
- [ ] History filters.
- [ ] Malformed payload.
- [ ] Vision regression.

## Evidence required
- [ ] 2D/3D screenshots.
- [ ] Playwright.
- [ ] Backend tests.

## Acceptance criteria
- [ ] BLE live positions visible without corrupting camera data.
- [ ] Quality visible.
- [ ] Existing UX works.
- [ ] BLE/vision remain separate.

## Out of scope
- Fusion.
- Incident semantics.

## Rollback / disable strategy
Disable BLE layer/source adapter; stored data remains.

## Implementation record
- Implementation commit: _not yet recorded_
- Evidence: _not yet recorded_
- Known deviations: _none at planning baseline_

## Continuation prompt
> Implement BT-09 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-09, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-09:`.
