# BT-03 Evidence — Bluetooth Management UI

## Status

**COMPLETE**

## Validated implementation head

`d96f962ac7ab`

## Implementation record

- Core React management workspace and typed Bluetooth API client: `2a34112b8883`
- Browser selector/evidence hygiene corrections: `3acb10435e1f`
- Lifecycle assertion correction: `c812f0437e0d`
- Mock lifecycle state correction: `9fddf97db843`
- Canonical formatting closure: `a3216d76a8e1`
- Final inventory context and keyboard coverage: `d96f962ac7ab`

## Delivered management surface

SceneScape now exposes **Configuration → Bluetooth positioning** with four management tabs:

- **Anchors** — scene/state/serial filtering, stable hardware identity, provider metadata, capabilities, model, state, explicit lifecycle actions, revision-aware updates and delete safeguards.
- **Tags** — administrator-only mobile tag inventory, provider/capability context, lifecycle management, truthful battery/last-seen telemetry and assignment history.
- **Diagnostics** — anchor state counts, unassigned anchors, administrator-visible tag/battery summary and effective scene scope.
- **Calibration** — explicit BT-04 placeholder; BT-03 does not invent coordinates or calibration quality.

Inventory rows expose the context required for operations rather than forcing operators to open each record:

- serial number
- scene/assignment
- state
- provider
- capabilities
- battery where available
- last-seen state

Where telemetry does not yet exist, the UI shows **Unknown** instead of fabricated data.

## API and error behavior

The React workspace uses a typed client over BT-02 only:

- `/api/v2/bluetooth/anchors`
- `/api/v2/bluetooth/tags`
- `/api/v2/bluetooth/assignments`
- `/api/v2/bluetooth/diagnostics`

Mutations preserve BT-02 optimistic revision semantics. Structured API errors now retain HTTP status/code information through the shared client instead of collapsing structured conflicts into `[object Object]`.

## Security and privacy behavior

- Anchor reads continue to inherit BT-02 server-side scene scope.
- Bluetooth inventory mutations remain administrator-only.
- Tag identity and assignment history remain administrator-only because BT-02 intentionally has no trustworthy static tag-to-scene binding.
- Service tokens remain rejected from the interactive Bluetooth management plane.
- The integrated browser fixture was corrected to mint a browser-style test Bearer token so the UI smoke exercises the same auth semantics as production.
- Pairing secrets/provider credentials are not added to the UI or URLs.

## Accessibility and quality-honesty evidence

- Bluetooth sections use an ARIA tablist with tab roles and selected state.
- The browser smoke focuses the Tags tab and activates it with **Enter**, proving keyboard reachability for the management tabs.
- Device state uses text plus a status marker; color is not the only signal.
- Empty/error/loading states are explicit.
- Unknown battery and last-seen values remain `Unknown`.
- The Calibration tab states that map placement/geometry belong to BT-04 instead of presenting placeholder coordinates as real data.

## Bluetooth-specific CI

GitHub Actions run: `36187077710`

Result:

```text
Bluetooth management UI contract/build: PASS
Bluetooth backend/native regression: 16 passed, 1 warning in 2.76s
TypeScript typecheck: PASS
Production build: PASS
BT-03 contract test: PASS
```

The warning is the existing upstream test-client deprecation warning.

## Scene Workspace regression and E2E evidence

GitHub Actions run: `36187077694`

Final-head results:

```text
Focused native API integrity regression: 21 passed, 1 warning in 1.99s
Mocked browser smoke: 9 passed in 20.3s
Integrated React + real FastAPI browser smoke: 7 passed in 14.4s
TypeScript typecheck: PASS
Production build: PASS
```

BT-03 browser scenarios included:

- navigation to Bluetooth positioning
- anchor commissioning
- provider/capability/inventory context
- scene assignment
- anchor activation
- keyboard activation of the Tags tab
- tag commissioning
- truthful Unknown battery/last-seen state
- asset assignment
- diagnostics
- BT-04 calibration placeholder

The integrated scenario performs anchor/tag/assignment operations through the real FastAPI BT-02 control-plane API, not a mocked HTTP implementation.

### Browser evidence artifacts

The Scene Workspace workflows upload screenshots/results including:

- `bt03-bluetooth-management.png`
- `bt03-integrated-control-plane.png`
- `scene-workspace-ux-smoke` artifact
- `scene-workspace-native-integration` artifact

## Required lint evidence

GitHub Actions run: `36187084400`

Required lint job: **PASS**

- repository Prettier check: PASS
- GitHub Actions linter: PASS
- Python indentation check: PASS

## Security and repository-wide regression evidence

Validated on `d96f962ac7ab`:

- License Check: PASS — run `36187084202`
- Trivy: PASS — run `36187084502`
- Bandit: PASS — run `36187084140`
- CodeQL: PASS — run `36187084081`
- Gitleaks: PASS — run `36187084380`
- Zizmor: PASS — run `36187084155`
- ClamAV: PASS — run `36187084429`
- Basic Acceptance Tests: PASS — run `36187084456`
- Tracker Service: PASS — run `36187084308`
- Documentation Check: PASS — run `36187084421`

## Defects found and corrected during BT-03

1. The integrated browser fixture originally authenticated with a service token, which BT-02 correctly rejects from the interactive management plane. The fixture now uses a browser-style Bearer principal.
2. Initial Playwright selectors were ambiguous between filter/editor fields; selectors were scoped to the editor surface.
3. The mocked lifecycle route mapped `activate` to an invalid `activate` state rather than BT-02's `active` state; the fixture was corrected.
4. Gitleaks classified a full commit SHA in BT-02 evidence as a generic API key; evidence references were shortened to normal Git abbreviations without losing traceability.
5. Required Prettier lint exposed non-canonical formatting; the BT-03 files and workflow were normalized and the required lint job now passes.
6. Final acceptance review found provider/capability/last-seen context was too buried in editors and keyboard tab activation was not explicitly tested; both were added before closure.

## Acceptance

- [x] Admin can complete anchor commissioning/lifecycle workflow from the UI.
- [x] Admin can complete tag commissioning and assignment workflow from the UI.
- [x] Search and server-side filters are wired to BT-02.
- [x] Provider/capability/state/scene-or-assignment/last-seen context is visible in inventory.
- [x] Battery and last-seen are truthful when telemetry is unavailable.
- [x] Offline/unassigned/battery diagnostics are available without false precision.
- [x] Conflict/error responses are surfaced through the shared API client.
- [x] Management tabs are keyboard reachable/activatable.
- [x] Existing navigation, themes, native APIs and Scene Workspace browser flows remain green.
- [x] Calibration/live positioning remain explicitly outside BT-03.

## Deliberate scope decision

BT-03 preserves the BT-02 privacy model: mobile tags are not assigned a fabricated static scene solely for UI filtering. Until BT-09 provides a trustworthy live scene association, full tag inventory and assignment history remain administrator-only. Non-admin operators can inspect only scene-authorized anchors/diagnostics.

Battery and device last-seen telemetry are read-only and may remain `Unknown` until BT-10 introduces provider/device telemetry ingestion.

## Rollback

Remove/disable the Bluetooth navigation route and management component. BT-01/BT-02 persistence and APIs remain intact, preserving commissioned device and assignment history for later re-enable.
