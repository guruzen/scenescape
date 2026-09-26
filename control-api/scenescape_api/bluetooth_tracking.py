# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Quality-aware constant-velocity tracker for Bluetooth positions (BT-08)."""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np

from .database import BluetoothTrackedPosition

TRACKER_NAME = "cv-kalman"
TRACKER_VERSION = "1"


def _utc(value: datetime) -> datetime:
  if value.tzinfo is None:
    return value.replace(tzinfo=timezone.utc)
  return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class TrackerConfig:
  process_accel_std_mps2: float = 1.5
  default_measurement_std_m: float = 0.5
  prediction_horizon_s: float = 2.0
  stale_horizon_s: float = 5.0
  reset_gap_s: float = 8.0
  max_speed_mps: float = 15.0
  max_jump_margin_m: float = 2.0
  max_tracks: int = 10_000
  min_heading_speed_mps: float = 0.15


@dataclass
class TrackState:
  state: np.ndarray
  covariance: np.ndarray
  timestamp: datetime
  last_measured_at: datetime
  scene_id: str
  calibration_revision: str
  identity_revision: str
  last_quality: dict[str, Any]
  last_solver: dict[str, Any]
  last_method: str


def _transition(dt_s: float) -> np.ndarray:
  f = np.eye(6, dtype=float)
  f[0, 3] = dt_s
  f[1, 4] = dt_s
  f[2, 5] = dt_s
  return f


def _process_noise(dt_s: float, accel_std: float) -> np.ndarray:
  q = max(float(accel_std), 1e-6) ** 2
  block = np.array(
      [
          [dt_s**4 / 4.0, dt_s**3 / 2.0],
          [dt_s**3 / 2.0, dt_s**2],
      ],
      dtype=float,
  ) * q
  result = np.zeros((6, 6), dtype=float)
  for position_index, velocity_index in ((0, 3), (1, 4), (2, 5)):
    result[position_index, position_index] = block[0, 0]
    result[position_index, velocity_index] = block[0, 1]
    result[velocity_index, position_index] = block[1, 0]
    result[velocity_index, velocity_index] = block[1, 1]
  return result


def _measurement_covariance(raw: dict[str, Any], config: TrackerConfig) -> np.ndarray:
  quality = raw.get("quality") or {}
  horizontal = quality.get("horizontal_uncertainty_m")
  vertical = quality.get("vertical_uncertainty_m")
  if horizontal is None or not math.isfinite(float(horizontal)) or float(horizontal) <= 0.0:
    horizontal_std = config.default_measurement_std_m
  else:
    # Solver uncertainty is a 95% radius-like quantity. Convert conservatively
    # to per-axis standard deviation.
    horizontal_std = max(float(horizontal) / 1.96 / math.sqrt(2.0), 0.02)
  if vertical is None or not math.isfinite(float(vertical)) or float(vertical) <= 0.0:
    vertical_std = max(horizontal_std * 2.0, config.default_measurement_std_m)
  else:
    vertical_std = max(float(vertical) / 1.96, 0.02)
  return np.diag(
      [horizontal_std**2, horizontal_std**2, vertical_std**2]
  ).astype(float)


def _position_from_raw(raw: dict[str, Any]) -> np.ndarray | None:
  position = raw.get("position")
  if not isinstance(position, dict):
    return None
  values = [position.get("x_m"), position.get("y_m"), position.get("z_m")]
  try:
    numbers = np.array([float(value) for value in values], dtype=float)
  except (TypeError, ValueError):
    return None
  return numbers if np.all(np.isfinite(numbers)) else None


def _heading_deg(velocity: np.ndarray, min_speed_mps: float) -> float | None:
  horizontal_speed = math.hypot(float(velocity[0]), float(velocity[1]))
  if horizontal_speed < min_speed_mps:
    return None
  return (math.degrees(math.atan2(float(velocity[1]), float(velocity[0]))) + 360.0) % 360.0


def _covariance_uncertainty(covariance: np.ndarray) -> tuple[float, float]:
  horizontal = 1.96 * math.sqrt(
      max(0.0, float(covariance[0, 0] + covariance[1, 1]))
  )
  vertical = 1.96 * math.sqrt(max(0.0, float(covariance[2, 2])))
  return horizontal, vertical


