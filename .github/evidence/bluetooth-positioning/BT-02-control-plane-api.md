# BT-02 Evidence — Bluetooth Control Plane API

## Status

**COMPLETE**

## Implementation commits

- API implementation: `4fafabae4714`
- Compliance fix: `c07b8d517919`

## Delivered API surface

### Anchors

- `GET /api/v2/bluetooth/anchors`
- `GET /api/v2/bluetooth/anchors/{anchor_id}`
- `POST /api/v2/bluetooth/anchors`
- `PATCH /api/v2/bluetooth/anchors/{anchor_id}?revision=...`
- lifecycle actions: `activate`, `deactivate`, `maintenance`, `retire`
- `DELETE /api/v2/bluetooth/anchors/{anchor_id}?revision=...`

### Tags

- `GET /api/v2/bluetooth/tags`
- `GET /api/v2/bluetooth/tags/{tag_id}`
- `POST /api/v2/bluetooth/tags`
- `PATCH /api/v2/bluetooth/tags/{tag_id}?revision=...`
- lifecycle actions: `activate`, `deactivate`, `maintenance`, `retire`
- `DELETE /api/v2/bluetooth/tags/{tag_id}?revision=...`

### Assignments

- `GET /api/v2/bluetooth/assignments`
- `GET /api/v2/bluetooth/tags/{tag_id}/assignments`
- `POST /api/v2/bluetooth/assignments`
- `POST /api/v2/bluetooth/assignments/{assignment_id}/close?revision=...`

### Diagnostics

- `GET /api/v2/bluetooth/diagnostics`

## Security and authorization evidence

- Bluetooth management uses interactive/browser Bearer principals.
- Service tokens are explicitly rejected from the Bluetooth management plane.
- Mutations require `scenescape-admin`.
- Person/tag assignment history is administrator-only.
- Non-admin anchor reads are filtered by server-side scene scope.
- Cross-scene anchor reads return a structured 403.
- Unlocated tags remain admin-only until a trustworthy scene association exists.
- Mutation audit entries are persisted in `native_bluetooth_audit`.
- Audit records do not store pairing secrets or provider credentials.

## Lifecycle and history safeguards

- New devices may start only as `discovered` or `commissioned`.
- State changes use explicit lifecycle endpoints rather than arbitrary PATCH state changes.
- Invalid lifecycle transitions return structured conflicts.
- Optimistic revision conflicts return HTTP 409.
- Anchor deletion is refused when calibration history exists; retirement is required.
- Tag deletion is refused when assignment history exists; retirement is required.
- Assignment history is append/close oriented rather than destructively overwritten.

## Pagination and filtering

Anchor filtering:

- scene
- state
- serial substring
- provider
- bounded offset/limit

Tag filtering:

- state
- serial substring
- provider
- bounded offset/limit

Assignment filtering:

- tag
- entity type
- entity ID
- active/closed
- bounded offset/limit

Maximum list page size is 200.

## OpenAPI evidence

The test suite verifies that OpenAPI contains the Bluetooth anchor, tag, assignment and diagnostics routes and that the anchor POST schema contains a Channel Sounding commissioning example.

## Bluetooth CI

### Initial BT-02 run

GitHub Actions:
https://github.com/guruzen/scenescape/actions/runs/36147043529

Result:

```text
16 passed, 1 warning in 2.76s
Python compile: PASS
```

### Corrected compliance head

GitHub Actions:
https://github.com/guruzen/scenescape/actions/runs/36147215047

Result:

```text
16 passed, 1 warning in 3.18s
Python compile: PASS
```

The warning is the existing Starlette/AnyIO TestClient deprecation warning.

## Repository-wide regression evidence

Scene Workspace Gate:
https://github.com/guruzen/scenescape/actions/runs/36147222765

Validated on the corrected head:

- Focused native API integrity regression: PASS
- Modern UI UX tests: PASS
- TypeScript typecheck: PASS
- production build: PASS
- browser smoke: PASS
- integrated native UI/API browser smoke: PASS

This confirms the Bluetooth router/auth changes did not regress the existing native SceneScape control plane or UI smoke path.

## Security/compliance evidence on corrected head

- REUSE License Check: PASS — run `36147222981`
- Trivy: PASS — run `36147222973`
- Gitleaks: PASS — run `36147223012`
- Bandit: PASS — run `36147222968`
- Zizmor: PASS — run `36147222941`
- Basic Acceptance Tests: PASS — run `36147223381`
- Tracker Service: PASS — run `36147223000`
- Required lint job: PASS — run `36147223077`
- CodeQL changed Python files: PASS — run `36147223043`
- CodeQL changed Actions files: PASS — run `36147223043`
- CodeQL changed JavaScript/TypeScript files: PASS — run `36147223043`

## Compliance defect found and fixed

The first repository-wide License Check on the API implementation commit failed because the newly added Bluetooth workflow contained an SPDX license identifier but no SPDX copyright line.

Failure run:
https://github.com/guruzen/scenescape/actions/runs/36147054967

The workflow header was corrected in `c07b8d517919`. The subsequent REUSE License Check passed.

## Acceptance

- [x] Anchor CRUD, filters, pagination and lifecycle are exposed by API.
- [x] Tag CRUD, filters, pagination and lifecycle are exposed by API.
- [x] Assignment create/close/history is exposed by API.
- [x] Revision conflicts and invalid transitions are structured.
- [x] Scene-scoped anchor isolation is server enforced.
- [x] Service credentials cannot use the interactive Bluetooth management API.
- [x] Sensitive tag assignment inventory is administrator-only.
- [x] No provider secrets/pairing material is returned.
- [x] Mutation audit is persisted.
- [x] Existing native API/UI regression suites remain green.
- [x] OpenAPI route/example evidence exists.
- [x] Required repository license/security gates relevant to changed files are green.

## Deliberate scope decision

Tags are mobile and BT-01 did not bind them permanently to a scene. BT-02 therefore does not invent a static scene field merely to satisfy UI filtering. Until BT-09 supplies a trustworthy live scene association, full tag inventory and assignment history remain administrator-only. Scene-scoped non-admin users receive only anchor inventory/diagnostics for their authorized scenes.

## Rollback

Disable/remove the Bluetooth router while retaining BT-01/BT-02 tables. Existing SceneScape APIs remain independent. Device, assignment and audit history remain intact for later re-enable.
