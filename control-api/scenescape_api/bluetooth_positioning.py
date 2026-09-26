# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Robust Bluetooth range positioning engine (BT-07)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Literal

import numpy as np
from scipy.optimize import least_squares
from sqlalchemy import func, select

from .database import (
    BluetoothCalibration,
    BluetoothMeasurement,
    BluetoothRawPosition,
    utcnow,
)

SOLVER_NAME = "robust-wls"
SOLVER_VERSION = "1"


@dataclass(frozen=True)
class SolverConfig:
  window_ms: float = 250.0
  fixed_z_m: float = 1.0
  mode: Literal["auto", "2d", "3d"] = "auto"
  max_abs_residual_m: float = 0.75
  sigma_floor_m: float = 0.03
  max_condition_number: float = 1e10


def _utc(value: datetime) -> datetime:
  if value.tzinfo is None:
    return value.replace(tzinfo=timezone.utc)
  return value.astimezone(timezone.utc)


def _finite(value: float | None) -> bool:
  return value is not None and math.isfinite(float(value))


def _calibration_map(
    calibrations: Iterable[BluetoothCalibration | dict[str, Any]],
) -> dict[str, dict[str, float]]:
  result: dict[str, dict[str, float]] = {}
  for item in calibrations:
    if isinstance(item, dict):
      anchor_id = str(item.get("anchor_id") or item.get("anchor_uid") or "")
      state = str(item.get("state") or "active")
      if state != "active":
        continue
      if "position" in item:
        position = item["position"]
        x_m = position.get("x_m")
        y_m = position.get("y_m")
        z_m = position.get("z_m")
      else:
        x_m, y_m, z_m = item.get("x_m"), item.get("y_m"), item.get("z_m")
    else:
      anchor_id = item.anchor_uid
      if item.state != "active":
        continue
      x_m, y_m, z_m = item.x_m, item.y_m, item.z_m
    if anchor_id and all(_finite(value) for value in (x_m, y_m, z_m)):
      result[anchor_id] = {
          "x_m": float(x_m),
          "y_m": float(y_m),
          "z_m": float(z_m),
      }
  return result


def _measurement_dict(item: BluetoothMeasurement | dict[str, Any]) -> dict[str, Any]:
  if isinstance(item, dict):
    return dict(item)
  return {
      "anchor_id": item.anchor_uid,
      "tag_id": item.tag_uid,
      "scene_id": item.scene_id,
      "source_timestamp": item.source_timestamp,
      "method": item.method,
      "distance_m": item.distance_m,
      "distance_stddev_m": item.distance_stddev_m,
      "nlos_probability": item.nlos_probability,
      "quality": item.quality,
      "sequence": item.sequence,
  }


def _effective_sigma(row: dict[str, Any], config: SolverConfig) -> float:
  base = max(float(row.get("distance_stddev_m") or config.sigma_floor_m), config.sigma_floor_m)
  quality = min(max(float(row.get("quality") or 0.01), 0.01), 1.0)
  nlos = min(max(float(row.get("nlos_probability") or 0.0), 0.0), 1.0)
  return base * (1.0 + 2.5 * nlos) / math.sqrt(quality)


def _geometry_rank(anchor_xyz: np.ndarray, dimension: int) -> tuple[int, float]:
  if len(anchor_xyz) < dimension + 1:
    return 0, math.inf
  centered = anchor_xyz[:, :dimension] - np.mean(anchor_xyz[:, :dimension], axis=0)
  rank = int(np.linalg.matrix_rank(centered, tol=1e-8))
  singular = np.linalg.svd(centered, compute_uv=False)
  if len(singular) < dimension or singular[-1] <= 1e-12:
    condition = math.inf
  else:
    condition = float(singular[0] / singular[-1])
  return rank, condition


