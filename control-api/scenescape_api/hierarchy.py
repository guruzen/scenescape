from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from .database import Resource

CHILD_FIELDS = {
    "uid", "child_type", "transform", "name", "remote_child_id", "child", "parent",
    "host_name", "child_name", "mqtt_username", "mqtt_password", "retrack",
    "transform_type", "cached_rois", "cached_tripwires",
    *(f"transform{i}" for i in range(1, 17)),
}
CACHE_FIELDS = {"cached_rois", "cached_tripwires"}
REMOTE_FIELDS = {"remote_child_id", "child_name", "host_name", "mqtt_username", "mqtt_password"}
TRANSFORM_TYPES = {"matrix", "euler", "quaternion"}
IDENTITY = [
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
]
CHILD_DEFAULTS = {
    "child_type": "local",
    "retrack": True,
    "transform_type": "matrix",
    "cached_rois": [],
    "cached_tripwires": [],
    **{f"transform{i + 1}": value for i, value in enumerate(IDENTITY)},
}


def _bad(field: str, message: str) -> None:
    raise HTTPException(400, detail={field: [message]})


def _child_rows(db) -> list[Resource]:
    return db.scalars(select(Resource).where(Resource.kind == "child").order_by(Resource.id)).all()


def _scene_row(db, uid: str | None) -> Resource | None:
    if uid in (None, ""):
        return None
    return db.scalar(select(Resource).where(Resource.kind == "scene", Resource.uid == str(uid)))


def _scene_required(db, uid: Any, field: str) -> str:
    if uid in (None, ""):
        _bad(field, "required")
    value = str(uid)
    if _scene_row(db, value) is None:
        _bad(field, "Scene with given UUID does not exist.")
    return value


def resolve_child_link(db, uid: str, *, required: bool = True) -> Resource | None:
    """Resolve a child link by link uid, or by its local/remote child id.

    The 2026.2 scenario file inconsistently uses a local child Scene UUID in a
    few /child/{uid} calls although ChildScene.pk is the public serializer uid.
    Accepting both is backward compatible and makes the published contract
    executable without changing the canonical response uid.
    """
    value = str(uid)
    row = db.scalar(select(Resource).where(Resource.kind == "child", Resource.uid == value))
    if row is None:
        for candidate in _child_rows(db):
            payload = candidate.payload or {}
            if value in {str(payload.get("child") or ""), str(payload.get("remote_child_id") or "")}:
                row = candidate
                break
    if row is None and required:
        raise HTTPException(404, "Child scene link not found")
    return row


def _other_child_rows(db, exclude_uid: str | None = None):
    for row in _child_rows(db):
        if exclude_uid is not None and row.uid == str(exclude_uid):
            continue
        yield row


def _would_cycle(db, parent: str, child: str, exclude_uid: str | None = None) -> bool:
    if parent == child:
        return True
    adjacency: dict[str, list[str]] = {}
    for row in _other_child_rows(db, exclude_uid):
        payload = row.payload or {}
        if str(payload.get("child_type") or "local") != "local":
            continue
        existing_parent = payload.get("parent") or payload.get("scene")
        existing_child = payload.get("child")
        if existing_parent and existing_child:
            adjacency.setdefault(str(existing_parent), []).append(str(existing_child))

    # Adding parent -> child is illegal if parent is already reachable from child.
    stack = [child]
    visited: set[str] = set()
    while stack:
        current = stack.pop()
        if current == parent:
            return True
        if current in visited:
            continue
        visited.add(current)
        stack.extend(adjacency.get(current, ()))
    return False


def _validate_cache(value: Any, field: str) -> list:
    if not isinstance(value, list):
        _bad(field, "Must be a list.")
    return deepcopy(value)


def _as_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "on"}:
            return True
        if text in {"false", "0", "no", "off"}:
            return False
    _bad(field, "Must be a valid boolean.")