class BluetoothTracker:
  """Bounded LRU tracker keyed by scene/tag.

  A caller supplies calibration_revision and identity_revision tokens. Any
  change resets the filter, preventing smoothing across calibration or tag
  assignment boundaries.
  """

  def __init__(self, config: TrackerConfig | None = None):
    self.config = config or TrackerConfig()
    if self.config.max_tracks < 1:
      raise ValueError("max_tracks must be >= 1")
    self._tracks: OrderedDict[tuple[str, str], TrackState] = OrderedDict()
    self.metrics = {
        "created": 0,
        "resets": 0,
        "evicted": 0,
        "out_of_order": 0,
        "jump_resets": 0,
        "predictions": 0,
        "stale": 0,
    }

  def clear(self) -> None:
    self._tracks.clear()

  def __len__(self) -> int:
    return len(self._tracks)

  def _remember(self, key: tuple[str, str], state: TrackState) -> None:
    self._tracks[key] = state
    self._tracks.move_to_end(key)
    while len(self._tracks) > self.config.max_tracks:
      self._tracks.popitem(last=False)
      self.metrics["evicted"] += 1

  def _new_track(
      self,
      scene_id: str,
      tag_id: str,
      raw: dict[str, Any],
      timestamp: datetime,
      calibration_revision: str,
      identity_revision: str,
      *,
      reason: str,
  ) -> dict[str, Any]:
    position = _position_from_raw(raw)
    if position is None:
      return self._unavailable(
          scene_id,
          tag_id,
          timestamp,
          raw,
          reason="no_measured_position",
      )
    measurement_covariance = _measurement_covariance(raw, self.config)
    covariance = np.zeros((6, 6), dtype=float)
    covariance[:3, :3] = measurement_covariance
    covariance[3:, 3:] = np.eye(3, dtype=float) * max(
        self.config.max_speed_mps / 3.0,
        1.0,
    ) ** 2
    state = np.zeros(6, dtype=float)
    state[:3] = position
    quality = dict(raw.get("quality") or {})
    track = TrackState(
        state=state,
        covariance=covariance,
        timestamp=timestamp,
        last_measured_at=timestamp,
        scene_id=scene_id,
        calibration_revision=str(calibration_revision),
        identity_revision=str(identity_revision),
        last_quality=quality,
        last_solver=dict(raw.get("solver") or {}),
        last_method=str(quality.get("method") or "unknown"),
    )
    self._remember((scene_id, tag_id), track)
    self.metrics["created"] += 1
    return self._render(
        scene_id,
        tag_id,
        track,
        timestamp,
        state_name=str(raw.get("state") or quality.get("state") or "degraded"),
        predicted=False,
        reason=reason,
        raw=raw,
    )

  def _predict_state(
      self,
      track: TrackState,
      timestamp: datetime,
  ) -> tuple[np.ndarray, np.ndarray, float]:
    dt_s = max(0.0, (timestamp - track.timestamp).total_seconds())
    transition = _transition(dt_s)
    state = transition @ track.state
    covariance = (
        transition @ track.covariance @ transition.T
        + _process_noise(dt_s, self.config.process_accel_std_mps2)
    )
    return state, covariance, dt_s

  def update(
      self,
      scene_id: str,
      tag_id: str,
      raw: dict[str, Any],
      *,
      calibration_revision: str = "",
      identity_revision: str = "",
  ) -> dict[str, Any]:
    timestamp_value = raw.get("source_timestamp")
    if not isinstance(timestamp_value, datetime):
      raise ValueError("raw source_timestamp must be a datetime")
    timestamp = _utc(timestamp_value)
    key = (str(scene_id), str(tag_id))
    track = self._tracks.get(key)
    measured_position = _position_from_raw(raw)
    measured_state = str(raw.get("state") or (raw.get("quality") or {}).get("state") or "unavailable")

    if track is None:
      if measured_position is None or measured_state == "unavailable":
        return self._unavailable(scene_id, tag_id, timestamp, raw, reason="no_track")
      return self._new_track(
          scene_id,
          tag_id,
          raw,
          timestamp,
          calibration_revision,
          identity_revision,
          reason="track_created",
      )

    if timestamp <= track.timestamp:
      self.metrics["out_of_order"] += 1
      return self._render(
          scene_id,
          tag_id,
          track,
          track.timestamp,
          state_name="degraded",
          predicted=False,
          reason="out_of_order_ignored",
          raw=raw,
      )

    gap_s = (timestamp - track.timestamp).total_seconds()
    reset_reason: str | None = None
    if str(calibration_revision) != track.calibration_revision:
      reset_reason = "calibration_revision_changed"
    elif str(identity_revision) != track.identity_revision:
      reset_reason = "identity_revision_changed"
    elif gap_s > self.config.reset_gap_s and measured_position is not None:
      reset_reason = "long_gap"

    if reset_reason is not None:
      self.metrics["resets"] += 1
      return self._new_track(
          scene_id,
          tag_id,
          raw,
          timestamp,
          calibration_revision,
          identity_revision,
          reason=reset_reason,
      )

    predicted_state, predicted_covariance, dt_s = self._predict_state(track, timestamp)

    if measured_position is None or measured_state == "unavailable":
      age_s = (timestamp - track.last_measured_at).total_seconds()
      track.state = predicted_state
      track.covariance = predicted_covariance
      track.timestamp = timestamp
      self._remember(key, track)
      if age_s <= self.config.prediction_horizon_s:
        self.metrics["predictions"] += 1
        return self._render(
            scene_id,
            tag_id,
            track,
            timestamp,
            state_name="predicted",
            predicted=True,
            reason="measurement_dropout",
            raw=raw,
        )
      if age_s <= self.config.stale_horizon_s:
        self.metrics["stale"] += 1
        return self._render(
            scene_id,
            tag_id,
            track,
            timestamp,
            state_name="stale",
            predicted=True,
            reason="prediction_expired",
            raw=raw,
        )
      self._tracks.pop(key, None)
      return self._unavailable(
          scene_id,
          tag_id,
          timestamp,
          raw,
          reason="stale_expired",
      )

    predicted_position = predicted_state[:3]
    jump_m = float(np.linalg.norm(measured_position - predicted_position))
    allowed_jump = (
        self.config.max_jump_margin_m
        + self.config.max_speed_mps * max(dt_s, 0.0)
    )
    if jump_m > allowed_jump:
      self.metrics["resets"] += 1
      self.metrics["jump_resets"] += 1
      return self._new_track(
          scene_id,
          tag_id,
          raw,
          timestamp,
          calibration_revision,
          identity_revision,
          reason="impossible_jump_reset",
      )

    measurement_covariance = _measurement_covariance(raw, self.config)
    h = np.zeros((3, 6), dtype=float)
    h[0, 0] = 1.0
    h[1, 1] = 1.0
    h[2, 2] = 1.0
    innovation = measured_position - h @ predicted_state
    innovation_covariance = h @ predicted_covariance @ h.T + measurement_covariance
    try:
      gain = (
          predicted_covariance
          @ h.T
          @ np.linalg.inv(innovation_covariance)
      )
    except np.linalg.LinAlgError:
      self.metrics["resets"] += 1
      return self._new_track(
          scene_id,
          tag_id,
          raw,
          timestamp,
          calibration_revision,
          identity_revision,
          reason="covariance_reset",
      )
    updated_state = predicted_state + gain @ innovation
    identity = np.eye(6, dtype=float)
    # Joseph stabilized covariance update keeps covariance positive semidefinite.
    kh = gain @ h
    updated_covariance = (
        (identity - kh)
        @ predicted_covariance
        @ (identity - kh).T
        + gain @ measurement_covariance @ gain.T
    )
    if not np.all(np.isfinite(updated_state)) or not np.all(np.isfinite(updated_covariance)):
      self.metrics["resets"] += 1
      return self._new_track(
          scene_id,
          tag_id,
          raw,
          timestamp,
          calibration_revision,
          identity_revision,
          reason="non_finite_filter_reset",
      )

    track.state = updated_state
    track.covariance = updated_covariance
    track.timestamp = timestamp
    track.last_measured_at = timestamp
    track.calibration_revision = str(calibration_revision)
    track.identity_revision = str(identity_revision)
    track.last_quality = dict(raw.get("quality") or {})
    track.last_solver = dict(raw.get("solver") or {})
    track.last_method = str(track.last_quality.get("method") or "unknown")
    self._remember(key, track)
    output_state = "good" if measured_state == "good" else "degraded"
    return self._render(
        scene_id,
        tag_id,
        track,
        timestamp,
        state_name=output_state,
        predicted=False,
        reason="measurement_update",
        raw=raw,
    )

  def predict(
      self,
      scene_id: str,
      tag_id: str,
      timestamp: datetime,
  ) -> dict[str, Any]:
    key = (str(scene_id), str(tag_id))
    track = self._tracks.get(key)
    timestamp = _utc(timestamp)
    synthetic_raw = {
        "state": "unavailable",
        "source_timestamp": timestamp,
        "quality": track.last_quality if track is not None else {},
        "solver": track.last_solver if track is not None else {},
    }
    return self.update(
        scene_id,
        tag_id,
        synthetic_raw,
        calibration_revision=track.calibration_revision if track else "",
        identity_revision=track.identity_revision if track else "",
    )

  def _render(
      self,
      scene_id: str,
      tag_id: str,
      track: TrackState,
      timestamp: datetime,
      *,
      state_name: str,
      predicted: bool,
      reason: str,
      raw: dict[str, Any],
  ) -> dict[str, Any]:
    horizontal_uncertainty, vertical_uncertainty = _covariance_uncertainty(track.covariance)
    velocity = track.state[3:6]
    quality = dict(track.last_quality)
    raw_quality = raw.get("quality") or {}
    score = float(raw_quality.get("score", quality.get("score", 0.0)) or 0.0)
    if predicted:
      measured_age = max(0.0, (timestamp - track.last_measured_at).total_seconds())
      score *= math.exp(-measured_age / max(self.config.prediction_horizon_s, 0.1))
    if state_name == "stale":
      score = min(score, 0.2)
    return {
        "schema_version": "1.0",
        "source_timestamp": timestamp,
        "tag_id": str(tag_id),
        "scene_id": str(scene_id),
        "position": {
            "x_m": float(track.state[0]),
            "y_m": float(track.state[1]),
            "z_m": float(track.state[2]),
        },
        "velocity": {
            "vx_mps": float(velocity[0]),
            "vy_mps": float(velocity[1]),
            "vz_mps": float(velocity[2]),
        },
        "heading_deg": _heading_deg(velocity, self.config.min_heading_speed_mps),
        "quality": {
            "state": state_name,
            "horizontal_uncertainty_m": horizontal_uncertainty,
            "vertical_uncertainty_m": vertical_uncertainty,
            "score": max(0.0, min(score, 1.0)),
            "anchors_visible": int(raw_quality.get("anchors_visible", quality.get("anchors_visible", 0)) or 0),
            "anchors_used": int(raw_quality.get("anchors_used", quality.get("anchors_used", 0)) or 0),
            "residual_rms_m": raw_quality.get("residual_rms_m", quality.get("residual_rms_m")),
            "gdop": raw_quality.get("gdop", quality.get("gdop")),
            "method": str(raw_quality.get("method", track.last_method) or "unknown"),
        },
        "solver": dict(track.last_solver),
        "tracker": {
            "name": TRACKER_NAME,
            "version": TRACKER_VERSION,
            "predicted": bool(predicted),
        },
        "provenance": {
            "reason": reason,
            "calibration_revision": track.calibration_revision,
            "identity_revision": track.identity_revision,
            "last_measured_at": track.last_measured_at,
        },
    }

  def _unavailable(
      self,
      scene_id: str,
      tag_id: str,
      timestamp: datetime,
      raw: dict[str, Any],
      *,
      reason: str,
  ) -> dict[str, Any]:
    quality = dict(raw.get("quality") or {})
    return {
        "schema_version": "1.0",
        "source_timestamp": timestamp,
        "tag_id": str(tag_id),
        "scene_id": str(scene_id),
        "position": None,
        "velocity": None,
        "heading_deg": None,
        "quality": {
            "state": "unavailable",
            "horizontal_uncertainty_m": None,
            "vertical_uncertainty_m": None,
            "score": 0.0,
            "anchors_visible": int(quality.get("anchors_visible") or 0),
            "anchors_used": 0,
            "residual_rms_m": quality.get("residual_rms_m"),
            "gdop": quality.get("gdop"),
            "method": str(quality.get("method") or "unknown"),
        },
        "solver": dict(raw.get("solver") or {}),
        "tracker": {
            "name": TRACKER_NAME,
            "version": TRACKER_VERSION,
            "predicted": False,
        },
        "provenance": {"reason": reason},
    }


