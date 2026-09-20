<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Scene Workspace UX 2.0 — Specification and Execution Plan

## Document status

- **Status:** Active
- **Owner:** SceneScape modern UI migration
- **Branch:** `feature/react-keycloak-modern-ui`
- **Spec baseline commit:** `b6c95714de710504a49c6282174090b7491cef59`
- **Purpose:** This file is the durable handoff and progress record for the Scene Workspace UX overhaul. It must remain usable if implementation continues in another chat/session.
- **Progress rule:** When a task is completed, change its checkbox from `[ ]` to `[x]` and append the implementation commit SHA to the Progress Log. Prefer updating this file in the same commit as the task, or in an immediate follow-up commit if the code commit must land first.

---

## 1. Problem statement

The React-based SceneScape UI has reached broad functional parity with the 2026.2 Django experience and has been hardened for authorization, media/archive safety, concurrency, live-stream resilience, and lifecycle cleanup.

The current Scene Workspace is nevertheless still shaped like an engineering console:

- Operational monitoring, analysis, and configuration are mixed in one long tab row.
- Controls with different semantics are presented with equal visual weight.
- Several view controls are global even when they only make sense in 2D or 3D.
- Object/camera/sensor details are rendered directly in the visualization instead of through a contextual inspector.
- Runtime health is distributed across multiple views instead of forming one coherent scene-status model.
- Telemetry, diagnostics, and visualization layers are conflated.
- The interface becomes harder to understand as new capabilities are added.

The UX overhaul must improve task clarity and operational usability **without regressing migrated feature parity**.

---

## 2. Product UX principles

The implementation must follow these principles.

1. **Operate first.** The primary scene experience is live operations, not CRUD.
2. **Separate intent.** Monitoring, analysis, and configuration must be visibly distinct modes.
3. **Context over clutter.** Detailed information belongs in a contextual inspector rather than permanently on top of the scene.
4. **Every control must explain itself.** A control must visibly affect the current view or explain why it cannot.
5. **2D and 3D are related but not identical.** Only show controls meaningful to the active renderer.
6. **Health is persistent.** Operators should never have to navigate away to learn whether the scene, cameras, or MQTT path are healthy.
7. **Progressive disclosure.** Advanced diagnostics and configuration should not compete with primary operational actions.
8. **Preserve capability.** Existing 2026.2 parity work and native capabilities must remain reachable.
9. **Accessible by default.** Keyboard interaction, focus states, labels, contrast, and screen-reader semantics are part of acceptance.
10. **No hidden failure.** Missing velocity, missing telemetry, stale feeds, or unsupported data must be communicated explicitly.

---

## 3. Scope

### In scope

- Scene Workspace information architecture.
- Monitor / Analyze / Configure primary modes.
- Secondary navigation within each mode.
- Persistent scene health/status header.
- Live 2D and Live 3D toolbar redesign.
- Layers and Diagnostics separation.
- Contextual right-side inspector.
- Object, camera, sensor, region, and tripwire inspection.
- Telemetry HUD redesign.
- Contextual 2D/3D controls.
- Heatmap UX improvement.
- Velocity visualization UX improvement.
- Responsive behavior.
- Accessibility.
- Regression coverage for navigation and critical control behavior.
- Documentation updates for the new Scene Workspace.

### Out of scope

- Replacing React/Vite/Three.js.
- Rewriting the FastAPI backend solely for UX reasons.
- Reintroducing Django UI components.
- Changing Keycloak identity architecture.
- Changing MQTT topic contracts unless a verified UX requirement cannot be satisfied otherwise.
- Replacing the current scene map or 3D rendering engine.
- New analytics algorithms unrelated to the UX.
- Removing existing scene capabilities to simplify the UI.

---

## 4. Current functional baseline that must be preserved

The overhaul must preserve access to and behavior of:

