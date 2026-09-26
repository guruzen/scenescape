# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Production retention policy for Bluetooth high-rate data (BT-16).

Control-plane configuration, assignment history and calibration/survey
configuration are intentionally excluded. This module only purges high-rate
operational data whose retention is explicitly bounded by policy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from .database import (
    BluetoothDeviceTelemetry,
    BluetoothMeasurement,
    BluetoothRawPosition,
    BluetoothTrackedPosition,
    utcnow,
)


def _utc(value: datetime) -> datetime:
  if value.tzinfo is None:
    return value.replace(tzinfo=timezone.utc)
  return value.astimezone(timezone.utc)


def _env_seconds(name: str, default: int) -> int:
  raw = os.getenv(name, str(default)).strip()
  try:
    value = int(raw)
  except ValueError as exc:
    raise ValueError(f"{name} must be an integer number of seconds") from exc
  if value < 0:
    raise ValueError(f"{name} must be >= 0")
  return value


@dataclass(frozen=True)
class BluetoothRetentionPolicy:
  raw_measurement_s: int = 86_400
  raw_position_s: int = 86_400
  tracked_position_s: int = 604_800
  device_telemetry_s: int = 604_800

  @classmethod
  def from_env(cls) -> "BluetoothRetentionPolicy":
    return cls(
        raw_measurement_s=_env_seconds(
            "BLUETOOTH_RAW_RETENTION_S",
            86_400,
        ),
        raw_position_s=_env_seconds(
            "BLUETOOTH_RAW_POSITION_RETENTION_S",
            86_400,
        ),
        tracked_position_s=_env_seconds(
            "BLUETOOTH_TRACKED_POSITION_RETENTION_S",
            604_800,
        ),
        device_telemetry_s=_env_seconds(
            "BLUETOOTH_DEVICE_TELEMETRY_RETENTION_S",
            604_800,
        ),
    )

  def to_dict(self) -> dict[str, int]:
    return {
        "raw_measurement_s": self.raw_measurement_s,
        "raw_position_s": self.raw_position_s,
        "tracked_position_s": self.tracked_position_s,
        "device_telemetry_s": self.device_telemetry_s,
    }


def purge_bluetooth_history(
    db,
    *,
    policy: BluetoothRetentionPolicy | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
  """Purge high-rate data according to independent retention windows.

  A retention of zero removes all rows older than the supplied current time;
  it does not delete control-plane configuration, assignment history,
  calibration revisions or survey configuration.
  """
  policy = policy or BluetoothRetentionPolicy.from_env()
  current = _utc(now or utcnow())

  statements = {
      "measurements": delete(BluetoothMeasurement).where(
          BluetoothMeasurement.ingested_at
          < current - timedelta(seconds=policy.raw_measurement_s)
      ),
      "raw_positions": delete(BluetoothRawPosition).where(
          BluetoothRawPosition.created_at
          < current - timedelta(seconds=policy.raw_position_s)
      ),
      "tracked_positions": delete(BluetoothTrackedPosition).where(
          BluetoothTrackedPosition.created_at
          < current - timedelta(seconds=policy.tracked_position_s)
      ),
      "device_telemetry": delete(BluetoothDeviceTelemetry).where(
          BluetoothDeviceTelemetry.ingested_at
          < current - timedelta(seconds=policy.device_telemetry_s)
      ),
  }
  result: dict[str, int] = {}
  for name, statement in statements.items():
    execution = db.execute(statement)
    result[name] = int(execution.rowcount or 0)
  return result
