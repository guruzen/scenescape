# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""End-to-end Bluetooth measurement -> solve -> track -> scene/event pipeline."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy import select

from .bluetooth_ingest import solver_buffer
from .bluetooth_operations import BluetoothSpatialAdapter
from .bluetooth_positioning import SolverConfig, solve_latest
from .bluetooth_tracking import BluetoothTracker, TrackerConfig, persist_tracked_position
from .database import (
    BluetoothAssignment,
    BluetoothCalibration,
    BluetoothMeasurement,
)


_tracker = BluetoothTracker(
    TrackerConfig(
        max_tracks=max(1, int(os.getenv("BLUETOOTH_TRACKER_MAX_TRACKS", "10000"))),
        prediction_horizon_s=max(
            0.1,
            float(os.getenv("BLUETOOTH_TRACKER_PREDICTION_HORIZON_S", "2")),
        ),
        stale_horizon_s=max(
            0.2,
            float(os.getenv("BLUETOOTH_TRACKER_STALE_HORIZON_S", "5")),
        ),
    )
)
_spatial = BluetoothSpatialAdapter()
metrics = {
    "measurements_processed": 0,
    "raw_solves": 0,
    "tracked_positions": 0,
    "spatial_events": 0,
    "errors": 0,
}


def _enabled(name: str, default: str = "1") -> bool:
  return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def calibration_revision_token(db, scene_id: str) -> str:
  rows = db.scalars(
      select(BluetoothCalibration)
      .where(
          BluetoothCalibration.scene_id == scene_id,
          BluetoothCalibration.state == "active",
      )
      .order_by(BluetoothCalibration.anchor_uid)
  ).all()
  return "|".join(
      f"{row.anchor_uid}:{row.uid}:{row.calibration_revision}:{row.revision}"
      for row in rows
  )


def identity_revision_token(
    db,
    tag_id: str,
    at: datetime,
) -> str:
  row = db.scalar(
      select(BluetoothAssignment)
      .where(
          BluetoothAssignment.tag_uid == tag_id,
          BluetoothAssignment.valid_from <= at,
          (
              (BluetoothAssignment.valid_to.is_(None))
              | (BluetoothAssignment.valid_to > at)
          ),
      )
      .order_by(BluetoothAssignment.valid_from.desc())
      .limit(1)
  )
  if row is None:
    return f"tag:{tag_id}:unassigned"
  return f"assignment:{row.uid}:{row.revision}"


def process_measurement_id(
    db,
    measurement_id: int,
    *,
    solver_config: SolverConfig | None = None,
) -> dict[str, Any] | None:
  if not _enabled("BLUETOOTH_POSITIONING_ENABLED"):
    return None
  measurement = db.get(BluetoothMeasurement, int(measurement_id))
  if measurement is None:
    return None

  result, raw_row = solve_latest(
      db,
      measurement.scene_id,
      measurement.tag_uid,
      solver_config,
  )
  metrics["measurements_processed"] += 1
  metrics["raw_solves"] += 1

  calibration_revision = calibration_revision_token(db, measurement.scene_id)
  identity_revision = identity_revision_token(
      db,
      measurement.tag_uid,
      measurement.source_timestamp,
  )
  tracked = _tracker.update(
      measurement.scene_id,
      measurement.tag_uid,
      result,
      calibration_revision=calibration_revision,
      identity_revision=identity_revision,
  )
  tracked_row = persist_tracked_position(db, tracked)
  metrics["tracked_positions"] += 1

  events = []
  if _enabled("BLUETOOTH_SPATIAL_EVENTS_ENABLED", "1"):
    events = _spatial.process(db, tracked)
    metrics["spatial_events"] += len(events)

  return {
      "measurement_id": measurement.id,
      "raw_position_id": raw_row.id,
      "tracked_position_id": tracked_row.id,
      "state": tracked["quality"]["state"],
      "events": [event.id for event in events],
  }


def drain_solver_queue(
    db,
    *,
    maximum: int = 100,
    solver_config: SolverConfig | None = None,
) -> list[dict[str, Any]]:
  maximum = max(1, min(int(maximum), 10_000))
  results: list[dict[str, Any]] = []
  for _ in range(maximum):
    measurement_id = solver_buffer.take()
    if measurement_id is None:
      break
    try:
      result = process_measurement_id(
          db,
          measurement_id,
          solver_config=solver_config,
      )
      if result is not None:
        results.append(result)
    except Exception:
      metrics["errors"] += 1
      raise
  return results


def reset_runtime_state() -> None:
  _tracker.clear()
  _spatial.clear()
  for key in metrics:
    metrics[key] = 0


def runtime_diagnostics() -> dict[str, Any]:
  return {
      "pipeline": dict(metrics),
      "tracker": {
          "active_tracks": len(_tracker),
          "metrics": dict(_tracker.metrics),
      },
      "spatial": {
          "metrics": dict(_spatial.metrics),
      },
      "queue_depth": len(solver_buffer),
  }
