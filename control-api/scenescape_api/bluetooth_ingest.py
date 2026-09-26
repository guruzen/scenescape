# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Bluetooth range-measurement validation, normalization and retention (BT-06)."""

from __future__ import annotations

import json
import math
import os
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from .database import (
    BluetoothAnchor,
    BluetoothMeasurement,
    BluetoothProvider,
    BluetoothTag,
    utcnow,
)

SCHEMA_VERSION = "1.0"
ACCEPTED_DEVICE_STATES = frozenset({"commissioned", "active"})
ACCEPTED_PROVIDER_STATES = frozenset({"configured", "active"})


class MeasurementRejected(ValueError):
  def __init__(self, code: str, message: str):
    super().__init__(message)
    self.code = code
    self.message = message


class MeasurementModel(BaseModel):
  model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RangePayload(MeasurementModel):
  schema_version: str = Field(pattern=r"^1\.0$")
  provider_id: str = Field(min_length=1, max_length=96)
  session_id: str = Field(min_length=1, max_length=96)
  sequence: int = Field(ge=0, le=9_223_372_036_854_775_807)
  source_timestamp: datetime
  method: str = Field(pattern=r"^(channel_sounding|aoa|rssi)$")
  distance_m: float = Field(ge=0.0, allow_inf_nan=False)
  distance_stddev_m: float = Field(gt=0.0, allow_inf_nan=False)
  rssi_dbm: float | None = Field(default=None, allow_inf_nan=False)
  azimuth_deg: float | None = Field(default=None, allow_inf_nan=False)
  elevation_deg: float | None = Field(default=None, allow_inf_nan=False)
  nlos_probability: float = Field(default=0.0, ge=0.0, le=1.0, allow_inf_nan=False)
  quality: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
  provider_details: dict[str, Any] = Field(default_factory=dict)

  @field_validator("source_timestamp")
  @classmethod
  def utc_timestamp(cls, value: datetime) -> datetime:
    if value.tzinfo is None:
      return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

  @field_validator("rssi_dbm")
  @classmethod
  def plausible_rssi(cls, value: float | None) -> float | None:
    if value is not None and not (-200.0 <= value <= 50.0):
      raise ValueError("rssi_dbm is outside the supported physical bound")
    return value

  @field_validator("azimuth_deg")
  @classmethod
  def plausible_azimuth(cls, value: float | None) -> float | None:
    if value is not None and not (-360.0 <= value <= 360.0):
      raise ValueError("azimuth_deg must be inside [-360, 360]")
    return value

  @field_validator("elevation_deg")
  @classmethod
  def plausible_elevation(cls, value: float | None) -> float | None:
    if value is not None and not (-180.0 <= value <= 180.0):
      raise ValueError("elevation_deg must be inside [-180, 180]")
    return value

  @field_validator("provider_details")
  @classmethod
  def bounded_provider_details(cls, value: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True)
    if len(encoded.encode("utf-8")) > 4096:
      raise ValueError("provider_details exceeds the 4096-byte normalized limit")
    return value


class RangeEnvelope(MeasurementModel):
  scene_id: str = Field(min_length=1, max_length=96)
  anchor_id: str = Field(min_length=1, max_length=96)
  tag_id: str = Field(min_length=1, max_length=96)
  payload: RangePayload


class IngressMetrics:
  def __init__(self):
    self._lock = Lock()
    self._accepted = 0
    self._rejected: Counter[str] = Counter()
    self._lag_total = 0.0
    self._lag_max = 0.0
    self._solver_queue_drops = 0

  def accepted(self, lag_s: float) -> None:
    with self._lock:
      self._accepted += 1
      self._lag_total += max(0.0, lag_s)
      self._lag_max = max(self._lag_max, max(0.0, lag_s))

  def rejected(self, reason: str) -> None:
    with self._lock:
      self._rejected[reason] += 1

  def queue_drop(self) -> None:
    with self._lock:
      self._solver_queue_drops += 1

  def snapshot(self) -> dict[str, Any]:
    with self._lock:
      average = self._lag_total / self._accepted if self._accepted else 0.0
      return {
          "accepted": self._accepted,
          "rejected": sum(self._rejected.values()),
          "rejected_by_reason": dict(sorted(self._rejected.items())),
          "ingest_lag_s": {
              "average": round(average, 6),
              "max": round(self._lag_max, 6),
          },
          "solver_queue_drops": self._solver_queue_drops,
      }

  def reset(self) -> None:
    with self._lock:
      self._accepted = 0
      self._rejected.clear()
      self._lag_total = 0.0
      self._lag_max = 0.0
      self._solver_queue_drops = 0


