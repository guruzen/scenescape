from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from .database import (
    BluetoothAnchor,
    BluetoothAssignment,
    BluetoothCalibration,
    BluetoothProvider,
    BluetoothTag,
    Resource,
    utcnow,
)


class BluetoothDomainError(ValueError):
  def __init__(self, code: str, message: str):
    super().__init__(message)
    self.code = code
    self.message = message


class BluetoothConflict(BluetoothDomainError):
  pass


class BluetoothNotFound(BluetoothDomainError):
  pass


class BluetoothRevisionConflict(BluetoothConflict):
  pass


class DeviceState(str, Enum):
  DISCOVERED = "discovered"
  COMMISSIONED = "commissioned"
  ACTIVE = "active"
  MAINTENANCE = "maintenance"
  DISABLED = "disabled"
  OFFLINE = "offline"
  RETIRED = "retired"


class ProviderState(str, Enum):
  CONFIGURED = "configured"
  ACTIVE = "active"
  OFFLINE = "offline"
  DISABLED = "disabled"


class BatteryStatus(str, Enum):
  UNKNOWN = "unknown"
  NORMAL = "normal"
  LOW = "low"
  CRITICAL = "critical"


class CalibrationState(str, Enum):
  DRAFT = "draft"
  ACTIVE = "active"
  RETIRED = "retired"


class EntityType(str, Enum):
  PERSON = "person"
  ASSET = "asset"
  VEHICLE = "vehicle"
  TOOL = "tool"
  OTHER = "other"


class BluetoothModel(BaseModel):
  model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _clean_capabilities(values: list[str]) -> list[str]:
  result: list[str] = []
  seen: set[str] = set()
  for raw in values:
    value = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    if not value or len(value) > 64:
      raise ValueError("capability names must contain 1-64 characters")
    if value not in seen:
      seen.add(value)
      result.append(value)
  return result


class ProviderInput(BluetoothModel):
  uid: str | None = Field(default=None, min_length=1, max_length=96)
  name: str = Field(min_length=1, max_length=160)
  kind: str = Field(default="generic", min_length=1, max_length=64)
  state: ProviderState = ProviderState.CONFIGURED
  capabilities: list[str] = Field(default_factory=list)

  @field_validator("capabilities")
  @classmethod
  def capabilities_are_normalized(cls, value: list[str]) -> list[str]:
    return _clean_capabilities(value)


class AnchorInput(BluetoothModel):
  uid: str | None = Field(default=None, min_length=1, max_length=96)
  serial_number: str = Field(min_length=1, max_length=128)
  scene_id: str | None = Field(default=None, min_length=1, max_length=96)
  provider_id: str | None = Field(default=None, min_length=1, max_length=96)
  provider_device_id: str | None = Field(default=None, min_length=1, max_length=192)
  bluetooth_address: str | None = Field(default=None, min_length=1, max_length=64)
  manufacturer: str | None = Field(default=None, max_length=160)
  model: str | None = Field(default=None, max_length=160)
  hardware_revision: str | None = Field(default=None, max_length=96)
  firmware_revision: str | None = Field(default=None, max_length=96)
  state: DeviceState = DeviceState.COMMISSIONED
  capabilities: list[str] = Field(default_factory=list)

  @field_validator("capabilities")
  @classmethod
  def capabilities_are_normalized(cls, value: list[str]) -> list[str]:
    return _clean_capabilities(value)

  @model_validator(mode="after")
  def provider_identity_is_complete(self):
    if self.provider_device_id and not self.provider_id:
      raise ValueError("provider_device_id requires provider_id")
    return self


class AnchorPatch(BluetoothModel):
  serial_number: str | None = Field(default=None, min_length=1, max_length=128)
  scene_id: str | None = Field(default=None, max_length=96)
  provider_id: str | None = Field(default=None, max_length=96)
  provider_device_id: str | None = Field(default=None, max_length=192)
  bluetooth_address: str | None = Field(default=None, max_length=64)
  manufacturer: str | None = Field(default=None, max_length=160)
  model: str | None = Field(default=None, max_length=160)
  hardware_revision: str | None = Field(default=None, max_length=96)
  firmware_revision: str | None = Field(default=None, max_length=96)
  state: DeviceState | None = None
  capabilities: list[str] | None = None

  @field_validator("capabilities")
  @classmethod
  def capabilities_are_normalized(cls, value: list[str] | None) -> list[str] | None:
    return None if value is None else _clean_capabilities(value)


