import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from sqlalchemy import func, or_, select

from .auth import Principal, current_principal, issue_token, verify_service
from .camera_io import CameraSnapshotError, fetch_camera_snapshot
from .database import Event, Heartbeat, Incident, Observation, Resource, sessions
from .resources import ALIASES, delete_resource, get_resource, list_resources, to_dict, upsert

app = FastAPI(title="SceneScape Native Control API", version="0.2")


def db_dep():
    db = sessions()()
    try:
        yield db
    finally:
        db.close()


def _kind(plural):
    if plural not in ALIASES:
        raise HTTPException(404, "Unknown resource type")
    return ALIASES[plural]


def _scene_allowed(p: Principal, scene_id: str):
    if p.is_admin or "*" in p.scene_scopes or scene_id in p.scene_scopes:
        return
    raise HTTPException(403, "Scene is outside token scope")



def _age_seconds(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - value).total_seconds()


def _scene_observation_clause(scene_id: str):
    # Older native-worker builds incorrectly used payload["id"] (often a camera
    # id) as Observation.scene_id. The MQTT topic has always carried the
    # authoritative scene UUID, so include it for backward-compatible reads.
    return or_(
        Observation.scene_id == scene_id,
        Observation.topic == f"scenescape/regulated/scene/{scene_id}",
    )


def _latest_scene_observation(db, scene_id: str):
    return db.scalar(
        select(Observation)
        .where(_scene_observation_clause(scene_id))
        .order_by(Observation.observed_at.desc(), Observation.id.desc())
        .limit(1)
    )

def _scene_matches(item, scene_id):
    payload = item.payload or {}
    return str(payload.get("scene") or payload.get("scene_id") or payload.get("parent") or "") == str(scene_id)


@app.post("/api/v1/auth")
def service_auth(username: str = Form(...), password: str = Form(...)):
    if not verify_service(username, password):
        raise HTTPException(401, "Invalid service credentials")
    return {"token": issue_token(username)}


@app.get("/api/v2/overview")
def overview(p=Depends(current_principal), db=Depends(db_dep)):
    counts = {}
    for plural, kind in ALIASES.items():
        counts[plural] = db.scalar(select(func.count()).select_from(Resource).where(Resource.kind == kind)) or 0
    counts["incidents"] = db.scalar(select(func.count()).select_from(Incident)) or 0
    counts["observations"] = db.scalar(select(func.count()).select_from(Observation)) or 0
    counts["events"] = db.scalar(select(func.count()).select_from(Event)) or 0
    hb = db.get(Heartbeat, "mqtt")
    latest = db.scalar(select(Observation.observed_at).order_by(Observation.observed_at.desc()).limit(1))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "health": {
            "database": "connected",
            "mqtt": hb.state if hb else "unknown",
            "last_observation": latest.isoformat() if latest else None,
        },
    }


@app.get("/api/v2/scenes/{scene_id}/bundle")
def scene_bundle(scene_id: str, p=Depends(current_principal), db=Depends(db_dep)):
    _scene_allowed(p, scene_id)
    scene = to_dict(get_resource(db, "scene", scene_id))
    result = {"scene": scene}
    for plural in ("cameras", "sensors", "regions", "tripwires", "children", "markers"):
        kind = ALIASES[plural]
        rows = db.scalars(select(Resource).where(Resource.kind == kind).order_by(Resource.id)).all()
        result[plural] = [to_dict(row) for row in rows if _scene_matches(row, scene_id)]
    return result


@app.get("/api/v2/scenes/{scene_id}/live")
def live(scene_id: str, p=Depends(current_principal), db=Depends(db_dep)):
    _scene_allowed(p, scene_id)
    row = _latest_scene_observation(db, scene_id)
    if not row:
        return {"id": scene_id, "objects": [], "stale": True}
    payload = dict(row.payload or {})
    payload["scene_id"] = scene_id
    payload["observed_at"] = row.observed_at.isoformat()
    payload["stale"] = _age_seconds(row.observed_at) > 5
    return payload


@app.get("/api/v2/scenes/{scene_id}/live/stream")
async def live_stream(scene_id: str, p=Depends(current_principal)):
    _scene_allowed(p, scene_id)

    async def events():
        last_id = None
        stale_sent = False
        while True:
            db = sessions()()
            try:
                row = _latest_scene_observation(db, scene_id)
                if row and row.id != last_id:
                    last_id = row.id
                    stale_sent = False
                    payload = dict(row.payload or {})
                    payload["scene_id"] = scene_id
                    payload["observed_at"] = row.observed_at.isoformat()
                    payload["stale"] = False
                    yield f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
                elif row and not stale_sent and _age_seconds(row.observed_at) > 5:
                    stale_sent = True
                    payload = dict(row.payload or {})
                    payload["scene_id"] = scene_id
                    payload["observed_at"] = row.observed_at.isoformat()
                    payload["stale"] = True
                    yield f"event: status\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
            finally:
                db.close()
            await asyncio.sleep(0.2)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/v2/scenes/{scene_id}/history")
def history(scene_id: str, limit: int = Query(200, ge=1, le=5000), p=Depends(current_principal), db=Depends(db_dep)):
    _scene_allowed(p, scene_id)
    rows = db.scalars(
        select(Observation).where(_scene_observation_clause(scene_id)).order_by(Observation.observed_at.desc()).limit(limit)
    ).all()
    return [{"id": r.id, "timestamp": r.observed_at.isoformat(), "payload": r.payload} for r in reversed(rows)]