- Live 2D scene rendering.
- Live 3D scene rendering.
- Camera feeds.
- Sensor telemetry.
- Regions and tripwires.
- Child-scene spatial metadata.
- Scene hierarchy.
- Camera calibration.
- Runtime status.
- History and replay.
- Trends and analytics.
- Trails.
- Telemetry.
- Heatmap.
- Velocity visualization.
- ROI visualization.
- 3D floor control.
- Camera frame projection.
- Camera opacity.
- Camera-view selection.
- Lighting controls.
- Fullscreen mode.
- Scene/camera/sensor/asset/spatial/hierarchy configuration.
- Existing authorization and scene-scope behavior.

No task is complete if it makes one of these capabilities unreachable or materially less functional without an explicit replacement.

---

## 5. Target information architecture

### Primary scene modes

The Scene Workspace must expose exactly three primary intents:

1. **Monitor**
2. **Analyze**
3. **Configure**

The active primary mode must remain obvious at all times.

### Monitor secondary navigation

- **2D Scene**
- **3D Scene**
- **Cameras**
- **Sensors**

### Analyze secondary navigation

- **History**
- **Trends**
- **Incidents / Events** when scene-specific incident support is available in the current UI
- **Runtime diagnostics** may live here or as a persistent diagnostics drawer; final placement is decided during UX-03 based on implementation fit.

### Configure secondary navigation

- **Scene**
- **Geometry**
- **Hierarchy**
- **Cameras**
- **Sensors**
- **Calibration**

Global administration such as identity/security remains outside the Scene Workspace.

---

## 6. Target layout

Desktop target:

```text
┌───────────────────────────────────────────────────────────────────────┐
│ Retail Store                                      ● LIVE             │
│ 85 objects · 29.8 Hz · 4/4 cameras · MQTT connected · 120 ms ago    │
├───────────────────────────────────────────────────────────────────────┤
│ Monitor             Analyze             Configure                    │
├───────────────────────────────────────────────────────────────────────┤
│ 2D Scene   3D Scene   Cameras   Sensors                              │
├───────────────────────────────────────────────────────┬───────────────┤
│                                                       │ Inspector     │
│                                                       │               │
│                    Visualization                      │ Selected      │
│                                                       │ object /      │
│                                                       │ camera /      │
│                                                       │ region /      │
│                                                       │ sensor        │
├───────────────────────────────────────────────────────┴───────────────┤
│ Layers                                 Diagnostics                    │
│ Objects Regions Tripwires Sensors     Telemetry Camera FPS IDs       │
│ Trails Heatmap Velocity                                              │
└───────────────────────────────────────────────────────────────────────┘
```

The inspector may collapse when nothing is selected or when viewport width is constrained.

---

## 7. Persistent scene status model

The header must provide an at-a-glance scene status.

### Required fields

- Scene name.
- Overall state: `LIVE`, `DEGRADED`, or `STALE/OFFLINE`.
- Tracked object count.
- Scene update rate.
- Camera health count, where data is available.
- MQTT historian/ingestion state.
- Age of latest scene observation.

### State semantics

- **LIVE:** scene observation is fresh and required runtime dependencies are healthy.
- **DEGRADED:** scene is fresh but one or more inputs/dependencies are degraded, or partial input health is detected.
- **STALE/OFFLINE:** latest scene observation exceeds the stale threshold or runtime is unavailable.

The status header must not invent health. Unknown data must be rendered as `Unknown`.

---

## 8. Layers versus Diagnostics

### Layers

Layers affect what is drawn in the scene.

Common:

- Objects.
- Regions.
- Tripwires.
- Sensors.
- Cameras where meaningful.
- Trails.
- Heatmap.
- Velocity.

2D-specific controls may include labels.

3D-specific controls may include:

- Floor plane.
- Camera frustums.
- Projected camera frames.
- Lighting.

### Diagnostics

Diagnostics explain runtime data rather than changing scene geometry.

- Scene telemetry.
- Camera FPS.
- Object identifiers.
- Object persistent data.
- Feed freshness.
- Missing-data notices.

A diagnostics control must never silently do nothing. Example:

`Velocity: 0 / 85 objects reporting velocity`

is acceptable; a checked box with no visible acknowledgement is not.

---

## 9. Contextual inspector

The right-side inspector is a first-class feature.

### Supported selections

- Tracked object.
- Camera.
- Sensor.
- Region.
- Tripwire.

### Tracked object inspector