class TagInput(BluetoothModel):
  uid: str | None = Field(default=None, min_length=1, max_length=96)
  serial_number: str = Field(min_length=1, max_length=128)
  provider_id: str | None = Field(default=None, min_length=1, max_length=96)
  provider_device_id: str | None = Field(default=None, min_length=1, max_length=192)
  bluetooth_address: str | None = Field(default=None, min_length=1, max_length=64)
  manufacturer: str | None = Field(default=None, max_length=160)
  model: str | None = Field(default=None, max_length=160)
  hardware_revision: str | None = Field(default=None, max_length=96)
  firmware_revision: str | None = Field(default=None, max_length=96)
  state: DeviceState = DeviceState.COMMISSIONED
  capabilities: list[str] = Field(default_factory=list)
  battery_percent: float | None = Field(default=None, ge=0.0, le=100.0, allow_inf_nan=False)
  battery_voltage_v: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
  battery_status: BatteryStatus = BatteryStatus.UNKNOWN
  battery_source: str | None = Field(default=None, max_length=96)
  battery_observed_at: datetime | None = None
  last_seen_at: datetime | None = None

  @field_validator("capabilities")
  @classmethod
  def capabilities_are_normalized(cls, value: list[str]) -> list[str]:
    return _clean_capabilities(value)

  @model_validator(mode="after")
  def provider_identity_is_complete(self):
    if self.provider_device_id and not self.provider_id:
      raise ValueError("provider_device_id requires provider_id")
    if self.battery_percent is None and self.battery_status != BatteryStatus.UNKNOWN:
      raise ValueError("battery_status must be unknown when battery_percent is unknown")
    return self


class TagPatch(BluetoothModel):
  serial_number: str | None = Field(default=None, min_length=1, max_length=128)
  provider_id: str | None = Field(default=None, max_length=96)
  provider_device_id: str | None = Field(default=None, max_length=192)
  bluetooth_address: str | None = Field(default=None, max_length=64)
  manufacturer: str | None = Field(default=None, max_length=160)
  model: str | None = Field(default=None, max_length=160)
  hardware_revision: str | None = Field(default=None, max_length=96)
  firmware_revision: str | None = Field(default=None, max_length=96)
  state: DeviceState | None = None
  capabilities: list[str] | None = None
  battery_percent: float | None = Field(default=None, ge=0.0, le=100.0, allow_inf_nan=False)
  battery_voltage_v: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
  battery_status: BatteryStatus | None = None
  battery_source: str | None = Field(default=None, max_length=96)
  battery_observed_at: datetime | None = None
  last_seen_at: datetime | None = None

  @field_validator("capabilities")
  @classmethod
  def capabilities_are_normalized(cls, value: list[str] | None) -> list[str] | None:
    return None if value is None else _clean_capabilities(value)


class AssignmentInput(BluetoothModel):
  uid: str | None = Field(default=None, min_length=1, max_length=96)
  tag_uid: str = Field(min_length=1, max_length=96)
  entity_type: EntityType
  entity_id: str = Field(min_length=1, max_length=160)
  display_name: str | None = Field(default=None, max_length=240)
  valid_from: datetime = Field(default_factory=utcnow)
  valid_to: datetime | None = None
  reason: str | None = Field(default=None, max_length=500)

  @model_validator(mode="after")
  def interval_is_valid(self):
    start = _as_utc(self.valid_from)
    end = _as_utc(self.valid_to) if self.valid_to else None
    if end is not None and end <= start:
      raise ValueError("valid_to must be later than valid_from")
    self.valid_from = start
    self.valid_to = end
    return self


