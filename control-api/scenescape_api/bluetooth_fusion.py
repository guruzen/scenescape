# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Privacy-preserving Bluetooth + vision association (BT-15)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


def _utc(value: datetime | str | None) -> datetime | None:
  if value is None:
    return None
  if isinstance(value, str):
    try:
      value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
      return None
  if value.tzinfo is None:
    return value.replace(tzinfo=timezone.utc)
  return value.astimezone(timezone.utc)


def _xyz(value: Mapping[str, Any]) -> tuple[float, float, float] | None:
  raw = value.get("translation")
  if not isinstance(raw, (list, tuple)) or len(raw) < 2:
    position = value.get("position")
    if isinstance(position, Mapping):
      raw = [position.get("x_m"), position.get("y_m"), position.get("z_m", 0.0)]
  if not isinstance(raw, (list, tuple)) or len(raw) < 2:
    return None
  try:
    point = (
        float(raw[0]),
        float(raw[1]),
        float(raw[2] if len(raw) > 2 else 0.0),
    )
  except (TypeError, ValueError):
    return None
  return point if all(math.isfinite(component) for component in point) else None


def _vision_id(value: Mapping[str, Any]) -> str:
  raw = value.get("id")
  return str(raw) if raw is not None else ""


def _vision_category(value: Mapping[str, Any]) -> str:
  return str(value.get("category") or value.get("type") or "").strip().lower()


def _bt_assignment(value: Mapping[str, Any]) -> Mapping[str, Any] | None:
  bluetooth = value.get("bluetooth")
  if not isinstance(bluetooth, Mapping):
    return None
  assignment = bluetooth.get("assignment")
  return assignment if isinstance(assignment, Mapping) else None


def _bt_tag_id(value: Mapping[str, Any]) -> str:
  bluetooth = value.get("bluetooth")
  if isinstance(bluetooth, Mapping) and bluetooth.get("tag_id"):
    return str(bluetooth["tag_id"])
  object_id = str(value.get("id") or "")
  return object_id[3:] if object_id.startswith("bt:") else object_id


def _bt_identity_revision(value: Mapping[str, Any]) -> str:
  bluetooth = value.get("bluetooth")
  if not isinstance(bluetooth, Mapping):
    return ""
  return str(bluetooth.get("identity_revision") or "")


def _bt_quality_score(value: Mapping[str, Any]) -> float:
  bluetooth = value.get("bluetooth")
  if not isinstance(bluetooth, Mapping):
    return 0.0
  try:
    score = float(bluetooth.get("score") or 0.0)
  except (TypeError, ValueError):
    return 0.0
  return max(0.0, min(score, 1.0))


def _category_compatible(bt: Mapping[str, Any], vision: Mapping[str, Any]) -> bool:
  assignment = _bt_assignment(bt)
  if assignment is None:
    return True
  entity_type = str(assignment.get("entity_type") or "").lower()
  category = _vision_category(vision)
  if not entity_type or not category:
    return True
  if entity_type == "person":
    return category in {"person", "human", "pedestrian"}
  if entity_type in {"asset", "vehicle"}:
    return category not in {"person", "human", "pedestrian"}
  return True


@dataclass(frozen=True)
class FusionConfig:
  max_distance_m: float = 1.5
  max_time_delta_s: float = 0.75
  minimum_confidence: float = 0.72
  ambiguity_margin: float = 0.12
  retain_confidence: float = 0.58
  split_distance_m: float = 2.5

  def __post_init__(self):
    if self.max_distance_m <= 0 or self.max_time_delta_s <= 0:
      raise ValueError("fusion gates must be positive")
    if not 0 <= self.retain_confidence <= self.minimum_confidence <= 1:
      raise ValueError("fusion confidence thresholds are invalid")


@dataclass
class AssociationState:
  vision_id: str
  confidence: float
  identity_revision: str


