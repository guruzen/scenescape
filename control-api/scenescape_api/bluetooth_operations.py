# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Quality-gated Bluetooth spatial events and operational health (BT-14)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from sqlalchemy import func, select

from .database import (
    BluetoothAnchor,
    BluetoothDeviceTelemetry,
    BluetoothProvider,
    BluetoothRawPosition,
    BluetoothTag,
    BluetoothTrackedPosition,
    Resource,
    utcnow,
)
from .ingest import persist


def _utc(value: datetime | str) -> datetime:
  if isinstance(value, str):
    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
  if value.tzinfo is None:
    return value.replace(tzinfo=timezone.utc)
  return value.astimezone(timezone.utc)


def _scene_id(resource: Resource) -> str:
  payload = resource.payload or {}
  return str(payload.get("scene_id") or payload.get("scene") or "")


def _points(resource: Resource) -> list[tuple[float, float]]:
  raw = (resource.payload or {}).get("points")
  result: list[tuple[float, float]] = []
  if not isinstance(raw, list):
    return result
  for value in raw:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
      continue
    try:
      x, y = float(value[0]), float(value[1])
    except (TypeError, ValueError):
      continue
    if math.isfinite(x) and math.isfinite(y):
      result.append((x, y))
  return result


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
  if len(polygon) < 3:
    return False
  x, y = point
  inside = False
  j = len(polygon) - 1
  for i in range(len(polygon)):
    xi, yi = polygon[i]
    xj, yj = polygon[j]
    intersects = ((yi > y) != (yj > y)) and (
        x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-15) + xi
    )
    if intersects:
      inside = not inside
    j = i
  return inside


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a, b, c, epsilon=1e-9) -> bool:
  return (
      min(a[0], c[0]) - epsilon <= b[0] <= max(a[0], c[0]) + epsilon
      and min(a[1], c[1]) - epsilon <= b[1] <= max(a[1], c[1]) + epsilon
  )


def segments_intersect(a, b, c, d) -> bool:
  o1 = _orientation(a, b, c)
  o2 = _orientation(a, b, d)
  o3 = _orientation(c, d, a)
  o4 = _orientation(c, d, b)
  epsilon = 1e-9
  if ((o1 > epsilon and o2 < -epsilon) or (o1 < -epsilon and o2 > epsilon)) and (
      (o3 > epsilon and o4 < -epsilon) or (o3 < -epsilon and o4 > epsilon)
  ):
    return True
  if abs(o1) <= epsilon and _on_segment(a, c, b):
    return True
  if abs(o2) <= epsilon and _on_segment(a, d, b):
    return True
  if abs(o3) <= epsilon and _on_segment(c, a, d):
    return True
  if abs(o4) <= epsilon and _on_segment(c, b, d):
    return True
  return False


@dataclass(frozen=True)
class SpatialEventConfig:
  minimum_score: float = 0.55
  maximum_uncertainty_m: float = 1.5
  transition_confirmations: int = 2
  event_debounce_s: float = 1.5
  allow_predicted: bool = False


