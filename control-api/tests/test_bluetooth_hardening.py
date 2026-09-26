# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from scenescape_api.bluetooth_benchmark import run_benchmark
from scenescape_api.bluetooth_retention import (
    BluetoothRetentionPolicy,
    purge_bluetooth_history,
)
from scenescape_api.cli import (
    _mqtt_client_id,
    _mqtt_subscription,
    worker_health,
)
from scenescape_api.database import (
    BluetoothAnchor,
    BluetoothDeviceTelemetry,
    BluetoothMeasurement,
    BluetoothProvider,
    BluetoothRawPosition,
    BluetoothTag,
    BluetoothTrackedPosition,
    Heartbeat,
    Resource,
)


NOW = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path, monkeypatch):
  monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/bt16.db")
  import scenescape_api.database as database

  if database._engine is not None:
    database._engine.dispose()
  database._engine = None
  database._Session = None
  database.Base.metadata.create_all(database.get_engine())
  session = database.sessions()()
  yield session, database
  session.close()
  database.get_engine().dispose()
  database._engine = None
  database._Session = None


def _seed_control_plane(db):
  db.add(Resource(kind="scene", uid="scene-a", revision=1, payload={"uid": "scene-a"}))
  db.add(BluetoothProvider(
      uid="provider-a",
      name="Provider A",
      state="active",
      capabilities=["channel_sounding"],
  ))
  db.add(BluetoothAnchor(
      uid="anchor-a",
      serial_number="ANCHOR-A",
      scene_id="scene-a",
      provider_id="provider-a",
      state="active",
      capabilities=["channel_sounding"],
  ))
  db.add(BluetoothTag(
      uid="tag-a",
      serial_number="TAG-A",
      provider_id="provider-a",
      state="active",
      capabilities=["channel_sounding"],
  ))
  db.flush()


def _measurement(timestamp, sequence):
  return BluetoothMeasurement(
      scene_id="scene-a",
      anchor_uid="anchor-a",
      tag_uid="tag-a",
      provider_id="provider-a",
      session_id="bt16-session",
      sequence=sequence,
      source_timestamp=timestamp,
      ingested_at=timestamp,
      method="channel_sounding",
      distance_m=4.0,
      distance_stddev_m=0.1,
      nlos_probability=0.0,
      quality=0.95,
      provider_details={},
  )


def _raw_position(timestamp):
  return BluetoothRawPosition(
      scene_id="scene-a",
      tag_uid="tag-a",
      source_timestamp=timestamp,
      x_m=1.0,
      y_m=2.0,
      z_m=1.0,
      dimension="2.5d",
      state="good",
      horizontal_uncertainty_m=0.2,
      vertical_uncertainty_m=None,
      score=0.95,
      anchors_visible=4,
      anchors_used=4,
      residual_rms_m=0.05,
      gdop=1.4,
      method="channel_sounding",
      solver_name="robust-wls",
      solver_version="1",
      diagnostics={},
      created_at=timestamp,
  )


def _tracked(timestamp):
  return BluetoothTrackedPosition(
      scene_id="scene-a",
      tag_uid="tag-a",
      source_timestamp=timestamp,
      x_m=1.0,
      y_m=2.0,
      z_m=1.0,
      vx_mps=0.0,
      vy_mps=0.0,
      vz_mps=0.0,
      heading_deg=None,
      state="good",
      predicted=False,
      horizontal_uncertainty_m=0.2,
      vertical_uncertainty_m=None,
      score=0.95,
      anchors_used=4,
      method="channel_sounding",
      solver_name="robust-wls",
      solver_version="1",
      tracker_name="cv-kalman",
      tracker_version="1",
      provenance={},
      created_at=timestamp,
  )


def _telemetry(timestamp):
  return BluetoothDeviceTelemetry(
      device_type="tag",
      device_uid="tag-a",
      provider_id="provider-a",
      source="gatt_battery_service",
      observed_at=timestamp,
      ingested_at=timestamp,
      battery_percent=80.0,
      battery_status="normal",
      details={},
  )


def test_bt16_retention_purges_high_rate_history_but_preserves_control_plane(db):
  session, database = db
  _seed_control_plane(session)
  old = NOW - timedelta(days=2)
  recent = NOW - timedelta(hours=1)
  session.add_all([
      _measurement(old, 1),
      _measurement(recent, 2),
      _raw_position(old),
      _raw_position(recent),
      _tracked(old),
      _tracked(recent),
      _telemetry(old),
      _telemetry(recent),
  ])
  session.commit()

  result = purge_bluetooth_history(
      session,
      policy=BluetoothRetentionPolicy(
          raw_measurement_s=86_400,
          raw_position_s=86_400,
          tracked_position_s=86_400,
          device_telemetry_s=86_400,
      ),
      now=NOW,
  )
  session.commit()

  assert result == {
      "measurements": 1,
      "raw_positions": 1,
      "tracked_positions": 1,
      "device_telemetry": 1,
  }
  for model in (
      BluetoothMeasurement,
      BluetoothRawPosition,
      BluetoothTrackedPosition,
      BluetoothDeviceTelemetry,
  ):
    assert session.scalar(select(func.count()).select_from(model)) == 1
  assert session.get(BluetoothProvider, "provider-a") is not None
  assert session.get(BluetoothAnchor, "anchor-a") is not None
  assert session.get(BluetoothTag, "tag-a") is not None
  assert session.scalar(
      select(Resource).where(Resource.kind == "scene", Resource.uid == "scene-a")
  ) is not None