def _choose_dimension(
    anchor_xyz: np.ndarray,
    config: SolverConfig,
) -> tuple[int | None, str]:
  if config.mode == "2d":
    rank, condition = _geometry_rank(anchor_xyz, 2)
    if rank < 2 or condition > config.max_condition_number:
      return None, "singular_2d_geometry"
    return 2, "requested_2d"

  if config.mode == "3d":
    rank, condition = _geometry_rank(anchor_xyz, 3)
    if len(anchor_xyz) < 4 or rank < 3 or condition > config.max_condition_number:
      return None, "unobservable_3d_geometry"
    return 3, "requested_3d"

  rank3, condition3 = _geometry_rank(anchor_xyz, 3)
  z_span = float(np.ptp(anchor_xyz[:, 2])) if len(anchor_xyz) else 0.0
  if (
      len(anchor_xyz) >= 4
      and rank3 >= 3
      and z_span >= 0.75
      and condition3 <= config.max_condition_number
  ):
    return 3, "auto_3d"
  rank2, condition2 = _geometry_rank(anchor_xyz, 2)
  if len(anchor_xyz) >= 3 and rank2 >= 2 and condition2 <= config.max_condition_number:
    return 2, "auto_2d_constrained_z"
  return None, "singular_geometry"


def _initial_guess(anchor_xyz: np.ndarray, dimension: int, fixed_z_m: float) -> np.ndarray:
  center = np.mean(anchor_xyz, axis=0)
  if dimension == 2:
    return np.array([center[0], center[1]], dtype=float)
  z = center[2] if math.isfinite(float(center[2])) else fixed_z_m
  return np.array([center[0], center[1], z], dtype=float)


def _predicted_ranges(
    state: np.ndarray,
    anchor_xyz: np.ndarray,
    dimension: int,
    fixed_z_m: float,
) -> np.ndarray:
  if dimension == 2:
    point = np.array([state[0], state[1], fixed_z_m], dtype=float)
  else:
    point = np.array(state[:3], dtype=float)
  return np.linalg.norm(anchor_xyz - point, axis=1)


def _weighted_residuals(
    state: np.ndarray,
    anchor_xyz: np.ndarray,
    distances: np.ndarray,
    sigmas: np.ndarray,
    dimension: int,
    fixed_z_m: float,
) -> np.ndarray:
  predicted = _predicted_ranges(state, anchor_xyz, dimension, fixed_z_m)
  return (predicted - distances) / sigmas


def _physical_jacobian(
    point: np.ndarray,
    anchor_xyz: np.ndarray,
    dimension: int,
    sigmas: np.ndarray | None = None,
) -> np.ndarray:
  deltas = point[None, :] - anchor_xyz
  ranges = np.linalg.norm(deltas, axis=1)
  ranges = np.maximum(ranges, 1e-9)
  jac = deltas[:, :dimension] / ranges[:, None]
  if sigmas is not None:
    jac = jac / sigmas[:, None]
  return jac


def _uncertainty(
    point: np.ndarray,
    anchor_xyz: np.ndarray,
    dimension: int,
    sigmas: np.ndarray,
    residuals_m: np.ndarray,
    config: SolverConfig,
) -> tuple[float | None, float | None, float | None, float]:
  geometry = _physical_jacobian(point, anchor_xyz, dimension)
  weighted = _physical_jacobian(point, anchor_xyz, dimension, sigmas)
  try:
    normal = geometry.T @ geometry
    condition = float(np.linalg.cond(normal))
    if not math.isfinite(condition) or condition > config.max_condition_number:
      return None, None, None, condition
    gdop = float(math.sqrt(max(0.0, float(np.trace(np.linalg.inv(normal))))))

    weighted_normal = weighted.T @ weighted
    weighted_condition = float(np.linalg.cond(weighted_normal))
    if not math.isfinite(weighted_condition) or weighted_condition > config.max_condition_number:
      return None, None, gdop, weighted_condition
    base_covariance = np.linalg.inv(weighted_normal)
    variance = max(
        float(np.mean(np.square(residuals_m))) if len(residuals_m) else 0.0,
        float(np.median(np.square(sigmas))) if len(sigmas) else config.sigma_floor_m**2,
        1e-6,
    )
    covariance = base_covariance * variance
    horizontal = 1.96 * math.sqrt(max(0.0, float(covariance[0, 0] + covariance[1, 1])))
    vertical = None
    if dimension == 3:
      vertical = 1.96 * math.sqrt(max(0.0, float(covariance[2, 2])))
    return horizontal, vertical, gdop, weighted_condition
  except (np.linalg.LinAlgError, ValueError, OverflowError):
    return None, None, None, math.inf


