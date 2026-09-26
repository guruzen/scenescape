import json
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect, select

from scenescape_api.bluetooth_domain import (
    BluetoothConflict,
    BluetoothRevisionConflict,
    activate_calibration,
    anchor_to_dict,
    assignment_to_dict,
    calibration_to_dict,
    cascade_scene_bluetooth,
    close_assignment,
    create_anchor,
    create_assignment,
    create_calibration,
    create_provider,
    create_tag,
    tag_to_dict,
    update_anchor,
)
from scenescape_api.bluetooth_schema import (
    bluetooth_all_table_names,
    bluetooth_table_names,
    downgrade_all_bluetooth,
    downgrade_bt01,
    upgrade_bt01,
    upgrade_bt02,
    upgrade_bt06,
    upgrade_bt07,
    upgrade_bt08,
    upgrade_bt10,
    upgrade_bt11,
)
from scenescape_api.database import (
    Base,
    BluetoothAnchor,
    BluetoothCalibration,
    Resource,
    utcnow,
)


@pytest.fixture
def db(tmp_path, monkeypatch):
  monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/bluetooth.db")
  import scenescape_api.database as database

  if database._engine is not None:
    database._engine.dispose()
  database._engine = None
  database._Session = None
  engine = database.get_engine()
  Base.metadata.create_all(engine)
  with database.sessions()() as session:
    yield session
    session.rollback()
  engine.dispose()
  database._engine = None
  database._Session = None


def add_scene(db, uid="scene-a"):
  db.add(Resource(kind="scene", uid=uid, revision=1, payload={"uid": uid, "name": uid}))
  db.commit()


def test_bt01_schema_upgrade_and_safe_downgrade_preserve_native_data(db):
  db.add(Resource(kind="scene", uid="keep-scene", revision=1, payload={"uid": "keep-scene"}))
  db.commit()
  engine = db.get_bind()

  downgrade_bt01(engine)
  tables = set(inspect(engine).get_table_names())
  assert not set(bluetooth_table_names()) & tables
  assert "native_resources" in tables
  assert db.scalar(
      select(Resource).where(Resource.kind == "scene", Resource.uid == "keep-scene")
  ) is not None

  upgrade_bt01(engine)
  tables = set(inspect(engine).get_table_names())
  assert set(bluetooth_table_names()) <= tables
  assert db.scalar(
      select(Resource).where(Resource.kind == "scene", Resource.uid == "keep-scene")
  ) is not None


def test_bt16_full_schema_rollback_preserves_native_data_and_can_reupgrade(db):
  db.add(Resource(
      kind="scene",
      uid="keep-scene-bt16",
      revision=1,
      payload={"uid": "keep-scene-bt16"},
  ))
  db.commit()
  engine = db.get_bind()

  downgrade_all_bluetooth(engine)
  tables = set(inspect(engine).get_table_names())
  assert not set(bluetooth_all_table_names()) & tables
  assert "native_resources" in tables
  assert db.scalar(
      select(Resource).where(
          Resource.kind == "scene",
          Resource.uid == "keep-scene-bt16",
      )
  ) is not None

  for upgrade in (
      upgrade_bt01,
      upgrade_bt02,
      upgrade_bt06,
      upgrade_bt07,
      upgrade_bt08,
      upgrade_bt10,
      upgrade_bt11,
  ):
    upgrade(engine)
  tables = set(inspect(engine).get_table_names())
  assert set(bluetooth_all_table_names()) <= tables


def test_bt16_full_schema_rollback_refuses_any_populated_bluetooth_table(db):
  create_provider(db, {"uid": "provider-bt16", "name": "Provider BT16"}, "admin")
  db.commit()
  engine = db.get_bind()

  with pytest.raises(RuntimeError, match="Refusing Bluetooth full schema downgrade"):
    downgrade_all_bluetooth(engine)

  tables = set(inspect(engine).get_table_names())
  assert set(bluetooth_all_table_names()) <= tables


def test_bt01_schema_downgrade_refuses_silent_bluetooth_data_loss(db):
  create_provider(db, {"uid": "provider-a", "name": "Provider A"}, "admin")
  db.commit()
  with pytest.raises(RuntimeError, match="Refusing Bluetooth schema downgrade"):
    downgrade_bt01(db.get_bind())


