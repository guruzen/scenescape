# BT-04 Evidence — Scene Anchor Calibration

## Status

**COMPLETE**

## Validated implementation head

`048db9c569b3`

## Implementation record

- Calibration domain and geometry model: `defd07a5f44f`
- Calibration revision API and backend tests: `be2ccfe1b1f4`
- React scene-anchor calibration workspace: `5365d9616d13`
- E2E placement and restore semantics: `a2b155fd6f09`
- UI regression contract update: `a0e7d7c497f2`
- Working-revision rollback selection fix: `d6330bc58c53`
- Map-transform/persistence separation: `cb2731fef5d9`
- Explicit 1 cm UI click tolerance: `2207fd662e71`
- Calibration operation feedback preservation: `048db9c569b3`

## Delivered calibration model

Bluetooth anchor calibration is a versioned resource separate from hardware identity. Each revision records anchor, scene, revision number, draft/active/retired state, X/Y/Z metres, yaw/pitch/roll, Z provenance, author/timestamps and optimistic record revision.

The authoritative stored coordinate frame is `scene_local_m`. Browser or image pixels are never persisted as positioning coordinates.

## Coordinate transform evidence

The floor-map editor uses the existing SceneScape convention:

```text
x_m = image_x_px / scene_scale_px_per_m
y_m = (image_height_px - image_y_px) / scene_scale_px_per_m
```

The mocked browser test clicks a known map location at 100 px/m and verifies the derived coordinates are within 1 cm of the expected metre position. It then enters exact surveyed coordinates before persistence, separating browser click quantization from database fidelity.

## Calibration workspace

- scene and anchor selection
- authenticated floor-map image
- clickable X/Y placement
- explicit X/Y/Z metre fields
- mounting height through Z
- Z provenance: measured / surveyed / default
- yaw / pitch / roll
- anchor markers
- save draft / publish
- active-revision indicator
- revision history and explicit restore
- immediate-parent projection for local child scenes
- geometry quality metrics and warnings
- truthful no-map fallback without fabricated coordinates

Non-admin users receive a read-only calibration view consistent with BT-02 scene-scope authorization.

## Revision and rollback semantics

- New calibration creates a draft revision.
- A newer draft drives geometry preview while under evaluation.
- Publishing makes the draft active and retires the previous active revision.
- Restoring a retired revision makes that historical revision active and retires the formerly active revision.
- The UI selects draft, then active, then historical for the working revision.
- Operation feedback survives internal refresh/reselection after a successful mutation.

## Geometry validation

- fewer than three anchors → `insufficient_anchors` error
- exactly three anchors → `limited_redundancy` warning
- less than 0.05 m separation → `duplicate_anchor_location` error
- less than 0.5 m separation → `near_duplicate_anchor_location` warning
- low horizontal spread → `collinear_geometry` warning
- well-spread four-anchor layouts report `ready_for_2d=true`

Advanced GDOP, RF bias and coverage modelling remain deferred to BT-11.

## Child-scene behavior

Calibration remains authoritative in the selected scene local metre frame. For local child scenes the API additionally returns an informational immediate-parent projection using the existing hierarchy scale, XYZ Euler rotation and translation.

A backend test verifies child-local `(2, 3, 4)` under translation `(10, 20, 1)` projects to parent `(12, 23, 5)` while stored calibration remains `(2, 3, 4)`.

## API surface

- `GET /api/v2/bluetooth/calibrations`
- `GET /api/v2/bluetooth/anchors/{anchor_id}/calibrations`
- `GET /api/v2/bluetooth/calibrations/geometry?scene_id=...`
- `POST /api/v2/bluetooth/calibrations`
- `POST /api/v2/bluetooth/calibrations/{calibration_id}/publish?revision=...`
- `POST /api/v2/bluetooth/calibrations/{calibration_id}/restore?revision=...`

Reads are scene-scope filtered. Create/publish/restore require administrator authorization and are audited as `draft:create`, `publish`, and `restore`. The server rejects non-finite or implausibly out-of-bound coordinates and prevents new calibration revisions on retired anchors.

