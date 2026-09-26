# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scene data-plane adapter for Bluetooth tracked positions (BT-09)."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any

from sqlalchemy import select

from .bluetooth_fusion import EntityFusionProvider, FusionConfig

from .database import (
    BluetoothAnchor,
    BluetoothAssignment,
    BluetoothCalibration,
    BluetoothTag,
    BluetoothTrackedPosition,
)


def _positioning_enabled() -> bool:
  return os.getenv("BLUETOOTH_POSITIONING_ENABLED", "1").strip().lower() in {
      "1",
      "true",
      "yes",
      "on",
  }


def _utc(value: datetime) -> datetime:
  if value.tzinfo is None:
    return value.replace(tzinfo=timezone.utc)
  return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
  return _utc(value).isoformat().replace("+00:00", "Z")


def _assignment_for_tag(db, tag_id: str, when: datetime) -> BluetoothAssignment | None:
  return db.scalar(
      select(BluetoothAssignment)
      .where(
          BluetoothAssignment.tag_uid == tag_id,
          BluetoothAssignment.valid_from <= when,
          (
              (BluetoothAssignment.valid_to.is_(None))
              | (BluetoothAssignment.valid_to > when)
          ),
      )
      .order_by(BluetoothAssignment.valid_from.desc())
      .limit(1)
  )


def _latest_tracks(db, scene_id: str) -> list[BluetoothTrackedPosition]:
  rows = db.scalars(
      select(BluetoothTrackedPosition)
      .where(BluetoothTrackedPosition.scene_id == scene_id)
      .order_by(
          BluetoothTrackedPosition.source_timestamp.desc(),
          BluetoothTrackedPosition.id.desc(),
      )
  ).all()
  latest: dict[str, BluetoothTrackedPosition] = {}
  for row in rows:
    latest.setdefault(row.tag_uid, row)
  return [latest[key] for key in sorted(latest)]


def bluetooth_object(
    db,
    row: BluetoothTrackedPosition,
    *,
    include_assignment_label: bool,
) -> dict[str, Any] | None:
  if row.x_m is None or row.y_m is None or row.z_m is None:
    return None
  if row.state == "unavailable":
    return None
  tag = db.get(BluetoothTag, row.tag_uid)
  if tag is None or tag.state in {"disabled", "retired"}:
    return None
  assignment = _assignment_for_tag(db, row.tag_uid, row.source_timestamp)
  entity_type = assignment.entity_type if assignment is not None else "tag"
  assignment_label = (
      assignment.display_name or assignment.entity_id
      if assignment is not None and include_assignment_label
      else None
  )
  label = assignment_label or row.tag_uid
  provenance = dict(row.provenance or {})
  return {
      "id": f"bt:{row.tag_uid}",
      "source": "bluetooth",
      "category": entity_type,
      "type": "bluetooth-tag",
      "label": label,
      "translation": [float(row.x_m), float(row.y_m), float(row.z_m)],
      "velocity": [
          float(row.vx_mps or 0.0),
          float(row.vy_mps or 0.0),
          float(row.vz_mps or 0.0),
      ],
      "tracking_radius": float(row.horizontal_uncertainty_m or 0.0),
      "timestamp": _iso(row.source_timestamp),
      "bluetooth": {
          "tag_id": row.tag_uid,
          "state": row.state,
          "predicted": bool(row.predicted),
          "method": row.method,
          "score": float(row.score),
          "anchors_used": int(row.anchors_used),
          "horizontal_uncertainty_m": row.horizontal_uncertainty_m,
          "vertical_uncertainty_m": row.vertical_uncertainty_m,
          "solver": {
              "name": row.solver_name,
              "version": row.solver_version,
          },
          "tracker": {
              "name": row.tracker_name,
              "version": row.tracker_version,
          },
          "calibration_revision": provenance.get("calibration_revision"),
          "identity_revision": provenance.get("identity_revision"),
          "last_measured_at": provenance.get("last_measured_at"),
          "anchor_ids": list(provenance.get("accepted_anchor_ids") or []),
          "assignment": (
              {
                  "entity_type": assignment.entity_type,
                  "entity_id": assignment.entity_id,
                  "display_name": assignment_label,
              }
              if assignment is not None
              else None
          ),
          "battery": {
              "percent": tag.battery_percent,
              "voltage_v": tag.battery_voltage_v,
              "status": tag.battery_status,
              "source": tag.battery_source,
              "observed_at": (
                  _iso(tag.battery_observed_at)
                  if tag.battery_observed_at is not None
                  else None
              ),
          },
      },
  }


def scene_bluetooth_objects(
    db,
    scene_id: str,
    *,
    include_assignment_label: bool,
) -> list[dict[str, Any]]:
  if not _positioning_enabled():
    return []
  objects: list[dict[str, Any]] = []
  for row in _latest_tracks(db, scene_id):
    value = bluetooth_object(
        db,
        row,
        include_assignment_label=include_assignment_label,
    )
    if value is not None:
      objects.append(value)
  return objects