class CalibrationInput(BluetoothModel):
  uid: str | None = Field(default=None, min_length=1, max_length=96)
  anchor_uid: str = Field(min_length=1, max_length=96)
  scene_id: str = Field(min_length=1, max_length=96)
  x_m: float
  y_m: float
  z_m: float
  yaw_deg: float = 0.0
  pitch_deg: float = 0.0
  roll_deg: float = 0.0
  z_source: str = Field(default="measured", pattern="^(measured|default|surveyed)$")
  details: dict[str, Any] = Field(default_factory=dict)

  @field_validator("x_m", "y_m", "z_m", "yaw_deg", "pitch_deg", "roll_deg")
  @classmethod
  def finite_coordinates(cls, value: float) -> float:
    number = float(value)
    if not math.isfinite(number):
      raise ValueError("calibration coordinates and angles must be finite")
    return number


def _as_utc(value: datetime) -> datetime:
  if value.tzinfo is None:
    return value.replace(tzinfo=timezone.utc)
  return value.astimezone(timezone.utc)


def _uid(prefix: str, requested: str | None) -> str:
  return requested or f"{prefix}-{uuid.uuid4()}"


def _scene_exists(db, scene_id: str) -> bool:
  return db.scalar(
      select(Resource.id).where(Resource.kind == "scene", Resource.uid == scene_id).limit(1)
  ) is not None


def _require_scene(db, scene_id: str) -> None:
  if not _scene_exists(db, scene_id):
    raise BluetoothNotFound("scene_not_found", f"Scene {scene_id!r} does not exist")


def _require_provider(db, provider_id: str | None) -> None:
  if provider_id is None:
    return
  if db.get(BluetoothProvider, provider_id) is None:
    raise BluetoothNotFound("provider_not_found", f"Bluetooth provider {provider_id!r} does not exist")


def _require_tag(db, tag_uid: str) -> BluetoothTag:
  row = db.get(BluetoothTag, tag_uid)
  if row is None:
    raise BluetoothNotFound("tag_not_found", f"Bluetooth tag {tag_uid!r} does not exist")
  return row


def _require_anchor(db, anchor_uid: str) -> BluetoothAnchor:
  row = db.get(BluetoothAnchor, anchor_uid)
  if row is None:
    raise BluetoothNotFound("anchor_not_found", f"Bluetooth anchor {anchor_uid!r} does not exist")
  return row


def _raise_integrity(exc: IntegrityError, message: str) -> None:
  raise BluetoothConflict("duplicate", message) from exc


def _unique_serial(db, model, serial_number: str, exclude_uid: str | None = None) -> None:
  statement = select(model.uid).where(model.serial_number == serial_number)
  if exclude_uid:
    statement = statement.where(model.uid != exclude_uid)
  if db.scalar(statement.limit(1)) is not None:
    raise BluetoothConflict("duplicate_serial", f"Serial number {serial_number!r} is already registered")


def _unique_provider_identity(
    db,
    model,
    provider_id: str | None,
    provider_device_id: str | None,
    exclude_uid: str | None = None,
) -> None:
  if not provider_id or not provider_device_id:
    return
  statement = select(model.uid).where(
      model.provider_id == provider_id,
      model.provider_device_id == provider_device_id,
  )
  if exclude_uid:
    statement = statement.where(model.uid != exclude_uid)
  if db.scalar(statement.limit(1)) is not None:
    raise BluetoothConflict(
        "duplicate_provider_device",
        f"Provider device {provider_id!r}/{provider_device_id!r} is already registered",
    )


def create_provider(db, payload: dict[str, Any], actor: str) -> BluetoothProvider:
  del actor
  data = ProviderInput.model_validate(payload)
  uid = _uid("bt-provider", data.uid)
  if db.get(BluetoothProvider, uid) is not None:
    raise BluetoothConflict("duplicate_uid", f"Bluetooth provider {uid!r} already exists")
  if db.scalar(select(BluetoothProvider.uid).where(BluetoothProvider.name == data.name).limit(1)):
    raise BluetoothConflict("duplicate_name", f"Bluetooth provider name {data.name!r} already exists")
  row = BluetoothProvider(
      uid=uid,
      name=data.name,
      kind=data.kind,
      state=data.state.value,
      capabilities=data.capabilities,
      revision=1,
  )
  try:
    with db.begin_nested():
      db.add(row)
      db.flush()
  except IntegrityError as exc:
    _raise_integrity(exc, "Bluetooth provider identity already exists")
  return row