When data exists:

- ID.
- Category/type.
- Position.
- Velocity and speed.
- Current regions.
- Dwell times.
- Persistent data.
- Visibility/camera sources.
- First/last observation if available.

### Camera inspector

When data exists:

- Name and ID.
- Scene.
- Receive state.
- FPS.
- Detection count.
- Last observation age.
- Calibration state.
- Pipeline/runtime state.
- Action to open camera feed.
- Action to enter camera view in 3D where applicable.

### Sensor inspector

- Name and ID.
- Type.
- Area/coverage.
- Latest telemetry.
- Latest observation timestamp.

### Region inspector

- Name/ID.
- Geometry summary.
- Occupancy if available.
- Threshold settings if configured.
- Dwell/event configuration if available.

### Tripwire inspector

- Name/ID.
- Directionality.
- Geometry summary.
- Recent event information if available.

Unsupported/missing fields must be omitted or shown as `Unknown`; never fabricate values.

---

## 10. Telemetry UX

Telemetry should not primarily mean “more text over the map.”

### Scene telemetry HUD

When enabled:

- Scene rate.
- Object count.
- Per-camera FPS from `live.rate` when present.
- Feed freshness.
- MQTT/runtime state if already available without introducing excessive polling.

### Object telemetry

Object-specific telemetry belongs primarily in the inspector.

Small object labels may still show concise information such as ID or speed when the corresponding diagnostics option is enabled.

### Camera-feed telemetry

The existing camera feed telemetry strip remains supported and must be visually consistent with the scene telemetry language.

---

## 11. Heatmap UX

### Phase 1

Preserve the current live-position heat overlay so the switch is immediately useful.

### Phase 2 target

Move toward a density-oriented visualization rather than simple per-object circles.

Desired controls:

- Current.
- 5 min.
- 30 min.
- 1 hr.

Historical heatmap ranges require backend/history support and must not be faked. If only current data is available, expose only `Current`.

A legend should explain relative intensity.

---

## 12. Velocity UX

- Draw velocity direction when the object provides a valid vector.
- Scale arrows within bounded minimum/maximum visual lengths.
- Explain missing vectors in the UI.
- Inspector displays numeric velocity/speed.
- Do not infer velocity from position history unless a separate, explicit feature is implemented and documented.

---

## 13. Responsive behavior

### Desktop

- Visualization plus optional inspector.
- Full persistent status header.
- Expanded layer/diagnostic controls.

### Medium-width

- Inspector may become a drawer.
- Secondary navigation may horizontally scroll or collapse into a compact selector.

### Narrow/mobile

The primary objective is monitoring, not full editing.

- Scene status remains visible.
- Visualization remains usable.
- Inspector opens as a drawer/sheet.
- Configuration editors may remain available but must not require desktop-only hover behavior.

---

## 14. Accessibility requirements

- Every control has an accessible name.
- Checkboxes/switches expose checked state.
- Tab/mode navigation follows keyboard expectations.
- Inspector selection is keyboard-reachable where feasible.
- Focus indicators remain visible.
- Status is not communicated by color alone.
- Live status updates must not create excessive screen-reader announcements.
- Contrast must remain acceptable in supported themes.
- Tooltips cannot be the sole carrier of required information.

---

## 15. Implementation constraints

1. Preserve existing route behavior where practical.
2. Prefer composition/refactoring over duplicating Live 2D/3D logic.
3. Do not introduce a second global state framework solely for this work unless local React state becomes demonstrably insufficient.
4. Keep API requests scene-scoped and consistent with current authorization.
5. Avoid new high-frequency polling when the existing scene stream already carries the data.
6. Continue proper cleanup of intervals, object URLs, SSE streams, Three.js resources, and event listeners.
7. Keep expensive overlays off by default.
8. Do not weaken stale-feed or security behavior to simplify rendering.

---

## 16. Execution plan and progress checklist

### Phase 0 — Specification and guardrails

- [x] **UX-00** Create and check in the durable Scene Workspace UX 2.0 specification.
- [ ] **UX-01** Capture a component-level implementation map before refactor: current SceneWorkspace responsibilities, candidate reusable components, and state ownership.
- [ ] **UX-02** Add a lightweight regression checklist for all currently reachable Scene Workspace capabilities before changing navigation.