_fusion_provider = EntityFusionProvider(
    FusionConfig(
        max_distance_m=max(0.1, float(os.getenv("BLUETOOTH_FUSION_MAX_DISTANCE_M", "1.5"))),
        max_time_delta_s=max(0.05, float(os.getenv("BLUETOOTH_FUSION_MAX_TIME_DELTA_S", "0.75"))),
        minimum_confidence=min(max(float(os.getenv("BLUETOOTH_FUSION_MIN_CONFIDENCE", "0.72")), 0.0), 1.0),
        ambiguity_margin=min(max(float(os.getenv("BLUETOOTH_FUSION_AMBIGUITY_MARGIN", "0.12")), 0.0), 1.0),
        retain_confidence=min(max(float(os.getenv("BLUETOOTH_FUSION_RETAIN_CONFIDENCE", "0.58")), 0.0), 1.0),
        split_distance_m=max(0.1, float(os.getenv("BLUETOOTH_FUSION_SPLIT_DISTANCE_M", "2.5"))),
    )
)


def _fusion_enabled() -> bool:
  return os.getenv("BLUETOOTH_FUSION_ENABLED", "").strip().lower() in {
      "1",
      "true",
      "yes",
      "on",
  }

def merge_live_payload(
    payload: dict[str, Any],
    bluetooth_objects: list[dict[str, Any]],
) -> dict[str, Any]:
  """Append BLE objects without mutating or normalizing the vision payload."""
  result = dict(payload)
  original = result.get("objects")
  if isinstance(original, list):
    vision_objects = list(original)
  elif original is None:
    vision_objects = []
  else:
    # Existing native normalization expects a list. Preserve malformed/non-list
    # source data separately rather than silently replacing it.
    vision_objects = []
    result["vision_objects_unparsed"] = original
  result["vision_objects"] = vision_objects
  result["bluetooth"] = {
      "objects": bluetooth_objects,
      "count": len(bluetooth_objects),
  }
  if _fusion_enabled() and vision_objects and bluetooth_objects:
    fused = _fusion_provider.fuse(vision_objects, bluetooth_objects)
    result["objects"] = fused["objects"]
    result["fusion"] = {
        "enabled": True,
        "fused": fused["fused"],
        "count": len(fused["fused"]),
        "metrics": fused["metrics"],
    }
  else:
    result["objects"] = [*vision_objects, *bluetooth_objects]
    result["fusion"] = {
        "enabled": False,
        "fused": [],
        "count": 0,
    }
  return result


def scene_bluetooth_anchors(db, scene_id: str) -> list[dict[str, Any]]:
  if not _positioning_enabled():
    return []
  anchors = db.scalars(
      select(BluetoothAnchor)
      .where(
          BluetoothAnchor.scene_id == scene_id,
          BluetoothAnchor.state.notin_(["retired"]),
      )
      .order_by(BluetoothAnchor.serial_number, BluetoothAnchor.uid)
  ).all()
  result: list[dict[str, Any]] = []
  for anchor in anchors:
    calibration = db.scalar(
        select(BluetoothCalibration)
        .where(
            BluetoothCalibration.anchor_uid == anchor.uid,
            BluetoothCalibration.scene_id == scene_id,
            BluetoothCalibration.state == "active",
        )
        .limit(1)
    )
    result.append({
        "id": anchor.uid,
        "serial_number": anchor.serial_number,
        "state": anchor.state,
        "translation": (
            [calibration.x_m, calibration.y_m, calibration.z_m]
            if calibration is not None
            else None
        ),
        "calibration_revision": (
            calibration.calibration_revision if calibration is not None else None
        ),
        "capabilities": list(anchor.capabilities or []),
    })
  return result


def bluetooth_history(
    db,
    scene_id: str,
    *,
    tag_id: str | None = None,
    state: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 500,
    include_assignment_label: bool = False,
) -> list[dict[str, Any]]:
  statement = select(BluetoothTrackedPosition).where(
      BluetoothTrackedPosition.scene_id == scene_id
  )
  if tag_id:
    statement = statement.where(BluetoothTrackedPosition.tag_uid == tag_id)
  if state:
    statement = statement.where(BluetoothTrackedPosition.state == state)
  if since is not None:
    statement = statement.where(
        BluetoothTrackedPosition.source_timestamp >= _utc(since)
    )
  if until is not None:
    statement = statement.where(
        BluetoothTrackedPosition.source_timestamp <= _utc(until)
    )
  rows = db.scalars(
      statement.order_by(
          BluetoothTrackedPosition.source_timestamp.desc(),
          BluetoothTrackedPosition.id.desc(),
      ).limit(limit)
  ).all()
  items: list[dict[str, Any]] = []
  for row in reversed(rows):
    value = bluetooth_object(
        db,
        row,
        include_assignment_label=include_assignment_label,
    )
    items.append({
        "id": row.id,
        "timestamp": _iso(row.source_timestamp),
        "tag_id": row.tag_uid,
        "state": row.state,
        "object": value,
      })
  return items