class BoundedMeasurementBuffer:
  """Bounded handoff queue for the asynchronous solver path.

  Raw accepted records are persisted before this queue is offered a record ID,
  so queue pressure can degrade processing latency without silently deleting
  the source measurement.
  """

  def __init__(self, capacity: int):
    if capacity < 1:
      raise ValueError("capacity must be >= 1")
    self.capacity = capacity
    self._values: deque[int] = deque()
    self._lock = Lock()

  def offer(self, measurement_id: int) -> bool:
    with self._lock:
      if len(self._values) >= self.capacity:
        return False
      self._values.append(int(measurement_id))
      return True

  def take(self) -> int | None:
    with self._lock:
      return self._values.popleft() if self._values else None

  def __len__(self) -> int:
    with self._lock:
      return len(self._values)

  def clear(self) -> None:
    with self._lock:
      self._values.clear()


metrics = IngressMetrics()
solver_buffer = BoundedMeasurementBuffer(
    int(os.getenv("BLUETOOTH_SOLVER_QUEUE_CAPACITY", "10000"))
)


def _reject(code: str, message: str) -> None:
  metrics.rejected(code)
  raise MeasurementRejected(code, message)


def _utc(value: datetime) -> datetime:
  if value.tzinfo is None:
    return value.replace(tzinfo=timezone.utc)
  return value.astimezone(timezone.utc)


def _max_range_m() -> float:
  value = float(os.getenv("BLUETOOTH_MAX_RANGE_M", "1000"))
  if not math.isfinite(value) or value <= 0.0:
    return 1000.0
  return value


def _replay_window_s() -> float:
  return max(0.0, float(os.getenv("BLUETOOTH_REPLAY_WINDOW_S", "300")))


def _future_skew_s() -> float:
  return max(0.0, float(os.getenv("BLUETOOTH_FUTURE_SKEW_S", "5")))


def parse_mqtt_range_topic(topic: str) -> tuple[str, str, str]:
  parts = [part for part in str(topic).split("/") if part]
  if len(parts) != 7 or parts[:4] != ["scenescape", "data", "bluetooth", "range"]:
    raise MeasurementRejected("invalid_topic", "MQTT topic is not a Bluetooth range topic")
  scene_id, anchor_id, tag_id = parts[4:7]
  if any(not value or len(value) > 96 for value in (scene_id, anchor_id, tag_id)):
    raise MeasurementRejected("invalid_topic", "MQTT Bluetooth topic identifiers are invalid")
  return scene_id, anchor_id, tag_id


def mqtt_envelope(topic: str, payload: Mapping[str, Any]) -> RangeEnvelope:
  scene_id, anchor_id, tag_id = parse_mqtt_range_topic(topic)
  return RangeEnvelope.model_validate({
      "scene_id": scene_id,
      "anchor_id": anchor_id,
      "tag_id": tag_id,
      "payload": dict(payload),
  })


def _configured_entities(db, envelope: RangeEnvelope):
  provider = db.get(BluetoothProvider, envelope.payload.provider_id)
  if provider is None:
    _reject("provider_not_found", "Bluetooth provider is not commissioned")
  if provider.state not in ACCEPTED_PROVIDER_STATES:
    _reject("provider_inactive", "Bluetooth provider is not in an ingest-capable state")

  anchor = db.get(BluetoothAnchor, envelope.anchor_id)
  if anchor is None:
    _reject("anchor_not_found", "Bluetooth anchor is not commissioned")
  if anchor.scene_id != envelope.scene_id:
    _reject("scene_mismatch", "Bluetooth anchor does not belong to the topic scene")
  if anchor.state not in ACCEPTED_DEVICE_STATES:
    _reject("anchor_inactive", "Bluetooth anchor is not in an ingest-capable state")
  if anchor.provider_id and anchor.provider_id != provider.uid:
    _reject("provider_mismatch", "Bluetooth anchor is bound to a different provider")

  tag = db.get(BluetoothTag, envelope.tag_id)
  if tag is None:
    _reject("tag_not_found", "Bluetooth tag is not commissioned")
  if tag.state not in ACCEPTED_DEVICE_STATES:
    _reject("tag_inactive", "Bluetooth tag is not in an ingest-capable state")
  if tag.provider_id and tag.provider_id != provider.uid:
    _reject("provider_mismatch", "Bluetooth tag is bound to a different provider")
  return provider, anchor, tag


def _validate_timing(payload: RangePayload, now: datetime) -> float:
  source = _utc(payload.source_timestamp)
  current = _utc(now)
  age = (current - source).total_seconds()
  if age > _replay_window_s():
    _reject("stale_timestamp", "Bluetooth measurement is outside the replay window")
  if age < -_future_skew_s():
    _reject("future_timestamp", "Bluetooth measurement timestamp is too far in the future")
  return max(0.0, age)


def _validate_ordering(db, payload: RangePayload) -> None:
  duplicate = db.scalar(
      select(BluetoothMeasurement.id)
      .where(
          BluetoothMeasurement.provider_id == payload.provider_id,
          BluetoothMeasurement.session_id == payload.session_id,
          BluetoothMeasurement.sequence == payload.sequence,
      )
      .limit(1)
  )
  if duplicate is not None:
    _reject("duplicate", "Bluetooth measurement provider/session/sequence already exists")

  latest = db.scalar(
      select(func.max(BluetoothMeasurement.sequence)).where(
          BluetoothMeasurement.provider_id == payload.provider_id,
          BluetoothMeasurement.session_id == payload.session_id,
      )
  )
  if latest is not None and payload.sequence < int(latest):
    _reject("out_of_order", "Bluetooth measurement sequence is older than the accepted session head")


