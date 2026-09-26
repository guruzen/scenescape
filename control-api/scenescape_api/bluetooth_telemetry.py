# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Bluetooth device telemetry normalization and bounded polling (BT-10)."""

from __future__ import annotations

import json
import math
import os
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Mapping, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from .database import (
    BluetoothAnchor,
    BluetoothDeviceTelemetry,
    BluetoothTag,
    utcnow,
)


def _utc(value: datetime) -> datetime:
  if value.tzinfo is None:
    return value.replace(tzinfo=timezone.utc)
  return value.astimezone(timezone.utc)


def battery_thresholds() -> tuple[float, float]:
  critical = float(os.getenv("BLUETOOTH_BATTERY_CRITICAL_PERCENT", "10"))
  low = float(os.getenv("BLUETOOTH_BATTERY_LOW_PERCENT", "20"))
  critical = min(max(critical, 0.0), 100.0)
  low = min(max(low, critical), 100.0)
  return critical, low


def battery_status(percent: float | None) -> str:
  if percent is None:
    return "unknown"
  critical, low = battery_thresholds()
  if percent <= critical:
    return "critical"
  if percent <= low:
    return "low"
  return "normal"


class TelemetryModel(BaseModel):
  model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DeviceTelemetryEnvelope(TelemetryModel):
  schema_version: str = Field(default="1.0", pattern=r"^1\.0$")
  provider_id: str = Field(min_length=1, max_length=96)
  source_timestamp: datetime
  device_type: Literal["tag", "anchor"]
  device_id: str = Field(min_length=1, max_length=96)
  source: str = Field(default="provider", min_length=1, max_length=64)
  battery_percent: float | None = Field(default=None, ge=0.0, le=100.0, allow_inf_nan=False)
  battery_voltage_v: float | None = Field(default=None, ge=0.0, le=100.0, allow_inf_nan=False)
  manufacturer: str | None = Field(default=None, max_length=160)
  model: str | None = Field(default=None, max_length=160)
  hardware_revision: str | None = Field(default=None, max_length=96)
  firmware_revision: str | None = Field(default=None, max_length=96)
  details: dict[str, Any] = Field(default_factory=dict)

  @field_validator("source_timestamp")
  @classmethod
  def timestamp_utc(cls, value: datetime) -> datetime:
    return _utc(value)

  @field_validator("details")
  @classmethod
  def bounded_secret_free_details(cls, value: dict[str, Any]) -> dict[str, Any]:
    forbidden = {
        "password",
        "passwd",
        "secret",
        "token",
        "pairing_key",
        "pin",
        "private_key",
        "psk",
    }
    stack: list[tuple[str, Any]] = list(value.items())
    while stack:
      key, item = stack.pop()
      if str(key).casefold() in forbidden:
        raise ValueError(f"telemetry details may not contain secret field {key!r}")
      if isinstance(item, dict):
        stack.extend((str(child_key), child_value) for child_key, child_value in item.items())
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True)
    if len(encoded.encode("utf-8")) > 4096:
      raise ValueError("telemetry details exceeds 4096 bytes")
    return value


def normalize_standard_services(
    *,
    provider_id: str,
    device_type: Literal["tag", "anchor"],
    device_id: str,
    source_timestamp: datetime,
    battery_service: Mapping[str, Any] | None = None,
    device_information: Mapping[str, Any] | None = None,
) -> DeviceTelemetryEnvelope:
  battery_service = dict(battery_service or {})
  device_information = dict(device_information or {})
  raw_level = battery_service.get("battery_level")
  percent = None if raw_level is None else float(raw_level)
  raw_voltage = battery_service.get("battery_voltage_v")
  voltage = None if raw_voltage is None else float(raw_voltage)
  return DeviceTelemetryEnvelope(
      provider_id=provider_id,
      source_timestamp=source_timestamp,
      device_type=device_type,
      device_id=device_id,
      source="bluetooth_standard_services",
      battery_percent=percent,
      battery_voltage_v=voltage,
      manufacturer=device_information.get("manufacturer_name"),
      model=device_information.get("model_number"),
      hardware_revision=device_information.get("hardware_revision"),
      firmware_revision=device_information.get("firmware_revision"),
      details={
          "battery_service_present": bool(battery_service),
          "device_information_service_present": bool(device_information),
      },
  )


def normalize_vendor_telemetry(
    *,
    provider_id: str,
    device_type: Literal["tag", "anchor"],
    device_id: str,
    source_timestamp: datetime,
    payload: Mapping[str, Any],
    battery_percent_field: str = "battery_percent",
    battery_voltage_field: str = "battery_voltage_v",
) -> DeviceTelemetryEnvelope:
  value = dict(payload)
  raw_percent = value.pop(battery_percent_field, None)
  raw_voltage = value.pop(battery_voltage_field, None)
  return DeviceTelemetryEnvelope(
      provider_id=provider_id,
      source_timestamp=source_timestamp,
      device_type=device_type,
      device_id=device_id,
      source="vendor_adapter",
      battery_percent=None if raw_percent is None else float(raw_percent),
      battery_voltage_v=None if raw_voltage is None else float(raw_voltage),
      manufacturer=value.pop("manufacturer", None),
      model=value.pop("model", None),
      hardware_revision=value.pop("hardware_revision", None),
      firmware_revision=value.pop("firmware_revision", None),
      details=value,
  )


