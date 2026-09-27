# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math
import random
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from sqlalchemy import select

from scenescape_api.bluetooth_tracking import (
    BluetoothTracker,
    TrackerConfig,
    persist_tracked_position,
)
from scenescape_api.database import Base, BluetoothTrackedPosition


BASE = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)


def _raw(
    t_s,
    x,
    y,
    z=1.0,
    *,
    uncertainty=0.35,
    state="good",
    score=0.95,
):
  position = None if x is None else {"x_m": x, "y_m": y, "z_m": z}
  return {
      "state": state,
      "source_timestamp": BASE + timedelta(seconds=t_s),
      "position": position,
      "quality": {
          "state": state,
          "horizontal_uncertainty_m": uncertainty,
          "vertical_uncertainty_m": None,
          "score": score,
          "anchors_visible": 5,
          "anchors_used": 4,
          "residual_rms_m": 0.08,
          "gdop": 1.6,
          "method": "channel_sounding",
      },
      "solver": {"name": "robust-wls", "version": "1"},
      "accepted_anchors": [
          {"anchor_id": "a1"},
          {"anchor_id": "a2"},
          {"anchor_id": "a3"},
          {"anchor_id": "a4"},
      ],
  }


def test_bt08_constant_velocity_converges_to_position_and_velocity():
  tracker = BluetoothTracker(
      TrackerConfig(
          process_accel_std_mps2=0.5,
          max_speed_mps=5.0,
          default_measurement_std_m=0.15,
      )
  )
  result = None
  for second in range(15):
    result = tracker.update(
        "scene-a",
        "tag-a",
        _raw(second, x=1.2 * second, y=2.0),
        calibration_revision="cal-1",
        identity_revision="assign-1",
    )

  assert result is not None
  assert result["quality"]["state"] == "good"
  assert abs(result["position"]["x_m"] - 16.8) < 0.2
  assert abs(result["velocity"]["vx_mps"] - 1.2) < 0.15
  assert abs(result["velocity"]["vy_mps"]) < 0.1
  assert result["heading_deg"] is not None
  assert min(abs(result["heading_deg"]), abs(result["heading_deg"] - 360.0)) < 5.0


def test_bt08_filter_reduces_seeded_stationary_jitter():
  rng = random.Random(808)
  tracker = BluetoothTracker(
      TrackerConfig(
          process_accel_std_mps2=0.15,
          max_speed_mps=3.0,
          default_measurement_std_m=0.25,
      )
  )
  raw_errors = []
  tracked_errors = []
  truth = np.array([5.0, 4.0])
  for second in range(60):
    measured = np.array(
        [5.0 + rng.gauss(0, 0.22), 4.0 + rng.gauss(0, 0.22)]
    )
    raw_errors.append(float(np.linalg.norm(measured - truth)))
    result = tracker.update(
        "scene-a",
        "tag-a",
        _raw(
            second,
            x=float(measured[0]),
            y=float(measured[1]),
            uncertainty=0.6,
        ),
        calibration_revision="cal-1",
        identity_revision="assign-1",
    )
    tracked = np.array(
        [result["position"]["x_m"], result["position"]["y_m"]]
    )
    tracked_errors.append(float(np.linalg.norm(tracked - truth)))

  assert float(np.mean(tracked_errors[10:])) < float(np.mean(raw_errors[10:]))


def test_bt08_stop_start_and_turn_update_velocity_direction():
  tracker = BluetoothTracker(TrackerConfig(max_speed_mps=6.0))
  for second in range(8):
    tracker.update(
        "scene-a",
        "tag-a",
        _raw(second, x=float(second), y=0.0),
        calibration_revision="cal-1",
        identity_revision="assign-1",
    )
  moving = tracker.update(
      "scene-a",
      "tag-a",
      _raw(8, x=8.0, y=0.0),
      calibration_revision="cal-1",
      identity_revision="assign-1",
  )
  assert moving["velocity"]["vx_mps"] > 0.5

  for second in range(9, 18):
    stopped = tracker.update(
        "scene-a",
        "tag-a",
        _raw(second, x=8.0, y=0.0),
        calibration_revision="cal-1",
        identity_revision="assign-1",
    )
  assert abs(stopped["velocity"]["vx_mps"]) < 0.25

  for second in range(18, 28):
    turned = tracker.update(
        "scene-a",
        "tag-a",
        _raw(second, x=8.0, y=(second - 18) * 0.8),
        calibration_revision="cal-1",
        identity_revision="assign-1",
    )
  assert turned["velocity"]["vy_mps"] > 0.4
  assert turned["heading_deg"] is not None
  assert 45.0 < turned["heading_deg"] < 135.0