def test_bt01_provider_anchor_tag_round_trip_and_identity_invariants(db):
  add_scene(db)
  provider = create_provider(
      db,
      {
          "uid": "provider-a",
          "name": "Provider A",
          "kind": "channel-sounding-gateway",
          "capabilities": ["Channel-Sounding", "battery service"],
      },
      "admin",
  )
  anchor = create_anchor(
      db,
      {
          "uid": "anchor-a",
          "serial_number": "ANCHOR-0001",
          "scene_id": "scene-a",
          "provider_id": provider.uid,
          "provider_device_id": "gw-anchor-1",
          "bluetooth_address": "AA:BB:CC:DD:EE:01",
          "capabilities": ["channel_sounding"],
      },
      "admin",
  )
  tag = create_tag(
      db,
      {
          "uid": "tag-a",
          "serial_number": "TAG-0001",
          "provider_id": provider.uid,
          "provider_device_id": "gw-tag-1",
          "capabilities": ["channel_sounding", "battery_service"],
      },
      "admin",
  )
  db.commit()

  assert anchor_to_dict(anchor)["serial_number"] == "ANCHOR-0001"
  value = tag_to_dict(tag)
  assert value["serial_number"] == "TAG-0001"
  assert value["battery"]["percent"] is None
  assert value["battery"]["status"] == "unknown"
  json.dumps(value, default=str)

  with pytest.raises(BluetoothConflict) as duplicate:
    create_anchor(db, {"serial_number": "ANCHOR-0001"}, "admin")
  assert duplicate.value.code == "duplicate_serial"

  with pytest.raises(ValidationError):
    create_tag(
        db,
        {"serial_number": "TAG-ORPHAN", "provider_device_id": "missing-provider"},
        "admin",
    )


def test_bt01_anchor_optimistic_revision_rejects_stale_write(db):
  add_scene(db)
  anchor = create_anchor(
      db,
      {"uid": "anchor-cas", "serial_number": "ANCHOR-CAS", "scene_id": "scene-a"},
      "admin",
  )
  db.commit()
  assert anchor.revision == 1

  updated = update_anchor(
      db,
      anchor.uid,
      {"state": "active", "bluetooth_address": "AA:00:00:00:00:01"},
      "admin",
      expected_revision=1,
  )
  db.commit()
  assert updated.revision == 2
  assert updated.state == "active"

  with pytest.raises(BluetoothRevisionConflict):
    update_anchor(
        db,
        anchor.uid,
        {"state": "maintenance"},
        "admin",
        expected_revision=1,
    )


def test_bt01_assignment_history_prevents_overlap_and_preserves_audit(db):
  tag = create_tag(db, {"uid": "tag-a", "serial_number": "TAG-A"}, "admin")
  db.commit()
  start = utcnow()
  assignment = create_assignment(
      db,
      {
          "uid": "assignment-1",
          "tag_uid": tag.uid,
          "entity_type": "asset",
          "entity_id": "forklift-27",
          "display_name": "Forklift 27",
          "valid_from": start,
          "reason": "commissioning",
      },
      "commissioner",
  )
  db.commit()

  with pytest.raises(BluetoothConflict) as overlap:
    create_assignment(
        db,
        {
            "tag_uid": tag.uid,
            "entity_type": "asset",
            "entity_id": "forklift-28",
            "valid_from": start + timedelta(seconds=1),
        },
        "commissioner",
    )
  assert overlap.value.code == "assignment_overlap"

  closed = close_assignment(
      db,
      assignment.uid,
      "supervisor",
      expected_revision=1,
      closed_at=start + timedelta(minutes=5),
  )
  db.commit()
  assert closed.closed_by == "supervisor"
  assert closed.revision == 2

  next_assignment = create_assignment(
      db,
      {
          "uid": "assignment-2",
          "tag_uid": tag.uid,
          "entity_type": "asset",
          "entity_id": "forklift-28",
          "valid_from": start + timedelta(minutes=6),
      },
      "commissioner",
  )
  db.commit()
  assert assignment_to_dict(next_assignment)["created_by"] == "commissioner"