class BluetoothSpatialAdapter:
  """Stateful, bounded-by-active-tags spatial event adapter."""

  def __init__(self, config: SpatialEventConfig | None = None):
    self.config = config or SpatialEventConfig()
    self._region_stable: dict[tuple[str, str, str], bool] = {}
    self._region_pending: dict[tuple[str, str, str], tuple[bool, int]] = {}
    self._last_position: dict[tuple[str, str], tuple[tuple[float, float], datetime]] = {}
    self._last_spatial_timestamp: dict[tuple[str, str], datetime] = {}
    self._last_event: dict[tuple[str, str, str, str], datetime] = {}
    self.metrics = {
        "processed": 0,
        "suppressed_quality": 0,
        "suppressed_debounce": 0,
        "region_events": 0,
        "tripwire_events": 0,
    }

  def clear(self) -> None:
    self._region_stable.clear()
    self._region_pending.clear()
    self._last_position.clear()
    self._last_spatial_timestamp.clear()
    self._last_event.clear()

  def _quality_allowed(self, tracked: Mapping[str, Any], rule: Mapping[str, Any]) -> bool:
    quality = tracked.get("quality") if isinstance(tracked.get("quality"), Mapping) else {}
    state = str(quality.get("state") or "")
    score = float(quality.get("score") or 0.0)
    uncertainty = quality.get("horizontal_uncertainty_m")
    predicted = bool((tracked.get("tracker") or {}).get("predicted")) if isinstance(tracked.get("tracker"), Mapping) else False
    allow_predicted = bool(rule.get("bluetooth_allow_predicted", self.config.allow_predicted))
    minimum_score = float(rule.get("bluetooth_min_score", self.config.minimum_score))
    maximum_uncertainty = float(
        rule.get("bluetooth_max_uncertainty_m", self.config.maximum_uncertainty_m)
    )
    if state in {"stale", "unavailable"}:
      return False
    if predicted and not allow_predicted:
      return False
    if score < minimum_score:
      return False
    if uncertainty is None or not math.isfinite(float(uncertainty)):
      return False
    if float(uncertainty) > maximum_uncertainty:
      return False
    return True

  def _debounced(
      self,
      *,
      scene_id: str,
      tag_id: str,
      rule_id: str,
      action: str,
      timestamp: datetime,
      rule: Mapping[str, Any],
  ) -> bool:
    key = (scene_id, tag_id, rule_id, action)
    minimum = float(rule.get("bluetooth_event_debounce_s", self.config.event_debounce_s))
    previous = self._last_event.get(key)
    if previous is not None and (timestamp - previous).total_seconds() < minimum:
      self.metrics["suppressed_debounce"] += 1
      return False
    self._last_event[key] = timestamp
    return True

  def _event_object(self, tracked: Mapping[str, Any]) -> dict[str, Any]:
    quality = dict(tracked.get("quality") or {})
    provenance = dict(tracked.get("provenance") or {})
    return {
        "object": {
            "id": f"bt:{tracked['tag_id']}",
            "type": "bluetooth-tag",
            "source": "bluetooth",
            "translation": [
                float(tracked["position"]["x_m"]),
                float(tracked["position"]["y_m"]),
                float(tracked["position"]["z_m"]),
            ],
        },
        "source": "bluetooth",
        "tag_id": str(tracked["tag_id"]),
        "quality": {
            "state": quality.get("state"),
            "score": quality.get("score"),
            "horizontal_uncertainty_m": quality.get("horizontal_uncertainty_m"),
            "anchors_used": quality.get("anchors_used"),
            "method": quality.get("method"),
        },
        "assignment_id": provenance.get("identity_revision"),
    }

  def _emit(
      self,
      db,
      *,
      scene_id: str,
      rule_type: str,
      resource: Resource,
      tracked: Mapping[str, Any],
      action: str,
      direction: str | None = None,
  ):
    timestamp = _utc(tracked["source_timestamp"])
    payload = resource.payload or {}
    rule_id = resource.uid
    if not self._debounced(
        scene_id=scene_id,
        tag_id=str(tracked["tag_id"]),
        rule_id=rule_id,
        action=action,
        timestamp=timestamp,
        rule=payload,
    ):
      return None
    event_object = self._event_object(tracked)
    event_payload = {
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "scene_id": scene_id,
        "source": "bluetooth",
        f"{rule_type}_name": str(payload.get("name") or rule_id),
        f"{rule_type}_id": rule_id,
        "objects": [event_object],
        "entered": [event_object] if action == "enter" else [],
        "exited": [event_object] if action == "exit" else [],
        "bluetooth": {
            "tag_id": str(tracked["tag_id"]),
            "assignment_id": event_object.get("assignment_id"),
            "quality": event_object["quality"],
            "direction": direction,
        },
    }
    topic = f"scenescape/event/{rule_type}/{scene_id}/{rule_id}/objects"
    event = persist(db, topic, json.dumps(event_payload).encode())
    if rule_type == "region":
      self.metrics["region_events"] += 1
    else:
      self.metrics["tripwire_events"] += 1
    return event

  def process(self, db, tracked: Mapping[str, Any]) -> list[Any]:
    self.metrics["processed"] += 1
    position = tracked.get("position")
    if not isinstance(position, Mapping):
      return []
    try:
      point = (float(position["x_m"]), float(position["y_m"]))
    except (KeyError, TypeError, ValueError):
      return []
    if not all(math.isfinite(value) for value in point):
      return []
    scene_id = str(tracked.get("scene_id") or "")
    tag_id = str(tracked.get("tag_id") or "")
    timestamp = _utc(tracked["source_timestamp"])
    spatial_key = (scene_id, tag_id)
    previous_spatial_time = self._last_spatial_timestamp.get(spatial_key)
    if previous_spatial_time is not None and timestamp <= previous_spatial_time:
      return []
    self._last_spatial_timestamp[spatial_key] = timestamp
    events = []

    resources = db.scalars(
        select(Resource)
        .where(Resource.kind.in_(["region", "tripwire"]))
        .order_by(Resource.kind, Resource.uid)
    ).all()
    for resource in resources:
      if _scene_id(resource) != scene_id:
        continue
      rule = resource.payload or {}
      if rule.get("bluetooth_events_enabled") is False:
        continue
      if not self._quality_allowed(tracked, rule):
        self.metrics["suppressed_quality"] += 1
        continue
      vertices = _points(resource)
      if resource.kind == "region":
        inside = point_in_polygon(point, vertices)
        key = (scene_id, tag_id, resource.uid)
        if key not in self._region_stable:
          self._region_stable[key] = inside
          self._region_pending.pop(key, None)
          continue
        stable = self._region_stable[key]
        if inside == stable:
          self._region_pending.pop(key, None)
          continue
        pending_state, count = self._region_pending.get(key, (inside, 0))
        if pending_state != inside:
          pending_state, count = inside, 0
        count += 1
        self._region_pending[key] = (pending_state, count)
        required = max(
            1,
            int(rule.get("bluetooth_transition_confirmations", self.config.transition_confirmations)),
        )
        if count >= required:
          self._region_stable[key] = inside
          self._region_pending.pop(key, None)
          event = self._emit(
              db,
              scene_id=scene_id,
              rule_type="region",
              resource=resource,
              tracked=tracked,
              action="enter" if inside else "exit",
          )
          if event is not None:
            events.append(event)

    previous = self._last_position.get((scene_id, tag_id))
    if previous is not None:
      previous_point, previous_time = previous
      if timestamp > previous_time:
        for resource in resources:
          if resource.kind != "tripwire" or _scene_id(resource) != scene_id:
            continue
          rule = resource.payload or {}
          if rule.get("bluetooth_events_enabled") is False:
            continue
          if not self._quality_allowed(tracked, rule):
            continue
          vertices = _points(resource)
          crossed = False
          direction = None
          for start, end in zip(vertices, vertices[1:]):
            if segments_intersect(previous_point, point, start, end):
              before = _orientation(start, end, previous_point)
              after = _orientation(start, end, point)
              if before * after < 0:
                crossed = True
                direction = "forward" if before < after else "reverse"
                break
          if crossed:
            event = self._emit(
                db,
                scene_id=scene_id,
                rule_type="tripwire",
                resource=resource,
                tracked=tracked,
                action="cross",
                direction=direction,
            )
            if event is not None:
              events.append(event)
    self._last_position[(scene_id, tag_id)] = (point, timestamp)
    return events