def _device(db, envelope: DeviceTelemetryEnvelope):
  model = BluetoothTag if envelope.device_type == "tag" else BluetoothAnchor
  row = db.get(model, envelope.device_id)
  if row is None:
    raise ValueError(f"Bluetooth {envelope.device_type} is not commissioned")
  if row.provider_id and row.provider_id != envelope.provider_id:
    raise ValueError("Bluetooth device is bound to a different provider")
  return row


def ingest_device_telemetry(
    db,
    envelope: DeviceTelemetryEnvelope | Mapping[str, Any],
    *,
    ingested_at: datetime | None = None,
) -> BluetoothDeviceTelemetry:
  value = (
      envelope
      if isinstance(envelope, DeviceTelemetryEnvelope)
      else DeviceTelemetryEnvelope.model_validate(dict(envelope))
  )
  device = _device(db, value)
  now = _utc(ingested_at or utcnow())
  if value.source_timestamp > now + timedelta(seconds=5):
    raise ValueError("device telemetry timestamp is too far in the future")
  if value.source_timestamp < now - timedelta(days=7):
    raise ValueError("device telemetry is outside the retention ingest window")

  status = battery_status(value.battery_percent)
  row = BluetoothDeviceTelemetry(
      device_type=value.device_type,
      device_uid=value.device_id,
      provider_id=value.provider_id,
      source=value.source,
      observed_at=value.source_timestamp,
      ingested_at=now,
      battery_percent=value.battery_percent,
      battery_voltage_v=value.battery_voltage_v,
      battery_status=status,
      manufacturer=value.manufacturer,
      model=value.model,
      hardware_revision=value.hardware_revision,
      firmware_revision=value.firmware_revision,
      details=value.details,
  )
  db.add(row)
  db.flush()

  # Compatibility projection: latest trustworthy telemetry is reflected in
  # the BT-01 tag snapshot without making those fields the source of truth.
  if value.device_type == "tag":
    device.last_seen_at = value.source_timestamp
    device.battery_percent = value.battery_percent
    device.battery_voltage_v = value.battery_voltage_v
    device.battery_status = status
    device.battery_source = value.source
    device.battery_observed_at = value.source_timestamp
    if value.manufacturer:
      device.manufacturer = value.manufacturer
    if value.model:
      device.model = value.model
    if value.hardware_revision:
      device.hardware_revision = value.hardware_revision
    if value.firmware_revision:
      device.firmware_revision = value.firmware_revision
    device.updated_at = now
  else:
    if value.manufacturer:
      device.manufacturer = value.manufacturer
    if value.model:
      device.model = value.model
    if value.hardware_revision:
      device.hardware_revision = value.hardware_revision
    if value.firmware_revision:
      device.firmware_revision = value.firmware_revision
    device.updated_at = now
  return row


def telemetry_public(row: BluetoothDeviceTelemetry, *, now: datetime | None = None) -> dict[str, Any]:
  current = _utc(now or utcnow())
  age_s = max(0.0, (current - _utc(row.observed_at)).total_seconds())
  stale_after = max(1.0, float(os.getenv("BLUETOOTH_TELEMETRY_STALE_S", "3600")))
  return {
      "id": row.id,
      "device_type": row.device_type,
      "device_id": row.device_uid,
      "provider_id": row.provider_id,
      "source": row.source,
      "observed_at": _utc(row.observed_at).isoformat().replace("+00:00", "Z"),
      "ingested_at": _utc(row.ingested_at).isoformat().replace("+00:00", "Z"),
      "freshness": {
          "age_s": round(age_s, 3),
          "stale": age_s > stale_after,
      },
      "battery": {
          "percent": row.battery_percent,
          "voltage_v": row.battery_voltage_v,
          "status": row.battery_status,
      },
      "device_information": {
          "manufacturer": row.manufacturer,
          "model": row.model,
          "hardware_revision": row.hardware_revision,
          "firmware_revision": row.firmware_revision,
      },
      "details": dict(row.details or {}),
  }


def latest_device_telemetry(db, device_type: str, device_id: str) -> BluetoothDeviceTelemetry | None:
  return db.scalar(
      select(BluetoothDeviceTelemetry)
      .where(
          BluetoothDeviceTelemetry.device_type == device_type,
          BluetoothDeviceTelemetry.device_uid == device_id,
      )
      .order_by(
          BluetoothDeviceTelemetry.observed_at.desc(),
          BluetoothDeviceTelemetry.id.desc(),
      )
      .limit(1)
  )


class TelemetryPollCache:
  """Bounded LRU poll guard that protects battery-powered devices."""

  def __init__(self, *, min_interval_s: float = 60.0, max_entries: int = 10_000):
    if min_interval_s < 0:
      raise ValueError("min_interval_s must be non-negative")
    if max_entries < 1:
      raise ValueError("max_entries must be >= 1")
    self.min_interval_s = float(min_interval_s)
    self.max_entries = int(max_entries)
    self._values: OrderedDict[str, datetime] = OrderedDict()
    self._lock = Lock()

  def should_poll(self, device_key: str, now: datetime) -> bool:
    now = _utc(now)
    key = str(device_key)
    with self._lock:
      previous = self._values.get(key)
      if previous is not None and (now - previous).total_seconds() < self.min_interval_s:
        self._values.move_to_end(key)
        return False
      self._values[key] = now
      self._values.move_to_end(key)
      while len(self._values) > self.max_entries:
        self._values.popitem(last=False)
      return True

  def __len__(self) -> int:
    with self._lock:
      return len(self._values)
