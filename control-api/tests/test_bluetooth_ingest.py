# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from scenescape_api.bluetooth_domain import create_anchor, create_provider, create_tag
from scenescape_api.bluetooth_ingest import (
    BoundedMeasurementBuffer,
    MeasurementRejected,
    RangeEnvelope,
    ingest_measurement,
    ingest_mqtt_message,
    measurement_to_dict,
    metrics,
    purge_measurements,
    solver_buffer,
)
from scenescape_api.bluetooth_simulator import scenario_from_dict, simulate
from scenescape_api.database import BluetoothMeasurement


def _browser_token():
  return jwt.encode(
      {
          "sub": "admin",
          "name": "admin",
          "roles": ["scenescape-admin"],
          "scenes": ["*"],
          "iat": int(time.time()),
          "exp": int(time.time()) + 600,
          "aud": "scenescape-api",
      },
      "test-signing-key-abcdefghijklmnopqrstuvwxyz",
      algorithm="HS256",
  )


def _browser_headers():
  return {"Authorization": "Bearer " + _browser_token()}


@pytest.fixture
def api(tmp_path, monkeypatch):
  monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/bluetooth-ingest.db")
  monkeypatch.setenv("API_SIGNING_KEY", "test-signing-key-abcdefghijklmnopqrstuvwxyz")
  monkeypatch.setenv("BLUETOOTH_REPLAY_WINDOW_S", "300")
  monkeypatch.setenv("BLUETOOTH_FUTURE_SKEW_S", "5")
  auth_file = tmp_path / "service.json"
  auth_file.write_text(json.dumps({"user": "svc", "password": "pw"}))
  monkeypatch.setenv("SERVICE_AUTH_FILES", str(auth_file))

  import scenescape_api.database as database

  if database._engine is not None:
    database._engine.dispose()
  database._engine = None
  database._Session = None

  import scenescape_api.app as app_module

  monkeypatch.setattr(app_module, "notify_config_change", lambda kind, uid=None: {"ok": True})
  monkeypatch.setattr(
      app_module,
      "notify_camera_change",
      lambda camera, action, previous=None: {"ok": True},
  )
  database.Base.metadata.create_all(database.get_engine())
  metrics.reset()
  solver_buffer.clear()
  client = TestClient(app_module.app)
  yield client, database

  metrics.reset()
  solver_buffer.clear()
  database.get_engine().dispose()
  database._engine = None
  database._Session = None


def _scene(client, uid):
  response = client.post(
      "/api/v2/scenes",
      headers=_browser_headers(),
      json={"uid": uid, "name": uid},
  )
  assert response.status_code == 200, response.text


def _commission(client, database, *, scene_id="scene-a", anchor_ids=("anchor-a",), tag_id="tag-a"):
  _scene(client, scene_id)
  with database.sessions()() as db:
    create_provider(
        db,
        {
            "uid": "svc",
            "name": "BT provider svc",
            "kind": "simulator",
            "state": "active",
            "capabilities": ["channel_sounding"],
        },
        "admin",
    )
    for anchor_id in anchor_ids:
      create_anchor(
          db,
          {
              "uid": anchor_id,
              "serial_number": anchor_id.upper(),
              "scene_id": scene_id,
              "provider_id": "svc",
              "provider_device_id": f"provider-{anchor_id}",
              "state": "active",
              "capabilities": ["channel_sounding"],
          },
          "admin",
      )
    create_tag(
        db,
        {
            "uid": tag_id,
            "serial_number": tag_id.upper(),
            "provider_id": "svc",
            "provider_device_id": f"provider-{tag_id}",
            "state": "active",
            "capabilities": ["channel_sounding"],
        },
        "admin",
    )
    db.commit()


def _service_headers(client):
  response = client.post(
      "/api/v1/auth",
      data={"username": "svc", "password": "pw"},
  )
  assert response.status_code == 200, response.text
  return {"Authorization": "Token " + response.json()["token"]}


def _envelope(
    *,
    now=None,
    scene_id="scene-a",
    anchor_id="anchor-a",
    tag_id="tag-a",
    provider_id="svc",
    session_id="session-1",
    sequence=1,
    distance_m=3.5,
    provider_details=None,
):
  stamp = now or datetime.now(timezone.utc)
  return {
      "scene_id": scene_id,
      "anchor_id": anchor_id,
      "tag_id": tag_id,
      "payload": {
          "schema_version": "1.0",
          "provider_id": provider_id,
          "session_id": session_id,
          "sequence": sequence,
          "source_timestamp": stamp.isoformat(),
          "method": "channel_sounding",
          "distance_m": distance_m,
          "distance_stddev_m": 0.1,
          "rssi_dbm": -60.0,
          "azimuth_deg": None,
          "elevation_deg": None,
          "nlos_probability": 0.05,
          "quality": 0.95,
          "provider_details": provider_details or {},
      },
  }