def bluetooth_health_summary(db, *, now: datetime | None = None) -> dict[str, Any]:
  current = _utc(now or utcnow())
  telemetry_stale_s = max(1.0, float(os.getenv("BLUETOOTH_TELEMETRY_STALE_S", "3600"))) if False else 3600.0
  anchors = db.scalars(select(BluetoothAnchor)).all()
  tags = db.scalars(select(BluetoothTag)).all()
  providers = db.scalars(select(BluetoothProvider)).all()

  low_tags = [tag.uid for tag in tags if tag.battery_status in {"low", "critical"}]
  unknown_battery = [tag.uid for tag in tags if tag.battery_status == "unknown"]
  offline_anchors = [
      anchor.uid for anchor in anchors
      if anchor.state in {"disabled", "maintenance", "retired"}
  ]
  inactive_providers = [
      provider.uid for provider in providers
      if provider.state not in {"active", "configured"}
  ]

  latest_tracks = db.scalars(
      select(BluetoothTrackedPosition)
      .order_by(
          BluetoothTrackedPosition.tag_uid,
          BluetoothTrackedPosition.source_timestamp.desc(),
      )
  ).all()
  seen: set[str] = set()
  degraded_tags: list[str] = []
  stale_tags: list[str] = []
  for row in latest_tracks:
    if row.tag_uid in seen:
      continue
    seen.add(row.tag_uid)
    if row.state in {"degraded", "stale", "unavailable"}:
      degraded_tags.append(row.tag_uid)
    if (current - _utc(row.source_timestamp)).total_seconds() > 5.0:
      stale_tags.append(row.tag_uid)

  latest_telemetry = db.scalars(
      select(BluetoothDeviceTelemetry)
      .order_by(
          BluetoothDeviceTelemetry.device_type,
          BluetoothDeviceTelemetry.device_uid,
          BluetoothDeviceTelemetry.observed_at.desc(),
      )
  ).all()
  telemetry_seen: set[tuple[str, str]] = set()
  stale_telemetry: list[str] = []
  for row in latest_telemetry:
    key = (row.device_type, row.device_uid)
    if key in telemetry_seen:
      continue
    telemetry_seen.add(key)
    if (current - _utc(row.observed_at)).total_seconds() > telemetry_stale_s:
      stale_telemetry.append(f"{row.device_type}:{row.device_uid}")

  return {
      "generated_at": current.isoformat(),
      "anchors": {
          "total": len(anchors),
          "offline_or_maintenance": offline_anchors,
      },
      "tags": {
          "total": len(tags),
          "low_battery": low_tags,
          "unknown_battery": unknown_battery,
          "degraded_positioning": degraded_tags,
          "stale_positioning": stale_tags,
      },
      "providers": {
          "total": len(providers),
          "inactive": inactive_providers,
      },
      "telemetry": {
          "stale": stale_telemetry,
      },
  }
