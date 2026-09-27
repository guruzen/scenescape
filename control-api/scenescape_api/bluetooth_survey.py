# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Survey calibration, bias estimation and coverage diagnostics (BT-11)."""

from __future__ import annotations

import math
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping

import numpy as np
from sqlalchemy import func, select

from .bluetooth_domain import create_calibration
from .database import (
    BluetoothAnchor,
    BluetoothCalibration,
    BluetoothSurveyPoint,
    BluetoothSurveySample,
    Resource,
    utcnow,
)


def _utc(value: datetime) -> datetime:
  if value.tzinfo is None:
    return value.replace(tzinfo=timezone.utc)
  return value.astimezone(timezone.utc)


def _finite(value: Any) -> float:
  number = float(value)
  if not math.isfinite(number):
    raise ValueError("survey numeric values must be finite")
  return number


def create_survey_point(
    db,
    *,
    scene_id: str,
    name: str,
    x_m: float,
    y_m: float,
    z_m: float,
    actor: str,
    uid: str | None = None,
) -> BluetoothSurveyPoint:
  if db.scalar(
      select(Resource.id)
      .where(Resource.kind == "scene", Resource.uid == scene_id)
      .limit(1)
  ) is None:
    raise ValueError("survey scene does not exist")
  coordinates = [_finite(x_m), _finite(y_m), _finite(z_m)]
  if abs(coordinates[0]) > 1_000_000 or abs(coordinates[1]) > 1_000_000:
    raise ValueError("survey x/y exceeds supported site bound")
  if coordinates[2] < -1_000 or coordinates[2] > 10_000:
    raise ValueError("survey z exceeds supported site bound")
  label = str(name).strip()
  if not label or len(label) > 160:
    raise ValueError("survey point name is required and must be <=160 chars")
  point = BluetoothSurveyPoint(
      uid=uid or f"bt-survey-{uuid.uuid4()}",
      scene_id=scene_id,
      name=label,
      x_m=coordinates[0],
      y_m=coordinates[1],
      z_m=coordinates[2],
      state="open",
      created_by=actor,
  )
  db.add(point)
  db.flush()
  return point


def add_survey_sample(
    db,
    *,
    survey_point_uid: str,
    anchor_uid: str,
    distance_m: float,
    distance_stddev_m: float,
    quality: float,
    observed_at: datetime,
    details: Mapping[str, Any] | None = None,
) -> BluetoothSurveySample:
  point = db.get(BluetoothSurveyPoint, survey_point_uid)
  if point is None:
    raise ValueError("survey point not found")
  if point.state != "open":
    raise ValueError("survey point is closed")
  anchor = db.get(BluetoothAnchor, anchor_uid)
  if anchor is None:
    raise ValueError("survey anchor not found")
  if anchor.scene_id != point.scene_id:
    raise ValueError("survey anchor belongs to a different scene")
  distance = _finite(distance_m)
  stddev = _finite(distance_stddev_m)
  score = _finite(quality)
  if distance < 0.0:
    raise ValueError("survey distance must be non-negative")
  if stddev <= 0.0:
    raise ValueError("survey distance_stddev_m must be >0")
  if not 0.0 <= score <= 1.0:
    raise ValueError("survey quality must be inside [0,1]")
  max_samples = max(1, int(os.getenv("BLUETOOTH_SURVEY_MAX_SAMPLES_PER_POINT", "5000")))
  count = int(
      db.scalar(
          select(func.count())
          .select_from(BluetoothSurveySample)
          .where(BluetoothSurveySample.survey_point_uid == point.uid)
      )
      or 0
  )
  if count >= max_samples:
    raise ValueError("survey point sample limit reached")
  sample = BluetoothSurveySample(
      survey_point_uid=point.uid,
      anchor_uid=anchor.uid,
      distance_m=distance,
      distance_stddev_m=stddev,
      quality=score,
      observed_at=_utc(observed_at),
      details=dict(details or {}),
  )
  db.add(sample)
  db.flush()
  return sample


def close_survey_point(db, survey_point_uid: str) -> BluetoothSurveyPoint:
  point = db.get(BluetoothSurveyPoint, survey_point_uid)
  if point is None:
    raise ValueError("survey point not found")
  point.state = "closed"
  point.updated_at = utcnow()
  db.flush()
  return point