### Phase 1 — Information architecture foundation

- [ ] **UX-10** Introduce primary mode navigation: Monitor / Analyze / Configure.
- [ ] **UX-11** Introduce secondary navigation for Monitor.
- [ ] **UX-12** Introduce secondary navigation for Analyze.
- [ ] **UX-13** Introduce secondary navigation for Configure.
- [ ] **UX-14** Remove the existing single long tab row after all destinations are represented in the new structure.
- [ ] **UX-15** Preserve direct scene-entry behavior and sensible default selection: Monitor → 2D Scene.

**Acceptance gate — Phase 1**

- [ ] Every pre-overhaul Scene Workspace destination remains reachable.
- [ ] No duplicated destination exists in conflicting navigation structures.
- [ ] Browser refresh/navigation does not leave the workspace in an invalid state.
- [ ] Monitor/Analyze/Configure intent is visually obvious.

### Phase 2 — Persistent operational status

- [ ] **UX-20** Build a reusable SceneStatusHeader component.
- [ ] **UX-21** Display scene freshness, object count, scene rate, camera health summary, and MQTT state.
- [ ] **UX-22** Implement LIVE / DEGRADED / STALE semantics using only available runtime data.
- [ ] **UX-23** Make unknown health explicit instead of mapping it to healthy.
- [ ] **UX-24** Verify status remains visible while switching scene subviews.

**Acceptance gate — Phase 2**

- [ ] Operator can determine scene health without opening Runtime.
- [ ] Stale scene feed is unmistakable.
- [ ] Unknown and degraded states are differentiated.

### Phase 3 — Contextual view controls

- [ ] **UX-30** Replace the flat checkbox row with structured Layers and Diagnostics controls.
- [ ] **UX-31** Define common layer controls.
- [ ] **UX-32** Define 2D-only controls.
- [ ] **UX-33** Define 3D-only controls.
- [ ] **UX-34** Hide controls that cannot affect the active renderer.
- [ ] **UX-35** Add explicit availability/status messaging for data-dependent controls such as velocity.
- [ ] **UX-36** Preserve fullscreen and current 3D camera/light controls in an appropriate advanced/view section.

**Acceptance gate — Phase 3**

- [ ] No visible control silently has no effect.
- [ ] 2D does not expose 3D-only controls.
- [ ] 3D controls remain accessible without dominating the main toolbar.

### Phase 4 — Contextual inspector

- [ ] **UX-40** Add selection state and inspector shell.
- [ ] **UX-41** Make tracked objects selectable in 2D.
- [ ] **UX-42** Make tracked objects selectable in 3D.
- [ ] **UX-43** Add tracked-object inspector fields.
- [ ] **UX-44** Add camera selection and camera inspector.
- [ ] **UX-45** Add sensor selection and sensor inspector.
- [ ] **UX-46** Add region selection and region inspector.
- [ ] **UX-47** Add tripwire selection and tripwire inspector.
- [ ] **UX-48** Add clear-selection and inspector collapse behavior.
- [ ] **UX-49** Ensure missing optional data is represented honestly.

**Acceptance gate — Phase 4**

- [ ] Clicking a supported visual entity opens the correct inspector.
- [ ] Selection is visually distinguishable.
- [ ] Inspector does not obscure the primary scene on standard desktop width.
- [ ] Object telemetry no longer requires cluttering every object label.

### Phase 5 — Telemetry redesign

- [ ] **UX-50** Refactor scene telemetry into a dedicated HUD/component.
- [ ] **UX-51** Display scene rate and object count.
- [ ] **UX-52** Display per-camera FPS from `live.rate` when available.
- [ ] **UX-53** Add feed freshness.
- [ ] **UX-54** Move rich object `persistent_data` presentation into inspector.
- [ ] **UX-55** Align Camera Feeds telemetry styling and terminology with the scene HUD.
- [ ] **UX-56** Ensure telemetry state survives appropriate Monitor subview switches without stale values leaking between scenes.