def test_bt01_calibration_is_scene_bound_versioned_and_scene_delete_safe(db):
  add_scene(db)
  anchor = create_anchor(
      db,
      {"uid": "anchor-cal", "serial_number": "ANCHOR-CAL"},
      "admin",
  )
  db.commit()
  calibration = create_calibration(
      db,
      {
          "uid": "cal-1",
          "anchor_uid": anchor.uid,
          "scene_id": "scene-a",
          "x_m": 2.2,
          "y_m": 3.1,
          "z_m": 3.2,
          "yaw_deg": 90,
          "z_source": "measured",
      },
      "installer",
  )
  db.commit()
  assert calibration.calibration_revision == 1
  assert db.get(BluetoothAnchor, anchor.uid).scene_id == "scene-a"

  active = activate_calibration(db, calibration.uid, "installer", expected_revision=1)
  db.commit()
  assert active.state == "active"
  assert calibration_to_dict(active)["position"] == {"x_m": 2.2, "y_m": 3.1, "z_m": 3.2}

  cascade_scene_bluetooth(db, "scene-a")
  db.commit()
  saved_anchor = db.get(BluetoothAnchor, anchor.uid)
  saved_calibration = db.get(BluetoothCalibration, calibration.uid)
  assert saved_anchor is not None
  assert saved_anchor.scene_id is None
  assert saved_anchor.state == "maintenance"
  assert saved_calibration is not None
  assert saved_calibration.state == "retired"


def test_bt01_second_calibration_revision_retires_previous_active(db):
  add_scene(db)
  anchor = create_anchor(
      db,
      {"uid": "anchor-revisions", "serial_number": "ANCHOR-REVISIONS", "scene_id": "scene-a"},
      "admin",
  )
  first = create_calibration(
      db,
      {
          "uid": "cal-r1",
          "anchor_uid": anchor.uid,
          "scene_id": "scene-a",
          "x_m": 1,
          "y_m": 2,
          "z_m": 3,
      },
      "installer",
  )
  activate_calibration(db, first.uid, "installer", expected_revision=1)
  second = create_calibration(
      db,
      {
          "uid": "cal-r2",
          "anchor_uid": anchor.uid,
          "scene_id": "scene-a",
          "x_m": 1.1,
          "y_m": 2.1,
          "z_m": 3.0,
      },
      "installer",
  )
  db.commit()
  assert second.calibration_revision == 2
  activate_calibration(db, second.uid, "installer", expected_revision=1)
  db.commit()
  assert db.get(BluetoothCalibration, first.uid).state == "retired"
  assert db.get(BluetoothCalibration, second.uid).state == "active"


def test_bt04_four_anchor_calibrations_reload_identically(db):
  add_scene(db, "bt04-reload")
  expected = {}
  for index, point in enumerate(
      ((1.25, 1.5, 3.0), (8.75, 1.5, 3.1), (8.75, 5.5, 3.2), (1.25, 5.5, 3.3)),
      start=1,
  ):
    anchor = create_anchor(
        db,
        {
            "uid": f"bt04-anchor-{index}",
            "serial_number": f"BT04-ANCHOR-{index}",
            "scene_id": "bt04-reload",
        },
        "admin",
    )
    calibration = create_calibration(
        db,
        {
            "uid": f"bt04-cal-{index}",
            "anchor_uid": anchor.uid,
            "scene_id": "bt04-reload",
            "x_m": point[0],
            "y_m": point[1],
            "z_m": point[2],
            "z_source": "surveyed",
        },
        "installer",
    )
    activate_calibration(db, calibration.uid, "installer", 1)
    expected[anchor.uid] = point
  db.commit()
  db.expire_all()

  rows = db.scalars(
      select(BluetoothCalibration)
      .where(
          BluetoothCalibration.scene_id == "bt04-reload",
          BluetoothCalibration.state == "active",
      )
      .order_by(BluetoothCalibration.anchor_uid)
  ).all()
  actual = {row.anchor_uid: (row.x_m, row.y_m, row.z_m) for row in rows}
  assert actual == expected
