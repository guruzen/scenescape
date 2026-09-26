# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math

import pytest

from scenescape_api.bluetooth_calibration import calibration_public, geometry_report
from scenescape_api.bluetooth_domain import create_anchor, create_calibration
from scenescape_api.database import Base, Resource


@pytest.fixture
def db(tmp_path, monkeypatch):
  monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/bt04-calibration.db")
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


def _scene(db, uid):
  db.add(Resource(kind="scene", uid=uid, revision=1, payload={"name": uid}))
  db.commit()


def test_bt04_geometry_detects_duplicate_and_collinear_layout(db):
  _scene(db, "geometry-scene")
  rows = []
  for index, point in enumerate([(0, 0), (0.01, 0.01), (4, 0), (8, 0)], start=1):
    anchor = create_anchor(
        db,
        {
            "uid": f"geometry-anchor-{index}",
            "serial_number": f"GEOMETRY-{index}",
            "scene_id": "geometry-scene",
        },
        "admin",
    )
    rows.append(
        create_calibration(
            db,
            {
                "uid": f"geometry-cal-{index}",
                "anchor_uid": anchor.uid,
                "scene_id": "geometry-scene",
                "x_m": point[0],
                "y_m": point[1],
                "z_m": 2.5,
            },
            "installer",
        )
    )
  db.commit()

  report = geometry_report(rows)
  codes = {warning["code"] for warning in report["warnings"]}
  assert report["anchor_count"] == 4
  assert "duplicate_anchor_location" in codes
  assert "collinear_geometry" in codes
  assert report["ready_for_2d"] is False


def test_bt04_geometry_accepts_well_spread_four_anchor_layout(db):
  _scene(db, "square-scene")
  rows = []
  for index, point in enumerate([(0, 0), (8, 0), (8, 6), (0, 6)], start=1):
    anchor = create_anchor(
        db,
        {
            "uid": f"square-anchor-{index}",
            "serial_number": f"SQUARE-{index}",
            "scene_id": "square-scene",
        },
        "admin",
    )
    rows.append(
        create_calibration(
            db,
            {
                "uid": f"square-cal-{index}",
                "anchor_uid": anchor.uid,
                "scene_id": "square-scene",
                "x_m": point[0],
                "y_m": point[1],
                "z_m": 3,
            },
            "installer",
        )
    )
  db.commit()

  report = geometry_report(rows)
  assert report["anchor_count"] == 4
  assert report["ready_for_2d"] is True
  assert report["warnings"] == []
  assert report["spread_ratio"] > 0.1


def test_bt04_child_scene_projection_preserves_local_coordinates(db):
  _scene(db, "parent-scene")
  _scene(db, "child-scene")
  db.add(
      Resource(
          kind="child",
          uid="parent-child-link",
          revision=1,
          payload={
              "child_type": "local",
              "parent": "parent-scene",
              "child": "child-scene",
              "transform_type": "euler",
              "transform1": 10.0,
              "transform2": 20.0,
              "transform3": 1.0,
              "transform4": 0.0,
              "transform5": 0.0,
              "transform6": 0.0,
              "transform7": 1.0,
              "transform8": 1.0,
              "transform9": 1.0,
          },
      )
  )
  anchor = create_anchor(
      db,
      {
          "uid": "child-anchor",
          "serial_number": "CHILD-ANCHOR",
          "scene_id": "child-scene",
      },
      "admin",
  )
  row = create_calibration(
      db,
      {
          "uid": "child-cal",
          "anchor_uid": anchor.uid,
          "scene_id": "child-scene",
          "x_m": 2,
          "y_m": 3,
          "z_m": 4,
          "z_source": "surveyed",
      },
      "installer",
  )
  db.commit()

  value = calibration_public(db, row)
  assert value["position"] == {"x_m": 2.0, "y_m": 3.0, "z_m": 4.0}
  assert value["coordinate_frame"] == "scene_local_m"
  assert value["parent_projection"]["parent_scene_id"] == "parent-scene"
  projected = value["parent_projection"]["position"]
  assert math.isclose(projected["x_m"], 12.0)
  assert math.isclose(projected["y_m"], 23.0)
  assert math.isclose(projected["z_m"], 5.0)