def create_anchor(db, payload: dict[str, Any], actor: str) -> BluetoothAnchor:
  del actor
  data = AnchorInput.model_validate(payload)
  uid = _uid("bt-anchor", data.uid)
  if db.get(BluetoothAnchor, uid) is not None:
    raise BluetoothConflict("duplicate_uid", f"Bluetooth anchor {uid!r} already exists")
  if data.scene_id:
    _require_scene(db, data.scene_id)
  _require_provider(db, data.provider_id)
  _unique_serial(db, BluetoothAnchor, data.serial_number)
  _unique_provider_identity(db, BluetoothAnchor, data.provider_id, data.provider_device_id)
  row = BluetoothAnchor(
      uid=uid,
      serial_number=data.serial_number,
      scene_id=data.scene_id,
      provider_id=data.provider_id,
      provider_device_id=data.provider_device_id,
      bluetooth_address=data.bluetooth_address,
      manufacturer=data.manufacturer,
      model=data.model,
      hardware_revision=data.hardware_revision,
      firmware_revision=data.firmware_revision,
      state=data.state.value,
      capabilities=data.capabilities,
      revision=1,
  )
  try:
    with db.begin_nested():
      db.add(row)
      db.flush()
  except IntegrityError as exc:
    _raise_integrity(exc, "Bluetooth anchor identity already exists")
  return row


def _anchor_payload(row: BluetoothAnchor) -> dict[str, Any]:
  return {
      "uid": row.uid,
      "serial_number": row.serial_number,
      "scene_id": row.scene_id,
      "provider_id": row.provider_id,
      "provider_device_id": row.provider_device_id,
      "bluetooth_address": row.bluetooth_address,
      "manufacturer": row.manufacturer,
      "model": row.model,
      "hardware_revision": row.hardware_revision,
      "firmware_revision": row.firmware_revision,
      "state": row.state,
      "capabilities": list(row.capabilities or []),
  }


def update_anchor(
    db,
    uid: str,
    payload: dict[str, Any],
    actor: str,
    expected_revision: int,
) -> BluetoothAnchor:
  del actor
  row = _require_anchor(db, uid)
  if row.revision != expected_revision:
    raise BluetoothRevisionConflict("revision_conflict", "Bluetooth anchor revision conflict")
  changes = AnchorPatch.model_validate(payload).model_dump(exclude_unset=True)
  merged = {**_anchor_payload(row), **changes, "uid": uid}
  data = AnchorInput.model_validate(merged)
  if data.scene_id:
    _require_scene(db, data.scene_id)
  _require_provider(db, data.provider_id)
  _unique_serial(db, BluetoothAnchor, data.serial_number, exclude_uid=uid)
  _unique_provider_identity(
      db,
      BluetoothAnchor,
      data.provider_id,
      data.provider_device_id,
      exclude_uid=uid,
  )
  values = data.model_dump(exclude={"uid"}, mode="json")
  values["state"] = data.state.value
  values["revision"] = expected_revision + 1
  values["updated_at"] = utcnow()
  result = db.execute(
      update(BluetoothAnchor)
      .where(BluetoothAnchor.uid == uid, BluetoothAnchor.revision == expected_revision)
      .values(**values)
  )
  if result.rowcount != 1:
    raise BluetoothRevisionConflict("revision_conflict", "Bluetooth anchor revision conflict")
  db.flush()
  return _require_anchor(db, uid)


