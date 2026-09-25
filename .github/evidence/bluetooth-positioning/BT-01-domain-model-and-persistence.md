# BT-01 Evidence — Domain Model and Persistence

## Status
**COMPLETE**

## Scope delivered
BT-01 introduced dedicated relational control-plane persistence for Bluetooth positioning:
- providers;
- anchors;
- tags;
- tag-to-entity assignments;
- versioned anchor calibration records.

High-rate range/position storage remains intentionally deferred to BT-06/BT-07.

## Implementation commits
- Primary implementation: `a5ea92a16cec170487f61e5eca9c28fd27db1791`
- Refresh correctness fix: `23b03b99e9d8e19438190f937279bdedd28d8f3b`

## Key design evidence
- BLE address is transport metadata, not primary identity.
- Anchor/tag serial numbers are unique.
- Provider + provider-device identity has uniqueness protection.
- Unknown battery values remain null/unknown.
- Assignments retain validity intervals, actor, close actor and revision.
- Overlapping tag assignments are rejected.
- Anchor/tag updates use optimistic revision checks.
- Calibration records are revisioned independently from anchor identity.
- Only one active calibration per anchor is allowed.
- Deleting a scene does not delete Bluetooth hardware inventory:
  - anchors are detached from the scene;
  - non-disabled/non-retired anchors move to maintenance;
  - scene calibration records move to retired.
- Physical schema downgrade refuses to discard populated Bluetooth tables unless data loss is explicitly allowed.

## Files
- `control-api/scenescape_api/database.py`
- `control-api/scenescape_api/bluetooth_domain.py`
- `control-api/scenescape_api/bluetooth_schema.py`
- `control-api/scenescape_api/cli.py`
- `control-api/scenescape_api/scene_service.py`
- `control-api/tests/test_bluetooth_domain.py`
- `.github/workflows/bluetooth-positioning-gate.yml`

## CI execution

### Run 1 — defect found
GitHub Actions run: https://github.com/guruzen/scenescape/actions/runs/36141262705

Result:
- Python compile: PASS
- Tests: **9 passed, 1 failed, 1 warning**
- Failure: `test_bt01_assignment_history_prevents_overlap_and_preserves_audit`
- Cause: mutation succeeded in the database, but the service returned an already-loaded SQLAlchemy assignment object without an explicit refresh, so `closed_by` was stale in the same session.

Resolution:
- Explicitly expire/refresh assignment and calibration rows after atomic update before returning from the domain service.

### Run 2 — passing gate
GitHub Actions run: https://github.com/guruzen/scenescape/actions/runs/36141424205

Commands:
```text
python -m compileall -q control-api/scenescape_api

pytest -q \
  control-api/tests/test_bluetooth_domain.py \
  control-api/tests/test_native_api.py::test_native_updates_require_revision_and_reject_stale_writes \
  control-api/tests/test_native_api.py::test_resource_kind_uid_unique_index_survives_migrate \
  control-api/tests/test_native_api.py::test_native_delete_requires_current_revision
```

Result:
```text
10 passed, 1 warning in 2.04s
```

The warning is the existing Starlette/AnyIO deprecation warning from TestClient infrastructure; it is not introduced by BT-01.

## Acceptance evidence
- [x] Migration upgrade/downgrade tested with existing native data preserved.
- [x] Populated downgrade refuses silent data loss.
- [x] Provider/anchor/tag round-trip and identity invariants tested.
- [x] Optimistic revision conflict tested.
- [x] Assignment overlap and close/audit behavior tested.
- [x] Calibration revision activation/retirement tested.
- [x] Scene deletion/cascade policy tested.
- [x] Existing native revision/unique-index/delete regression tests passed in the BT gate.
- [x] Python modules compiled successfully.

## Known limitations / deferred items
- Public Bluetooth CRUD APIs are BT-02.
- Management UI is BT-03.
- Fine anchor placement workflow is BT-04.
- High-rate measurements and solved positions are not part of BT-01.
- PostgreSQL-specific runtime validation remains part of later integration/production gates; the current BT-01 CI gate exercises SQLite plus SQLAlchemy cross-dialect schema definitions.

## Rollback
Normal operational rollback is to disable Bluetooth positioning and leave additive control-plane tables intact. The explicit BT-01 downgrade helper can remove empty tables; populated tables require `allow_data_loss=True` so rollback cannot silently destroy Bluetooth configuration.
