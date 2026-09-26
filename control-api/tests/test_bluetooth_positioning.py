# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math
import random
import time
from datetime import datetime, timezone

import numpy as np
import pytest

from scenescape_api.bluetooth_positioning import SolverConfig, solve_ranges


def _calibrations(points):
  return [
      {
          "anchor_id": f"a{index}",
          "state": "active",
          "x_m": point[0],
          "y_m": point[1],
          "z_m": point[2],
      }
      for index, point in enumerate(points, start=1)
  ]


def _measurements(points, tag, *, noise=None, qualities=None, nlos=None):
  stamp = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
  rows = []
  for index, point in enumerate(points, start=1):
    ideal = math.dist(point, tag)
    delta = 0.0 if noise is None else noise[index - 1]
    rows.append({
        "anchor_id": f"a{index}",
        "tag_id": "tag-1",
        "scene_id": "scene-a",
        "source_timestamp": stamp,
        "method": "channel_sounding",
        "distance_m": ideal + delta,
        "distance_stddev_m": 0.05,
        "quality": 1.0 if qualities is None else qualities[index - 1],
        "nlos_probability": 0.0 if nlos is None else nlos[index - 1],
        "sequence": index,
    })
  return rows


def _error(result, truth):
  assert result["position"] is not None
  point = result["position"]
  return math.hypot(point["x_m"] - truth[0], point["y_m"] - truth[1])


def test_bt07_exact_square_geometry_solves_2d_without_false_z_precision():
  anchors = [(0, 0, 3), (10, 0, 3), (10, 10, 3), (0, 10, 3)]
  truth = (4.0, 3.0, 1.0)
  result = solve_ranges(
      _measurements(anchors, truth),
      _calibrations(anchors),
      SolverConfig(fixed_z_m=1.0),
  )

  assert result["state"] == "good"
  assert result["dimension"] == "2d_constrained_z"
  assert _error(result, truth) < 1e-5
  assert result["position"]["z_m"] == 1.0
  assert result["quality"]["anchors_used"] == 4
  assert result["quality"]["residual_rms_m"] < 1e-5
  assert result["quality"]["horizontal_uncertainty_m"] is not None
  assert result["solver"] == {"name": "robust-wls", "version": "1"}


def test_bt07_seeded_noise_reports_quantified_p50_p95_accuracy():
  anchors = [(0, 0, 3), (12, 0, 3), (12, 8, 3), (0, 8, 3), (6, 0, 3)]
  truth = (5.5, 3.5, 1.0)
  rng = random.Random(707)
  errors = []
  for sample in range(120):
    noise = [rng.gauss(0.0, 0.06) for _ in anchors]
    rows = _measurements(anchors, truth, noise=noise)
    for index, row in enumerate(rows):
      row["sequence"] = sample * 10 + index
    result = solve_ranges(rows, _calibrations(anchors), SolverConfig(fixed_z_m=1.0))
    assert result["state"] in {"good", "degraded"}
    errors.append(_error(result, truth))

  p50 = float(np.percentile(errors, 50))
  p95 = float(np.percentile(errors, 95))
  assert p50 < 0.12
  assert p95 < 0.30


def test_bt07_outlier_and_nlos_are_downweighted_or_rejected():
  anchors = [(0, 0, 3), (10, 0, 3), (10, 10, 3), (0, 10, 3), (5, 10, 3)]
  truth = (4.0, 4.0, 1.0)
  noise = [0.02, -0.03, 0.01, -0.01, 4.0]
  quality = [0.98, 0.98, 0.98, 0.98, 0.2]
  nlos = [0.02, 0.02, 0.02, 0.02, 0.95]
  result = solve_ranges(
      _measurements(anchors, truth, noise=noise, qualities=quality, nlos=nlos),
      _calibrations(anchors),
      SolverConfig(fixed_z_m=1.0),
  )

  assert result["state"] in {"good", "degraded"}
  assert _error(result, truth) < 0.35
  accepted = {item["anchor_id"] for item in result["accepted_anchors"]}
  rejected = {item["anchor_id"] for item in result["rejected_anchors"]}
  assert "a5" in rejected or "a5" in accepted
  if "a5" in accepted:
    a5 = next(item for item in result["accepted_anchors"] if item["anchor_id"] == "a5")
    assert a5["effective_sigma_m"] > 0.3