def create_tag(db, payload: dict[str, Any], actor: str) -> BluetoothTag:
  del actor
  data = TagInput.model_validate(payload)
  uid = _uid("bt-tag", data.uid)
  if db.get(BluetoothTag, uid) is not None:
    raise BluetoothConflict("duplicate_uid", f"Bluetooth tag {uid!r} already exists")
  _require_provider(db, data.provider_id)
  _unique_serial(db, BluetoothTag, data.serial_number)
  _unique_provider_identity(db, BluetoothTag, data.provider_id, data.provider_device_id)
  row = BluetoothTag(
      uid=uid,
      serial_number=data.serial_number,
      provider_id=data.provider_id,
      provider_device_id=data.provider_device_id,
      bluetooth_address=data.bluetooth_address,
      manufacturer=data.manufacturer,
      model=data.model,
      hardware_revision=data.hardware_revision,
      firmware_revision=data.firmware_revision,
      state=data.state.value,
      capabilities=data.capabilities,
      battery_percent=data.battery_percent,
      battery_voltage_v=data.battery_voltage_v,
      battery_status=data.battery_status.value,
      battery_source=data.battery_source,
      battery_observed_at=data.battery_observed_at,
      last_seen_at=data.last_seen_at,
      revision=1,
  )
  try:
    with db.begin_nested():
      db.add(row)
      db.flush()
  except IntegrityError as exc:
    _raise_integrity(exc, "Bluetooth tag identity already exists")
  return row


def _tag_payload(row: BluetoothTag) -> dict[str, Any]:
  return {
      "uid": row.uid,
      "serial_number": row.serial_number,
      "provider_id": row.provider_id,
      "provider_device_id": row.provider_device_id,
      "bluetooth_address": row.bluetooth_address,
      "manufacturer": row.manufacturer,
      "model": row.model,
      "hardware_revision": row.hardware_revision,
      "firmware_revision": row.firmware_revision,
      "state": row.state,
      "capabilities": list(row.capabilities or []),
      "battery_percent": row.battery_percent,
      "battery_voltage_v": row.battery_voltage_v,
      "battery_status": row.battery_status,
      "battery_source": row.battery_source,
      "battery_observed_at": row.battery_observed_at,
      "last_seen_at": row.last_seen_at,
  }


def update_tag(
    db,
    uid: str,
    payload: dict[str, Any],
    actor: str,
    expected_revision: int,
) -> BluetoothTag:
  del actor
  row = _require_tag(db, uid)
  if row.revision != expected_revision:
    raise BluetoothRevisionConflict("revision_conflict", "Bluetooth tag revision conflict")
  changes = TagPatch.model_validate(payload).model_dump(exclude_unset=True)
  merged = {**_tag_payload(row), **changes, "uid": uid}
  data = TagInput.model_validate(merged)
  _require_provider(db, data.provider_id)
  _unique_serial(db, BluetoothTag, data.serial_number, exclude_uid=uid)
  _unique_provider_identity(
      db,
      BluetoothTag,
      data.provider_id,
      data.provider_device_id,
      exclude_uid=uid,
  )
  values = data.model_dump(exclude={"uid"}, mode="python")
  values["state"] = data.state.value
  values["battery_status"] = data.battery_status.value
  values["revision"] = expected_revision + 1
  values["updated_at"] = utcnow()
  result = db.execute(
      update(BluetoothTag)
      .where(BluetoothTag.uid == uid, BluetoothTag.revision == expected_revision)
      .values(**values)
  )
  if result.rowcount != 1:
    raise BluetoothRevisionConflict("revision_conflict", "Bluetooth tag revision conflict")
  db.flush()
  return _require_tag(db, uid)


def _assignment_overlaps(
    db,
    tag_uid: str,
    valid_from: datetime,
    valid_to: datetime | None,
) -> bool:
  statement = select(BluetoothAssignment.uid).where(
      BluetoothAssignment.tag_uid == tag_uid,
      or_(BluetoothAssignment.valid_to.is_(None), BluetoothAssignment.valid_to > valid_from),
  )
  if valid_to is not None:
    statement = statement.where(BluetoothAssignment.valid_from < valid_to)
  return db.scalar(statement.limit(1)) is not None