class EntityFusionProvider:
  """Gated nearest-neighbour association with identity-aware hysteresis.

  Visual appearance never supplies identity. Any label/name on a fused object
  comes only from the explicit Bluetooth assignment already authorized by the
  caller that constructed the Bluetooth object.
  """

  def __init__(self, config: FusionConfig | None = None):
    self.config = config or FusionConfig()
    self._associations: dict[str, AssociationState] = {}
    self.metrics = {
        "fused": 0,
        "ambiguous": 0,
        "distance_rejected": 0,
        "category_rejected": 0,
        "split": 0,
    }

  def clear(self) -> None:
    self._associations.clear()

  def _candidate_score(
      self,
      bt: Mapping[str, Any],
      vision: Mapping[str, Any],
  ) -> tuple[float, float] | None:
    bt_position = _xyz(bt)
    vision_position = _xyz(vision)
    if bt_position is None or vision_position is None:
      return None
    distance = math.dist(bt_position, vision_position)
    if distance > self.config.max_distance_m:
      self.metrics["distance_rejected"] += 1
      return None
    if not _category_compatible(bt, vision):
      self.metrics["category_rejected"] += 1
      return None

    bt_time = _utc(bt.get("timestamp"))
    vision_time = _utc(vision.get("timestamp") or vision.get("observed_at"))
    time_score = 1.0
    if bt_time is not None and vision_time is not None:
      delta = abs((bt_time - vision_time).total_seconds())
      if delta > self.config.max_time_delta_s:
        return None
      time_score = max(0.0, 1.0 - delta / self.config.max_time_delta_s)

    distance_score = max(0.0, 1.0 - distance / self.config.max_distance_m)
    bt_quality = _bt_quality_score(bt)
    confidence = (
        0.55 * distance_score
        + 0.20 * time_score
        + 0.25 * bt_quality
    )
    return min(max(confidence, 0.0), 1.0), distance

  def _fused_object(
      self,
      bt: Mapping[str, Any],
      vision: Mapping[str, Any],
      confidence: float,
  ) -> dict[str, Any]:
    tag_id = _bt_tag_id(bt)
    assignment = _bt_assignment(bt)
    label = None
    if assignment is not None:
      label = assignment.get("display_name") or assignment.get("entity_id")
    # Prefer vision position when it is a current camera track; BLE remains
    # available as an occlusion bridge through source metadata.
    translation = list(_xyz(vision) or _xyz(bt) or (0.0, 0.0, 0.0))
    velocity = vision.get("velocity")
    if not isinstance(velocity, (list, tuple)):
      velocity = bt.get("velocity")
    return {
        "id": f"fused:{tag_id}",
        "source": "fusion",
        "category": vision.get("category") or bt.get("category") or "object",
        "type": vision.get("type") or bt.get("type") or "object",
        "label": label or tag_id,
        "translation": translation,
        "velocity": list(velocity) if isinstance(velocity, (list, tuple)) else [0.0, 0.0, 0.0],
        "fusion": {
            "confidence": confidence,
            "bluetooth_tag_id": tag_id,
            "vision_object_id": _vision_id(vision),
            "source_ids": {
                "bluetooth": str(bt.get("id") or f"bt:{tag_id}"),
                "vision": _vision_id(vision),
            },
            "identity_source": "explicit_bluetooth_assignment" if assignment is not None else "anonymous_tag",
            "identity_revision": _bt_identity_revision(bt),
        },
        # Constituents are retained for forensic/support use; they are not
        # mutated and remain separately queryable in the live payload.
        "source_objects": {
            "bluetooth": dict(bt),
            "vision": dict(vision),
        },
    }

  def fuse(
      self,
      vision_objects: list[dict[str, Any]],
      bluetooth_objects: list[dict[str, Any]],
  ) -> dict[str, Any]:
    vision_by_id = {
        _vision_id(value): value
        for value in vision_objects
        if _vision_id(value)
    }
    used_vision: set[str] = set()
    fused: list[dict[str, Any]] = []
    unmatched_bt: list[dict[str, Any]] = []

    for bt in bluetooth_objects:
      tag_id = _bt_tag_id(bt)
      if not tag_id:
        unmatched_bt.append(bt)
        continue
      identity_revision = _bt_identity_revision(bt)
      previous = self._associations.get(tag_id)
      if previous is not None and previous.identity_revision != identity_revision:
        self._associations.pop(tag_id, None)
        self.metrics["split"] += 1
        previous = None

      candidates: list[tuple[float, float, str, dict[str, Any]]] = []
      for vision_id, vision in vision_by_id.items():
        if vision_id in used_vision:
          continue
        scored = self._candidate_score(bt, vision)
        if scored is None:
          continue
        confidence, distance = scored
        # Retention bonus discourages fuse/split oscillation without defeating
        # the hard distance/category/time gates.
        if previous is not None and previous.vision_id == vision_id:
          confidence = min(1.0, confidence + 0.10)
        candidates.append((confidence, distance, vision_id, vision))
      candidates.sort(key=lambda item: (-item[0], item[1], item[2]))

      if not candidates:
        if previous is not None:
          self._associations.pop(tag_id, None)
          self.metrics["split"] += 1
        unmatched_bt.append(bt)
        continue

      best_confidence, best_distance, best_id, best_vision = candidates[0]
      second_confidence = candidates[1][0] if len(candidates) > 1 else 0.0
      ambiguous = (
          len(candidates) > 1
          and best_confidence - second_confidence < self.config.ambiguity_margin
      )
      threshold = (
          self.config.retain_confidence
          if previous is not None and previous.vision_id == best_id
          else self.config.minimum_confidence
      )
      if ambiguous or best_confidence < threshold:
        if ambiguous:
          self.metrics["ambiguous"] += 1
        unmatched_bt.append(bt)
        continue
      if previous is not None and best_distance > self.config.split_distance_m:
        self._associations.pop(tag_id, None)
        self.metrics["split"] += 1
        unmatched_bt.append(bt)
        continue

      fused_object = self._fused_object(bt, best_vision, best_confidence)
      fused.append(fused_object)
      used_vision.add(best_id)
      self._associations[tag_id] = AssociationState(
          vision_id=best_id,
          confidence=best_confidence,
          identity_revision=identity_revision,
      )
      self.metrics["fused"] += 1

    unmatched_vision = [
        value for value in vision_objects
        if _vision_id(value) not in used_vision
    ]
    return {
        "objects": [*unmatched_vision, *unmatched_bt, *fused],
        "fused": fused,
        "unmatched_vision": unmatched_vision,
        "unmatched_bluetooth": unmatched_bt,
        "metrics": dict(self.metrics),
    }