def test_bt06_simulator_measurements_use_same_normalized_ingest_contract(api):
  client, database = api
  anchors = ("a1", "a2", "a3", "a4")
  _commission(client, database, anchor_ids=anchors, tag_id="tag-sim")
  now = datetime.now(timezone.utc)
  scenario = scenario_from_dict({
      "name": "ingest-e2e",
      "scene_id": "scene-a",
      "provider_id": "svc",
      "session_id": "sim-e2e",
      "seed": 77,
      "start_time": now.isoformat(),
      "duration_s": 1.0,
      "step_s": 1.0,
      "anchors": [
          {"anchor_id": "a1", "x_m": 0, "y_m": 0, "z_m": 3},
          {"anchor_id": "a2", "x_m": 10, "y_m": 0, "z_m": 3},
          {"anchor_id": "a3", "x_m": 10, "y_m": 10, "z_m": 3},
          {"anchor_id": "a4", "x_m": 0, "y_m": 10, "z_m": 3},
      ],
      "tags": [{
          "tag_id": "tag-sim",
          "trajectory": [
              {"t_s": 0, "x_m": 2, "y_m": 2, "z_m": 1},
              {"t_s": 1, "x_m": 3, "y_m": 2, "z_m": 1},
          ],
      }],
      "faults": {"noise_stddev_m": 0.0},
  })
  generated = simulate(scenario).measurements

  with database.sessions()() as db:
    rows = [
        ingest_measurement(db, RangeEnvelope.model_validate(item), now=now + timedelta(seconds=2))
        for item in generated
    ]
    db.commit()
    stored = db.scalars(
        select(BluetoothMeasurement).order_by(BluetoothMeasurement.sequence)
    ).all()

  assert len(rows) == 8
  assert len(stored) == 8
  assert measurement_to_dict(stored[0])["provider_details"]["synthetic"] is True
  assert metrics.snapshot()["accepted"] == 8


def test_bt06_mqtt_and_http_converge_on_same_row_shape(api):
  client, database = api
  _commission(client, database)
  now = datetime.now(timezone.utc)
  envelope = _envelope(now=now)

  with database.sessions()() as db:
    mqtt = ingest_mqtt_message(
        db,
        "scenescape/data/bluetooth/range/scene-a/anchor-a/tag-a",
        json.dumps(envelope["payload"]).encode(),
        now=now,
    )
    db.commit()
    mqtt_value = measurement_to_dict(mqtt)

  second = _envelope(now=now, session_id="http-session", sequence=9)
  response = client.post(
      "/api/v2/bluetooth/measurements",
      headers=_service_headers(client),
      json=second,
  )
  assert response.status_code == 202, response.text
  http_value = response.json()["measurement"]

  for key in (
      "scene_id",
      "anchor_id",
      "tag_id",
      "provider_id",
      "method",
      "distance_m",
      "quality",
  ):
    assert http_value[key] == mqtt_value[key]


def test_bt06_rejects_nan_impossible_range_and_oversized_metadata(api):
  client, database = api
  _commission(client, database)
  now = datetime.now(timezone.utc)

  invalid = _envelope(now=now)
  invalid["payload"]["distance_m"] = float("nan")
  with pytest.raises(ValidationError):
    RangeEnvelope.model_validate(invalid)

  with database.sessions()() as db:
    with pytest.raises(MeasurementRejected, match="site maximum") as too_far:
      ingest_measurement(db, _envelope(now=now, distance_m=1001.0), now=now)
    assert too_far.value.code == "range_too_large"

  oversized = _envelope(
      now=now,
      provider_details={"blob": "x" * 5000},
  )
  response = client.post(
      "/api/v2/bluetooth/measurements",
      headers=_service_headers(client),
      json=oversized,
  )
  assert response.status_code == 422


def test_bt06_duplicate_and_out_of_order_sequences_are_rejected(api):
  client, database = api
  _commission(client, database)
  now = datetime.now(timezone.utc)
  with database.sessions()() as db:
    ingest_measurement(
        db,
        _envelope(now=now, session_id="ordering", sequence=2),
        now=now,
    )
    with pytest.raises(MeasurementRejected) as duplicate:
      ingest_measurement(
          db,
          _envelope(now=now, session_id="ordering", sequence=2),
          now=now,
      )
    assert duplicate.value.code == "duplicate"

    with pytest.raises(MeasurementRejected) as old:
      ingest_measurement(
          db,
          _envelope(now=now, session_id="ordering", sequence=1),
          now=now,
      )
    assert old.value.code == "out_of_order"


def test_bt06_cross_scene_and_provider_spoofing_are_denied(api):
  client, database = api
  _commission(client, database)
  now = datetime.now(timezone.utc)

  with database.sessions()() as db:
    with pytest.raises(MeasurementRejected) as mismatch:
      ingest_measurement(
          db,
          _envelope(now=now, scene_id="scene-b"),
          now=now,
      )
    assert mismatch.value.code == "scene_mismatch"

  spoof = _envelope(now=now, provider_id="someone-else")
  response = client.post(
      "/api/v2/bluetooth/measurements",
      headers=_service_headers(client),
      json=spoof,
  )
  assert response.status_code == 403
  assert response.json()["detail"]["code"] == "provider_scope_denied"

  browser = client.post(
      "/api/v2/bluetooth/measurements",
      headers=_browser_headers(),
      json=_envelope(now=now),
  )
  assert browser.status_code == 401


