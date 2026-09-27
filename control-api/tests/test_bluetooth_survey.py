# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math
from datetime import datetime, timedelta, timezone

import pytest

from scenescape_api.bluetooth_domain import (
    activate_calibration,
    create_anchor,
    create_calibration,
    create_tag,
)
from scenescape_api.bluetooth_positioning import SolverConfig, solve_ranges
from scenescape_api.bluetooth_survey import (
    add_survey_sample,
    coverage_diagnostics,
    create_bias_calibration_revisions,
    create_survey_point,
    estimate_anchor_biases,
)
from scenescape_api.database import Resource


NOW = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path, monkeypatch):
  monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/bt-survey.db")
  import scenescape_api.database as database
  if database._engine is not None:
    database._engine.dispose()
  database._engine = None
  database._Session = None
  database.Base.metadata.create_all(database.get_engine())
  session = database.sessions()()
  session.add(Resource(
      kind="scene",
      uid="scene-a",
      revision=1,
      payload={"uid": "scene-a", "name": "Survey scene"},
  ))
  session.flush()
  yield session, database
  session.close()
  database.get_engine().dispose()
  database._engine = None
  database._Session = None


def _seed_anchors(db):
  positions = {
      "a1": (0.0, 0.0, 3.0),
      "a2": (10.0, 0.0, 3.0),
      "a3": (10.0, 10.0, 3.0),
      "a4": (0.0, 10.0, 3.0),
  }
  calibrations = {}
  for anchor_id, position in positions.items():
    create_anchor(
        db,
        {
            "uid": anchor_id,
            "serial_number": anchor_id.upper(),
            "scene_id": "scene-a",
            "state": "active",
        },
        "admin",
    )
    calibration = create_calibration(
        db,
        {
            "uid": f"cal-{anchor_id}-r1",
            "anchor_uid": anchor_id,
            "scene_id": "scene-a",
            "x_m": position[0],
            "y_m": position[1],
            "z_m": position[2],
        },
        "admin",
    )
    activate_calibration(db, calibration.uid, "admin", 1)
    calibrations[anchor_id] = calibration
  create_tag(
      db,
      {"uid": "tag-a", "serial_number": "TAG-A", "state": "active"},
      "admin",
  )
  db.flush()
  return positions, calibrations


def _survey_ranges(db, positions, biases, *, outlier_anchor=None):
  survey_points = [
      ("p1", (2.0, 2.0, 1.0)),
      ("p2", (8.0, 2.0, 1.0)),
      ("p3", (8.0, 8.0, 1.0)),
      ("p4", (2.0, 8.0, 1.0)),
  ]
  for point_index, (point_id, point) in enumerate(survey_points):
    create_survey_point(
        db,
        uid=point_id,
        scene_id="scene-a",
        name=point_id,
        x_m=point[0],
        y_m=point[1],
        z_m=point[2],
        actor="admin",
    )
    for repeat in range(5):
      for anchor_id, anchor in positions.items():
        noise = (repeat - 2) * 0.005
        distance = math.dist(anchor, point) + biases[anchor_id] + noise
        if anchor_id == outlier_anchor and point_id == "p2" and repeat == 4:
          distance += 4.0
        add_survey_sample(
            db,
            survey_point_uid=point_id,
            anchor_uid=anchor_id,
            distance_m=distance,
            distance_stddev_m=0.04,
            quality=0.98,
            observed_at=NOW + timedelta(seconds=point_index * 10 + repeat),
        )
  db.flush()


def _solve_with_calibration_details(positions, details, truth, biases):
  measurements = []
  calibrations = []
  for sequence, (anchor_id, anchor) in enumerate(positions.items(), start=1):
    measurements.append({
        "anchor_id": anchor_id,
        "tag_id": "tag-a",
        "scene_id": "scene-a",
        "source_timestamp": NOW,
        "method": "channel_sounding",
        "distance_m": math.dist(anchor, truth) + biases[anchor_id],
        "distance_stddev_m": 0.04,
        "quality": 0.98,
        "nlos_probability": 0.01,
        "sequence": sequence,
    })
    calibrations.append({
        "anchor_id": anchor_id,
        "state": "active",
        "x_m": anchor[0],
        "y_m": anchor[1],
        "z_m": anchor[2],
        "details": details.get(anchor_id, {}),
    })
  return solve_ranges(
      measurements,
      calibrations,
      SolverConfig(fixed_z_m=truth[2]),
  )


