from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from .auth import Principal, browser_principal, service_principal
from .bluetooth_calibration import calibration_public, geometry_report
from .bluetooth_control import delete_anchor, delete_tag, transition_anchor, transition_tag
from .bluetooth_telemetry import DeviceTelemetryEnvelope, ingest_device_telemetry, latest_device_telemetry, telemetry_public
from .bluetooth_survey import add_survey_sample, close_survey_point, coverage_diagnostics, create_bias_calibration_revisions, create_survey_point, estimate_anchor_biases
from .bluetooth_pipeline import runtime_diagnostics as pipeline_runtime_diagnostics
from .bluetooth_ingest import (
    MeasurementRejected,
    RangeEnvelope,
    ingest_measurement,
    measurement_to_dict,
    metrics as ingress_metrics,
)
from .bluetooth_domain import (
    AnchorInput,
    AnchorPatch,
    AssignmentInput,
    CalibrationInput,
    CalibrationState,
    BluetoothConflict,
    BluetoothDomainError,
    BluetoothNotFound,
    BluetoothRevisionConflict,
    DeviceState,
    TagInput,
    TagPatch,
    activate_calibration,
    anchor_to_dict,
    assignment_to_dict,
    close_assignment,
    create_anchor,
    create_assignment,
    create_calibration,
    create_tag,
    calibration_to_dict,
    tag_to_dict,
    update_anchor,
    update_tag,
)
from .database import (
    BluetoothAnchor,
    BluetoothAssignment,
    BluetoothAudit,
    BluetoothCalibration,
    BluetoothMeasurement,
    BluetoothTag,
    sessions,
    utcnow,
)


router = APIRouter(prefix="/api/v2/bluetooth", tags=["Bluetooth positioning"])


class AssignmentCloseBody(BaseModel):
  model_config = ConfigDict(extra="forbid")
  closed_at: datetime | None = None


def db_dep():
  db = sessions()()
  try:
    yield db
  finally:
    db.close()


def _admin(p: Principal) -> None:
  if not p.is_admin:
    raise HTTPException(403, detail={"code": "admin_required", "message": "Administrator role required"})


def _scene_allowed(p: Principal, scene_id: str | None) -> None:
  if p.is_admin or "*" in p.scene_scopes:
    return
  value = str(scene_id or "")
  if value and value in p.scene_scopes:
    return
  raise HTTPException(
      403,
      detail={"code": "scene_scope_denied", "message": "Bluetooth resource is outside token scene scope"},
  )


def _domain_call(fn, *args, **kwargs):
  try:
    return fn(*args, **kwargs)
  except BluetoothNotFound as exc:
    raise HTTPException(404, detail={"code": exc.code, "message": exc.message}) from exc
  except BluetoothRevisionConflict as exc:
    raise HTTPException(409, detail={"code": exc.code, "message": exc.message}) from exc
  except BluetoothConflict as exc:
    raise HTTPException(409, detail={"code": exc.code, "message": exc.message}) from exc
  except BluetoothDomainError as exc:
    raise HTTPException(422, detail={"code": exc.code, "message": exc.message}) from exc