def ingest_measurement(
    db,
    value: RangeEnvelope | Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> BluetoothMeasurement:
  """Validate and persist one normalized range observation.

  This function is transport-independent and is shared by MQTT, simulator
  replay and service-auth HTTP ingestion.
  """
  envelope = value if isinstance(value, RangeEnvelope) else RangeEnvelope.model_validate(dict(value))
  payload = envelope.payload
  if payload.distance_m > _max_range_m():
    _reject("range_too_large", "Bluetooth distance exceeds configured site maximum")

  _configured_entities(db, envelope)
  current = _utc(now or utcnow())
  lag_s = _validate_timing(payload, current)
  _validate_ordering(db, payload)

  row = BluetoothMeasurement(
      scene_id=envelope.scene_id,
      anchor_uid=envelope.anchor_id,
      tag_uid=envelope.tag_id,
      provider_id=payload.provider_id,
      session_id=payload.session_id,
      sequence=payload.sequence,
      source_timestamp=payload.source_timestamp,
      ingested_at=current,
      method=payload.method,
      distance_m=payload.distance_m,
      distance_stddev_m=payload.distance_stddev_m,
      rssi_dbm=payload.rssi_dbm,
      azimuth_deg=payload.azimuth_deg,
      elevation_deg=payload.elevation_deg,
      nlos_probability=payload.nlos_probability,
      quality=payload.quality,
      provider_details=payload.provider_details,
  )
  try:
    with db.begin_nested():
      db.add(row)
      db.flush()
  except IntegrityError as exc:
    metrics.rejected("duplicate")
    raise MeasurementRejected(
        "duplicate",
        "Bluetooth measurement provider/session/sequence already exists",
    ) from exc

  metrics.accepted(lag_s)
  if not solver_buffer.offer(row.id):
    metrics.queue_drop()
  return row


def ingest_mqtt_message(
    db,
    topic: str,
    raw: bytes | bytearray | str | Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> BluetoothMeasurement:
  if isinstance(raw, (bytes, bytearray)):
    if len(raw) > 16 * 1024:
      _reject("payload_too_large", "Bluetooth range MQTT payload exceeds 16 KiB")
    try:
      payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
      _reject("malformed_json", f"Bluetooth range payload is not valid JSON: {exc}")
  elif isinstance(raw, str):
    if len(raw.encode("utf-8")) > 16 * 1024:
      _reject("payload_too_large", "Bluetooth range MQTT payload exceeds 16 KiB")
    try:
      payload = json.loads(raw)
    except json.JSONDecodeError as exc:
      _reject("malformed_json", f"Bluetooth range payload is not valid JSON: {exc}")
  else:
    payload = dict(raw)

  if not isinstance(payload, dict):
    _reject("invalid_payload", "Bluetooth range payload must be a JSON object")
  try:
    envelope = mqtt_envelope(topic, payload)
  except MeasurementRejected:
    metrics.rejected("invalid_topic")
    raise
  return ingest_measurement(db, envelope, now=now)


def measurement_to_dict(row: BluetoothMeasurement) -> dict[str, Any]:
  return {
      "id": row.id,
      "scene_id": row.scene_id,
      "anchor_id": row.anchor_uid,
      "tag_id": row.tag_uid,
      "schema_version": SCHEMA_VERSION,
      "provider_id": row.provider_id,
      "session_id": row.session_id,
      "sequence": row.sequence,
      "source_timestamp": _utc(row.source_timestamp).isoformat().replace("+00:00", "Z"),
      "ingested_at": _utc(row.ingested_at).isoformat().replace("+00:00", "Z"),
      "method": row.method,
      "distance_m": row.distance_m,
      "distance_stddev_m": row.distance_stddev_m,
      "rssi_dbm": row.rssi_dbm,
      "azimuth_deg": row.azimuth_deg,
      "elevation_deg": row.elevation_deg,
      "nlos_probability": row.nlos_probability,
      "quality": row.quality,
      "provider_details": dict(row.provider_details or {}),
  }


def purge_measurements(
    db,
    *,
    now: datetime | None = None,
    retention_s: float | None = None,
) -> int:
  current = _utc(now or utcnow())
  seconds = (
      max(0.0, float(retention_s))
      if retention_s is not None
      else max(0.0, float(os.getenv("BLUETOOTH_RAW_RETENTION_S", "86400")))
  )
  cutoff = current - timedelta(seconds=seconds)
  result = db.execute(
      delete(BluetoothMeasurement).where(BluetoothMeasurement.ingested_at < cutoff)
  )
  return int(result.rowcount or 0)