**Acceptance gate — Phase 5**

- [ ] Telemetry visibly reproduces the useful 2026.2 semantics.
- [ ] The scene remains readable with telemetry enabled.
- [ ] No misleading zero is shown when the real state is unknown.

### Phase 6 — Heatmap and velocity refinement

- [ ] **UX-60** Formalize current heatmap layer styling and legend.
- [ ] **UX-61** Ensure heatmap works consistently in 2D and 3D.
- [ ] **UX-62** Add heatmap intensity/opacity control if it improves usability without excessive complexity.
- [ ] **UX-63** Add historical range choices only if backed by real retained data.
- [ ] **UX-64** Refine 2D velocity arrows.
- [ ] **UX-65** Refine 3D velocity arrows.
- [ ] **UX-66** Add numeric speed/velocity to object inspector.
- [ ] **UX-67** Add explicit vector availability count.

**Acceptance gate — Phase 6**

- [ ] Heatmap semantics are explained by the UI.
- [ ] Velocity semantics are explained by the UI.
- [ ] No historical visualization is synthesized from unavailable data.

### Phase 7 — Visual hierarchy and responsive polish

- [ ] **UX-70** Establish clear primary/secondary/tertiary visual hierarchy.
- [ ] **UX-71** Reduce equal-weight borders/buttons where they create visual noise.
- [ ] **UX-72** Standardize spacing and toolbar density.
- [ ] **UX-73** Implement responsive inspector drawer behavior.
- [ ] **UX-74** Validate at desktop, medium, and narrow breakpoints.
- [ ] **UX-75** Verify all existing themes.
- [ ] **UX-76** Verify fullscreen behavior after layout refactor.

### Phase 8 — Accessibility and interaction quality

- [ ] **UX-80** Keyboard-test primary/secondary navigation.
- [ ] **UX-81** Keyboard-test layer/diagnostic controls.
- [ ] **UX-82** Add/verify visible focus styles.
- [ ] **UX-83** Add accessible labels/roles for status, inspector, and controls.
- [ ] **UX-84** Ensure health status is not color-only.
- [ ] **UX-85** Validate live updates do not create excessive announcements.

### Phase 9 — Regression, documentation, and completion

- [ ] **UX-90** Run modern-ui TypeScript build.
- [ ] **UX-91** Run relevant frontend lint/test targets available in the repository.
- [ ] **UX-92** Run focused backend regression tests if API behavior changed.
- [ ] **UX-93** Runtime smoke test: Live 2D.
- [ ] **UX-94** Runtime smoke test: Live 3D.
- [ ] **UX-95** Runtime smoke test: Cameras and telemetry.
- [ ] **UX-96** Runtime smoke test: Sensors.
- [ ] **UX-97** Runtime smoke test: Analyze destinations.
- [ ] **UX-98** Runtime smoke test: Configure destinations.
- [ ] **UX-99** Update relevant SceneScape user-guide documentation/screenshots and mark this specification Complete.

---

## 17. Detailed functional regression checklist

The following checklist is deliberately redundant with the task plan. It is a release gate.

### Monitor

- [ ] Scene loads with correct map.
- [ ] Live objects update.
- [ ] Trails toggle.
- [ ] Telemetry toggle.
- [ ] Heatmap toggle.
- [ ] Velocity toggle.
- [ ] Region/tripwire visualization.
- [ ] Child-scene spatial overlays.
- [ ] 3D map/model loads.
- [ ] 3D floor toggle.
- [ ] Camera helpers/frustums.
- [ ] Camera-frame projection.
- [ ] Camera opacity.
- [ ] Selected camera view.
- [ ] Lighting control.
- [ ] Fullscreen.
- [ ] Camera feeds.
- [ ] Camera telemetry.
- [ ] Sensor runtime data.

### Analyze

- [ ] History loads.
- [ ] History data belongs to selected scene.
- [ ] Trends load.
- [ ] Runtime/freshness information is reachable.
- [ ] Incident/event navigation, if included, remains scene-scoped.

### Configure

