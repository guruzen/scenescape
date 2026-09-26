# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from scenescape_api.bluetooth_domain import create_anchor, create_provider, create_tag
from scenescape_api.database import Resource
from scenescape_api.bluetooth_telemetry import (
    TelemetryPollCache,
    battery_status,
    ingest_device_telemetry,
    normalize_standard_services,
    normalize_vendor_telemetry,
    telemetry_public,
)


def _browser_token(*, admin=True, scenes=None):
  return jwt.encode(
      {
          "sub": "admin" if admin else "viewer",
          "name": "admin" if admin else "viewer",
          "roles": ["scenescape-admin"] if admin else ["scenescape-viewer"],
          "scenes": scenes if scenes is not None else ["*"],
          "iat": int(time.time()),
          "exp": int(time.time()) + 600,
          "aud": "scenescape-api",
      },
      "test-signing-key-abcdefghijklmnopqrstuvwxyz",
      algorithm="HS256",
  )


def _headers(*, admin=True, scenes=None):
  return {"Authorization": "Bearer " + _browser_token(admin=admin, scenes=scenes)}


@pytest.fixture
def api(tmp_path, monkeypatch):
  monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/bt-telemetry.db")
  monkeypatch.setenv("API_SIGNING_KEY", "test-signing-key-abcdefghijklmnopqrstuvwxyz")
  auth_file = tmp_path / "service.json"
  auth_file.write_text(json.dumps({"user": "svc", "password": "pw"}))
  monkeypatch.setenv("SERVICE_AUTH_FILES", str(auth_file))

  import scenescape_api.database as database
  if database._engine is not None:
    database._engine.dispose()
  database._engine = None
  database._Session = None

  import scenescape_api.app as app_module
  database.Base.metadata.create_all(database.get_engine())
  client = TestClient(app_module.app)

  with database.sessions()() as db:
    db.add(Resource(
        kind="scene",
        uid="scene-a",
        revision=1,
        payload={"uid": "scene-a", "name": "Telemetry scene"},
    ))
    db.flush()
    create_provider(
        db,
        {"uid": "svc", "name": "provider", "state": "active"},
        "admin",
    )
    create_anchor(
        db,
        {
            "uid": "anchor-a",
            "serial_number": "ANCHOR-A",
            "scene_id": "scene-a",
            "provider_id": "svc",
            "state": "active",
        },
        "admin",
    )
    create_tag(
        db,
        {
            "uid": "tag-a",
            "serial_number": "TAG-A",
            "provider_id": "svc",
            "state": "active",
        },
        "admin",
    )
    db.commit()

  yield client, database

  database.get_engine().dispose()
  database._engine = None
  database._Session = None


def _service_headers(client):
  response = client.post("/api/v1/auth", data={"username": "svc", "password": "pw"})
  assert response.status_code == 200
  return {"Authorization": "Token " + response.json()["token"]}


def test_bt10_standard_service_fixture_normalizes_without_requiring_optional_services():
  now = datetime.now(timezone.utc)
  complete = normalize_standard_services(
      provider_id="svc",
      device_type="tag",
      device_id="tag-a",
      source_timestamp=now,
      battery_service={"battery_level": 73, "battery_voltage_v": 3.1},
      device_information={
          "manufacturer_name": "Example",
          "model_number": "CS-Tag",
          "hardware_revision": "A",
          "firmware_revision": "1.2.3",
      },
  )
  assert complete.battery_percent == 73
  assert complete.manufacturer == "Example"
  assert complete.firmware_revision == "1.2.3"

  missing = normalize_standard_services(
      provider_id="svc",
      device_type="tag",
      device_id="tag-a",
      source_timestamp=now,
  )
  assert missing.battery_percent is None
  assert missing.details["battery_service_present"] is False


def test_bt10_vendor_fixture_is_normalized_and_extra_fields_remain_bounded_details():
  now = datetime.now(timezone.utc)
  value = normalize_vendor_telemetry(
      provider_id="svc",
      device_type="anchor",
      device_id="anchor-a",
      source_timestamp=now,
      payload={
          "soc": 42,
          "volts": 3.0,
          "firmware_revision": "9.8",
          "temperature_c": 31.2,
      },
      battery_percent_field="soc",
      battery_voltage_field="volts",
  )
  assert value.battery_percent == 42
  assert value.battery_voltage_v == 3.0
  assert value.firmware_revision == "9.8"
  assert value.details == {"temperature_c": 31.2}


def test_bt10_unknown_and_zero_percent_are_distinct(monkeypatch):
  monkeypatch.setenv("BLUETOOTH_BATTERY_CRITICAL_PERCENT", "10")
  monkeypatch.setenv("BLUETOOTH_BATTERY_LOW_PERCENT", "20")
  assert battery_status(None) == "unknown"
  assert battery_status(0.0) == "critical"
  assert battery_status(10.0) == "critical"
  assert battery_status(15.0) == "low"
  assert battery_status(50.0) == "normal"


