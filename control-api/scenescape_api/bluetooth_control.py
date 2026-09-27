from __future__ import annotations

from sqlalchemy import select, update

from .bluetooth_domain import (
    BluetoothConflict,
    BluetoothNotFound,
    BluetoothRevisionConflict,
    DeviceState,
)
from .database import BluetoothAnchor, BluetoothAssignment, BluetoothCalibration, BluetoothTag, utcnow


_ALLOWED_TRANSITIONS = {
    DeviceState.DISCOVERED.value: {
        DeviceState.COMMISSIONED.value,
        DeviceState.DISABLED.value,
        DeviceState.RETIRED.value,
    },
    DeviceState.COMMISSIONED.value: {
        DeviceState.ACTIVE.value,
        DeviceState.MAINTENANCE.value,
        DeviceState.DISABLED.value,
        DeviceState.RETIRED.value,
    },
    DeviceState.ACTIVE.value: {
        DeviceState.MAINTENANCE.value,
        DeviceState.DISABLED.value,
        DeviceState.RETIRED.value,
    },
    DeviceState.MAINTENANCE.value: {
        DeviceState.ACTIVE.value,
        DeviceState.DISABLED.value,
        DeviceState.RETIRED.value,
    },
    DeviceState.OFFLINE.value: {
        DeviceState.ACTIVE.value,
        DeviceState.MAINTENANCE.value,
        DeviceState.DISABLED.value,
        DeviceState.RETIRED.value,
    },
    DeviceState.DISABLED.value: {
        DeviceState.COMMISSIONED.value,
        DeviceState.ACTIVE.value,
        DeviceState.RETIRED.value,
    },
    DeviceState.RETIRED.value: set(),
}


def _transition(db, model, uid: str, target: DeviceState, expected_revision: int):
  row = db.get(model, uid)
  if row is None:
    kind = "anchor" if model is BluetoothAnchor else "tag"
    raise BluetoothNotFound(f"{kind}_not_found", f"Bluetooth {kind} {uid!r} does not exist")
  if row.revision != expected_revision:
    raise BluetoothRevisionConflict("revision_conflict", "Bluetooth device revision conflict")
  if target.value == row.state:
    return row
  allowed = _ALLOWED_TRANSITIONS.get(str(row.state), set())
  if target.value not in allowed:
    raise BluetoothConflict(
        "invalid_state_transition",
        f"Cannot transition Bluetooth device from {row.state!r} to {target.value!r}",
    )
  result = db.execute(
      update(model)
      .where(model.uid == uid, model.revision == expected_revision)
      .values(
          state=target.value,
          revision=expected_revision + 1,
          updated_at=utcnow(),
      )
  )
  if result.rowcount != 1:
    raise BluetoothRevisionConflict("revision_conflict", "Bluetooth device revision conflict")
  db.flush()
  db.expire(row)
  db.refresh(row)
  return row


def transition_anchor(db, uid: str, target: DeviceState, expected_revision: int):
  return _transition(db, BluetoothAnchor, uid, target, expected_revision)


def transition_tag(db, uid: str, target: DeviceState, expected_revision: int):
  return _transition(db, BluetoothTag, uid, target, expected_revision)


def delete_anchor(db, uid: str, expected_revision: int):
  row = db.get(BluetoothAnchor, uid)
  if row is None:
    raise BluetoothNotFound("anchor_not_found", f"Bluetooth anchor {uid!r} does not exist")
  if row.revision != expected_revision:
    raise BluetoothRevisionConflict("revision_conflict", "Bluetooth anchor revision conflict")
  has_history = db.scalar(
      select(BluetoothCalibration.uid).where(BluetoothCalibration.anchor_uid == uid).limit(1)
  )
  if has_history:
    raise BluetoothConflict(
        "anchor_has_calibration_history",
        "Anchor has calibration history and must be retired instead of deleted",
    )
  db.delete(row)
  db.flush()
  return {"deleted": True, "uid": uid, "kind": "bluetooth_anchor"}


def delete_tag(db, uid: str, expected_revision: int):
  row = db.get(BluetoothTag, uid)
  if row is None:
    raise BluetoothNotFound("tag_not_found", f"Bluetooth tag {uid!r} does not exist")
  if row.revision != expected_revision:
    raise BluetoothRevisionConflict("revision_conflict", "Bluetooth tag revision conflict")
  has_history = db.scalar(
      select(BluetoothAssignment.uid).where(BluetoothAssignment.tag_uid == uid).limit(1)
  )
  if has_history:
    raise BluetoothConflict(
        "tag_has_assignment_history",
        "Tag has assignment history and must be retired instead of deleted",
    )
  db.delete(row)
  db.flush()
  return {"deleted": True, "uid": uid, "kind": "bluetooth_tag"}