def test_bt16_retention_policy_is_independently_configurable(monkeypatch):
  monkeypatch.setenv("BLUETOOTH_RAW_RETENTION_S", "60")
  monkeypatch.setenv("BLUETOOTH_RAW_POSITION_RETENTION_S", "120")
  monkeypatch.setenv("BLUETOOTH_TRACKED_POSITION_RETENTION_S", "180")
  monkeypatch.setenv("BLUETOOTH_DEVICE_TELEMETRY_RETENTION_S", "240")
  assert BluetoothRetentionPolicy.from_env().to_dict() == {
      "raw_measurement_s": 60,
      "raw_position_s": 120,
      "tracked_position_s": 180,
      "device_telemetry_s": 240,
  }

  monkeypatch.setenv("BLUETOOTH_RAW_RETENTION_S", "-1")
  with pytest.raises(ValueError, match="must be >= 0"):
    BluetoothRetentionPolicy.from_env()


def test_bt16_shared_subscription_and_client_identity_are_deterministic(monkeypatch):
  monkeypatch.setenv("MQTT_SHARED_SUBSCRIPTION_GROUP", "native-workers")
  monkeypatch.setenv("MQTT_CLIENT_ID", "scenescape-native")
  monkeypatch.setenv("MQTT_CLIENT_ID_SUFFIX", "worker-2")
  assert (
      _mqtt_subscription("scenescape/data/bluetooth/range/#")
      == "$share/native-workers/scenescape/data/bluetooth/range/#"
  )
  assert _mqtt_client_id() == "scenescape-native-worker-2"

  monkeypatch.delenv("MQTT_SHARED_SUBSCRIPTION_GROUP")
  assert _mqtt_subscription("scenescape/event/#") == "scenescape/event/#"


def test_bt16_worker_health_distinguishes_liveness_and_readiness(db, capsys):
  session, _database = db
  session.merge(
      Heartbeat(
          key="mqtt",
          state="connected",
          details={},
          updated_at=datetime.now(timezone.utc),
      )
  )
  session.commit()

  worker_health(ready=True)
  assert '"ready": true' in capsys.readouterr().out

  row = session.get(Heartbeat, "mqtt")
  row.state = "degraded"
  row.updated_at = datetime.now(timezone.utc)
  session.commit()
  worker_health(ready=False)
  with pytest.raises(SystemExit, match="not ready"):
    worker_health(ready=True)



def test_bt16_helm_defaults_fail_closed_and_schedule_retention():
  values = Path("kubernetes/scenescape-native/values.yaml").read_text(encoding="utf-8")
  worker = Path(
      "kubernetes/scenescape-native/templates/worker.yaml"
  ).read_text(encoding="utf-8")
  api = Path(
      "kubernetes/scenescape-native/templates/api.yaml"
  ).read_text(encoding="utf-8")
  retention = Path(
      "kubernetes/scenescape-native/templates/bluetooth-retention.yaml"
  ).read_text(encoding="utf-8")
  pdb = Path(
      "kubernetes/scenescape-native/templates/worker-pdb.yaml"
  ).read_text(encoding="utf-8")

  assert "bluetooth:\n" in values
  assert "enabled: false" in values
  assert "telemetryEnabled: false" in values
  assert "sharedSubscriptionGroup" in values
  assert "worker.replicas > 1" in values

  assert "MQTT_SHARED_SUBSCRIPTION_GROUP" in worker
  assert "MQTT_CLIENT_ID_SUFFIX" in worker
  assert "worker-ready" in worker
  assert "worker-health" in worker
  assert "mqtt.sharedSubscriptionGroup is required when worker.replicas > 1" in worker

  assert "BLUETOOTH_POSITIONING_ENABLED" in api
  assert "BLUETOOTH_TELEMETRY_ENABLED" in api
  assert "BLUETOOTH_RAW_RETENTION_S" in api

  assert "kind: CronJob" in retention
  assert "concurrencyPolicy: Forbid" in retention
  assert "args: [retention]" in retention

  assert "kind: PodDisruptionBudget" in pdb
  assert "minAvailable: 1" in pdb



def test_bt16_benchmark_smoke_reports_truthful_workload_and_no_invalid_positions():
  report = run_benchmark(
      tags=3,
      anchors=4,
      update_hz=2.0,
      duration_s=1.0,
      seed=1616,
  )
  assert report["workload"]["fixes"] == 6
  assert report["workload"]["range_observations"] == 24
  assert report["quality"]["available_fraction"] == 1.0
  assert report["quality"]["invalid_numeric"] == 0
  assert report["runtime"]["fix_throughput_hz"] > 0
  assert report["runtime"]["solve_latency_ms"]["p95"] is not None