def _audit(
    db,
    p: Principal,
    action: str,
    resource_type: str,
    resource_uid: str,
    *,
    scene_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
  db.add(
      BluetoothAudit(
          actor=p.subject,
          action=action,
          resource_type=resource_type,
          resource_uid=resource_uid,
          scene_id=scene_id,
          details=details or {},
          observed_at=utcnow(),
      )
  )


def _page(db, statement, model, offset: int, limit: int, serializer):
  count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
  total = int(db.scalar(count_statement) or 0)
  rows = db.scalars(statement.offset(offset).limit(limit)).all()
  return {
      "items": [serializer(row) for row in rows],
      "total": total,
      "offset": offset,
      "limit": limit,
  }


def _anchor_statement(
    p: Principal,
    *,
    scene_id: str | None,
    state: DeviceState | None,
    serial: str | None,
    provider_id: str | None,
):
  statement = select(BluetoothAnchor).order_by(BluetoothAnchor.serial_number, BluetoothAnchor.uid)
  if not (p.is_admin or "*" in p.scene_scopes):
    if scene_id is not None and scene_id not in p.scene_scopes:
      _scene_allowed(p, scene_id)
    scopes = list(p.scene_scopes)
    if not scopes:
      return statement.where(BluetoothAnchor.uid == "__no_authorized_scene__")
    statement = statement.where(BluetoothAnchor.scene_id.in_(scopes))
  if scene_id is not None:
    statement = statement.where(BluetoothAnchor.scene_id == scene_id)
  if state is not None:
    statement = statement.where(BluetoothAnchor.state == state.value)
  if serial:
    statement = statement.where(func.lower(BluetoothAnchor.serial_number).contains(serial.casefold()))
  if provider_id:
    statement = statement.where(BluetoothAnchor.provider_id == provider_id)
  return statement


@router.get("/anchors", summary="List Bluetooth anchors")
def list_anchors(
    scene_id: str | None = Query(default=None, max_length=96),
    state: DeviceState | None = None,
    serial: str | None = Query(default=None, max_length=128),
    provider_id: str | None = Query(default=None, max_length=96),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  statement = _anchor_statement(
      p,
      scene_id=scene_id,
      state=state,
      serial=serial,
      provider_id=provider_id,
  )
  return _page(db, statement, BluetoothAnchor, offset, limit, anchor_to_dict)


@router.get("/anchors/{anchor_id}", summary="Get a Bluetooth anchor")
def get_anchor(anchor_id: str, p: Principal = Depends(browser_principal), db=Depends(db_dep)):
  row = db.get(BluetoothAnchor, anchor_id)
  if row is None:
    raise HTTPException(404, detail={"code": "anchor_not_found", "message": "Bluetooth anchor not found"})
  _scene_allowed(p, row.scene_id)
  return anchor_to_dict(row)


@router.post("/anchors", summary="Commission a Bluetooth anchor")
def add_anchor(
    body: Annotated[
        AnchorInput,
        Body(
            openapi_examples={
                "channel-sounding-anchor": {
                    "summary": "Commission a fixed Channel Sounding anchor",
                    "value": {
                        "serial_number": "ANCHOR-00042",
                        "scene_id": "warehouse-a",
                        "provider_device_id": None,
                        "capabilities": ["channel_sounding"],
                    },
                }
            }
        ),
    ],
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _admin(p)
  if body.state not in {DeviceState.DISCOVERED, DeviceState.COMMISSIONED}:
    raise HTTPException(
        422,
        detail={"code": "invalid_initial_state", "message": "New anchors must be discovered or commissioned"},
    )
  row = _domain_call(create_anchor, db, body.model_dump(mode="python"), p.subject)
  _audit(db, p, "create", "anchor", row.uid, scene_id=row.scene_id)
  db.commit()
  return anchor_to_dict(row)


@router.patch("/anchors/{anchor_id}", summary="Update Bluetooth anchor metadata")
def edit_anchor(
    anchor_id: str,
    body: AnchorPatch,
    revision: int = Query(..., ge=1),
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _admin(p)
  if body.state is not None:
    raise HTTPException(
        422,
        detail={"code": "state_transition_required", "message": "Use a lifecycle action to change state"},
    )
  row = _domain_call(
      update_anchor,
      db,
      anchor_id,
      body.model_dump(exclude_unset=True, mode="python"),
      p.subject,
      revision,
  )
  _audit(
      db,
      p,
      "update",
      "anchor",
      row.uid,
      scene_id=row.scene_id,
      details={"fields": sorted(body.model_fields_set)},
  )
  db.commit()
  return anchor_to_dict(row)


def _anchor_lifecycle(anchor_id: str, target: DeviceState, revision: int, p: Principal, db):
  _admin(p)
  row = _domain_call(transition_anchor, db, anchor_id, target, revision)
  _audit(db, p, f"state:{target.value}", "anchor", row.uid, scene_id=row.scene_id)
  db.commit()
  return anchor_to_dict(row)


@router.post("/anchors/{anchor_id}/activate")
def activate_anchor(anchor_id: str, revision: int = Query(..., ge=1), p: Principal = Depends(browser_principal), db=Depends(db_dep)):
  return _anchor_lifecycle(anchor_id, DeviceState.ACTIVE, revision, p, db)


@router.post("/anchors/{anchor_id}/deactivate")
def deactivate_anchor(anchor_id: str, revision: int = Query(..., ge=1), p: Principal = Depends(browser_principal), db=Depends(db_dep)):
  return _anchor_lifecycle(anchor_id, DeviceState.DISABLED, revision, p, db)


@router.post("/anchors/{anchor_id}/maintenance")
def maintain_anchor(anchor_id: str, revision: int = Query(..., ge=1), p: Principal = Depends(browser_principal), db=Depends(db_dep)):
  return _anchor_lifecycle(anchor_id, DeviceState.MAINTENANCE, revision, p, db)


@router.post("/anchors/{anchor_id}/retire")
def retire_anchor(anchor_id: str, revision: int = Query(..., ge=1), p: Principal = Depends(browser_principal), db=Depends(db_dep)):
  return _anchor_lifecycle(anchor_id, DeviceState.RETIRED, revision, p, db)


@router.delete("/anchors/{anchor_id}")
def remove_anchor(anchor_id: str, revision: int = Query(..., ge=1), p: Principal = Depends(browser_principal), db=Depends(db_dep)):
  _admin(p)
  current = db.get(BluetoothAnchor, anchor_id)
  scene_id = current.scene_id if current else None
  result = _domain_call(delete_anchor, db, anchor_id, revision)
  _audit(db, p, "delete", "anchor", anchor_id, scene_id=scene_id)
  db.commit()
  return result


def _tags_admin(p: Principal) -> None:
  _admin(p)


@router.get("/tags", summary="List Bluetooth tags")
def list_tags(
    state: DeviceState | None = None,
    serial: str | None = Query(default=None, max_length=128),
    provider_id: str | None = Query(default=None, max_length=96),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _tags_admin(p)
  statement = select(BluetoothTag).order_by(BluetoothTag.serial_number, BluetoothTag.uid)
  if state is not None:
    statement = statement.where(BluetoothTag.state == state.value)
  if serial:
    statement = statement.where(func.lower(BluetoothTag.serial_number).contains(serial.casefold()))
  if provider_id:
    statement = statement.where(BluetoothTag.provider_id == provider_id)
  return _page(db, statement, BluetoothTag, offset, limit, tag_to_dict)


@router.get("/tags/{tag_id}", summary="Get a Bluetooth tag")
def get_tag(tag_id: str, p: Principal = Depends(browser_principal), db=Depends(db_dep)):
  _tags_admin(p)
  row = db.get(BluetoothTag, tag_id)
  if row is None:
    raise HTTPException(404, detail={"code": "tag_not_found", "message": "Bluetooth tag not found"})
  return tag_to_dict(row)


@router.post("/tags", summary="Commission a Bluetooth tag")
def add_tag(
    body: Annotated[
        TagInput,
        Body(
            openapi_examples={
                "channel-sounding-tag": {
                    "summary": "Commission a mobile tag",
                    "value": {
                        "serial_number": "TAG-00421",
                        "capabilities": ["channel_sounding", "battery_service"],
                    },
                }
            }
        ),
    ],
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _tags_admin(p)
  if body.state not in {DeviceState.DISCOVERED, DeviceState.COMMISSIONED}:
    raise HTTPException(
        422,
        detail={"code": "invalid_initial_state", "message": "New tags must be discovered or commissioned"},
    )
  row = _domain_call(create_tag, db, body.model_dump(mode="python"), p.subject)
  _audit(db, p, "create", "tag", row.uid)
  db.commit()
  return tag_to_dict(row)


@router.patch("/tags/{tag_id}", summary="Update Bluetooth tag metadata")
def edit_tag(
    tag_id: str,
    body: TagPatch,
    revision: int = Query(..., ge=1),
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _tags_admin(p)
  if body.state is not None:
    raise HTTPException(
        422,
        detail={"code": "state_transition_required", "message": "Use a lifecycle action to change state"},
    )
  row = _domain_call(
      update_tag,
      db,
      tag_id,
      body.model_dump(exclude_unset=True, mode="python"),
      p.subject,
      revision,
  )
  _audit(db, p, "update", "tag", row.uid, details={"fields": sorted(body.model_fields_set)})
  db.commit()
  return tag_to_dict(row)


def _tag_lifecycle(tag_id: str, target: DeviceState, revision: int, p: Principal, db):
  _tags_admin(p)
  row = _domain_call(transition_tag, db, tag_id, target, revision)
  _audit(db, p, f"state:{target.value}", "tag", row.uid)
  db.commit()
  return tag_to_dict(row)


@router.post("/tags/{tag_id}/activate")
def activate_tag(tag_id: str, revision: int = Query(..., ge=1), p: Principal = Depends(browser_principal), db=Depends(db_dep)):
  return _tag_lifecycle(tag_id, DeviceState.ACTIVE, revision, p, db)


@router.post("/tags/{tag_id}/deactivate")
def deactivate_tag(tag_id: str, revision: int = Query(..., ge=1), p: Principal = Depends(browser_principal), db=Depends(db_dep)):
  return _tag_lifecycle(tag_id, DeviceState.DISABLED, revision, p, db)


@router.post("/tags/{tag_id}/maintenance")
def maintain_tag(tag_id: str, revision: int = Query(..., ge=1), p: Principal = Depends(browser_principal), db=Depends(db_dep)):
  return _tag_lifecycle(tag_id, DeviceState.MAINTENANCE, revision, p, db)


@router.post("/tags/{tag_id}/retire")
def retire_tag(tag_id: str, revision: int = Query(..., ge=1), p: Principal = Depends(browser_principal), db=Depends(db_dep)):
  return _tag_lifecycle(tag_id, DeviceState.RETIRED, revision, p, db)


@router.delete("/tags/{tag_id}")
def remove_tag(tag_id: str, revision: int = Query(..., ge=1), p: Principal = Depends(browser_principal), db=Depends(db_dep)):
  _tags_admin(p)
  result = _domain_call(delete_tag, db, tag_id, revision)
  _audit(db, p, "delete", "tag", tag_id)
  db.commit()
  return result


@router.get("/assignments", summary="List Bluetooth tag assignments")
def list_assignments(
    tag_id: str | None = Query(default=None, max_length=96),
    entity_type: str | None = Query(default=None, max_length=32),
    entity_id: str | None = Query(default=None, max_length=160),
    active: bool | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _admin(p)
  statement = select(BluetoothAssignment).order_by(
      BluetoothAssignment.valid_from.desc(), BluetoothAssignment.uid
  )
  if tag_id:
    statement = statement.where(BluetoothAssignment.tag_uid == tag_id)
  if entity_type:
    statement = statement.where(BluetoothAssignment.entity_type == entity_type)
  if entity_id:
    statement = statement.where(BluetoothAssignment.entity_id == entity_id)
  if active is True:
    statement = statement.where(BluetoothAssignment.valid_to.is_(None))
  elif active is False:
    statement = statement.where(BluetoothAssignment.valid_to.is_not(None))
  return _page(db, statement, BluetoothAssignment, offset, limit, assignment_to_dict)


@router.get("/tags/{tag_id}/assignments", summary="Get assignment history for a tag")
def tag_assignment_history(
    tag_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _admin(p)
  if db.get(BluetoothTag, tag_id) is None:
    raise HTTPException(404, detail={"code": "tag_not_found", "message": "Bluetooth tag not found"})
  statement = (
      select(BluetoothAssignment)
      .where(BluetoothAssignment.tag_uid == tag_id)
      .order_by(BluetoothAssignment.valid_from.desc(), BluetoothAssignment.uid)
  )
  return _page(db, statement, BluetoothAssignment, offset, limit, assignment_to_dict)


@router.post("/assignments", summary="Assign a Bluetooth tag")
def add_assignment(
    body: Annotated[
        AssignmentInput,
        Body(
            openapi_examples={
                "asset-assignment": {
                    "summary": "Assign a tag to an asset",
                    "value": {
                        "tag_uid": "tag-00421",
                        "entity_type": "asset",
                        "entity_id": "forklift-27",
                        "display_name": "Forklift 27",
                        "reason": "commissioning",
                    },
                }
            }
        ),
    ],
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _admin(p)
  row = _domain_call(create_assignment, db, body.model_dump(mode="python"), p.subject)
  _audit(
      db,
      p,
      "create",
      "assignment",
      row.uid,
      details={"tag_uid": row.tag_uid, "entity_type": row.entity_type},
  )
  db.commit()
  return assignment_to_dict(row)


@router.post("/assignments/{assignment_id}/close", summary="Close a tag assignment")
def end_assignment(
    assignment_id: str,
    body: AssignmentCloseBody,
    revision: int = Query(..., ge=1),
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _admin(p)
  row = _domain_call(
      close_assignment,
      db,
      assignment_id,
      p.subject,
      revision,
      body.closed_at,
  )
  _audit(
      db,
      p,
      "close",
      "assignment",
      row.uid,
      details={"tag_uid": row.tag_uid, "entity_type": row.entity_type},
  )
  db.commit()
  return assignment_to_dict(row)


@router.get("/calibrations", summary="List Bluetooth anchor calibration revisions")
def list_calibrations(
    scene_id: str | None = Query(default=None, max_length=96),
    anchor_id: str | None = Query(default=None, max_length=96),
    state: CalibrationState | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  statement = select(BluetoothCalibration)
  if not (p.is_admin or "*" in p.scene_scopes):
    if scene_id is not None:
      _scene_allowed(p, scene_id)
    scopes = list(p.scene_scopes)
    if not scopes:
      statement = statement.where(BluetoothCalibration.uid == "__no_authorized_scene__")
    else:
      statement = statement.where(BluetoothCalibration.scene_id.in_(scopes))
  if scene_id:
    statement = statement.where(BluetoothCalibration.scene_id == scene_id)
  if anchor_id:
    statement = statement.where(BluetoothCalibration.anchor_uid == anchor_id)
  if state is not None:
    statement = statement.where(BluetoothCalibration.state == state.value)
  statement = statement.order_by(
      BluetoothCalibration.anchor_uid,
      BluetoothCalibration.calibration_revision.desc(),
  )
  total = int(
      db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
  )
  rows = db.scalars(statement.offset(offset).limit(limit)).all()
  return {
      "items": [calibration_public(db, row) for row in rows],
      "total": total,
      "offset": offset,
      "limit": limit,
  }


@router.get(
    "/anchors/{anchor_id}/calibrations",
    summary="Get calibration history for one anchor",
)
def anchor_calibration_history(
    anchor_id: str,
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  anchor = db.get(BluetoothAnchor, anchor_id)
  if anchor is None:
    raise HTTPException(
        404,
        detail={"code": "anchor_not_found", "message": "Bluetooth anchor not found"},
    )
  _scene_allowed(p, anchor.scene_id)
  rows = db.scalars(
      select(BluetoothCalibration)
      .where(BluetoothCalibration.anchor_uid == anchor_id)
      .order_by(BluetoothCalibration.calibration_revision.desc())
  ).all()
  return {
      "items": [calibration_public(db, row) for row in rows],
      "total": len(rows),
  }


@router.get("/calibrations/geometry", summary="Evaluate Bluetooth anchor geometry")
def calibration_geometry(
    scene_id: str = Query(..., min_length=1, max_length=96),
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _scene_allowed(p, scene_id)
  rows = db.scalars(
      select(BluetoothCalibration).where(BluetoothCalibration.scene_id == scene_id)
  ).all()
  return {"scene_id": scene_id, **geometry_report(rows)}


@router.post("/calibrations", summary="Create a draft Bluetooth anchor calibration")
def add_calibration(
    body: Annotated[
        CalibrationInput,
        Body(
            openapi_examples={
                "floor-map-placement": {
                    "summary": "Draft a scene-local anchor placement",
                    "value": {
                        "anchor_uid": "anchor-a1",
                        "scene_id": "scene-123",
                        "x_m": 2.2,
                        "y_m": 3.1,
                        "z_m": 3.2,
                        "yaw_deg": 0,
                        "pitch_deg": 0,
                        "roll_deg": 0,
                        "z_source": "surveyed",
                    },
                }
            }
        ),
    ],
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _admin(p)
  row = _domain_call(
      create_calibration,
      db,
      body.model_dump(mode="python"),
      p.subject,
  )
  _audit(
      db,
      p,
      "draft:create",
      "calibration",
      row.uid,
      scene_id=row.scene_id,
      details={
          "anchor_uid": row.anchor_uid,
          "calibration_revision": row.calibration_revision,
      },
  )
  db.commit()
  return calibration_public(db, row)


@router.post(
    "/calibrations/{calibration_id}/publish",
    summary="Publish a draft Bluetooth calibration",
)
def publish_calibration(
    calibration_id: str,
    revision: int = Query(..., ge=1),
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _admin(p)
  current = db.get(BluetoothCalibration, calibration_id)
  if current is None:
    raise HTTPException(
        404,
        detail={
            "code": "calibration_not_found",
            "message": "Bluetooth calibration not found",
        },
    )
  if current.state != CalibrationState.DRAFT.value:
    raise HTTPException(
        409,
        detail={
            "code": "calibration_not_draft",
            "message": "Only draft calibration revisions can be published",
        },
    )
  row = _domain_call(
      activate_calibration,
      db,
      calibration_id,
      p.subject,
      revision,
  )
  _audit(
      db,
      p,
      "publish",
      "calibration",
      row.uid,
      scene_id=row.scene_id,
      details={
          "anchor_uid": row.anchor_uid,
          "calibration_revision": row.calibration_revision,
      },
  )
  db.commit()
  return calibration_public(db, row)


@router.post(
    "/calibrations/{calibration_id}/restore",
    summary="Restore a retired Bluetooth calibration",
)
def restore_calibration(
    calibration_id: str,
    revision: int = Query(..., ge=1),
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _admin(p)
  current = db.get(BluetoothCalibration, calibration_id)
  if current is None:
    raise HTTPException(
        404,
        detail={
            "code": "calibration_not_found",
            "message": "Bluetooth calibration not found",
        },
    )
  if current.state != CalibrationState.RETIRED.value:
    raise HTTPException(
        409,
        detail={
            "code": "calibration_not_retired",
            "message": "Only retired calibration revisions can be restored",
        },
    )
  row = _domain_call(
      activate_calibration,
      db,
      calibration_id,
      p.subject,
      revision,
  )
  _audit(
      db,
      p,
      "restore",
      "calibration",
      row.uid,
      scene_id=row.scene_id,
      details={
          "anchor_uid": row.anchor_uid,
          "calibration_revision": row.calibration_revision,
      },
  )
  db.commit()
  return calibration_public(db, row)


@router.post(
    "/measurements",
    status_code=202,
    summary="Ingest one normalized Bluetooth range measurement",
)
def add_measurement(
    body: RangeEnvelope,
    p: Principal = Depends(service_principal),
    db=Depends(db_dep),
):
  if body.payload.provider_id != p.subject:
    raise HTTPException(
        403,
        detail={
            "code": "provider_scope_denied",
            "message": "Service identity may ingest only its matching Bluetooth provider ID",
        },
    )
  try:
    row = ingest_measurement(db, body)
  except MeasurementRejected as exc:
    status = 409 if exc.code in {"duplicate", "out_of_order"} else 422
    raise HTTPException(
        status,
        detail={"code": exc.code, "message": exc.message},
    ) from exc
  db.commit()
  return {"accepted": True, "measurement": measurement_to_dict(row)}


@router.post(
    "/telemetry",
    status_code=202,
    summary="Ingest normalized Bluetooth device telemetry",
)
def add_device_telemetry(
    body: DeviceTelemetryEnvelope,
    p: Principal = Depends(service_principal),
    db=Depends(db_dep),
):
  if body.provider_id != p.subject:
    raise HTTPException(
        403,
        detail={
            "code": "provider_scope_denied",
            "message": "Service identity may ingest only its matching Bluetooth provider ID",
        },
    )
  try:
    row = ingest_device_telemetry(db, body)
  except ValueError as exc:
    raise HTTPException(
        422,
        detail={"code": "invalid_device_telemetry", "message": str(exc)},
    ) from exc
  db.commit()
  return {"accepted": True, "telemetry": telemetry_public(row)}


@router.get("/tags/{tag_id}/telemetry", summary="Read latest Bluetooth tag telemetry")
def get_tag_telemetry(
    tag_id: str,
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _admin(p)
  if db.get(BluetoothTag, tag_id) is None:
    raise HTTPException(
        404,
        detail={"code": "tag_not_found", "message": "Bluetooth tag not found"},
    )
  row = latest_device_telemetry(db, "tag", tag_id)
  return {"device_type": "tag", "device_id": tag_id, "telemetry": telemetry_public(row) if row else None}


@router.get("/anchors/{anchor_id}/telemetry", summary="Read latest Bluetooth anchor telemetry")
def get_anchor_telemetry(
    anchor_id: str,
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  anchor = db.get(BluetoothAnchor, anchor_id)
  if anchor is None:
    raise HTTPException(
        404,
        detail={"code": "anchor_not_found", "message": "Bluetooth anchor not found"},
    )
  _scene_allowed(p, anchor.scene_id)
  row = latest_device_telemetry(db, "anchor", anchor_id)
  return {"device_type": "anchor", "device_id": anchor_id, "telemetry": telemetry_public(row) if row else None}


@router.post("/surveys/points", summary="Create Bluetooth survey point")
def create_bt_survey_point(
    body: dict,
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _admin(p)
  try:
    point = create_survey_point(
        db,
        scene_id=str(body.get("scene_id") or ""),
        name=str(body.get("name") or ""),
        x_m=body.get("x_m"),
        y_m=body.get("y_m"),
        z_m=body.get("z_m"),
        actor=p.subject,
        uid=body.get("uid"),
    )
  except (TypeError, ValueError) as exc:
    raise HTTPException(422, detail={"code": "invalid_survey_point", "message": str(exc)}) from exc
  _audit(db, p, "create", "survey_point", point.uid, scene_id=point.scene_id)
  db.commit()
  return {
      "uid": point.uid,
      "scene_id": point.scene_id,
      "name": point.name,
      "position": {"x_m": point.x_m, "y_m": point.y_m, "z_m": point.z_m},
      "state": point.state,
  }


@router.post("/surveys/points/{point_id}/samples", summary="Add Bluetooth survey range sample")
def add_bt_survey_sample(
    point_id: str,
    body: dict,
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _admin(p)
  try:
    sample = add_survey_sample(
        db,
        survey_point_uid=point_id,
        anchor_uid=str(body.get("anchor_uid") or ""),
        distance_m=body.get("distance_m"),
        distance_stddev_m=body.get("distance_stddev_m", 0.05),
        quality=body.get("quality", 1.0),
        observed_at=(
            datetime.fromisoformat(str(body["observed_at"]).replace("Z", "+00:00"))
            if body.get("observed_at")
            else utcnow()
        ),
        details=body.get("details") or {},
    )
  except (TypeError, ValueError) as exc:
    raise HTTPException(422, detail={"code": "invalid_survey_sample", "message": str(exc)}) from exc
  _audit(db, p, "sample", "survey_point", point_id, details={"sample_id": sample.id, "anchor_uid": sample.anchor_uid})
  db.commit()
  return {"id": sample.id, "survey_point_uid": sample.survey_point_uid, "anchor_uid": sample.anchor_uid}


@router.post("/surveys/points/{point_id}/close", summary="Close Bluetooth survey point")
def close_bt_survey_point(
    point_id: str,
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _admin(p)
  try:
    point = close_survey_point(db, point_id)
  except ValueError as exc:
    raise HTTPException(404, detail={"code": "survey_point_not_found", "message": str(exc)}) from exc
  _audit(db, p, "close", "survey_point", point.uid, scene_id=point.scene_id)
  db.commit()
  return {"uid": point.uid, "state": point.state}


@router.get("/surveys/bias", summary="Estimate Bluetooth anchor range bias")
def get_bt_survey_bias(
    scene_id: str,
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _scene_allowed(p, scene_id)
  return {"scene_id": scene_id, "anchors": estimate_anchor_biases(db, scene_id)}


@router.post("/surveys/bias/revisions", summary="Create draft bias-corrected calibration revisions")
def create_bt_bias_revisions(
    scene_id: str,
    minimum_samples: int = Query(default=3, ge=3, le=10000),
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _admin(p)
  try:
    rows = create_bias_calibration_revisions(
        db,
        scene_id,
        p.subject,
        minimum_samples=minimum_samples,
    )
  except ValueError as exc:
    raise HTTPException(422, detail={"code": "bias_estimation_failed", "message": str(exc)}) from exc
  for row in rows:
    _audit(
        db,
        p,
        "create_bias_revision",
        "calibration",
        row.uid,
        scene_id=scene_id,
        details={"anchor_uid": row.anchor_uid, "calibration_revision": row.calibration_revision},
    )
  db.commit()
  return {"scene_id": scene_id, "created": [calibration_to_dict(row) for row in rows]}


@router.get("/surveys/coverage", summary="Read Bluetooth geometry and observed survey coverage")
def get_bt_survey_coverage(
    scene_id: str,
    min_x_m: float,
    max_x_m: float,
    min_y_m: float,
    max_y_m: float,
    step_m: float = Query(default=1.0, gt=0.0, le=1000.0),
    fixed_z_m: float = 1.0,
    p: Principal = Depends(browser_principal),
    db=Depends(db_dep),
):
  _scene_allowed(p, scene_id)
  try:
    return coverage_diagnostics(
        db,
        scene_id,
        min_x_m=min_x_m,
        max_x_m=max_x_m,
        min_y_m=min_y_m,
        max_y_m=max_y_m,
        step_m=step_m,
        fixed_z_m=fixed_z_m,
    )
  except ValueError as exc:
    raise HTTPException(422, detail={"code": "invalid_coverage_request", "message": str(exc)}) from exc


@router.get("/diagnostics", summary="Read Bluetooth control-plane diagnostics")
def diagnostics(p: Principal = Depends(browser_principal), db=Depends(db_dep)):
  anchor_statement = _anchor_statement(
      p,
      scene_id=None,
      state=None,
      serial=None,
      provider_id=None,
  )
  anchors = db.scalars(anchor_statement).all()
  anchor_states: dict[str, int] = {}
  for row in anchors:
    anchor_states[row.state] = anchor_states.get(row.state, 0) + 1

  value: dict[str, Any] = {
      "anchors": {
          "total": len(anchors),
          "by_state": anchor_states,
          "unassigned_scene": sum(1 for row in anchors if not row.scene_id),
      },
      "tags": {"visible": False},
      "scope": {
          "all_scenes": bool(p.is_admin or "*" in p.scene_scopes),
          "scenes": sorted(p.scene_scopes),
      },
  }
  if p.is_admin or "*" in p.scene_scopes:
    tags = db.scalars(select(BluetoothTag)).all()
    tag_states: dict[str, int] = {}
    battery_states: dict[str, int] = {}
    for row in tags:
      tag_states[row.state] = tag_states.get(row.state, 0) + 1
      battery_states[row.battery_status] = battery_states.get(row.battery_status, 0) + 1
    value["tags"] = {
        "visible": True,
        "total": len(tags),
        "by_state": tag_states,
        "battery": battery_states,
    }
    raw_count = int(db.scalar(select(func.count()).select_from(BluetoothMeasurement)) or 0)
    oldest = db.scalar(select(func.min(BluetoothMeasurement.source_timestamp)))
    newest = db.scalar(select(func.max(BluetoothMeasurement.source_timestamp)))
    value["ingress"] = {
        "visible": True,
        "raw_measurements": raw_count,
        "oldest_source_timestamp": oldest,
        "newest_source_timestamp": newest,
        "process_metrics": ingress_metrics.snapshot(),
        "pipeline": pipeline_runtime_diagnostics(),
    }
  else:
    value["ingress"] = {"visible": False}
  return value
