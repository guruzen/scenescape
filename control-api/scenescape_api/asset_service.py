from __future__ import annotations

import uuid
from copy import deepcopy

from .contracts import normalize_resource
from .database import Resource
from .media_files import delete_media
from .resources import delete_resource, get_resource, upsert


def create_asset(db, body: dict, actor, *, legacy: bool):
    normalized, resolved_uid = normalize_resource(db, 'asset', body, uid=None, creating=True, legacy=legacy)
    if resolved_uid is not None:
        return upsert(db, 'asset', resolved_uid, normalized, actor)
    # Asset3D.uid in 2026.2 is its integer primary key. Resource.id is the
    # native durable primary key, so expose that as the compatibility uid.
    row = Resource(kind='asset', uid=f'pending-{uuid.uuid4()}', payload=normalized, revision=1)
    db.add(row)
    db.flush()
    row.uid = str(row.id)
    row.payload = {**normalized, 'uid': row.uid}
    db.flush()
    return row


def update_asset(db, uid: str, body: dict, actor, *, legacy: bool, expected_revision: int | None = None):
    current = get_resource(db, 'asset', uid)
    before = deepcopy(current.payload or {})
    normalized, resolved_uid = normalize_resource(db, 'asset', body, uid=uid, creating=False, legacy=legacy)
    row = upsert(db, 'asset', resolved_uid or uid, normalized, actor, expected_revision)
    return row, before


def cleanup_replaced_asset_media(before: dict | None, after: dict) -> None:
    if not before:
        return
    old = before.get('model_3d')
    new = after.get('model_3d')
    if old and old != new:
        delete_media(str(old))


def delete_asset(db, uid: str):
    row = get_resource(db, 'asset', uid)
    media = str((row.payload or {}).get('model_3d') or '')
    result = delete_resource(db, 'asset', uid)
    return result, media