def create_assignment(db, payload: dict[str, Any], actor: str) -> BluetoothAssignment:
  data = AssignmentInput.model_validate(payload)
  _require_tag(db, data.tag_uid)
  if _assignment_overlaps(db, data.tag_uid, data.valid_from, data.valid_to):
    raise BluetoothConflict("assignment_overlap", "Tag already has an overlapping assignment")
  uid = _uid("bt-assignment", data.uid)
  row = BluetoothAssignment(
      uid=uid,
      tag_uid=data.tag_uid,
      entity_type=data.entity_type.value,
      entity_id=data.entity_id,
      display_name=data.display_name,
      valid_from=data.valid_from,
      valid_to=data.valid_to,
      reason=data.reason,
      created_by=actor,
      revision=1,
  )
  try:
    with db.begin_nested():
      db.add(row)
      db.flush()
  except IntegrityError as exc:
    _raise_integrity(exc, "Bluetooth assignment conflicts with an existing assignment")
  return row


def close_assignment(
    db,
    uid: str,
    actor: str,
    expected_revision: int,
    closed_at: datetime | None = None,
) -> BluetoothAssignment:
  row = db.get(BluetoothAssignment, uid)
  if row is None:
    raise BluetoothNotFound("assignment_not_found", f"Bluetooth assignment {uid!r} does not exist")
  if row.revision != expected_revision:
    raise BluetoothRevisionConflict("revision_conflict", "Bluetooth assignment revision conflict")
  if row.valid_to is not None:
    raise BluetoothConflict("assignment_closed", "Bluetooth assignment is already closed")
  closed_at = _as_utc(closed_at or utcnow())
  if closed_at <= _as_utc(row.valid_from):
    raise BluetoothDomainError("invalid_interval", "Assignment close time must be after valid_from")
  result = db.execute(
      update(BluetoothAssignment)
      .where(BluetoothAssignment.uid == uid, BluetoothAssignment.revision == expected_revision)
      .values(
          valid_to=closed_at,
          closed_by=actor,
          revision=expected_revision + 1,
          updated_at=utcnow(),
      )
  )
  if result.rowcount != 1:
    raise BluetoothRevisionConflict("revision_conflict", "Bluetooth assignment revision conflict")
  db.flush()
  db.expire(row)
  db.refresh(row)
  return row


def create_calibration(db, payload: dict[str, Any], actor: str) -> BluetoothCalibration:
  data = CalibrationInput.model_validate(payload)
  anchor = _require_anchor(db, data.anchor_uid)
  _require_scene(db, data.scene_id)
  if anchor.scene_id not in (None, data.scene_id):
    raise BluetoothConflict(
        "anchor_scene_conflict",
        f"Anchor {anchor.uid!r} is already assigned to scene {anchor.scene_id!r}",
    )
  if anchor.scene_id is None:
    anchor.scene_id = data.scene_id
    anchor.revision += 1
    anchor.updated_at = utcnow()
  maximum = db.scalar(
      select(func.max(BluetoothCalibration.calibration_revision)).where(
          BluetoothCalibration.anchor_uid == anchor.uid
      )
  )
  calibration_revision = int(maximum or 0) + 1
  uid = _uid("bt-calibration", data.uid)
  row = BluetoothCalibration(
      uid=uid,
      anchor_uid=anchor.uid,
      scene_id=data.scene_id,
      calibration_revision=calibration_revision,
      state=CalibrationState.DRAFT.value,
      x_m=data.x_m,
      y_m=data.y_m,
      z_m=data.z_m,
      yaw_deg=data.yaw_deg,
      pitch_deg=data.pitch_deg,
      roll_deg=data.roll_deg,
      z_source=data.z_source,
      details=data.details,
      created_by=actor,
      revision=1,
  )
  db.add(row)
  db.flush()
  return row