def _active_calibration(db, anchor_uid: str) -> BluetoothCalibration | None:
  return db.scalar(
      select(BluetoothCalibration)
      .where(
          BluetoothCalibration.anchor_uid == anchor_uid,
          BluetoothCalibration.state == "active",
      )
      .order_by(BluetoothCalibration.calibration_revision.desc())
      .limit(1)
  )


def _robust_residual_summary(values: list[float]) -> dict[str, Any]:
  if not values:
    return {
        "sample_count": 0,
        "accepted_count": 0,
        "rejected_count": 0,
        "bias_m": None,
        "stddev_m": None,
        "median_m": None,
        "mad_m": None,
  }
  data = np.asarray(values, dtype=float)
  median = float(np.median(data))
  absolute = np.abs(data - median)
  mad = float(np.median(absolute))
  robust_sigma = max(1.4826 * mad, 0.02)
  threshold = max(0.25, 3.5 * robust_sigma)
  mask = absolute <= threshold
  accepted = data[mask]
  if accepted.size == 0:
    accepted = data
    mask = np.ones_like(data, dtype=bool)
  bias = float(np.median(accepted))
  stddev = float(np.std(accepted, ddof=1)) if accepted.size > 1 else robust_sigma
  return {
      "sample_count": int(data.size),
      "accepted_count": int(accepted.size),
      "rejected_count": int(data.size - accepted.size),
      "bias_m": bias,
      "stddev_m": max(stddev, 0.001),
      "median_m": median,
      "mad_m": mad,
      "outlier_threshold_m": threshold,
  }


def estimate_anchor_biases(db, scene_id: str) -> dict[str, dict[str, Any]]:
  points = {
      point.uid: point
      for point in db.scalars(
          select(BluetoothSurveyPoint).where(BluetoothSurveyPoint.scene_id == scene_id)
      ).all()
  }
  anchors = db.scalars(
      select(BluetoothAnchor).where(BluetoothAnchor.scene_id == scene_id)
  ).all()
  result: dict[str, dict[str, Any]] = {}
  for anchor in anchors:
    calibration = _active_calibration(db, anchor.uid)
    if calibration is None:
      result[anchor.uid] = {
          "anchor_id": anchor.uid,
          "status": "missing_active_calibration",
          **_robust_residual_summary([]),
      }
      continue
    residuals: list[float] = []
    by_point: dict[str, list[float]] = defaultdict(list)
    samples = db.scalars(
        select(BluetoothSurveySample)
        .where(BluetoothSurveySample.anchor_uid == anchor.uid)
        .order_by(BluetoothSurveySample.observed_at)
    ).all()
    for sample in samples:
      point = points.get(sample.survey_point_uid)
      if point is None:
        continue
      true_distance = math.dist(
          (calibration.x_m, calibration.y_m, calibration.z_m),
          (point.x_m, point.y_m, point.z_m),
      )
      residual = float(sample.distance_m) - true_distance
      residuals.append(residual)
      by_point[point.uid].append(residual)
    summary = _robust_residual_summary(residuals)
    result[anchor.uid] = {
        "anchor_id": anchor.uid,
        "status": "ok" if summary["accepted_count"] >= 3 else "insufficient_samples",
        "calibration_uid": calibration.uid,
        "calibration_revision": calibration.calibration_revision,
        **summary,
        "points": [
            {
                "survey_point_uid": point_uid,
                "sample_count": len(values),
                "median_residual_m": float(np.median(np.asarray(values, dtype=float))),
            }
            for point_uid, values in sorted(by_point.items())
        ],
    }
  return result


def create_bias_calibration_revisions(
    db,
    scene_id: str,
    actor: str,
    *,
    minimum_samples: int = 3,
) -> list[BluetoothCalibration]:
  estimates = estimate_anchor_biases(db, scene_id)
  created: list[BluetoothCalibration] = []
  for anchor_id, estimate in sorted(estimates.items()):
    if int(estimate.get("accepted_count") or 0) < minimum_samples:
      continue
    active = _active_calibration(db, anchor_id)
    if active is None:
      continue
    details = dict(active.details or {})
    details.update({
        "range_bias_m": float(estimate["bias_m"]),
        "range_stddev_m": float(estimate["stddev_m"]),
        "survey_sample_count": int(estimate["sample_count"]),
        "survey_accepted_count": int(estimate["accepted_count"]),
        "survey_rejected_count": int(estimate["rejected_count"]),
        "survey_source_calibration_uid": active.uid,
        "survey_estimator": "median-mad-v1",
    })
    created.append(
        create_calibration(
            db,
            {
                "anchor_uid": active.anchor_uid,
                "scene_id": active.scene_id,
                "x_m": active.x_m,
                "y_m": active.y_m,
                "z_m": active.z_m,
                "yaw_deg": active.yaw_deg,
                "pitch_deg": active.pitch_deg,
                "roll_deg": active.roll_deg,
                "z_source": active.z_source,
                "details": details,
            },
            actor,
        )
    )
  return created


