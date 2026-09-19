from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from .database import Resource

MARKER_FIELDS = {'marker_id', 'apriltag_id', 'dims', 'scene'}


def _bad(field: str, message: str):
    raise HTTPException(400, {field: [message]})


def _scene_exists(db, uid: str) -> bool:
    return db.scalar(select(Resource.id).where(Resource.kind == 'scene', Resource.uid == str(uid)).limit(1)) is not None


def resolve_marker(db, marker_id: str, *, required: bool = True) -> Resource | None:
    value = str(marker_id)
    row = db.scalar(select(Resource).where(Resource.kind == 'marker', Resource.uid == value))
    if row is None:
        # Compatibility with the early native migration that used scene:marker.
        for candidate in db.scalars(select(Resource).where(Resource.kind == 'marker').order_by(Resource.id)).all():
            payload = candidate.payload or {}
            if str(payload.get('marker_id') or payload.get('uid') or '') == value:
                row = candidate
                break
    if row is None and required:
        raise HTTPException(404, 'Calibration marker not found')
    return row


def normalize_marker(db, body: dict[str, Any], *, row: Resource | None = None, creating: bool) -> tuple[dict, str]:
    if not isinstance(body, dict) or not body:
        _bad('body', 'Request body is required.')
    data = deepcopy(body)
    # Native metadata may round-trip through the React JSON editor.
    data.pop('kind', None)
    data.pop('revision', None)
    data.pop('uid', None)
    unknown = set(data) - MARKER_FIELDS
    if unknown:
        _bad(sorted(unknown)[0], 'Unknown field.')

    current = dict(row.payload or {}) if row else {}
    effective = {**current, **data}
    marker_id = effective.get('marker_id')
    if not marker_id:
        _bad('marker_id', 'This field is required.')
    marker_id = str(marker_id)
    if len(marker_id) > 50:
        _bad('marker_id', 'Ensure this field has no more than 50 characters.')
    if row is not None and marker_id != str((row.payload or {}).get('marker_id') or row.uid.split(':')[-1]):
        _bad('marker_id', 'This field is read-only on update.')
    duplicate = resolve_marker(db, marker_id, required=False)
    if creating and duplicate is not None:
        _bad('marker_id', f'Calibration marker "{marker_id}" already exists.')

    apriltag_id = effective.get('apriltag_id')
    if apriltag_id in (None, ''):
        _bad('apriltag_id', 'This field is required.')
    apriltag_id = str(apriltag_id)
    if len(apriltag_id) > 10:
        _bad('apriltag_id', 'Ensure this field has no more than 10 characters.')

    scene = effective.get('scene')
    if scene in (None, ''):
        _bad('scene', 'This field is required.')
    scene = str(scene)
    if not _scene_exists(db, scene):
        _bad('scene', 'Scene with given UUID does not exist.')

    dims = effective.get('dims', [])
    if not isinstance(dims, list):
        _bad('dims', 'Expected a list.')

    return {'marker_id': marker_id, 'apriltag_id': apriltag_id, 'dims': deepcopy(dims), 'scene': scene}, marker_id


def marker_to_dict(row: Resource, *, native: bool = False) -> dict:
    value = dict(row.payload or {})
    value['marker_id'] = str(value.get('marker_id') or row.uid.split(':')[-1])
    value.pop('uid', None)
    if native:
        value['uid'] = row.uid
        value['revision'] = row.revision
        value['kind'] = row.kind
    return value


def cascade_scene_markers(db, scene_uid: str) -> list[str]:
    deleted = []
    for row in list(db.scalars(select(Resource).where(Resource.kind == 'marker')).all()):
        if str((row.payload or {}).get('scene') or '') == str(scene_uid):
            deleted.append(row.uid)
            db.delete(row)
    db.flush()
    return deleted