def _quality_score(
    *,
    anchors_used: int,
    dimension: int,
    residual_rms_m: float,
    gdop: float | None,
    uncertainty_m: float | None,
    average_input_quality: float,
    average_nlos: float,
) -> float:
  minimum = dimension + 1
  redundancy = min(1.0, max(0.0, (anchors_used - minimum + 1) / 3.0))
  residual_term = math.exp(-max(0.0, residual_rms_m) / 0.5)
  geometry_term = 0.35 if gdop is None else min(1.0, 2.5 / max(gdop, 0.5))
  uncertainty_term = 0.35 if uncertainty_m is None else math.exp(-max(0.0, uncertainty_m) / 1.0)
  input_term = min(max(average_input_quality, 0.0), 1.0) * (1.0 - 0.5 * average_nlos)
  score = (
      0.15 * redundancy
      + 0.25 * residual_term
      + 0.20 * geometry_term
      + 0.20 * uncertainty_term
      + 0.20 * input_term
  )
  return min(max(score, 0.0), 1.0)


def unavailable_result(
    *,
    reason: str,
    source_timestamp: datetime | None,
    anchors_visible: int,
    method: str,
    dimension: str = "unavailable",
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
  return {
      "state": "unavailable",
      "position": None,
      "dimension": dimension,
      "source_timestamp": _utc(source_timestamp or utcnow()),
      "quality": {
          "state": "unavailable",
          "horizontal_uncertainty_m": None,
          "vertical_uncertainty_m": None,
          "score": 0.0,
          "anchors_visible": anchors_visible,
          "anchors_used": 0,
          "residual_rms_m": None,
          "gdop": None,
          "method": method,
      },
      "solver": {"name": SOLVER_NAME, "version": SOLVER_VERSION},
      "accepted_anchors": [],
      "rejected_anchors": [],
      "diagnostics": {"reason": reason, **(diagnostics or {})},
  }


def solve_ranges(
    measurements: Iterable[BluetoothMeasurement | dict[str, Any]],
    calibrations: Iterable[BluetoothCalibration | dict[str, Any]],
    config: SolverConfig | None = None,
) -> dict[str, Any]:
  config = config or SolverConfig()
  rows = [_measurement_dict(item) for item in measurements]
  if not rows:
    return unavailable_result(
        reason="no_measurements",
        source_timestamp=None,
        anchors_visible=0,
        method="unknown",
    )
  calibration = _calibration_map(calibrations)
  valid_rows: list[dict[str, Any]] = []
  missing_calibration: list[str] = []
  for row in rows:
    anchor_id = str(row.get("anchor_id") or row.get("anchor_uid") or "")
    values = (
        row.get("distance_m"),
        row.get("distance_stddev_m"),
        row.get("quality"),
        row.get("nlos_probability"),
    )
    if anchor_id not in calibration:
      missing_calibration.append(anchor_id)
      continue
    if not all(_finite(value) for value in values):
      continue
    if float(row["distance_m"]) < 0.0 or float(row["distance_stddev_m"]) <= 0.0:
      continue
    valid_rows.append({**row, "anchor_id": anchor_id})

  timestamps = [
      _utc(row["source_timestamp"])
      for row in valid_rows
      if isinstance(row.get("source_timestamp"), datetime)
  ]
  source_timestamp = max(timestamps) if timestamps else utcnow()
  methods = sorted({str(row.get("method") or "unknown") for row in valid_rows})
  method = methods[0] if len(methods) == 1 else "mixed"

  # Keep at most the newest range per anchor in the coherent solve.
  newest_by_anchor: dict[str, dict[str, Any]] = {}
  for row in valid_rows:
    anchor_id = row["anchor_id"]
    current = newest_by_anchor.get(anchor_id)
    current_ts = current.get("source_timestamp") if current else None
    row_ts = row.get("source_timestamp")
    if current is None or (
        isinstance(row_ts, datetime)
        and (not isinstance(current_ts, datetime) or _utc(row_ts) > _utc(current_ts))
    ):
      newest_by_anchor[anchor_id] = row
  valid_rows = [newest_by_anchor[key] for key in sorted(newest_by_anchor)]

  anchor_xyz = np.array(
      [
          [
              calibration[row["anchor_id"]]["x_m"],
              calibration[row["anchor_id"]]["y_m"],
              calibration[row["anchor_id"]]["z_m"],
          ]
          for row in valid_rows
      ],
      dtype=float,
  )
  dimension, dimension_reason = _choose_dimension(anchor_xyz, config)
  if dimension is None:
    return unavailable_result(
        reason=dimension_reason,
        source_timestamp=source_timestamp,
        anchors_visible=len(valid_rows),
        method=method,
        diagnostics={"missing_calibration": sorted(set(missing_calibration))},
    )
  minimum_anchors = dimension + 1
  if len(valid_rows) < minimum_anchors:
    return unavailable_result(
        reason="insufficient_anchors",
        source_timestamp=source_timestamp,
        anchors_visible=len(valid_rows),
        method=method,
        dimension=f"{dimension}d",
    )

  distances = np.array([float(row["distance_m"]) for row in valid_rows], dtype=float)
  sigmas = np.array([_effective_sigma(row, config) for row in valid_rows], dtype=float)
  initial = _initial_guess(anchor_xyz, dimension, config.fixed_z_m)
  try:
    first = least_squares(
        _weighted_residuals,
        initial,
        args=(anchor_xyz, distances, sigmas, dimension, config.fixed_z_m),
        loss="soft_l1",
        f_scale=1.0,
        max_nfev=200,
    )
  except (ValueError, FloatingPointError, OverflowError) as exc:
    return unavailable_result(
        reason="solver_exception",
        source_timestamp=source_timestamp,
        anchors_visible=len(valid_rows),
        method=method,
        dimension=f"{dimension}d",
        diagnostics={"exception": type(exc).__name__},
    )
  if not first.success or not np.all(np.isfinite(first.x)):
    return unavailable_result(
        reason="solver_diverged",
        source_timestamp=source_timestamp,
        anchors_visible=len(valid_rows),
        method=method,
        dimension=f"{dimension}d",
        diagnostics={"status": int(first.status), "message": str(first.message)[:240]},
    )

  predicted = _predicted_ranges(first.x, anchor_xyz, dimension, config.fixed_z_m)
  residuals = predicted - distances
  thresholds = np.maximum(
      config.max_abs_residual_m,
      3.0 * sigmas,
  )
  keep = np.abs(residuals) <= thresholds

  # Never throw away enough anchors to make the solve mathematically unsupported.
  if int(np.sum(keep)) < minimum_anchors:
    candidates = np.argsort(np.abs(residuals))
    keep = np.zeros(len(valid_rows), dtype=bool)
    keep[candidates[:minimum_anchors]] = True

  used_rows = [row for index, row in enumerate(valid_rows) if bool(keep[index])]
  rejected_rows = [
      {
          "anchor_id": row["anchor_id"],
          "reason": "residual_outlier",
          "residual_m": round(float(residuals[index]), 6),
      }
      for index, row in enumerate(valid_rows)
      if not bool(keep[index])
  ]
  used_xyz = anchor_xyz[keep]
  used_distances = distances[keep]
  used_sigmas = sigmas[keep]

  rank, condition = _geometry_rank(used_xyz, dimension)
  if rank < dimension or condition > config.max_condition_number:
    return unavailable_result(
        reason="singular_after_outlier_rejection",
        source_timestamp=source_timestamp,
        anchors_visible=len(valid_rows),
        method=method,
        dimension=f"{dimension}d",
        diagnostics={
            "geometry_condition": condition,
            "rejected_anchors": rejected_rows,
        },
    )

  refined_initial = first.x
  try:
    refined = least_squares(
        _weighted_residuals,
        refined_initial,
        args=(
            used_xyz,
            used_distances,
            used_sigmas,
            dimension,
            config.fixed_z_m,
        ),
        loss="soft_l1",
        f_scale=1.0,
        max_nfev=200,
    )
  except (ValueError, FloatingPointError, OverflowError) as exc:
    return unavailable_result(
        reason="solver_exception",
        source_timestamp=source_timestamp,
        anchors_visible=len(valid_rows),
        method=method,
        dimension=f"{dimension}d",
        diagnostics={"exception": type(exc).__name__},
    )
  if not refined.success or not np.all(np.isfinite(refined.x)):
    return unavailable_result(
        reason="solver_diverged",
        source_timestamp=source_timestamp,
        anchors_visible=len(valid_rows),
        method=method,
        dimension=f"{dimension}d",
    )

  if dimension == 2:
    point = np.array([refined.x[0], refined.x[1], config.fixed_z_m], dtype=float)
  else:
    point = np.array(refined.x[:3], dtype=float)
  if not np.all(np.isfinite(point)):
    return unavailable_result(
        reason="non_finite_solution",
        source_timestamp=source_timestamp,
        anchors_visible=len(valid_rows),
        method=method,
        dimension=f"{dimension}d",
    )

  final_residuals = (
      np.linalg.norm(used_xyz - point[None, :], axis=1) - used_distances
  )
  residual_rms = float(math.sqrt(float(np.mean(np.square(final_residuals)))))
  horizontal, vertical, gdop, covariance_condition = _uncertainty(
      point,
      used_xyz,
      dimension,
      used_sigmas,
      final_residuals,
      config,
  )
  average_quality = float(np.mean([float(row.get("quality") or 0.0) for row in used_rows]))
  average_nlos = float(
      np.mean([float(row.get("nlos_probability") or 0.0) for row in used_rows])
  )
  score = _quality_score(
      anchors_used=len(used_rows),
      dimension=dimension,
      residual_rms_m=residual_rms,
      gdop=gdop,
      uncertainty_m=horizontal,
      average_input_quality=average_quality,
      average_nlos=average_nlos,
  )
  state = "good"
  if (
      len(used_rows) <= minimum_anchors
      or horizontal is None
      or horizontal > 0.75
      or gdop is None
      or gdop > 3.5
      or residual_rms > 0.4
      or score < 0.65
  ):
    state = "degraded"

  accepted = []
  for row, residual in zip(used_rows, final_residuals):
    accepted.append({
        "anchor_id": row["anchor_id"],
        "residual_m": round(float(residual), 6),
        "distance_stddev_m": round(float(row["distance_stddev_m"]), 6),
        "effective_sigma_m": round(_effective_sigma(row, config), 6),
        "quality": round(float(row.get("quality") or 0.0), 4),
        "nlos_probability": round(float(row.get("nlos_probability") or 0.0), 4),
    })

  return {
      "state": state,
      "position": {
          "x_m": float(point[0]),
          "y_m": float(point[1]),
          "z_m": float(point[2]),
      },
      "dimension": f"{dimension}d" if dimension == 3 else "2d_constrained_z",
      "source_timestamp": source_timestamp,
      "quality": {
          "state": state,
          "horizontal_uncertainty_m": horizontal,
          "vertical_uncertainty_m": vertical,
          "score": score,
          "anchors_visible": len(valid_rows),
          "anchors_used": len(used_rows),
          "residual_rms_m": residual_rms,
          "gdop": gdop,
          "method": method,
      },
      "solver": {"name": SOLVER_NAME, "version": SOLVER_VERSION},
      "accepted_anchors": accepted,
      "rejected_anchors": rejected_rows,
      "diagnostics": {
          "dimension_reason": dimension_reason,
          "missing_calibration": sorted(set(missing_calibration)),
          "geometry_condition": condition,
          "covariance_condition": covariance_condition,
          "iterations": int(refined.nfev),
      },
  }


def coherent_measurements(
    db,
    scene_id: str,
    tag_id: str,
    *,
    window_ms: float,
) -> list[BluetoothMeasurement]:
  latest = db.scalar(
      select(func.max(BluetoothMeasurement.source_timestamp)).where(
          BluetoothMeasurement.scene_id == scene_id,
          BluetoothMeasurement.tag_uid == tag_id,
      )
  )
  if latest is None:
    return []
  cutoff = _utc(latest) - timedelta(milliseconds=max(1.0, float(window_ms)))
  rows = db.scalars(
      select(BluetoothMeasurement)
      .where(
          BluetoothMeasurement.scene_id == scene_id,
          BluetoothMeasurement.tag_uid == tag_id,
          BluetoothMeasurement.source_timestamp >= cutoff,
          BluetoothMeasurement.source_timestamp <= latest,
      )
      .order_by(
          BluetoothMeasurement.source_timestamp.desc(),
          BluetoothMeasurement.sequence.desc(),
      )
  ).all()
  newest_by_anchor: dict[str, BluetoothMeasurement] = {}
  for row in rows:
    newest_by_anchor.setdefault(row.anchor_uid, row)
  return [newest_by_anchor[key] for key in sorted(newest_by_anchor)]


def active_calibrations(db, scene_id: str) -> list[BluetoothCalibration]:
  return db.scalars(
      select(BluetoothCalibration)
      .where(
          BluetoothCalibration.scene_id == scene_id,
          BluetoothCalibration.state == "active",
      )
      .order_by(BluetoothCalibration.anchor_uid)
  ).all()


def persist_raw_solve(
    db,
    scene_id: str,
    tag_id: str,
    result: dict[str, Any],
) -> BluetoothRawPosition:
  quality = result["quality"]
  position = result.get("position") or {}
  row = BluetoothRawPosition(
      scene_id=scene_id,
      tag_uid=tag_id,
      source_timestamp=_utc(result["source_timestamp"]),
      x_m=position.get("x_m"),
      y_m=position.get("y_m"),
      z_m=position.get("z_m"),
      dimension=str(result.get("dimension") or "unavailable"),
      state=str(result.get("state") or "unavailable"),
      horizontal_uncertainty_m=quality.get("horizontal_uncertainty_m"),
      vertical_uncertainty_m=quality.get("vertical_uncertainty_m"),
      score=float(quality.get("score") or 0.0),
      anchors_visible=int(quality.get("anchors_visible") or 0),
      anchors_used=int(quality.get("anchors_used") or 0),
      residual_rms_m=quality.get("residual_rms_m"),
      gdop=quality.get("gdop"),
      method=str(quality.get("method") or "unknown"),
      solver_name=str(result["solver"]["name"]),
      solver_version=str(result["solver"]["version"]),
      diagnostics={
          "accepted_anchors": result.get("accepted_anchors", []),
          "rejected_anchors": result.get("rejected_anchors", []),
          **dict(result.get("diagnostics") or {}),
      },
  )
  db.add(row)
  db.flush()
  return row


def solve_latest(
    db,
    scene_id: str,
    tag_id: str,
    config: SolverConfig | None = None,
) -> tuple[dict[str, Any], BluetoothRawPosition]:
  config = config or SolverConfig()
  measurements = coherent_measurements(
      db,
      scene_id,
      tag_id,
      window_ms=config.window_ms,
  )
  calibrations = active_calibrations(db, scene_id)
  result = solve_ranges(measurements, calibrations, config)
  row = persist_raw_solve(db, scene_id, tag_id, result)
  return result, row