def _as_number(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        _bad(field, "A valid number is required.")


def _vec3(value: Any, field: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        _bad(field, "Must contain exactly 3 numeric values.")
    return [_as_number(item, field) for item in value]


def _quat_to_euler_xyz_degrees(q: list[float]) -> list[float]:
    x, y, z, w = q
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm == 0:
        _bad("transform", "Quaternion rotation cannot be all zeros.")
    x, y, z, w = (v / norm for v in (x, y, z, w))

    # XYZ intrinsic Euler angles; sufficient for API representation parity.
    sinr_cosp = 2 * (w * x - y * z)
    cosr_cosp = 1 - 2 * (x * x + y * y)
    rx = math.atan2(sinr_cosp, cosr_cosp)
    sinp = 2 * (w * y + z * x)
    ry = math.asin(max(-1.0, min(1.0, sinp)))
    siny_cosp = 2 * (w * z - x * y)
    cosy_cosp = 1 - 2 * (y * y + z * z)
    rz = math.atan2(siny_cosp, cosy_cosp)
    return [math.degrees(rx), math.degrees(ry), math.degrees(rz)]


def _matrix_pose(values: list[float]) -> dict[str, list[float]]:
    # Row-major 4x4 matrix, matching CameraPose.arrayToDictionary(..., "matrix").
    if len(values) != 16:
        _bad("transform", "Matrix transform requires 16 numeric values.")
    m = values
    translation = [m[3], m[7], m[11]]
    sx = math.sqrt(m[0] ** 2 + m[4] ** 2 + m[8] ** 2)
    sy = math.sqrt(m[1] ** 2 + m[5] ** 2 + m[9] ** 2)
    sz = math.sqrt(m[2] ** 2 + m[6] ** 2 + m[10] ** 2)
    scale = [sx, sy, sz]
    if min(scale) <= 1e-12:
        rotation = [0.0, 0.0, 0.0]
    else:
        r00, r01, r02 = m[0] / sx, m[1] / sy, m[2] / sz
        r10, r11, r12 = m[4] / sx, m[5] / sy, m[6] / sz
        r20, r21, r22 = m[8] / sx, m[9] / sy, m[10] / sz
        # XYZ decomposition consistent with scipy Rotation.as_euler('XYZ') for
        # the ordinary non-singular case used by SceneScape hierarchy links.
        ry = math.asin(max(-1.0, min(1.0, r02)))
        cy = math.cos(ry)
        if abs(cy) > 1e-8:
            rx = math.atan2(-r12, r22)
            rz = math.atan2(-r01, r00)
        else:
            rx = math.atan2(r21, r11)
            rz = 0.0
        rotation = [math.degrees(rx), math.degrees(ry), math.degrees(rz)]
    return {"translation": translation, "rotation": rotation, "scale": scale}


def transform_dict(payload: dict) -> dict[str, list[float]]:
    transform_type = str(payload.get("transform_type") or "matrix")
    values = [_as_number(payload.get(f"transform{i}", IDENTITY[i - 1]), f"transform{i}") for i in range(1, 17)]
    if transform_type == "matrix":
        return _matrix_pose(values)
    if transform_type == "euler":
        return {
            "translation": values[0:3],
            "rotation": values[3:6],
            "scale": values[6:9],
        }
    if transform_type == "quaternion":
        return {
            "translation": values[0:3],
            "rotation": _quat_to_euler_xyz_degrees(values[3:7]),
            "scale": values[7:10],
        }
    _bad("transform_type", f'"{transform_type}" is not a valid choice.')


def _apply_transform_object(data: dict) -> None:
    pose = data.pop("transform", None)
    if pose is None:
        return
    if not isinstance(pose, dict):
        _bad("transform", "Must be an object containing translation, rotation and scale.")
    translation = _vec3(pose.get("translation"), "transform.translation")
    rotation_raw = pose.get("rotation")
    if not isinstance(rotation_raw, (list, tuple)) or len(rotation_raw) not in (3, 4):
        _bad("transform.rotation", "Must contain 3 Euler angles or 4 quaternion values.")
    rotation = [_as_number(item, "transform.rotation") for item in rotation_raw]
    scale = _vec3(pose.get("scale"), "transform.scale")
    data["transform_type"] = "quaternion" if len(rotation) == 4 else "euler"
    values = translation + rotation + scale
    for index, value in enumerate(values, start=1):
        data[f"transform{index}"] = value


def _normalize_transform_fields(data: dict) -> None:
    if "transform_type" in data:
        transform_type = str(data["transform_type"])
        if transform_type not in TRANSFORM_TYPES:
            _bad("transform_type", f'"{transform_type}" is not a valid choice.')
        data["transform_type"] = transform_type
    for i in range(1, 17):
        field = f"transform{i}"
        if field in data and data[field] is not None:
            data[field] = _as_number(data[field], field)


def normalize_child(db, body: dict, *, row: Resource | None = None, creating: bool, legacy: bool = False) -> tuple[dict, str | None, bool]:
    if not isinstance(body, dict) or not body:
        _bad("body", "Request body is required.")
    data = deepcopy(body)
    requested_uid = data.pop("uid", None)
    if legacy and requested_uid not in (None, ""):
        _bad("uid", "This field is read-only.")
    if not legacy:
        data.pop("kind", None)
        data.pop("revision", None)

    # name is serializer-computed/read-only.
    data.pop("name", None)
    unknown = set(data) - (CHILD_FIELDS - {"uid", "name"})
    if unknown:
        field = sorted(unknown)[0]
        _bad(field, "Unknown field.")

    cache_only = (not creating) and bool(data) and set(data).issubset(CACHE_FIELDS)
    for field in CACHE_FIELDS & set(data):
        data[field] = _validate_cache(data[field], field)
    if cache_only:
        return data, row.uid if row else None, False

    existing = deepcopy((row.payload or {})) if row is not None else {}
    effective = deepcopy(CHILD_DEFAULTS) if creating else existing
    effective.update(data)
    # Pre-1C nested migration stored the containing scene as ``scene`` rather
    # than ``parent``. Treat it as the parent and canonicalize on any update.
    if not effective.get("parent") and effective.get("scene"):
        effective["parent"] = effective.get("scene")
    _apply_transform_object(effective)
    _normalize_transform_fields(effective)

    child_type = str(effective.get("child_type") or "local")
    if child_type not in {"local", "remote"}:
        _bad("child_type", 'Must be either "local" or "remote".')
    effective["child_type"] = child_type
    parent = _scene_required(db, effective.get("parent"), "parent")
    effective["parent"] = parent

    exclude_uid = row.uid if row is not None else None
    if child_type == "local":
        child = _scene_required(db, effective.get("child"), "child")
        if child == parent:
            _bad("child", "child cannot be the same as parent.")
        for candidate in _other_child_rows(db, exclude_uid):
            payload = candidate.payload or {}
            if str(payload.get("child_type") or "local") != "local":
                continue
            if str(payload.get("child") or "") == child:
                # Mirrors OneToOneField(Scene) -- a local child has one parent.
                _bad("child", f"{child} already has a parent.")
        if _would_cycle(db, parent, child, exclude_uid):
            _bad("child", f'Cannot link "{parent}" with "{child}" due to circular dependency')
        effective["child"] = child
        if creating:
            # On create the 2026.2 serializer does not sanitize remote fields.
            # The model constraint specifically requires child_name to be NULL
            # when a local child FK is present. Other optional remote metadata is
            # tolerated by the tagged model until a later local update clears it.
            if effective.get("child_name") is not None:
                _bad("child_name", "Must be empty for a local child link.")
        else:
            # Local updates clear all remote-only state, as the 2026.2 serializer does.
            for field in REMOTE_FIELDS:
                effective[field] = None
    else:
        for field in ("remote_child_id", "child_name", "host_name", "mqtt_username", "mqtt_password"):
            if not effective.get(field):
                _bad(field, "required")
        remote_id = str(effective["remote_child_id"])
        try:
            remote_id = str(uuid.UUID(remote_id))
        except (ValueError, TypeError, AttributeError):
            _bad("remote_child_id", "Must be a valid UUID.")
        if remote_id == parent:
            _bad("remote_child_id", "remote_child_id cannot be the same as parent.")
        child_name = str(effective["child_name"])
        for candidate in _other_child_rows(db, exclude_uid):
            payload = candidate.payload or {}
            if str(payload.get("remote_child_id") or "") == remote_id:
                _bad("remote_child_id", f"{remote_id} already exists.")
            if str(payload.get("child_type") or "local") == "remote" and str(payload.get("parent") or "") == parent and str(payload.get("child_name") or "") == child_name:
                _bad("child_name", f"{child_name} already exists for this parent.")
        effective["remote_child_id"] = remote_id
        effective["child_name"] = child_name
        effective["child"] = None

    if "retrack" in effective:
        effective["retrack"] = _as_bool(effective["retrack"], "retrack")
    for field in CACHE_FIELDS:
        effective[field] = _validate_cache(effective.get(field, []), field)

    # Preserve only declared persisted fields; uid/name/transform are representation fields.
    persisted = {key: value for key, value in effective.items() if key in CHILD_FIELDS - {"uid", "name", "transform"}}
    resolved_uid = str(requested_uid) if (creating and not legacy and requested_uid not in (None, "")) else (row.uid if row else None)
    return persisted, resolved_uid, True


def create_child_link(db, body: dict, actor, *, legacy: bool = False) -> Resource:
    payload, requested_uid, _ = normalize_child(db, body, creating=True, legacy=legacy)
    uid = requested_uid or f"pending-{uuid.uuid4()}"
    row = Resource(kind="child", uid=uid, payload={**payload, "uid": uid}, revision=1)
    db.add(row)
    db.flush()
    if requested_uid is None:
        # Django exposes the ChildScene PK as uid. Resource.id is the native
        # equivalent durable primary key; expose it as a string in JSON.
        row.uid = str(row.id)
        row.payload = {**payload, "uid": row.uid}
        db.flush()
    return row


def update_child_link(db, row: Resource, body: dict, actor, *, legacy: bool = False, expected_revision: int | None = None) -> tuple[Resource, bool]:
    if expected_revision is not None and row.revision != expected_revision:
        raise HTTPException(409, "Revision conflict")
    payload, _, notify = normalize_child(db, body, row=row, creating=False, legacy=legacy)
    current = dict(row.payload or {})
    if notify:
        # A normal hierarchy edit canonicalizes the pre-1C ``scene`` parent
        # artifact. Cache-only writes intentionally leave hierarchy fields alone.
        current.pop("scene", None)
    row.payload = {**current, **payload, "uid": row.uid}
    row.revision += 1
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return row, notify


def child_to_dict(db, row: Resource, *, native: bool = False) -> dict:
    payload = deepcopy(CHILD_DEFAULTS)
    payload.update(row.payload or {})
    if not payload.get("parent") and payload.get("scene"):
        payload["parent"] = payload.get("scene")
    payload.pop("scene", None)  # remove pre-1C migration artifact if present
    payload["uid"] = row.uid

    child_type = str(payload.get("child_type") or "local")
    if child_type == "local":
        scene = _scene_row(db, str(payload.get("child") or ""))
        payload["name"] = str((scene.payload or {}).get("name") or scene.uid) if scene else str(payload.get("child") or "")
    else:
        payload["name"] = str(payload.get("child_name") or "")
    payload["transform"] = transform_dict(payload)

    if native:
        payload["revision"] = row.revision
        payload["kind"] = row.kind

    result = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)) and not value:
            continue
        result[key] = value
    return result


def cascade_scene_links(db, scene_uid: str) -> list[str]:
    deleted: list[str] = []
    value = str(scene_uid)
    for row in list(_child_rows(db)):
        payload = row.payload or {}
        if str(payload.get("parent") or payload.get("scene") or "") == value or str(payload.get("child") or "") == value:
            deleted.append(row.uid)
            db.delete(row)
    db.flush()
    return deleted


def local_child_rows_for_parent(db, parent_uid: str) -> list[Resource]:
    value = str(parent_uid)
    return [
        row for row in _child_rows(db)
        if str((row.payload or {}).get("parent") or (row.payload or {}).get("scene") or "") == value
        and str((row.payload or {}).get("child_type") or "local") == "local"
    ]


def remote_child_rows_for_parent(db, parent_uid: str) -> list[Resource]:
    value = str(parent_uid)
    return [
        row for row in _child_rows(db)
        if str((row.payload or {}).get("parent") or (row.payload or {}).get("scene") or "") == value
        and str((row.payload or {}).get("child_type") or "local") == "remote"
    ]
