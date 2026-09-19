import uuid
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from .database import Resource

ALIASES={"scenes":"scene","cameras":"camera","sensors":"sensor","regions":"region","tripwires":"tripwire","assets":"asset","children":"child","markers":"marker"}

def _clean(payload):
    if not isinstance(payload, dict):
        raise HTTPException(422, "Resource payload must be an object")
    return payload

def to_dict(row):
    value=dict(row.payload or {})
    value.update(uid=row.uid, revision=row.revision, kind=row.kind)
    return value

def upsert(db, kind, uid, payload, actor, expected_revision=None):
    payload=_clean(payload)
    uid = uid or str(payload.get("uid") or uuid.uuid4())
    row=db.scalar(select(Resource).where(Resource.kind==kind, Resource.uid==uid))
    if row:
        if expected_revision is not None and row.revision != expected_revision:
            raise HTTPException(409, "Revision conflict")
        row.payload={**(row.payload or {}), **payload}
        row.revision += 1
        row.updated_at=datetime.now(timezone.utc)
    else:
        row=Resource(kind=kind,uid=uid,payload={**payload,"uid":uid},revision=1)
        db.add(row)
    db.flush()
    return row

def list_resources(db, kind):
    return [to_dict(x) for x in db.scalars(select(Resource).where(Resource.kind==kind).order_by(Resource.id)).all()]

def get_resource(db, kind, uid):
    row=db.scalar(select(Resource).where(Resource.kind==kind,Resource.uid==uid))
    if not row: raise HTTPException(404,"Resource not found")
    return row