def activate_calibration(
    db,
    uid: str,
    actor: str,
    expected_revision: int,
) -> BluetoothCalibration:
  del actor
  row = db.get(BluetoothCalibration, uid)
  if row is None:
    raise BluetoothNotFound("calibration_not_found", f"Bluetooth calibration {uid!r} does not exist")
  if row.revision != expected_revision:
    raise BluetoothRevisionConflict("revision_conflict", "Bluetooth calibration revision conflict")
  now = utcnow()
  db.execute(
      update(BluetoothCalibration)
      .where(
          BluetoothCalibration.anchor_uid == row.anchor_uid,
          BluetoothCalibration.uid != uid,
          BluetoothCalibration.state == CalibrationState.ACTIVE.value,
      )
      .values(
          state=CalibrationState.RETIRED.value,
          revision=BluetoothCalibration.revision + 1,
          updated_at=now,
      )
  )
  result = db.execute(
      update(BluetoothCalibration)
      .where(BluetoothCalibration.uid == uid, BluetoothCalibration.revision == expected_revision)
      .values(
          state=CalibrationState.ACTIVE.value,
          revision=expected_revision + 1,
          updated_at=now,
      )
  )
  if result.rowcount != 1:
    raise BluetoothRevisionConflict("revision_conflict", "Bluetooth calibration revision conflict")
  db.flush()
  db.expire(row)
  db.refresh(row)
  return row


def cascade_scene_bluetooth(db, scene_uid: str) -> None:
  now = utcnow()
  anchors = db.scalars(
      select(BluetoothAnchor).where(BluetoothAnchor.scene_id == str(scene_uid))
  ).all()
  for anchor in anchors:
    anchor.scene_id = None
    if anchor.state not in {DeviceState.DISABLED.value, DeviceState.RETIRED.value}:
      anchor.state = DeviceState.MAINTENANCE.value
    anchor.revision += 1
    anchor.updated_at = now

  calibrations = db.scalars(
      select(BluetoothCalibration).where(
          BluetoothCalibration.scene_id == str(scene_uid),
          BluetoothCalibration.state != CalibrationState.RETIRED.value,
      )
  ).all()
  for calibration in calibrations:
    calibration.state = CalibrationState.RETIRED.value
    calibration.revision += 1
    calibration.updated_at = now
  db.flush()


def provider_to_dict(row: BluetoothProvider) -> dict[str, Any]:
  return {
      "uid": row.uid,
      "name": row.name,
      "kind": row.kind,
      "state": row.state,
      "capabilities": list(row.capabilities or []),
      "revision": row.revision,
  }


def anchor_to_dict(row: BluetoothAnchor) -> dict[str, Any]:
  return {**_anchor_payload(row), "revision": row.revision}


def tag_to_dict(row: BluetoothTag) -> dict[str, Any]:
  return {
      **_tag_payload(row),
      "battery": {
          "percent": row.battery_percent,
          "voltage_v": row.battery_voltage_v,
          "status": row.battery_status,
          "source": row.battery_source,
          "observed_at": row.battery_observed_at,
      },
      "revision": row.revision,
  }


def assignment_to_dict(row: BluetoothAssignment) -> dict[str, Any]:
  return {
      "uid": row.uid,
      "tag_uid": row.tag_uid,
      "entity_type": row.entity_type,
      "entity_id": row.entity_id,
      "display_name": row.display_name,
      "valid_from": row.valid_from,
      "valid_to": row.valid_to,
      "reason": row.reason,
      "created_by": row.created_by,
      "closed_by": row.closed_by,
      "revision": row.revision,
  }


def calibration_to_dict(row: BluetoothCalibration) -> dict[str, Any]:
  return {
      "uid": row.uid,
      "anchor_uid": row.anchor_uid,
      "scene_id": row.scene_id,
      "calibration_revision": row.calibration_revision,
      "state": row.state,
      "position": {"x_m": row.x_m, "y_m": row.y_m, "z_m": row.z_m},
      "orientation": {
          "yaw_deg": row.yaw_deg,
          "pitch_deg": row.pitch_deg,
          "roll_deg": row.roll_deg,
      },
      "z_source": row.z_source,
      "details": dict(row.details or {}),
      "revision": row.revision,
  }