- [ ] Scene configuration reachable.
- [ ] Geometry editor reachable.
- [ ] Region editing works.
- [ ] Tripwire editing works.
- [ ] Hierarchy editing works.
- [ ] Camera configuration reachable.
- [ ] Sensor configuration reachable.
- [ ] Camera calibration reachable.

### Security and data integrity

- [ ] Scene-scoped viewer cannot expose data from another scene through the inspector.
- [ ] UI does not bypass admin-only mutation rules.
- [ ] Revisions remain attached to native edits/deletes.
- [ ] Protected media continues to use authenticated API access.
- [ ] No secrets/passwords are surfaced in inspectors or diagnostics.

---

## 18. Suggested component architecture

Names are suggestions and may change if implementation reveals a better decomposition.

```text
SceneWorkspace
├── SceneStatusHeader
├── ScenePrimaryNav
├── SceneSecondaryNav
├── MonitorWorkspace
│   ├── SceneViewToolbar
│   │   ├── LayerControls
│   │   └── DiagnosticControls
│   ├── Map2D / ThreeScene / CameraFeeds / SensorRuntime
│   ├── SceneTelemetryHud
│   └── SceneInspector
├── AnalyzeWorkspace
│   ├── HistoryView
│   ├── TrendsView
│   └── RuntimeDiagnostics
└── ConfigureWorkspace
    ├── SceneInventory/editor
    ├── SpatialEditor
    ├── HierarchyEditor
    ├── Camera editor
    ├── Sensor editor
    └── CameraCalibration
```

State that is shared only within Scene Workspace should remain local to the workspace unless a concrete need for wider state management appears.

---

## 19. Data model for UI selection

Suggested discriminated selection shape:

```ts
type SceneSelection =
  | { kind: 'object'; id: string; value: Row }
  | { kind: 'camera'; id: string; value: Row }
  | { kind: 'sensor'; id: string; value: Row }
  | { kind: 'region'; id: string; value: Row }
  | { kind: 'tripwire'; id: string; value: Row }
  | null
```

Do not persist live object payloads longer than necessary merely to support the inspector. The currently selected live object should be refreshed from the latest scene observation when possible.

---

## 20. Performance guardrails

- Do not increase scene polling solely because of the inspector.
- Prefer the existing SSE live scene stream.
- Avoid rebuilding the entire Three.js scene for inspector-only state changes.
- Keep historical heatmap processing bounded.
- Do not render large persistent-data payloads for every object simultaneously.
- Preserve proper disposal of Three.js geometries/materials.
- Preserve object URL revocation.
- Preserve interval/stream cleanup on view changes.
- If a new overlay materially affects frame rate, make it opt-in and document the trade-off.

---

## 21. Completion definition

Scene Workspace UX 2.0 is complete only when:

- [ ] All required UX task checkboxes above are complete or explicitly moved to a documented follow-up.
- [ ] Functional regression checklist passes.
- [ ] Modern UI production build passes.
- [ ] Runtime smoke tests pass against a live scene.
- [ ] Authorization behavior remains intact.
- [ ] Responsive and accessibility checks are complete.
- [ ] User-guide documentation reflects the new navigation and controls.
- [ ] This file's status is changed from **Active** to **Complete**.
- [ ] Final implementation commit SHA is recorded below.

---

## 22. Progress log

| Date | Task(s) | Commit | Notes |
| --- | --- | --- | --- |
| 2026-09-20 | UX-00 | `7060e99c387e84873fbae1cda7cc1e29c916bb8d` | Durable UX specification and execution checklist created. |

---

## 23. Handoff instructions for a future chat/session

When continuing this work:

1. Check out `feature/react-keycloak-modern-ui`.
2. Open this file first.
3. Read the latest Progress Log entry.
4. Start with the first unchecked task whose dependencies are complete.
5. Inspect the current code before assuming this document perfectly reflects implementation details.
6. Implement the task without removing existing capabilities.
7. Run the narrowest relevant checks available.
8. Change that task to `[x]`.
9. Record the commit SHA and any important decision in the Progress Log.
10. Continue in task order unless a dependency or runtime defect justifies reprioritization.

If implementation diverges materially from this specification, update this file **before** proceeding so the repository remains the source of truth.