def test_bt08_dropout_prediction_expires_to_stale_then_unavailable():
  tracker = BluetoothTracker(
      TrackerConfig(
          prediction_horizon_s=2.0,
          stale_horizon_s=4.0,
          reset_gap_s=10.0,
          max_speed_mps=5.0,
      )
  )
  for second in range(4):
    tracker.update(
        "scene-a",
        "tag-a",
        _raw(second, x=float(second), y=0.0),
        calibration_revision="cal-1",
        identity_revision="assign-1",
    )

  predicted = tracker.predict("scene-a", "tag-a", BASE + timedelta(seconds=4))
  assert predicted["quality"]["state"] == "predicted"
  assert predicted["tracker"]["predicted"] is True
  assert predicted["provenance"]["accepted_anchor_ids"] == ["a1", "a2", "a3", "a4"]

  stale = tracker.predict("scene-a", "tag-a", BASE + timedelta(seconds=6))
  assert stale["quality"]["state"] == "stale"
  assert stale["tracker"]["predicted"] is True

  unavailable = tracker.predict("scene-a", "tag-a", BASE + timedelta(seconds=8))
  assert unavailable["quality"]["state"] == "unavailable"
  assert unavailable["position"] is None
  assert len(tracker) == 0


def test_bt08_out_of_order_measurement_does_not_rewind_track():
  tracker = BluetoothTracker()
  tracker.update(
      "scene-a",
      "tag-a",
      _raw(5, x=5.0, y=1.0),
      calibration_revision="cal-1",
      identity_revision="assign-1",
  )
  result = tracker.update(
      "scene-a",
      "tag-a",
      _raw(4, x=100.0, y=100.0),
      calibration_revision="cal-1",
      identity_revision="assign-1",
  )

  assert result["provenance"]["reason"] == "out_of_order_ignored"
  assert result["position"]["x_m"] == 5.0
  assert result["position"]["y_m"] == 1.0
  assert tracker.metrics["out_of_order"] == 1


def test_bt08_impossible_jump_resets_instead_of_smoothing_false_path():
  tracker = BluetoothTracker(
      TrackerConfig(max_speed_mps=2.0, max_jump_margin_m=1.0)
  )
  tracker.update(
      "scene-a",
      "tag-a",
      _raw(0, x=0.0, y=0.0),
      calibration_revision="cal-1",
      identity_revision="assign-1",
  )
  result = tracker.update(
      "scene-a",
      "tag-a",
      _raw(1, x=50.0, y=50.0),
      calibration_revision="cal-1",
      identity_revision="assign-1",
  )

  assert result["provenance"]["reason"] == "impossible_jump_reset"
  assert math.hypot(
      result["position"]["x_m"] - 50.0,
      result["position"]["y_m"] - 50.0,
  ) < 1e-6
  assert tracker.metrics["jump_resets"] == 1


def test_bt08_calibration_and_identity_revision_changes_reset_filter():
  tracker = BluetoothTracker()
  tracker.update(
      "scene-a",
      "tag-a",
      _raw(0, x=1.0, y=1.0),
      calibration_revision="cal-1",
      identity_revision="assign-1",
  )
  calibration_reset = tracker.update(
      "scene-a",
      "tag-a",
      _raw(1, x=2.0, y=1.0),
      calibration_revision="cal-2",
      identity_revision="assign-1",
  )
  assert calibration_reset["provenance"]["reason"] == "calibration_revision_changed"

  identity_reset = tracker.update(
      "scene-a",
      "tag-a",
      _raw(2, x=3.0, y=1.0),
      calibration_revision="cal-2",
      identity_revision="assign-2",
  )
  assert identity_reset["provenance"]["reason"] == "identity_revision_changed"
  assert tracker.metrics["resets"] == 2


