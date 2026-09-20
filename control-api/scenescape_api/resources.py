import uuid
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .database import Resource

ALIASES = {
    "scenes": "scene", "cameras": "camera", "sensors": "sensor", "regions": "region",
    "tripwires": "tripwire", "assets": "asset", "children": "child", "markers": "marker",
}


def _clean(payload):
    if not isinstance(payload, dict):
        raise HTTPException(422, "Resource payload must be an object")
    return payload


def to_dict(row):
    value = dict(row.payload or {})
    value.update(uid=row.uid, revision=row.revision, kind=row.kind)
    return value


def upsert(db, kind, uid, payload, actor, expected_revision=None):
    payload = _clean(payload)
    uid = uid or str(payload.get("uid") or payload.get("id") or payload.get("uuid") or uuid.uuid4())
    row = db.scalar(select(Resource).where(Resource.kind == kind, Resource.uid == uid))
    now = datetime.now(timezone.utc)
    if row:
        merged = {**(row.payload or {}), **payload, "uid": uid}
        if expected_revision is not None:
            result = db.execute(
                update(Resource)
                .where(Resource.id == row.id, Resource.revision == expected_revision)
                .values(payload=merged, revision=expected_revision + 1, updated_at=now)
            )
            if result.rowcount != 1:
                raise HTTPException(409, "Revision conflict")
            db.flush()
            db.expire(row)
            db.refresh(row)
            return row
        row.payload = merged
        row.revision += 1
        row.updated_at = now
        db.flush()
        return row

    row = Resource(kind=kind, uid=uid, payload={**payload, "uid": uid}, revision=1)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "Resource already exists") from exc
    return row

def list_resources(db, kind):
    return [to_dict(x) for x in db.scalars(select(Resource).where(Resource.kind == kind).order_by(Resource.id)).all()]


def get_resource(db, kind, uid):
    row = db.scalar(select(Resource).where(Resource.kind == kind, Resource.uid == uid))
    if not row:
        raise HTTPException(404, "Resource not found")
    return row


def delete_resource(db, kind, uid):
    row = get_resource(db, kind, uid)
    db.delete(row)
    db.flush()
    return {"deleted": True, "uid": uid, "kind": kind}
