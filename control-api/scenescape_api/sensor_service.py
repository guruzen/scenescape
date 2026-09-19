from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from .contracts import normalize_resource
from .database import Resource
from .resources import get_resource, to_dict, upsert


def update_sensor_resource(db, uid: str, body: dict, actor, *, legacy: bool, expected_revision: int | None = None):
    current = get_resource(db, "sensor", uid)
    before = to_dict(current)
    normalized, resolved_uid = normalize_resource(
        db, "sensor", body, uid=uid, creating=False, legacy=legacy
    )
    target_uid = str(resolved_uid or uid)

    if target_uid == uid:
        row = upsert(db, "sensor", uid, normalized, actor, expected_revision)
        return row, before

    if expected_revision is not None and current.revision != expected_revision:
        raise HTTPException(409, "Revision conflict")
    conflict = db.scalar(
        select(Resource).where(Resource.kind == "sensor", Resource.uid == target_uid)
    )
    if conflict is not None and conflict.id != current.id:
        raise HTTPException(400, {"sensor_id": [f"A sensor with ID '{target_uid}' already exists."]})

    payload = {**(current.payload or {}), **normalized, "uid": target_uid, "sensor_id": target_uid}
    current.uid = target_uid
    current.payload = payload
    current.revision += 1
    current.updated_at = datetime.now(timezone.utc)
    db.flush()
    return current, before