def test_bt07_insufficient_and_collinear_geometry_return_unavailable_without_coordinate():
  truth = (3.0, 2.0, 1.0)
  two = [(0, 0, 3), (10, 0, 3)]
  insufficient = solve_ranges(
      _measurements(two, truth),
      _calibrations(two),
      SolverConfig(fixed_z_m=1.0),
  )
  assert insufficient["state"] == "unavailable"
  assert insufficient["position"] is None

  line = [(0, 0, 3), (5, 0, 3), (10, 0, 3), (15, 0, 3)]
  collinear = solve_ranges(
      _measurements(line, truth),
      _calibrations(line),
      SolverConfig(fixed_z_m=1.0),
  )
  assert collinear["state"] == "unavailable"
  assert collinear["position"] is None
  assert "geometry" in collinear["diagnostics"]["reason"]


def test_bt07_auto_falls_back_to_2d_when_3d_vertical_geometry_is_unobservable():
  anchors = [(0, 0, 3), (10, 0, 3), (10, 10, 3), (0, 10, 3)]
  truth = (4.0, 3.0, 1.0)
  automatic = solve_ranges(
      _measurements(anchors, truth),
      _calibrations(anchors),
      SolverConfig(mode="auto", fixed_z_m=1.0),
  )
  forced_3d = solve_ranges(
      _measurements(anchors, truth),
      _calibrations(anchors),
      SolverConfig(mode="3d", fixed_z_m=1.0),
  )

  assert automatic["dimension"] == "2d_constrained_z"
  assert automatic["position"] is not None
  assert forced_3d["state"] == "unavailable"
  assert forced_3d["position"] is None
  assert forced_3d["diagnostics"]["reason"] == "unobservable_3d_geometry"


def test_bt07_observable_3d_geometry_solves_three_dimensions():
  anchors = [(0, 0, 0), (10, 0, 2), (0, 10, 4), (10, 10, 7), (5, 5, 9)]
  truth = (4.0, 3.0, 2.5)
  result = solve_ranges(
      _measurements(anchors, truth),
      _calibrations(anchors),
      SolverConfig(mode="3d"),
  )

  assert result["state"] in {"good", "degraded"}
  assert result["dimension"] == "3d"
  point = result["position"]
  assert point is not None
  assert math.dist((point["x_m"], point["y_m"], point["z_m"]), truth) < 1e-4
  assert result["quality"]["vertical_uncertainty_m"] is not None


def test_bt07_non_finite_measurements_never_serialize_invalid_position():
  anchors = [(0, 0, 3), (10, 0, 3), (10, 10, 3), (0, 10, 3)]
  truth = (4.0, 3.0, 1.0)
  rows = _measurements(anchors, truth)
  rows[0]["distance_m"] = float("nan")
  rows[1]["distance_stddev_m"] = float("inf")
  result = solve_ranges(rows, _calibrations(anchors), SolverConfig(fixed_z_m=1.0))

  assert result["state"] == "unavailable"
  assert result["position"] is None
  assert all(
      value is None or math.isfinite(float(value))
      for value in result["quality"].values()
      if isinstance(value, (int, float))
  )


def test_bt07_many_tag_solver_path_has_bounded_runtime():
  anchors = [(0, 0, 3), (15, 0, 3), (15, 10, 3), (0, 10, 3), (7.5, 5, 3)]
  calibrations = _calibrations(anchors)
  rng = random.Random(1707)
  started = time.perf_counter()
  count = 250
  errors = []
  for index in range(count):
    truth = (
        1.0 + 13.0 * rng.random(),
        1.0 + 8.0 * rng.random(),
        1.0,
    )
    noise = [rng.gauss(0.0, 0.05) for _ in anchors]
    result = solve_ranges(
        _measurements(anchors, truth, noise=noise),
        calibrations,
        SolverConfig(fixed_z_m=1.0),
    )
    errors.append(_error(result, truth))
  elapsed = time.perf_counter() - started

  assert elapsed < 8.0
  assert float(np.percentile(errors, 95)) < 0.35