@app.get("/api/v2/scenes/{scene_id}/trends")
def trends(scene_id: str, p=Depends(current_principal), db=Depends(db_dep)):
    _scene_allowed(p, scene_id)
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = db.scalars(select(Observation).where(_scene_observation_clause(scene_id), Observation.observed_at >= since)).all()
    buckets = {}
    for row in rows:
        key = row.observed_at.replace(minute=0, second=0, microsecond=0).isoformat()
        buckets.setdefault(key, []).append(len((row.payload or {}).get("objects") or []))
    return [
        {"bucket": key, "samples": len(values), "average_objects": round(sum(values) / len(values), 2)}
        for key, values in sorted(buckets.items())
    ]


@app.get("/api/v2/cameras/{camera_id}/snapshot")
def camera_snapshot(camera_id: str, p=Depends(current_principal), db=Depends(db_dep)):
    camera = to_dict(get_resource(db, "camera", camera_id))
    scene_id = str(camera.get("scene") or camera.get("scene_id") or "")
    if scene_id:
        _scene_allowed(p, scene_id)
    try:
        image = fetch_camera_snapshot(camera_id)
    except CameraSnapshotError as exc:
        raise HTTPException(504, str(exc)) from exc
    return Response(content=image, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/v2/incidents")
def incidents(p=Depends(current_principal), db=Depends(db_dep)):
    rows = db.scalars(select(Incident).order_by(Incident.id.desc())).all()
    return [
        {
            "id": r.id,
            "scene_id": r.scene_id,
            "title": r.title,
            "status": r.status,
            "assignee": r.assignee,
            "notes": r.notes,
            "audit": r.audit,
        }
        for r in rows
    ]


@app.post("/api/v2/incidents/{incident_id}/action")
def incident_action(incident_id: int, body: dict, p=Depends(current_principal), db=Depends(db_dep)):
    row = db.get(Incident, incident_id)
    if not row:
        raise HTTPException(404, "Incident not found")
    status = str(body.get("status") or row.status)
    if status not in {"new", "acknowledged", "investigating", "resolved", "reopened"}:
        raise HTTPException(422, "Invalid incident status")
    note = str(body.get("note") or "").strip()
    assignee = str(body.get("assignee") or row.assignee or "").strip()
    now = datetime.now(timezone.utc).isoformat()
    notes = list(row.notes or [])
    audit = list(row.audit or [])
    if note:
        notes.append({"at": now, "by": p.subject, "note": note})
    audit.append({"at": now, "by": p.subject, "status": status, "assignee": assignee})
    row.status = status
    row.assignee = assignee
    row.notes = notes
    row.audit = audit
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": row.id, "status": row.status, "assignee": row.assignee, "notes": row.notes, "audit": row.audit, "title": row.title}


@app.get("/api/v2/{plural}")
def list_any(plural: str, p=Depends(current_principal), db=Depends(db_dep)):
    rows = list_resources(db, _kind(plural))
    if p.is_admin or "*" in p.scene_scopes:
        return rows
    if plural == "scenes":
        return [row for row in rows if str(row.get("uid")) in p.scene_scopes]
    return [row for row in rows if str(row.get("scene") or row.get("scene_id") or row.get("parent") or "") in p.scene_scopes]


@app.get("/api/v2/{plural}/{uid}")
def get_any(plural: str, uid: str, p=Depends(current_principal), db=Depends(db_dep)):
    row = to_dict(get_resource(db, _kind(plural), uid))
    if not (p.is_admin or "*" in p.scene_scopes):
        scene_id = uid if plural == "scenes" else str(row.get("scene") or row.get("scene_id") or row.get("parent") or "")
        _scene_allowed(p, scene_id)
    return row


@app.post("/api/v2/{plural}")
def create_any(plural: str, body: dict, p=Depends(current_principal), db=Depends(db_dep)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    row = upsert(db, _kind(plural), None, body, p)
    db.commit()
    return to_dict(row)


@app.put("/api/v2/{plural}/{uid}")
def update_any(
    plural: str,
    uid: str,
    body: dict,
    revision: int | None = Query(default=None),
    p=Depends(current_principal),
    db=Depends(db_dep),
):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    row = upsert(db, _kind(plural), uid, body, p, revision)
    db.commit()
    return to_dict(row)


@app.delete("/api/v2/{plural}/{uid}")
def delete_any(plural: str, uid: str, p=Depends(current_principal), db=Depends(db_dep)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    result = delete_resource(db, _kind(plural), uid)
    db.commit()
    return result


@app.get("/media/{path:path}")
def media(path: str, p=Depends(current_principal), db=Depends(db_dep)):
    root = Path(os.getenv("MEDIA_ROOT", "./media")).resolve()
    target = (root / path).resolve()
    if root not in target.parents and target != root:
        raise HTTPException(404)
    if not target.is_file():
        raise HTTPException(404)
    if not (p.is_admin or "*" in p.scene_scopes):
        request_path = "/media/" + path.lstrip("/")
        scenes = db.scalars(select(Resource).where(Resource.kind == "scene")).all()
        owning = [row.uid for row in scenes if request_path in {str((row.payload or {}).get("map") or ""), str((row.payload or {}).get("thumbnail") or "")} ]
        if owning and not any(scene_id in p.scene_scopes for scene_id in owning):
            raise HTTPException(403, "Media is outside token scope")
    return FileResponse(target)


@app.get("/api/v1/health")
def api_health(db=Depends(db_dep)):
    db.execute(select(1))
    return {"status": "ok", "database": "connected"}


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"