def test_bt06_replay_window_and_retention_are_explicit(api):
  client, database = api
  _commission(client, database)
  now = datetime.now(timezone.utc)

  with database.sessions()() as db:
    with pytest.raises(MeasurementRejected) as stale:
      ingest_measurement(
          db,
          _envelope(now=now - timedelta(seconds=301), session_id="stale"),
          now=now,
      )
    assert stale.value.code == "stale_timestamp"

    older = now - timedelta(seconds=100)
    ingest_measurement(
        db,
        _envelope(now=older, session_id="retention-old"),
        now=older,
    )
    ingest_measurement(
        db,
        _envelope(now=now, session_id="retention-new"),
        now=now,
    )
    db.commit()

    removed = purge_measurements(db, now=now, retention_s=50)
    db.commit()
    sessions = db.scalars(
        select(BluetoothMeasurement.session_id).order_by(BluetoothMeasurement.session_id)
    ).all()

  assert removed == 1
  assert sessions == ["retention-new"]


def test_bt06_bounded_solver_handoff_preserves_backpressure_signal(api):
  _client, _database = api
  queue = BoundedMeasurementBuffer(2)
  assert queue.offer(10) is True
  assert queue.offer(11) is True
  assert queue.offer(12) is False
  assert len(queue) == 2
  assert queue.take() == 10
  assert queue.offer(12) is True
  assert [queue.take(), queue.take(), queue.take()] == [11, 12, None]


def test_bt06_diagnostics_report_ingress_counts_without_exposing_to_viewer(api):
  client, database = api
  _commission(client, database)
  now = datetime.now(timezone.utc)
  response = client.post(
      "/api/v2/bluetooth/measurements",
      headers=_service_headers(client),
      json=_envelope(now=now),
  )
  assert response.status_code == 202

  admin = client.get("/api/v2/bluetooth/diagnostics", headers=_browser_headers())
  assert admin.status_code == 200
  assert admin.json()["ingress"]["visible"] is True
  assert admin.json()["ingress"]["raw_measurements"] == 1
  assert admin.json()["ingress"]["process_metrics"]["accepted"] == 1

  viewer_token = jwt.encode(
      {
          "sub": "viewer",
          "name": "viewer",
          "roles": ["scenescape-viewer"],
          "scenes": ["scene-a"],
          "iat": int(time.time()),
          "exp": int(time.time()) + 600,
          "aud": "scenescape-api",
      },
      "test-signing-key-abcdefghijklmnopqrstuvwxyz",
      algorithm="HS256",
  )
  viewer = client.get(
      "/api/v2/bluetooth/diagnostics",
      headers={"Authorization": "Bearer " + viewer_token},
  )
  assert viewer.status_code == 200
  assert viewer.json()["ingress"] == {"visible": False}



def test_bt16_http_ingress_feature_flag_disables_without_deleting_config(api, monkeypatch):
  client, database = api
  _commission(client, database)
  monkeypatch.setenv("BLUETOOTH_POSITIONING_ENABLED", "false")
  now = datetime.now(timezone.utc)

  response = client.post(
      "/api/v2/bluetooth/measurements",
      headers=_service_headers(client),
      json=_envelope(now=now),
  )
  assert response.status_code == 503
  assert response.json()["detail"]["code"] == "feature_disabled"

  with database.sessions()() as db:
    assert db.scalar(select(BluetoothMeasurement.id).limit(1)) is None
    from scenescape_api.database import BluetoothAnchor, BluetoothProvider, BluetoothTag
    assert db.get(BluetoothProvider, "svc") is not None
    assert db.get(BluetoothAnchor, "anchor-a") is not None
    assert db.get(BluetoothTag, "tag-a") is not None


def test_bt16_service_metrics_are_aggregate_and_location_private(api):
  client, database = api
  _commission(client, database)
  now = datetime.now(timezone.utc)
  accepted = client.post(
      "/api/v2/bluetooth/measurements",
      headers=_service_headers(client),
      json=_envelope(now=now),
  )
  assert accepted.status_code == 202

  response = client.get(
      "/api/v2/bluetooth/metrics",
      headers=_service_headers(client),
  )
  assert response.status_code == 200
  assert response.headers["content-type"].startswith("text/plain")
  body = response.text
  for metric in (
      "scenescape_bluetooth_enabled",
      "scenescape_bluetooth_ingress_accepted_total",
      "scenescape_bluetooth_solver_queue_depth",
      "scenescape_bluetooth_raw_measurements",
      "scenescape_bluetooth_raw_retention_seconds",
  ):
    assert metric in body

  # Prometheus output is intentionally aggregate: no scene, tag, anchor,
  # assignment or provider labels that disclose precise location/identity.
  for private_value in ("scene-a", "tag-a", "anchor-a", "svc"):
    assert private_value not in body