def persist_tracked_position(
    db,
    tracked: dict[str, Any],
) -> BluetoothTrackedPosition:
  quality = tracked.get("quality") or {}
  position = tracked.get("position") or {}
  velocity = tracked.get("velocity") or {}
  solver = tracked.get("solver") or {}
  tracker = tracked.get("tracker") or {}
  row = BluetoothTrackedPosition(
      scene_id=str(tracked["scene_id"]),
      tag_uid=str(tracked["tag_id"]),
      source_timestamp=_utc(tracked["source_timestamp"]),
      x_m=position.get("x_m"),
      y_m=position.get("y_m"),
      z_m=position.get("z_m"),
      vx_mps=velocity.get("vx_mps"),
      vy_mps=velocity.get("vy_mps"),
      vz_mps=velocity.get("vz_mps"),
      heading_deg=tracked.get("heading_deg"),
      state=str(quality.get("state") or "unavailable"),
      predicted=bool(tracker.get("predicted")),
      horizontal_uncertainty_m=quality.get("horizontal_uncertainty_m"),
      vertical_uncertainty_m=quality.get("vertical_uncertainty_m"),
      score=float(quality.get("score") or 0.0),
      anchors_used=int(quality.get("anchors_used") or 0),
      method=str(quality.get("method") or "unknown"),
      solver_name=str(solver.get("name") or "unknown"),
      solver_version=str(solver.get("version") or "unknown"),
      tracker_name=str(tracker.get("name") or TRACKER_NAME),
      tracker_version=str(tracker.get("version") or TRACKER_VERSION),
      provenance=dict(tracked.get("provenance") or {}),
  )
  db.add(row)
  db.flush()
  return row
