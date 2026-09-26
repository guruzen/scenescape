# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from scenescape_api.bluetooth_domain import (
    activate_calibration,
    create_anchor,
    create_assignment,
    create_calibration,
    create_tag,
)
from scenescape_api.bluetooth_scene import (
    bluetooth_history,
    merge_live_payload,
    scene_bluetooth_objects,
)
from scenescape_api.database import (
    BluetoothTrackedPosition,
    Observation,
    Resource,
)


def _token(*, admin=True, scenes=None):
  roles = ["scenescape-admin"] if admin else ["scenescape-viewer"]
  return jwt.encode(
      {
          "sub": "admin" if admin else "viewer",
          "name": "admin" if admin else "viewer",
          "roles": roles,
          "scenes": scenes if scenes is not None else ["*"],
          "iat": int(time.time()),
          "exp": int(time.time()) + 600,
          "aud": "scenescape-api",
      },
      "test-signing-key-abcdefghijklmnopqrstuvwxyz",
      algorithm="HS256",
  )


def _headers(*, admin=True, scenes=None):
  return {"Authorization": "Bearer " + _token(admin=admin, scenes=scenes)}


@pytest.fixture
def api(tmp_path, monkeypatch):
  monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/bt-scene.db")
  monkeypatch.setenv("API_SIGNING_KEY", "test-signing-key-abcdefghijklmnopqrstuvwxyz")

  import scenescape_api.database as database
  if database._engine is not None:
    database._engine.dispose()
  database._engine = None
  database._Session = None

  import scenescape_api.app as app_module
  monkeypatch.setattr(app_module, "notify_config_change", lambda *args, **kwargs: None)
  monkeypatch.setattr(app_module, "notify_camera_change", lambda *args, **kwargs: None)
  database.Base.metadata.create_all(database.get_engine())
  client = TestClient(app_module.app)
  yield client, database

  database.get_engine().dispose()
  database._engine = None
  database._Session = None


def _seed_scene(database, *, scene_id="scene-a", with_assignment=True):
  now = datetime.now(timezone.utc)
  with database.sessions()() as db:
    db.add(Resource(
        kind="scene",
        uid=scene_id,
        revision=1,
        payload={"uid": scene_id, "name": "Warehouse A", "scale": 100},
    ))
    anchor = create_anchor(
        db,
        {
            "uid": "anchor-a",
            "serial_number": "ANCHOR-A",
            "scene_id": scene_id,
            "state": "active",
            "capabilities": ["channel_sounding"],
        },
        "admin",
    )
    calibration = create_calibration(
        db,
        {
            "uid": "cal-a",
            "anchor_uid": anchor.uid,
            "scene_id": scene_id,
            "x_m": 1.0,
            "y_m": 2.0,
            "z_m": 3.0,
        },
        "admin",
    )
    activate_calibration(db, calibration.uid, "admin", 1)
    tag = create_tag(
        db,
        {
            "uid": "tag-a",
            "serial_number": "TAG-A",
            "state": "active",
            "battery_percent": 55.0,
            "battery_status": "normal",
            "battery_source": "gatt",
            "battery_observed_at": now,
        },
        "admin",
    )
    if with_assignment:
      create_assignment(
          db,
          {
              "uid": "assign-a",
              "tag_uid": tag.uid,
              "entity_type": "asset",
              "entity_id": "forklift-27",
              "display_name": "Forklift 27",
              "valid_from": now - timedelta(minutes=1),
          },
          "admin",
      )
    db.add(BluetoothTrackedPosition(
        scene_id=scene_id,
        tag_uid=tag.uid,
        source_timestamp=now,
        x_m=4.0,
        y_m=5.0,
        z_m=1.0,
        vx_mps=0.8,
        vy_mps=0.1,
        vz_mps=0.0,
        heading_deg=7.1,
        state="good",
        predicted=False,
        horizontal_uncertainty_m=0.24,
        vertical_uncertainty_m=None,
        score=0.92,
        anchors_used=4,
        method="channel_sounding",
        solver_name="robust-wls",
        solver_version="1",
        tracker_name="cv-kalman",
        tracker_version="1",
        provenance={
            "calibration_revision": "cal-r1",
            "identity_revision": "assign-a",
            "last_measured_at": now.isoformat(),
            "accepted_anchor_ids": ["anchor-a"],
        },
    ))
    db.commit()
  return now


def test_bt09_merge_is_additive_and_does_not_mutate_vision_objects():
  camera_object = {
      "id": "camera-person-7",
      "category": "person",
      "translation": [2.0, 3.0, 0.0],
      "velocity": [0.2, 0.0, 0.0],
      "camera_specific": {"reid": "abc"},
  }
  original = {"id": "scene-a", "objects": [camera_object], "scene_rate": 10.0}
  bt_object = {
      "id": "bt:tag-a",
      "source": "bluetooth",
      "translation": [4.0, 5.0, 1.0],
  }

  merged = merge_live_payload(original, [bt_object])

  assert original["objects"] == [camera_object]
  assert merged["objects"][0] == camera_object
  assert merged["objects"][1] == bt_object
  assert merged["bluetooth"]["objects"] == [bt_object]
  assert merged["bluetooth"]["count"] == 1