def test_bt11_recovers_known_bias_rejects_outlier_and_improves_solver(db):
  session, _database = db
  positions, _ = _seed_anchors(session)
  biases = {"a1": 0.35, "a2": -0.18, "a3": 0.24, "a4": -0.12}
  _survey_ranges(session, positions, biases, outlier_anchor="a3")

  estimates = estimate_anchor_biases(session, "scene-a")
  for anchor_id, expected in biases.items():
    estimate = estimates[anchor_id]
    assert estimate["status"] == "ok"
    assert estimate["bias_m"] == pytest.approx(expected, abs=0.03)
  assert estimates["a3"]["rejected_count"] >= 1

  truth = (4.2, 6.1, 1.0)
  uncorrected = _solve_with_calibration_details(positions, {}, truth, biases)
  corrected_details = {
      anchor_id: {
          "range_bias_m": estimates[anchor_id]["bias_m"],
          "range_stddev_m": estimates[anchor_id]["stddev_m"],
      }
      for anchor_id in positions
  }
  corrected = _solve_with_calibration_details(
      positions,
      corrected_details,
      truth,
      biases,
  )

  def error(result):
    point = result["position"]
    return math.hypot(point["x_m"] - truth[0], point["y_m"] - truth[1])

  assert error(corrected) < error(uncorrected)
  assert error(corrected) < 0.08


def test_bt11_creates_draft_revision_publish_and_revert(db):
  session, database = db
  positions, initial = _seed_anchors(session)
  biases = {"a1": 0.2, "a2": 0.1, "a3": -0.2, "a4": -0.1}
  _survey_ranges(session, positions, biases)

  drafts = create_bias_calibration_revisions(
      session,
      "scene-a",
      "admin",
      minimum_samples=3,
  )
  assert len(drafts) == 4
  a1_draft = next(row for row in drafts if row.anchor_uid == "a1")
  assert a1_draft.state == "draft"
  assert a1_draft.calibration_revision == 2
  assert a1_draft.details["range_bias_m"] == pytest.approx(0.2, abs=0.03)

  published = activate_calibration(session, a1_draft.uid, "admin", 1)
  assert published.state == "active"
  old = session.get(database.BluetoothCalibration, initial["a1"].uid)
  assert old.state == "retired"

  reverted = activate_calibration(session, old.uid, "admin", old.revision)
  assert reverted.state == "active"
  session.refresh(published)
  assert published.state == "retired"


def test_bt11_coverage_is_deterministic_and_separates_geometry_from_rf(db):
  session, _database = db
  positions, _ = _seed_anchors(session)
  biases = {key: 0.0 for key in positions}
  _survey_ranges(session, positions, biases)

  first = coverage_diagnostics(
      session,
      "scene-a",
      min_x_m=0,
      max_x_m=10,
      min_y_m=0,
      max_y_m=10,
      step_m=5,
      fixed_z_m=1,
  )
  second = coverage_diagnostics(
      session,
      "scene-a",
      min_x_m=0,
      max_x_m=10,
      min_y_m=0,
      max_y_m=10,
      step_m=5,
      fixed_z_m=1,
  )
  assert first == second
  assert first["theoretical_geometry"]["anchor_count"] == 4
  assert len(first["theoretical_geometry"]["cells"]) == 9
  assert len(first["observed_rf"]["points"]) == 4
  assert first["theoretical_geometry"]["model"] == "2d-range-gdop"
  assert first["observed_rf"]["source"] == "survey_samples"


def test_bt11_survey_sample_storage_is_bounded(db, monkeypatch):
  session, _database = db
  _seed_anchors(session)
  monkeypatch.setenv("BLUETOOTH_SURVEY_MAX_SAMPLES_PER_POINT", "2")
  create_survey_point(
      session,
      uid="limited",
      scene_id="scene-a",
      name="limited",
      x_m=1,
      y_m=1,
      z_m=1,
      actor="admin",
  )
  for index in range(2):
    add_survey_sample(
        session,
        survey_point_uid="limited",
        anchor_uid="a1",
        distance_m=3.0,
        distance_stddev_m=0.1,
        quality=1.0,
        observed_at=NOW + timedelta(seconds=index),
    )
  with pytest.raises(ValueError, match="sample limit"):
    add_survey_sample(
        session,
        survey_point_uid="limited",
        anchor_uid="a1",
        distance_m=3.0,
        distance_stddev_m=0.1,
        quality=1.0,
        observed_at=NOW + timedelta(seconds=3),
    )


def test_bt11_coverage_grid_is_bounded(db):
  session, _database = db
  _seed_anchors(session)
  with pytest.raises(ValueError, match="10000"):
    coverage_diagnostics(
        session,
        "scene-a",
        min_x_m=0,
        max_x_m=1000,
        min_y_m=0,
        max_y_m=1000,
        step_m=1,
    )