def _gdop_2d(anchor_xyz: np.ndarray, point: np.ndarray, fixed_z_m: float) -> float | None:
  if anchor_xyz.shape[0] < 3:
    return None
  target = np.array([point[0], point[1], fixed_z_m], dtype=float)
  delta = target[None, :] - anchor_xyz
  ranges = np.linalg.norm(delta, axis=1)
  if np.any(ranges <= 1e-9):
    return 0.0
  h = delta[:, :2] / ranges[:, None]
  normal = h.T @ h
  try:
    condition = float(np.linalg.cond(normal))
    if not math.isfinite(condition) or condition > 1e10:
      return None
    return float(math.sqrt(max(0.0, float(np.trace(np.linalg.inv(normal))))))
  except np.linalg.LinAlgError:
    return None


def coverage_diagnostics(
    db,
    scene_id: str,
    *,
    min_x_m: float,
    max_x_m: float,
    min_y_m: float,
    max_y_m: float,
    step_m: float = 1.0,
    fixed_z_m: float = 1.0,
) -> dict[str, Any]:
  bounds = [_finite(v) for v in (min_x_m, max_x_m, min_y_m, max_y_m, step_m, fixed_z_m)]
  min_x, max_x, min_y, max_y, step, fixed_z = bounds
  if max_x <= min_x or max_y <= min_y:
    raise ValueError("coverage bounds are invalid")
  if step <= 0.0:
    raise ValueError("coverage step must be >0")
  calibrations = db.scalars(
      select(BluetoothCalibration)
      .where(
          BluetoothCalibration.scene_id == scene_id,
          BluetoothCalibration.state == "active",
      )
      .order_by(BluetoothCalibration.anchor_uid)
  ).all()
  anchor_xyz = np.asarray(
      [[row.x_m, row.y_m, row.z_m] for row in calibrations],
      dtype=float,
  )
  xs = np.arange(min_x, max_x + step * 0.5, step)
  ys = np.arange(min_y, max_y + step * 0.5, step)
  if len(xs) * len(ys) > 10_000:
    raise ValueError("coverage grid exceeds 10000 cells")
  theoretical = []
  for y in ys:
    for x in xs:
      gdop = _gdop_2d(anchor_xyz, np.asarray([x, y], dtype=float), fixed_z)
      state = (
          "unavailable"
          if gdop is None
          else "good"
          if gdop <= 2.5
          else "degraded"
          if gdop <= 5.0
          else "poor"
      )
      theoretical.append({
          "x_m": float(x),
          "y_m": float(y),
          "gdop": gdop,
          "geometry_state": state,
      })

  observed = []
  points = db.scalars(
      select(BluetoothSurveyPoint)
      .where(BluetoothSurveyPoint.scene_id == scene_id)
      .order_by(BluetoothSurveyPoint.uid)
  ).all()
  for point in points:
    samples = db.scalars(
        select(BluetoothSurveySample)
        .where(BluetoothSurveySample.survey_point_uid == point.uid)
    ).all()
    qualities = [float(sample.quality) for sample in samples]
    observed.append({
        "survey_point_uid": point.uid,
        "name": point.name,
        "position": [point.x_m, point.y_m, point.z_m],
        "sample_count": len(samples),
        "average_quality": (
            float(np.mean(np.asarray(qualities, dtype=float))) if qualities else None
        ),
    })
  return {
      "scene_id": scene_id,
      "theoretical_geometry": {
          "model": "2d-range-gdop",
          "fixed_z_m": fixed_z,
          "anchor_count": len(calibrations),
          "cells": theoretical,
      },
      "observed_rf": {
          "source": "survey_samples",
          "points": observed,
      },
  }