def test_bt09_malformed_vision_objects_are_preserved_not_replaced():
  malformed = {"person": [{"id": 1}]}
  merged = merge_live_payload(
      {"objects": malformed},
      [{"id": "bt:tag-a", "source": "bluetooth"}],
  )
  assert merged["vision_objects_unparsed"] == malformed
  assert merged["objects"] == [{"id": "bt:tag-a", "source": "bluetooth"}]


def test_bt09_live_endpoint_appends_stable_bt_object_and_preserves_camera(api):
  client, database = api
  now = _seed_scene(database)
  vision = {
      "id": "scene-a",
      "objects": [{
          "id": "vision-1",
          "category": "person",
          "translation": [2, 2, 0],
          "detector": "camera-a",
      }],
      "scene_rate": 12.5,
  }
  with database.sessions()() as db:
    db.add(Observation(
        scene_id="scene-a",
        topic="scenescape/data/scene/scene-a",
        observed_at=now,
        payload=vision,
    ))
    db.commit()

  response = client.get("/api/v2/scenes/scene-a/live", headers=_headers())
  assert response.status_code == 200, response.text
  value = response.json()
  assert value["scene_rate"] == 12.5
  assert value["objects"][0] == vision["objects"][0]
  bluetooth = value["objects"][1]
  assert bluetooth["id"] == "bt:tag-a"
  assert bluetooth["source"] == "bluetooth"
  assert bluetooth["label"] == "Forklift 27"
  assert bluetooth["translation"] == [4.0, 5.0, 1.0]
  assert bluetooth["velocity"] == [0.8, 0.1, 0.0]
  assert bluetooth["bluetooth"]["method"] == "channel_sounding"
  assert bluetooth["bluetooth"]["anchor_ids"] == ["anchor-a"]
  assert bluetooth["bluetooth"]["battery"]["percent"] == 55.0


def test_bt09_scene_scoped_viewer_gets_position_but_not_assignment_label(api):
  client, database = api
  _seed_scene(database)
  response = client.get(
      "/api/v2/scenes/scene-a/live",
      headers=_headers(admin=False, scenes=["scene-a"]),
  )
  assert response.status_code == 200, response.text
  bt = next(item for item in response.json()["objects"] if item["id"] == "bt:tag-a")
  assert bt["label"] == "tag-a"
  assert bt["bluetooth"]["assignment"]["entity_id"] == "forklift-27"
  assert bt["bluetooth"]["assignment"]["display_name"] is None

  denied = client.get(
      "/api/v2/scenes/scene-a/live",
      headers=_headers(admin=False, scenes=["other-scene"]),
  )
  assert denied.status_code == 403


def test_bt09_bundle_exposes_calibrated_anchor_layer(api):
  client, database = api
  _seed_scene(database)
  response = client.get("/api/v2/scenes/scene-a/bundle", headers=_headers())
  assert response.status_code == 200, response.text
  anchors = response.json()["bluetooth_anchors"]
  assert len(anchors) == 1
  assert anchors[0]["id"] == "anchor-a"
  assert anchors[0]["translation"] == [1.0, 2.0, 3.0]
  assert anchors[0]["calibration_revision"] == 1


def test_bt09_bluetooth_history_filters_tag_and_state(api):
  client, database = api
  now = _seed_scene(database)
  with database.sessions()() as db:
    db.add(BluetoothTrackedPosition(
        scene_id="scene-a",
        tag_uid="tag-a",
        source_timestamp=now + timedelta(seconds=1),
        x_m=4.5,
        y_m=5.0,
        z_m=1.0,
        vx_mps=0.5,
        vy_mps=0.0,
        vz_mps=0.0,
        heading_deg=0.0,
        state="predicted",
        predicted=True,
        horizontal_uncertainty_m=0.4,
        vertical_uncertainty_m=None,
        score=0.6,
        anchors_used=4,
        method="channel_sounding",
        solver_name="robust-wls",
        solver_version="1",
        tracker_name="cv-kalman",
        tracker_version="1",
        provenance={},
    ))
    db.commit()

  response = client.get(
      "/api/v2/scenes/scene-a/history/bluetooth?tag_id=tag-a&state=predicted",
      headers=_headers(),
  )
  assert response.status_code == 200, response.text
  rows = response.json()
  assert len(rows) == 1
  assert rows[0]["tag_id"] == "tag-a"
  assert rows[0]["state"] == "predicted"
  assert rows[0]["object"]["id"] == "bt:tag-a"


def test_bt09_live_works_without_any_vision_observation(api):
  client, database = api
  _seed_scene(database)
  response = client.get("/api/v2/scenes/scene-a/live", headers=_headers())
  assert response.status_code == 200
  value = response.json()
  assert [item["id"] for item in value["objects"]] == ["bt:tag-a"]
  assert value["bluetooth"]["count"] == 1
  assert value["observed_at"]
