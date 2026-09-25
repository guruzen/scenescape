# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import math
from itertools import combinations
from typing import Any, Iterable

from sqlalchemy import select

from .bluetooth_domain import calibration_to_dict
from .database import BluetoothCalibration, Resource
from .hierarchy import transform_dict


def latest_calibrations(rows: Iterable[BluetoothCalibration]) -> list[BluetoothCalibration]:
  """Return the newest non-retired calibration for each anchor.

  A newer draft intentionally supersedes the currently active revision in the
  geometry preview so installers can evaluate a planned layout before publish.
  """
  latest: dict[str, BluetoothCalibration] = {}
  for row in rows:
    if row.state == "retired":
      continue
    current = latest.get(row.anchor_uid)
    if current is None or row.calibration_revision > current.calibration_revision:
      latest[row.anchor_uid] = row
  return sorted(latest.values(), key=lambda row: row.anchor_uid)


def geometry_report(rows: Iterable[BluetoothCalibration]) -> dict[str, Any]:
  selected = latest_calibrations(rows)
  positions = {
      row.anchor_uid: (float(row.x_m), float(row.y_m), float(row.z_m))
      for row in selected
  }
  warnings: list[dict[str, Any]] = []
  count = len(selected)

  if count < 3:
    warnings.append({
        "code": "insufficient_anchors",
        "severity": "error",
        "anchor_uids": sorted(positions),
        "message": "At least three distinct anchor positions are required for a 2D solve.",
    })
  elif count == 3:
    warnings.append({
        "code": "limited_redundancy",
        "severity": "warning",
        "anchor_uids": sorted(positions),
        "message": "Three anchors can solve 2D position but provide no redundancy; four or more are preferred.",
    })

  max_span = 0.0
  items = sorted(positions.items())
  for (left_id, left), (right_id, right) in combinations(items, 2):
    dx = left[0] - right[0]
    dy = left[1] - right[1]
    horizontal = math.hypot(dx, dy)
    max_span = max(max_span, horizontal)
    if horizontal < 0.05:
      warnings.append({
          "code": "duplicate_anchor_location",
          "severity": "error",
          "anchor_uids": [left_id, right_id],
          "distance_m": round(horizontal, 4),
          "message": "Two anchors occupy effectively the same horizontal location.",
      })
    elif horizontal < 0.5:
      warnings.append({
          "code": "near_duplicate_anchor_location",
          "severity": "warning",
          "anchor_uids": [left_id, right_id],
          "distance_m": round(horizontal, 4),
          "message": "Two anchors are very close together and contribute weak geometric diversity.",
      })

  spread_ratio = 0.0
  if count >= 3 and max_span > 1e-9:
    max_cross = 0.0
    for (_, a), (_, b), (_, c) in combinations(items, 3):
      cross = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
      max_cross = max(max_cross, cross)
    spread_ratio = max_cross / (max_span * max_span)
    if spread_ratio < 0.03:
      warnings.append({
          "code": "collinear_geometry",
          "severity": "warning",
          "anchor_uids": sorted(positions),
          "spread_ratio": round(spread_ratio, 6),
          "message": "Anchor geometry is nearly collinear; move at least one anchor away from the dominant line.",
      })

  return {
      "anchor_count": count,
      "basis": "latest_draft_or_active",
      "max_span_m": round(max_span, 4),
      "spread_ratio": round(spread_ratio, 6),
      "warnings": warnings,
      "ready_for_2d": count >= 3 and not any(
          warning["severity"] == "error" for warning in warnings
      ),
  }


def _rotate_xyz(
    point: tuple[float, float, float],
    rotation_deg: list[float],
) -> tuple[float, float, float]:
  """Apply the hierarchy XYZ Euler convention to a local point."""
  x, y, z = point
  rx, ry, rz = (math.radians(float(value)) for value in rotation_deg)

  cx, sx = math.cos(rx), math.sin(rx)
  cy, sy = math.cos(ry), math.sin(ry)
  cz, sz = math.cos(rz), math.sin(rz)

  y, z = y * cx - z * sx, y * sx + z * cx
  x, z = x * cy + z * sy, -x * sy + z * cy
  x, y = x * cz - y * sz, x * sz + y * cz
  return x, y, z


def parent_projection(
    db,
    scene_id: str,
    position: dict[str, float],
) -> dict[str, Any] | None:
  """Project a child-scene local metre point into its immediate parent.

  Stored calibration coordinates remain local to the selected scene. This
  projection is informational provenance for operators and later solvers that
  deliberately work in the parent frame.
  """
  links = db.scalars(select(Resource).where(Resource.kind == "child")).all()
  link = next(
      (
          row
          for row in links
          if str((row.payload or {}).get("child") or "") == str(scene_id)
          and str((row.payload or {}).get("child_type") or "local") == "local"
      ),
      None,
  )
  if link is None:
    return None

  payload = link.payload or {}
  parent_scene_id = payload.get("parent") or payload.get("scene")
  if not parent_scene_id:
    return None

  pose = transform_dict(payload)
  scale = [float(value) for value in pose.get("scale", [1.0, 1.0, 1.0])]
  point = (
      float(position["x_m"]) * scale[0],
      float(position["y_m"]) * scale[1],
      float(position["z_m"]) * scale[2],
  )
  rotated = _rotate_xyz(
      point,
      [float(value) for value in pose.get("rotation", [0.0, 0.0, 0.0])],
  )
  translation = [
      float(value) for value in pose.get("translation", [0.0, 0.0, 0.0])
  ]
  projected = {
      "x_m": rotated[0] + translation[0],
      "y_m": rotated[1] + translation[1],
      "z_m": rotated[2] + translation[2],
  }
  return {
      "parent_scene_id": str(parent_scene_id),
      "position": projected,
      "transform": pose,
  }


def calibration_public(db, row: BluetoothCalibration) -> dict[str, Any]:
  value = calibration_to_dict(row)
  value["coordinate_frame"] = "scene_local_m"
  value["parent_projection"] = parent_projection(
      db,
      row.scene_id,
      value["position"],
  )
  return value