def test_bt10_configurable_thresholds(monkeypatch):
  monkeypatch.setenv("BLUETOOTH_BATTERY_CRITICAL_PERCENT", "15")
  monkeypatch.setenv("BLUETOOTH_BATTERY_LOW_PERCENT", "30")
  assert battery_status(15) == "critical"
  assert battery_status(16) == "low"
  assert battery_status(31) == "normal"


def test_bt10_ingest_projects_latest_tag_snapshot_with_provenance(api):
  _client, database = api
  now = datetime.now(timezone.utc)
  with database.sessions()() as db:
    row = ingest_device_telemetry(
        db,
        {
            "provider_id": "svc",
            "source_timestamp": now,
            "device_type": "tag",
            "device_id": "tag-a",
            "source": "bluetooth_standard_services",
            "battery_percent": 19,
            "battery_voltage_v": 2.95,
            "firmware_revision": "1.4.0",
        },
        ingested_at=now,
    )
    db.commit()
    tag = db.get(database.BluetoothTag, "tag-a")
    assert tag.battery_percent == 19
    assert tag.battery_status == "low"
    assert tag.battery_source == "bluetooth_standard_services"
    assert tag.battery_observed_at.replace(tzinfo=timezone.utc) == now
    assert tag.firmware_revision == "1.4.0"
    public = telemetry_public(row, now=now)
  assert public["battery"]["status"] == "low"
  assert public["freshness"]["stale"] is False


def test_bt10_freshness_becomes_stale_without_rewriting_value(api, monkeypatch):
  _client, database = api
  monkeypatch.setenv("BLUETOOTH_TELEMETRY_STALE_S", "60")
  observed = datetime.now(timezone.utc) - timedelta(seconds=120)
  with database.sessions()() as db:
    row = ingest_device_telemetry(
        db,
        {
            "provider_id": "svc",
            "source_timestamp": observed,
            "device_type": "tag",
            "device_id": "tag-a",
            "battery_percent": 44,
        },
        ingested_at=observed,
    )
    value = telemetry_public(row, now=observed + timedelta(seconds=120))
  assert value["battery"]["percent"] == 44
  assert value["freshness"]["stale"] is True


def test_bt10_secret_fields_are_rejected(api):
  client, _database = api
  now = datetime.now(timezone.utc)
  response = client.post(
      "/api/v2/bluetooth/telemetry",
      headers=_service_headers(client),
      json={
          "provider_id": "svc",
          "source_timestamp": now.isoformat(),
          "device_type": "tag",
          "device_id": "tag-a",
          "details": {"pairing_key": "must-not-be-stored"},
      },
  )
  assert response.status_code == 422


def test_bt10_service_write_and_read_permissions(api):
  client, _database = api
  now = datetime.now(timezone.utc)
  accepted = client.post(
      "/api/v2/bluetooth/telemetry",
      headers=_service_headers(client),
      json={
          "provider_id": "svc",
          "source_timestamp": now.isoformat(),
          "device_type": "anchor",
          "device_id": "anchor-a",
          "battery_percent": None,
          "firmware_revision": "2.0",
      },
  )
  assert accepted.status_code == 202, accepted.text

  viewer = client.get(
      "/api/v2/bluetooth/anchors/anchor-a/telemetry",
      headers=_headers(admin=False, scenes=["scene-a"]),
  )
  assert viewer.status_code == 200
  assert viewer.json()["telemetry"]["device_information"]["firmware_revision"] == "2.0"

  denied = client.get(
      "/api/v2/bluetooth/anchors/anchor-a/telemetry",
      headers=_headers(admin=False, scenes=["scene-b"]),
  )
  assert denied.status_code == 403

  tag_viewer = client.get(
      "/api/v2/bluetooth/tags/tag-a/telemetry",
      headers=_headers(admin=False, scenes=["scene-a"]),
  )
  assert tag_viewer.status_code == 403


def test_bt10_poll_cache_protects_devices_and_is_memory_bounded():
  cache = TelemetryPollCache(min_interval_s=60, max_entries=3)
  now = datetime.now(timezone.utc)
  assert cache.should_poll("tag-a", now) is True
  assert cache.should_poll("tag-a", now + timedelta(seconds=10)) is False
  assert cache.should_poll("tag-a", now + timedelta(seconds=61)) is True

  assert cache.should_poll("tag-b", now) is True
  assert cache.should_poll("tag-c", now) is True
  assert cache.should_poll("tag-d", now) is True
  assert len(cache) == 3



def test_bt16_telemetry_ingress_honors_feature_disable(api, monkeypatch):
  client, database = api
  monkeypatch.setenv("BLUETOOTH_TELEMETRY_ENABLED", "false")
  now = datetime.now(timezone.utc)

  response = client.post(
      "/api/v2/bluetooth/telemetry",
      headers=_service_headers(client),
      json={
          "provider_id": "svc",
          "source_timestamp": now.isoformat(),
          "device_type": "tag",
          "device_id": "tag-a",
          "battery_percent": 72,
      },
  )
  assert response.status_code == 503
  assert response.json()["detail"]["code"] == "feature_disabled"

  with database.sessions()() as db:
    tag = db.get(database.BluetoothTag, "tag-a")
    assert tag.battery_percent is None
