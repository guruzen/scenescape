# BT-09 Evidence — Scene Data-Plane Integration

## Status

**COMPLETE**

## Scope delivered

BT-09 projects Bluetooth tracked positions into the existing SceneScape scene
data plane without replacing or mutating camera/vision observations.

Delivered behavior:

- stable live object ID `bt:{tag_id}`;
- additive live payload with preserved vision objects;
- bundle exposure of calibrated Bluetooth anchors;
- scene-scoped SSE live stream with polling fallback in the UI;
- Bluetooth-specific history with tag/state/time filters;
- 2D tags, calibrated anchors, uncertainty rings, velocity, trails and anchor links;
- 3D Bluetooth objects, anchors, uncertainty and contributing-anchor links;
- inspector fields for source/method, state, uncertainty, anchors, freshness and battery;
- assignment labels only for authorized/admin viewers;
- Bluetooth and vision remain separate by default.

## Implementation commits

Core backend:

- `1a97176bcacb` — additive SceneScape Bluetooth adapter.
- `5357f29d88c5` — scene isolation and history tests.
- `1c5314c19adf` — contributing-anchor provenance in live objects.
- `4ff1692d7a2d` — live anchor provenance test.
- `04f9e3e93325` — redact assignment identity for non-admin viewers.
- `76cecb2a7c50` — assignment privacy regression.

UI/data plane:

- `81513df092ff` — Bluetooth anchors and uncertainty in 2D.
- `05bf8b5f807f` — calibrated anchors passed to 3D.
- `bce6a9c356c3` — Bluetooth anchors and uncertainty in 3D.
- `18ec7d3b931d` — Tags/Anchors/Uncertainty/Anchor-links controls.
- `2ba9c2da5f9d` — 3D anchor diagnostics and contributing-anchor links.
- `f784c2f02a13` — Bluetooth inspector/live UX contract tests.

Completion evidence:

- `053532182eff` — dedicated Bluetooth 2D/3D Playwright scenario and screenshots.
- `092cdabf795c` — focused BT-09 backend/UI/Playwright gate.

## Camera/vision isolation

`merge_live_payload()` copies the original scene payload and appends Bluetooth
objects. Existing vision objects are preserved byte-for-structure in the
regression test.

If an upstream vision payload contains a malformed non-list `objects` field,
BT-09 does not silently overwrite or reinterpret it; the original value is
preserved as `vision_objects_unparsed` while Bluetooth remains independently
available.

The normal, fusion-disabled result is:

- `vision_objects`: original vision object list;
- `bluetooth.objects`: Bluetooth-only list;
- `objects`: vision objects followed by Bluetooth objects;
- `fusion.enabled=false`.

Thus BT-09 does not fuse or relabel vision identities.

## Live object contract

A tracked Bluetooth object exposes:

- `id=bt:{tag_id}`;
- `source=bluetooth`;
- position and velocity;
- horizontal tracking radius;
- source timestamp;
- position state and predicted flag;
- positioning method;
- quality score and anchors used;
- horizontal/vertical uncertainty;
- solver/tracker versions;
- calibration/identity revision provenance;
- last measured timestamp;
- contributing anchor IDs;
- battery value/status/source/timestamp.

Unavailable coordinates are not rendered.

## Authorization/privacy evidence

For an admin, the active assignment can provide an operator-friendly display
label such as `Forklift 27`.

For a scene-scoped non-admin viewer:

- the precise Bluetooth position remains available for the authorized scene;
- the object label falls back to the tag ID;
- assignment `entity_id` is redacted;
- assignment `display_name` is redacted;
- access to another scene returns HTTP 403.

Bluetooth history uses the same assignment-label authorization rule and scene
authorization gate.

## History evidence

`GET /api/v2/scenes/{scene}/history/bluetooth` supports:

- tag ID;
- state;
- `since`;
- `until`;
- bounded limit.

The backend regression verifies a predicted-state filter returns only the
matching tag/state row.

## SSE and polling fallback

The Scene Workspace consumes:

`/api/v2/scenes/{scene}/live/stream`

through `apiJsonStream()`. If the stream fails, the workspace starts a
500-ms polling fallback against the live endpoint. This preserves operation
when SSE is unavailable without creating a separate Bluetooth transport.

## 2D/3D UX evidence

2D rendering supports:

- Bluetooth object marker/source styling;
- uncertainty radius;
- velocity vector;
- bounded trail history;
- calibrated anchor markers;
- contributing-anchor links.

3D rendering supports:

- Bluetooth-specific generated model color;
- uncertainty ring;
- calibrated anchor octahedrons;
- contributing-anchor 3D links;
- velocity visualization through the existing scene controls.

The dedicated Playwright scenario verifies the Bluetooth object, anchor,
uncertainty and anchor-link layers, opens the inspector, verifies Channel
Sounding provenance/uncertainty/battery, then switches to the 3D scene.

## Playwright screenshot evidence

Focused GitHub Actions run:

`https://github.com/guruzen/scenescape/actions/runs/36291965894`

Playwright result:

```text
1 passed (4.6s)
```

Scenario:

`BT-09 Bluetooth live layer renders in 2D and 3D with provenance`

Screenshots generated:

- `bt09-live-2d.png`
- `bt09-live-3d.png`

Uploaded artifact:

- name: `bt09-playwright-evidence`
- artifact ID: `10923185091`
- size: 413,825 bytes
- SHA-256: `b5f8eba2646bd6ccd75d8f09894d601f78dbad111727e3801c16c25e2fd09655`
- retention expiry: 2026-10-27

## Backend CI evidence

Same focused run, BT-09 backend job:

```text
7 passed, 1 deselected, 1 warning in 2.08s
```

The deselected test is BT-16-specific and intentionally excluded by the
`-k bt09` feature gate.

## UI contract/build evidence

The same focused UI job completed successfully:

- Scene Workspace UX contracts;
- TypeScript typecheck;
- production Vite build;
- dedicated BT-09 Playwright scenario;
- screenshot artifact upload.

## Acceptance evidence

- [x] Bundle/live isolation.
- [x] 2D uncertainty/trails/velocity.
- [x] 3D rendering.
- [x] SSE plus polling fallback.
- [x] History filters.
- [x] Malformed vision payload isolation.
- [x] Vision regression / no replacement.
- [x] 2D/3D screenshots.
- [x] Playwright evidence.
- [x] Backend tests.
- [x] BLE live positions do not corrupt camera data.
- [x] Quality/provenance is visible.
- [x] Existing Scene Workspace UX remains functional.
- [x] BLE and vision remain separate.
- [x] Assignment identity is permissioned.

## Known limitations / deferred items

- BT-09 does not perform vision/Bluetooth fusion; that is BT-15.
- Weak-z honesty is inherited from BT-07/BT-08: a constrained-z solve is not
  promoted to independently observed 3D accuracy.
- Screenshot artifacts are retained by GitHub Actions for a bounded period;
  the textual CI evidence and committed Playwright scenario remain permanent.
- Incident semantics belong to BT-14.

## Rollback

Disable the Bluetooth live layer/source adapter. Stored raw/tracked history
remains intact and existing camera/vision scene data continues independently.
