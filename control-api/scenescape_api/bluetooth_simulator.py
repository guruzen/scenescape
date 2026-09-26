# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Deterministic Bluetooth positioning simulator for BT-05.

The simulator deliberately keeps ground truth in a separate result collection.
Only normalized provider-like measurement envelopes are exposed to downstream
ingestion/playback consumers.
"""

from __future__ import annotations

import json
import math
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SIMULATOR_VERSION = "1"
SCHEMA_VERSION = "1.0"


class SimulatorModel(BaseModel):
  model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Position3D(SimulatorModel):
  x_m: float
  y_m: float
  z_m: float

  @field_validator("x_m", "y_m", "z_m")
  @classmethod
  def finite_coordinate(cls, value: float) -> float:
    value = float(value)
    if not math.isfinite(value):
      raise ValueError("coordinates must be finite")
    return value


class Waypoint(Position3D):
  t_s: float = Field(ge=0.0, allow_inf_nan=False)


class SimulatorAnchor(Position3D):
  anchor_id: str = Field(min_length=1, max_length=96)
  bias_m: float = Field(default=0.0, allow_inf_nan=False)


class SimulatorTag(SimulatorModel):
  tag_id: str = Field(min_length=1, max_length=96)
  trajectory: list[Waypoint] = Field(min_length=1)
  battery_start_percent: float = Field(default=100.0, ge=0.0, le=100.0, allow_inf_nan=False)
  battery_drain_percent_per_hour: float = Field(default=0.5, ge=0.0, allow_inf_nan=False)

  @model_validator(mode="after")
  def trajectory_is_strictly_ordered(self):
    times = [point.t_s for point in self.trajectory]
    if times[0] != 0.0:
      raise ValueError("trajectory must start at t_s=0")
    if any(right <= left for left, right in zip(times, times[1:])):
      raise ValueError("trajectory waypoint times must be strictly increasing")
    return self


class OutageWindow(SimulatorModel):
  anchor_id: str = Field(min_length=1, max_length=96)
  start_s: float = Field(ge=0.0, allow_inf_nan=False)
  end_s: float = Field(gt=0.0, allow_inf_nan=False)

  @model_validator(mode="after")
  def interval_is_valid(self):
    if self.end_s <= self.start_s:
      raise ValueError("outage end_s must be later than start_s")
    return self


class SimulatorFaults(SimulatorModel):
  noise_stddev_m: float = Field(default=0.05, ge=0.0, allow_inf_nan=False)
  nlos_probability: float = Field(default=0.0, ge=0.0, le=1.0, allow_inf_nan=False)
  nlos_bias_m: float = Field(default=0.8, ge=0.0, allow_inf_nan=False)
  outlier_probability: float = Field(default=0.0, ge=0.0, le=1.0, allow_inf_nan=False)
  outlier_bias_m: float = Field(default=3.0, ge=0.0, allow_inf_nan=False)
  packet_loss_probability: float = Field(default=0.0, ge=0.0, le=1.0, allow_inf_nan=False)
  jitter_stddev_s: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
  out_of_order_probability: float = Field(default=0.0, ge=0.0, le=1.0, allow_inf_nan=False)
  outage_windows: list[OutageWindow] = Field(default_factory=list)


class SimulatorScenario(SimulatorModel):
  name: str = Field(min_length=1, max_length=160)
  scene_id: str = Field(min_length=1, max_length=96)
  provider_id: str = Field(default="bt-simulator", min_length=1, max_length=96)
  session_id: str = Field(default="sim-session", min_length=1, max_length=96)
  seed: int = 1
  method: Literal["channel_sounding", "aoa", "rssi"] = "channel_sounding"
  start_time: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)
  duration_s: float = Field(gt=0.0, allow_inf_nan=False)
  step_s: float = Field(gt=0.0, allow_inf_nan=False)
  mode: Literal["batch", "realtime", "accelerated"] = "batch"
  speed: float = Field(default=1.0, gt=0.0, allow_inf_nan=False)
  anchors: list[SimulatorAnchor] = Field(min_length=1)
  tags: list[SimulatorTag] = Field(min_length=1)
  faults: SimulatorFaults = Field(default_factory=SimulatorFaults)

  @field_validator("start_time")
  @classmethod
  def normalize_start_time(cls, value: datetime) -> datetime:
    if value.tzinfo is None:
      return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

  @model_validator(mode="after")
  def scenario_is_coherent(self):
    anchor_ids = [anchor.anchor_id for anchor in self.anchors]
    tag_ids = [tag.tag_id for tag in self.tags]
    if len(set(anchor_ids)) != len(anchor_ids):
      raise ValueError("anchor IDs must be unique")
    if len(set(tag_ids)) != len(tag_ids):
      raise ValueError("tag IDs must be unique")
    if any(tag.trajectory[-1].t_s < self.duration_s for tag in self.tags):
      raise ValueError("every tag trajectory must cover duration_s")
    unknown = sorted({
        outage.anchor_id
        for outage in self.faults.outage_windows
        if outage.anchor_id not in set(anchor_ids)
    })
    if unknown:
      raise ValueError(f"outage_windows reference unknown anchors: {unknown}")
    if self.mode == "realtime" and self.speed != 1.0:
      raise ValueError("realtime mode requires speed=1")
    return self


@dataclass(frozen=True)
class SimulationResult:
  measurements: list[dict[str, Any]]
  truth: list[dict[str, Any]]
  telemetry: list[dict[str, Any]]


def _iso(value: datetime) -> str:
  return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _clamp(value: float, low: float, high: float) -> float:
  return max(low, min(high, value))


def interpolate_trajectory(tag: SimulatorTag, t_s: float) -> Position3D:
  """Linearly interpolate a tag trajectory at a scenario-relative time."""
  if t_s <= 0.0:
    first = tag.trajectory[0]
    return Position3D(x_m=first.x_m, y_m=first.y_m, z_m=first.z_m)
  if t_s >= tag.trajectory[-1].t_s:
    last = tag.trajectory[-1]
    return Position3D(x_m=last.x_m, y_m=last.y_m, z_m=last.z_m)

  for left, right in zip(tag.trajectory, tag.trajectory[1:]):
    if left.t_s <= t_s <= right.t_s:
      fraction = (t_s - left.t_s) / (right.t_s - left.t_s)
      return Position3D(
          x_m=left.x_m + (right.x_m - left.x_m) * fraction,
          y_m=left.y_m + (right.y_m - left.y_m) * fraction,
          z_m=left.z_m + (right.z_m - left.z_m) * fraction,
      )
  raise ValueError("trajectory interpolation failed")


def _is_outage(faults: SimulatorFaults, anchor_id: str, t_s: float) -> bool:
  return any(
      window.anchor_id == anchor_id and window.start_s <= t_s < window.end_s
      for window in faults.outage_windows
  )


def _battery_status(percent: float) -> str:
  if percent <= 10.0:
    return "critical"
  if percent <= 20.0:
    return "low"
  return "normal"


def _battery_percent(tag: SimulatorTag, t_s: float) -> float:
  drained = tag.battery_drain_percent_per_hour * (t_s / 3600.0)
  return round(_clamp(tag.battery_start_percent - drained, 0.0, 100.0), 3)


def _time_steps(duration_s: float, step_s: float) -> list[float]:
  count = int(math.floor(duration_s / step_s))
  values = [round(index * step_s, 9) for index in range(count + 1)]
  if not math.isclose(values[-1], duration_s, abs_tol=1e-9):
    values.append(float(duration_s))
  return values


def _range_envelope(
    scenario: SimulatorScenario,
    anchor: SimulatorAnchor,
    tag: SimulatorTag,
    position: Position3D,
    t_s: float,
    rng: random.Random,
    sequence: int,
) -> dict[str, Any] | None:
  faults = scenario.faults
  if _is_outage(faults, anchor.anchor_id, t_s):
    return None
  if rng.random() < faults.packet_loss_probability:
    return None

  dx = position.x_m - anchor.x_m
  dy = position.y_m - anchor.y_m
  dz = position.z_m - anchor.z_m
  ideal_distance = math.sqrt(dx * dx + dy * dy + dz * dz)

  nlos = rng.random() < faults.nlos_probability
  outlier = rng.random() < faults.outlier_probability
  noise = rng.gauss(0.0, faults.noise_stddev_m) if faults.noise_stddev_m else 0.0
  distance = ideal_distance + anchor.bias_m + noise
  applied_faults: list[str] = []
  if nlos:
    distance += faults.nlos_bias_m
    applied_faults.append("nlos")
  if outlier:
    direction = -1.0 if rng.random() < 0.5 else 1.0
    distance += direction * faults.outlier_bias_m
    applied_faults.append("outlier")
  distance = max(0.0, distance)

  jitter = rng.gauss(0.0, faults.jitter_stddev_s) if faults.jitter_stddev_s else 0.0
  observed_at = scenario.start_time + timedelta(seconds=t_s + jitter)

  noise_penalty = min(abs(noise) / max(faults.noise_stddev_m * 4.0, 0.1), 0.25)
  quality = 1.0 - noise_penalty - (0.35 if nlos else 0.0) - (0.50 if outlier else 0.0)
  stddev = max(faults.noise_stddev_m, 0.001)
  if nlos:
    stddev = max(stddev, faults.nlos_bias_m / 2.0)
  if outlier:
    stddev = max(stddev, faults.outlier_bias_m / 2.0)

  payload = {
      "schema_version": SCHEMA_VERSION,
      "provider_id": scenario.provider_id,
      "session_id": scenario.session_id,
      "sequence": sequence,
      "source_timestamp": _iso(observed_at),
      "method": scenario.method,
      "distance_m": round(distance, 6),
      "distance_stddev_m": round(stddev, 6),
      "rssi_dbm": None,
      "azimuth_deg": None,
      "elevation_deg": None,
      "nlos_probability": 0.95 if nlos else 0.05,
      "quality": round(_clamp(quality, 0.01, 1.0), 4),
      "provider_details": {
          "synthetic": True,
          "simulator_version": SIMULATOR_VERSION,
          "faults": applied_faults,
      },
  }
  return {
      "scene_id": scenario.scene_id,
      "anchor_id": anchor.anchor_id,
      "tag_id": tag.tag_id,
      "payload": payload,
  }


def simulate(scenario: SimulatorScenario) -> SimulationResult:
  """Generate deterministic measurement, truth and device-telemetry streams."""
  rng = random.Random(scenario.seed)
  measurements: list[dict[str, Any]] = []
  truth: list[dict[str, Any]] = []
  telemetry: list[dict[str, Any]] = []
  sequence = 0

  for t_s in _time_steps(scenario.duration_s, scenario.step_s):
    for tag in scenario.tags:
      position = interpolate_trajectory(tag, t_s)
      observed_at = scenario.start_time + timedelta(seconds=t_s)
      truth.append({
          "schema_version": SCHEMA_VERSION,
          "scene_id": scenario.scene_id,
          "tag_id": tag.tag_id,
          "source_timestamp": _iso(observed_at),
          "position": position.model_dump(),
          "synthetic": True,
          "simulator_version": SIMULATOR_VERSION,
      })
      battery_percent = _battery_percent(tag, t_s)
      telemetry.append({
          "scene_id": scenario.scene_id,
          "device_id": tag.tag_id,
          "topic": f"scenescape/data/bluetooth/device/{scenario.scene_id}/{tag.tag_id}",
          "payload": {
              "schema_version": SCHEMA_VERSION,
              "provider_id": scenario.provider_id,
              "source_timestamp": _iso(observed_at),
              "device_type": "tag",
              "device_id": tag.tag_id,
              "last_seen_at": _iso(observed_at),
              "battery": {
                  "percent": battery_percent,
                  "status": _battery_status(battery_percent),
                  "source": "simulator",
                  "observed_at": _iso(observed_at),
              },
              "synthetic": True,
          },
      })
      for anchor in scenario.anchors:
        sequence += 1
        envelope = _range_envelope(
            scenario,
            anchor,
            tag,
            position,
            t_s,
            rng,
            sequence,
        )
        if envelope is not None:
          measurements.append(envelope)

  # Deliberately perturb delivery order after values are generated. Sequence and
  # source timestamps remain provider truth, allowing BT-06 to test reordering.
  if scenario.faults.out_of_order_probability:
    order_rng = random.Random(scenario.seed ^ 0xB105)
    index = 1
    while index < len(measurements):
      if order_rng.random() < scenario.faults.out_of_order_probability:
        measurements[index - 1], measurements[index] = measurements[index], measurements[index - 1]
        index += 2
      else:
        index += 1

  return SimulationResult(measurements=measurements, truth=truth, telemetry=telemetry)


def play_measurements(
    scenario: SimulatorScenario,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Iterator[dict[str, Any]]:
  """Yield measurements in delivery order, optionally respecting simulated time."""
  result = simulate(scenario)
  if scenario.mode == "batch":
    yield from result.measurements
    return

  speed = scenario.speed if scenario.mode == "accelerated" else 1.0
  previous: datetime | None = None
  for envelope in result.measurements:
    stamp = datetime.fromisoformat(envelope["payload"]["source_timestamp"].replace("Z", "+00:00"))
    if previous is not None:
      delay = max(0.0, (stamp - previous).total_seconds()) / speed
      if delay:
        sleep_fn(delay)
    previous = stamp
    yield envelope


def assert_simulator_runtime_allowed(env: Mapping[str, str] | None = None) -> None:
  """Fail closed unless the simulator is explicitly enabled outside production."""
  values = os.environ if env is None else env
  deployment = values.get("SCENESCAPE_ENV", "").strip().lower()
  if deployment in {"prod", "production"}:
    raise RuntimeError("Bluetooth simulator is disabled in production")
  enabled = values.get("SCENESCAPE_ENABLE_BLUETOOTH_SIMULATOR", "").strip().lower()
  if enabled not in {"1", "true", "yes", "on"}:
    raise RuntimeError(
        "Bluetooth simulator requires SCENESCAPE_ENABLE_BLUETOOTH_SIMULATOR=1"
    )


def scenario_from_dict(value: Mapping[str, Any]) -> SimulatorScenario:
  return SimulatorScenario.model_validate(dict(value))


def load_scenario_bundle(
    path: str | Path,
    env: Mapping[str, str] | None = None,
) -> list[SimulatorScenario]:
  """Load validated JSON scenarios after applying the explicit runtime guard."""
  assert_simulator_runtime_allowed(env)
  raw = json.loads(Path(path).read_text(encoding="utf-8"))
  if raw.get("schema_version") != SCHEMA_VERSION:
    raise ValueError(f"unsupported simulator scenario schema_version: {raw.get('schema_version')!r}")
  scenarios = raw.get("scenarios")
  if not isinstance(scenarios, list) or not scenarios:
    raise ValueError("scenario bundle must contain a non-empty scenarios list")
  return [scenario_from_dict(item) for item in scenarios]
