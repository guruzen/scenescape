<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# UX-90–UX-99 Evidence — Final Regression, Runtime Smoke, and Documentation

## Scope

This evidence closes the final Scene Workspace UX 2.0 gate:

- UX-90 production TypeScript/Vite build.
- UX-91 available frontend regression/typecheck/browser targets.
- UX-92 focused backend regressions for API behavior touched during final integration.
- UX-93 Live 2D runtime smoke.
- UX-94 Live 3D runtime smoke.
- UX-95 Cameras and telemetry runtime smoke.
- UX-96 Sensors runtime smoke.
- UX-97 Analyze destinations runtime smoke.
- UX-98 Configure destinations runtime smoke.
- UX-99 user-guide/documentation completion and automated screenshot evidence.

Validated implementation head: `7b7cc29310b20407c084da0edc7a96afd1a17a05`.

Validation PR: **#1**, draft, targeting `release-2026.2.0`.

Final Scene Workspace UX workflow run: **35490508522**.

## UX-90 — Production build

The CI job checked out the repository and ran:

```bash
cd modern-ui
npm install --no-audit --no-fund
npm run typecheck
npm run build
```

Result:

```text
TypeScript typecheck: success
vite v8.3.0
✓ built in 335ms
```

The Vite reporter emitted only the existing chunk-size advisory. The production build completed successfully.

## UX-91 — Frontend regression targets

`modern-ui/package.json` does not define a separate `lint` script. The available relevant frontend gates were therefore run:

- `npm run test:ux`
- `npm run typecheck`
- `npm run build`
- `npm run test:smoke:ux`
- `npm run test:smoke:native`

Contract/unit/integrity suite:

```text
tests 24
pass 24
fail 0
```

Browser fixture suite:

```text
Running 7 tests using 1 worker
7 passed (15.2s)
```

## UX-92 — Focused native API regression

The backend job runs authorization, scene-scope, revision, protected-media,
archive-safety, Keycloak projection, runtime parity, camera telemetry, and the
final scene-observation isolation regression.

Final result:

```text
21 passed, 1 warning in 1.65s
```

The warning is an upstream Starlette/AnyIO deprecation warning and is not a test failure.

## Final integration defect discovered and fixed

The real UI/API seam test exposed a genuine native API defect.

Camera observations can legitimately include the parent scene ID. The old
`_scene_observation_clause` matched any observation whose stored
`Observation.scene_id` equalled the scene. A newer camera observation could
therefore be selected as the scene's live observation. Camera payloads expose
`objects` as a category map, while the regulated scene contract exposes
tracked objects as an array. This could crash the React live trail path.

Fixes:

- `99e4d9dfb13ef9f1f8c5d32dbb640aa9153b60b5` — scene live/history/trends now select actual `regulated/scene` or `data/scene` topics instead of arbitrary observations carrying the same scene ID.
- `3d75118db120366cfbd9d82167e54328c44eb54e` — backend regression proving newer camera observations cannot contaminate scene live/history/trends.
- `8a88a5a4dae2a1b86770a457088ede8ced570b29` — pure live-scene normalization helper.
- `66687fa8a9e6dadb2dacd66256f51fd09aa9c4da` — live fetch/SSE consumption defensively normalizes non-array object payloads.
- `a29033aff58f511df584f7b1f7c11b9584fbb84f` — frontend regression for malformed/non-array object payloads.

The test was not weakened to accommodate the defect; the API and UI boundaries were corrected.

## UX-93–UX-98 — Integrated native UI/API smoke

A second Playwright layer runs the real React application against:

- the real FastAPI control API
- real SQLAlchemy persistence using isolated SQLite
- real service-token authentication path
- real SSE live-scene stream
- real native history/trends endpoints
- real sensor telemetry persistence
- real camera telemetry endpoint
- protected media proxying
- a deterministic synthetic live camera snapshot

The data source is synthetic, but the UI/API/database/stream path is the native implementation rather than browser-route mocks.

Final result:

```text
Running 6 tests using 1 worker
6 passed (13.4s)
```

### UX-93 — Live 2D

Verified:

- native 2D map is present
- map media renders
- operational state is visible
- tracked objects arrive from the native live stream
- a tracked object's X coordinate changes across successive SSE observations
- Trails can be enabled and a real trail polyline appears
- Telemetry HUD appears
- Heatmap is enabled and heatmap/core geometry is rendered
- Velocity is enabled and velocity arrows are rendered
- vector availability reports `2/2 vectors`
- configured region is rendered
- configured tripwire is rendered
- object inspector opens from the streamed object
- persistent object data is available in the inspector

The mocked browser suite additionally verifies child-region/child-tripwire overlays and fullscreen.

### UX-94 — Live 3D

Verified:

