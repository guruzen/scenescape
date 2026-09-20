from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, update

from .contracts import normalize_resource
from .database import Resource
from .resources import get_resource, to_dict, upsert


def update_camera_resource(db, uid: str, body: dict, actor, *, legacy: bool, expected_revision: int | None = None):
    current = get_resource(db, "camera", uid)
    before = to_dict(current)
    normalized, resolved_uid = normalize_resource(
        db, "camera", body, uid=uid, creating=False, legacy=legacy
    )
    target_uid = str(resolved_uid or uid)

    if target_uid == uid:
        row = upsert(db, "camera", uid, normalized, actor, expected_revision)
        return row, before

    conflict = db.scalar(
        select(Resource).where(Resource.kind == "camera", Resource.uid == target_uid)
    )
    if conflict is not None and conflict.id != current.id:
        raise HTTPException(400, {"sensor_id": [f"A camera with ID '{target_uid}' already exists."]})

    payload = {**(current.payload or {}), **normalized, "uid": target_uid}
    if expected_revision is not None:
        result = db.execute(
            update(Resource).where(Resource.id == current.id, Resource.revision == expected_revision).values(
                uid=target_uid, payload=payload, revision=expected_revision + 1, updated_at=datetime.now(timezone.utc)
            )
        )
        if result.rowcount != 1:
            raise HTTPException(409, "Revision conflict")
        db.flush(); db.expire(current); db.refresh(current)
    else:
        current.uid = target_uid
        current.payload = payload
        current.revision += 1
        current.updated_at = datetime.now(timezone.utc)
        db.flush()
    return current, before