## Stored calibration evidence

The integrated React → real FastAPI browser test persists and reads back:

```text
position = (2.0, 4.2, 3.4) metres
coordinate_frame = scene_local_m
z_source = surveyed
```

The browser is reloaded and the same values are restored. A separate backend regression creates four active anchors, expires the SQLAlchemy session, reloads from persistence and verifies all four X/Y/Z tuples are identical to the expected values.

## Bluetooth-specific CI

GitHub Actions run: `36193994359`

```text
Bluetooth backend/native regression: 19 passed, 1 warning in 3.10s
Bluetooth UI contract: PASS
TypeScript typecheck: PASS
Production build: PASS
BT-04 contract test: PASS
```

The warning is the existing upstream TestClient deprecation warning.

## Scene Workspace regression and E2E evidence

GitHub Actions run: `36193994417`

```text
Focused native API integrity regression: 21 passed, 1 warning in 2.55s
Mocked browser smoke: 10 passed
Integrated React + real FastAPI browser smoke: 8 passed
TypeScript typecheck: PASS
Production build: PASS
```

Mocked BT-04 coverage includes map placement, pixel-to-metre transform, exact surveyed entry, Z provenance/orientation, geometry warnings, draft/publish r1, draft/publish r2, restore r1, reload and restored-coordinate verification.

Integrated BT-04 coverage uses the real FastAPI backend to commission four anchors, persist `(2.0, 4.2, 3.4)` metres, verify `scene_local_m`, and reload the browser with the same coordinates.

### Browser evidence artifacts

- `bt04-anchor-calibration.png`
- `bt04-integrated-calibration.png`
- `scene-workspace-ux-smoke`
- `scene-workspace-native-integration`

## Required lint and security evidence

Validated on `048db9c569b3`:

- Required lint: PASS — run `36194002205`
  - Prettier: PASS
  - GitHub Actions lint: PASS
  - Python indentation: PASS
- CodeQL: PASS — run `36194002074`
- License Check: PASS — run `36194002178`
- Trivy: PASS — run `36194002200`
- Bandit: PASS — run `36194002058`
- Gitleaks: PASS — run `36194002194`
- Zizmor: PASS — run `36194002342`
- ClamAV: PASS — run `36194002082`
- Basic Acceptance Tests: PASS — run `36194002263`
- Tracker Service: PASS — run `36194001948`
- Documentation Check: PASS — run `36194002759`

## Defects found and corrected during BT-04

1. The BT-03 static contract expected the removed calibration placeholder; it was updated to inspect the real BT-04 component.
2. TypeScript caught stale variable references after introducing draft/active working-revision precedence.
3. Browser click quantization produced millimetre differences; map-transform evidence now uses an explicit 1 cm UI tolerance while persistence is tested exactly.
4. Programmatic anchor reselection cleared draft-save success feedback; manual selection and post-mutation refresh now have distinct feedback behavior.

## Acceptance

- [x] Installer can place an anchor through the floor map and edit exact metre coordinates.
- [x] X/Y/Z, mounting height, orientation and Z provenance are versioned.
- [x] Four active anchors reload identically from persistence.
- [x] Solver-facing coordinates are explicitly scene-local metres.
- [x] Duplicate, near-duplicate, insufficient and near-collinear geometry is surfaced.
- [x] Draft, publish and active states are explicit.
- [x] Historical calibration is explicitly restorable.
- [x] Child-scene calibration retains local coordinates and exposes parent projection provenance.
- [x] Mocked and real-FastAPI browser flows pass.
- [x] Existing native API, Scene Workspace, security and required lint gates remain green.

## Deliberate scope boundary

BT-04 validates geometric placement, not radio accuracy. It does not claim Bluetooth positioning accuracy, calculate GDOP, learn RF bias or infer RF coverage. Those concerns remain with BT-11 through BT-13.

## Rollback

Restore any retired calibration revision through the BT-04 restore endpoint/UI, or disable/retire the affected anchor. Hardware identity and calibration history remain intact.