- native WebGL/Three.js canvas renders
- 3D view controls remain present
- tracked-object selector follows live native scene data
- selected object opens in the contextual inspector
- Heatmap and Velocity remain available in 3D

The browser fixture suite additionally verifies:

- floor toggle
- camera-frame projection
- selected camera
- camera view
- camera opacity
- lighting control

### UX-95 — Cameras and telemetry

Verified against the native API:

- configured camera appears
- protected synthetic camera snapshot renders
- camera telemetry strip renders
- feed state is `Receiving`
- detections are derived from retained camera observations

### UX-96 — Sensors

Verified against native persistence:

- configured native sensor appears
- latest retained sensor telemetry is loaded
- deterministic live temperature values are rendered

### UX-97 — Analyze

Verified against native persistence:

- History destination is reachable
- persisted observations load in the native history list
- Trends destination is reachable
- retained trend rows load
- Runtime destination is reachable
- MQTT ingestion reports the synthetic native heartbeat as `connected`

History/trends requests are issued for the active scene ID, and backend scene-scope regressions protect those resources.

### UX-98 — Configure

Verified:

- Geometry destination is reachable
- Hierarchy destination is reachable
- Calibration destination is reachable
- Scene inventory route is reachable
- Camera inventory route is reachable
- Sensor inventory route is reachable

The browser fixture suite additionally performs real React interactions for region/tripwire edits, including revision-carrying native PUT operations.

## Functional regression checklist mapping

### Monitor

Covered by final browser/integration evidence:

- correct map
- live object updates
- trails
- telemetry
- heatmap
- velocity
- region/tripwire visualization
- child-scene spatial overlays
- 3D renderer
- 3D floor
- camera helpers/frame projection
- camera opacity
- selected camera view
- lighting
- fullscreen
- camera feeds/telemetry
- sensor runtime data

### Analyze

Covered:

- scene history
- active-scene history scope
- trends
- runtime/freshness

Scene-specific Incidents/Events are not part of the final Analyze secondary navigation contract; the application retains its separate incident workflow.

### Configure

Covered:

- scene configuration
- geometry editor
- region/tripwire editing
- hierarchy
- camera configuration
- sensor configuration
- camera calibration

### Security/data integrity

Focused backend regressions cover:

- viewer scene scopes
- camera-telemetry scene scope
- auto-calibration scene boundaries
- scene-scoped overview/incidents
- admin-only native mutation
- optimistic revision requirements
- stale update rejection
- revision-checked deletion
- protected media authorization
- model/scene archive traversal and archive-bomb rejection
- Keycloak role/ACL projection

Earlier hierarchy evidence also locks remote-child MQTT passwords as write-only and ensures blank updates preserve stored secrets.

## UX-99 — Documentation and screenshots

Updated documentation:

- `docs/user-guide/how-to-guides/ui-tutorial.md`
  - Monitor / Analyze / Configure navigation
  - persistent operational status
  - Layers vs Diagnostics
  - contextual inspector
  - telemetry semantics
  - heatmap/velocity behavior
  - 2D/3D controls
  - fullscreen
  - keyboard/accessibility behavior
  - native revision-conflict behavior
- `docs/user-guide/index.md`
  - replaces the obsolete Django-web-server description with the React + Keycloak + FastAPI native architecture.

Documentation commits:

- `a652594aae70727b1f4c9961ff9a387c437fbd34`
- `eac2460b5846fcfa933c78849979e1b4ebba5d93`

Automated screenshot/trace evidence from final run **35490508522**:

- `scene-workspace-ux-smoke` — artifact **10598677485**
- `scene-workspace-native-integration` — artifact **10599011878**

These include the monitored 2D/3D, cameras, sensors, Analyze, Configure, calibration/inventory, and accessibility evidence produced by Playwright.

## Repository quality checks

For validated implementation head `7b7cc29310b20407c084da0edc7a96afd1a17a05`, the following repository workflows completed successfully before this evidence was written:

- Basic Acceptance Tests
- Bandit Security Scan
- ClamAV Antivirus Scan
- CodeQL
- Gitleaks
- License Check
- OSSF Scorecard
- Tracker Service CI
- Trivy
- Zizmor
- Documentation Check
- Scene Workspace UX Gate

The native migration surfaces were also annotated in `REUSE.toml` so the branch passes the repository REUSE/license gate.

## Verification boundary

The final integration smoke is intentionally deterministic: it uses the real
native UI/API/database/SSE implementation with synthetic observations and a
test service identity. It does **not** claim validation of a production
Keycloak server, physical camera, external MQTT broker, GPU/driver stack, or a
specific customer deployment.

Within that boundary, the Scene Workspace UX 2.0 implementation, regression
suite, production build, native API integration, documentation, and automated
runtime smoke are complete.