def test_bt08_large_tag_count_is_memory_bounded_and_evicts_lru():
  tracker = BluetoothTracker(TrackerConfig(max_tracks=100))
  for index in range(250):
    tracker.update(
        "scene-a",
        f"tag-{index:04d}",
        _raw(0, x=float(index % 10), y=float(index // 10)),
        calibration_revision="cal-1",
        identity_revision=f"assign-{index}",
    )

  assert len(tracker) == 100
  assert tracker.metrics["evicted"] == 150

  # Oldest tags were evicted, therefore this becomes a fresh track.
  result = tracker.update(
      "scene-a",
      "tag-0000",
      _raw(1, x=0.0, y=0.0),
      calibration_revision="cal-1",
      identity_revision="assign-0",
  )
  assert result["provenance"]["reason"] == "track_created"



def test_bt08_long_measured_gap_resets_filter_instead_of_smoothing_across_gap():
  tracker = BluetoothTracker(
      TrackerConfig(reset_gap_s=3.0, max_speed_mps=5.0)
  )
  tracker.update(
      "scene-a",
      "tag-a",
      _raw(0, x=1.0, y=1.0),
      calibration_revision="cal-1",
      identity_revision="assign-1",
  )
  result = tracker.update(
      "scene-a",
      "tag-a",
      _raw(5, x=4.0, y=1.0),
      calibration_revision="cal-1",
      identity_revision="assign-1",
  )

  assert result["provenance"]["reason"] == "long_gap"
  assert result["velocity"]["vx_mps"] == pytest.approx(0.0)
  assert tracker.metrics["resets"] == 1


def test_bt08_same_tag_in_different_scene_starts_independent_track():
  tracker = BluetoothTracker()
  first = tracker.update(
      "scene-a",
      "tag-a",
      _raw(0, x=1.0, y=1.0),
      calibration_revision="cal-a",
      identity_revision="assign-1",
  )
  second = tracker.update(
      "scene-b",
      "tag-a",
      _raw(0, x=20.0, y=20.0),
      calibration_revision="cal-b",
      identity_revision="assign-1",
  )

  assert first["provenance"]["reason"] == "track_created"
  assert second["provenance"]["reason"] == "track_created"
  assert second["position"]["x_m"] == pytest.approx(20.0)
  assert len(tracker) == 2


@pytest.fixture
def bt08_db(tmp_path, monkeypatch):
  monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/bt08.db")
  import scenescape_api.database as database

  if database._engine is not None:
    database._engine.dispose()
  database._engine = None
  database._Session = None
  engine = database.get_engine()
  Base.metadata.create_all(engine)
  session = database.sessions()()
  yield session
  session.close()
  engine.dispose()
  database._engine = None
  database._Session = None


def test_bt08_persisted_track_retains_velocity_versions_and_provenance(bt08_db):
  tracker = BluetoothTracker()
  tracker.update(
      "scene-a",
      "tag-a",
      _raw(0, x=1.0, y=2.0),
      calibration_revision="cal-7",
      identity_revision="assign-9",
  )
  tracked = tracker.update(
      "scene-a",
      "tag-a",
      _raw(1, x=2.0, y=2.0),
      calibration_revision="cal-7",
      identity_revision="assign-9",
  )
  row = persist_tracked_position(bt08_db, tracked)
  bt08_db.commit()
  stored = bt08_db.scalar(
      select(BluetoothTrackedPosition).where(BluetoothTrackedPosition.id == row.id)
  )

  assert stored is not None
  assert stored.state == "good"
  assert stored.predicted is False
  assert stored.vx_mps is not None
  assert stored.vy_mps is not None
  assert stored.method == "channel_sounding"
  assert stored.solver_name == "robust-wls"
  assert stored.solver_version == "1"
  assert stored.tracker_name == "cv-kalman"
  assert stored.tracker_version == "1"
  assert stored.provenance["calibration_revision"] == "cal-7"
  assert stored.provenance["identity_revision"] == "assign-9"
  assert stored.provenance["accepted_anchor_ids"] == ["a1", "a2", "a3", "a4"]
  assert stored.provenance["reason"] == "measurement_update"



def test_bt08_tag_class_motion_limits_change_impossible_jump_gate():
  config = TrackerConfig(
      max_speed_mps=20.0,
      max_jump_margin_m=0.5,
      motion_limits_mps={"person": 2.0, "vehicle": 10.0},
  )

  person = BluetoothTracker(config)
  person.update(
      "scene-a",
      "tag-person",
      _raw(0, x=0.0, y=0.0),
      calibration_revision="cal-1",
      identity_revision="assign-person",
      motion_class="person",
  )
  person_result = person.update(
      "scene-a",
      "tag-person",
      _raw(1, x=5.0, y=0.0),
      calibration_revision="cal-1",
      identity_revision="assign-person",
      motion_class="person",
  )
  assert person_result["provenance"]["reason"] == "impossible_jump_reset"
  assert person_result["provenance"]["motion_class"] == "person"
  assert person_result["provenance"]["motion_limit_mps"] == pytest.approx(2.0)

  vehicle = BluetoothTracker(config)
  vehicle.update(
      "scene-a",
      "tag-vehicle",
      _raw(0, x=0.0, y=0.0),
      calibration_revision="cal-1",
      identity_revision="assign-vehicle",
      motion_class="vehicle",
  )
  vehicle_result = vehicle.update(
      "scene-a",
      "tag-vehicle",
      _raw(1, x=5.0, y=0.0),
      calibration_revision="cal-1",
      identity_revision="assign-vehicle",
      motion_class="vehicle",
  )
  assert vehicle_result["provenance"]["reason"] == "measurement_update"
  assert vehicle_result["provenance"]["motion_limit_mps"] == pytest.approx(10.0)


def test_bt08_motion_class_change_resets_filter():
  tracker = BluetoothTracker(
      TrackerConfig(motion_limits_mps={"person": 3.0, "vehicle": 12.0})
  )
  tracker.update(
      "scene-a",
      "tag-a",
      _raw(0, x=1.0, y=1.0),
      calibration_revision="cal-1",
      identity_revision="assign-1",
      motion_class="person",
  )
  changed = tracker.update(
      "scene-a",
      "tag-a",
      _raw(1, x=2.0, y=1.0),
      calibration_revision="cal-1",
      identity_revision="assign-1",
      motion_class="vehicle",
  )

  assert changed["provenance"]["reason"] == "motion_class_changed"
  assert changed["provenance"]["motion_class"] == "vehicle"
  assert tracker.metrics["resets"] == 1
