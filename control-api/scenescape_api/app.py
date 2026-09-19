import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from sqlalchemy import func, or_, select

from .auth import Principal, current_principal, issue_token, service_principal, verify_service
from .camera_io import CameraSnapshotError, fetch_camera_snapshot
from .contracts import normalize_resource
from .mqtt_commands import notify_config_change
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


LEGACY_V1 = {
    "scenes": "scene", "scene": "scene",
    "cameras": "camera", "camera": "camera",
    "sensors": "sensor", "sensor": "sensor",
    "regions": "region", "region": "region",
    "tripwires": "tripwire", "tripwire": "tripwire",
    "assets": "asset", "asset": "asset",
    "child": "child",
    "calibrationmarkers": "marker", "calibrationmarker": "marker",
}


def _legacy_clean(row):
    value = to_dict(row) if isinstance(row, Resource) else dict(row)
    value.pop("kind", None)
    value.pop("revision", None)
    return value


def _legacy_rows(db, kind):
    return db.scalars(select(Resource).where(Resource.kind == kind).order_by(Resource.id)).all()


def _legacy_filter(items, request: Request):
    allowed = {"name", "parent", "scene", "username", "id"}
    unknown = set(request.query_params.keys()) - allowed
    if unknown:
        return []
    result = []
    for item in items:
        row = _legacy_clean(item)
        ok = True
        for key, wanted in request.query_params.items():
            actual = row.get(key)
            if key == "id":
                actual = row.get("uid") or row.get("id")
            if str(actual or "") != str(wanted):
                ok = False
                break
        if ok:
            result.append(row)
    return result


def _legacy_scene(db, row):
    scene = _legacy_clean(row)
    scene_id = str(scene.get("uid") or "")
    for plural, kind in (("cameras","camera"),("sensors","sensor"),("regions","region"),("tripwires","tripwire")):
        nested = []
        for item in _legacy_rows(db, kind):
            payload = item.payload or {}
            if str(payload.get("scene") or payload.get("scene_id") or "") == scene_id:
                nested.append(_legacy_clean(item))
        scene[plural] = nested
    children = []
    for item in _legacy_rows(db, "child"):
        payload = item.payload or {}
        if str(payload.get("parent") or payload.get("scene") or "") == scene_id:
            children.append(_legacy_clean(item))
    scene["children"] = children
    return scene


@app.get("/api/v1/scenes")
def legacy_scenes(request: Request, p=Depends(service_principal), db=Depends(db_dep)):
    rows = [_legacy_scene(db, row) for row in _legacy_rows(db, "scene")]
    rows = _legacy_filter(rows, request)
    return {"count": len(rows), "next": None, "previous": None, "results": rows}


@app.get("/api/v1/scenes/child")
def legacy_children(request: Request, p=Depends(service_principal), db=Depends(db_dep)):
    rows = _legacy_filter(_legacy_rows(db, "child"), request)
    return {"count": len(rows), "next": None, "previous": None, "results": rows}


@app.get("/api/v1/cameras")
@app.get("/api/v1/sensors")
@app.get("/api/v1/regions")
@app.get("/api/v1/tripwires")
@app.get("/api/v1/assets")
@app.get("/api/v1/calibrationmarkers")
def legacy_list(request: Request, p=Depends(service_principal), db=Depends(db_dep)):
    plural = request.url.path.rstrip("/").rsplit("/", 1)[-1]
    kind = LEGACY_V1[plural]
    rows = _legacy_filter(_legacy_rows(db, kind), request)
    return {"count": len(rows), "next": None, "previous": None, "results": rows}


@app.get("/api/v1/database-ready")
def legacy_database_ready(db=Depends(db_dep)):
    db.execute(select(1))
    return {"databaseReady": True}


@app.get("/api/v1/{thing}/{uid}")
def legacy_get(thing: str, uid: str, p=Depends(service_principal), db=Depends(db_dep)):
    kind = LEGACY_V1.get(thing)
    if not kind:
        raise HTTPException(404)
    row = get_resource(db, kind, uid)
    return _legacy_scene(db, row) if kind == "scene" else _legacy_clean(row)


@app.post("/api/v1/{thing}/{uid}")
@app.put("/api/v1/{thing}/{uid}")
def legacy_update(thing: str, uid: str, body: dict, p=Depends(service_principal), db=Depends(db_dep)):
    kind = LEGACY_V1.get(thing)
    if not kind:
        raise HTTPException(404)
    current = get_resource(db, kind, uid)
    body, resolved_uid = normalize_resource(db, kind, body, uid=uid, creating=False, legacy=True)
    row = upsert(db, kind, resolved_uid or uid, body, p, current.revision)
    db.commit()
    notify_config_change(kind, row.uid)
    return _legacy_scene(db, row) if kind == "scene" else _legacy_clean(row)


@app.post("/api/v1/{thing}")
def legacy_create(thing: str, body: dict, p=Depends(service_principal), db=Depends(db_dep)):
    kind = LEGACY_V1.get(thing)
    if not kind:
        raise HTTPException(404)
    body, resolved_uid = normalize_resource(db, kind, body, uid=None, creating=True, legacy=True)
    row = upsert(db, kind, resolved_uid, body, p)
    db.commit()
    notify_config_change(kind, row.uid)
    value = _legacy_scene(db, row) if kind == "scene" else _legacy_clean(row)
    return Response(content=json.dumps(value), media_type="application/json", status_code=201)


@app.delete("/api/v1/{thing}/{uid}")
def legacy_delete(thing: str, uid: str, p=Depends(service_principal), db=Depends(db_dep)):
    kind = LEGACY_V1.get(thing)
    if not kind:
        raise HTTPException(404)
    result = delete_resource(db, kind, uid)
    db.commit()
    notify_config_change(kind, uid)
    return result


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
    kind = _kind(plural)
    body, resolved_uid = normalize_resource(db, kind, body, uid=None, creating=True, legacy=False)
    row = upsert(db, kind, resolved_uid, body, p)
    db.commit()
    notify_config_change(kind, row.uid)
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
    kind = _kind(plural)
    get_resource(db, kind, uid)
    body, resolved_uid = normalize_resource(db, kind, body, uid=uid, creating=False, legacy=False)
    row = upsert(db, kind, resolved_uid or uid, body, p, revision)
    db.commit()
    notify_config_change(kind, row.uid)
    return to_dict(row)


@app.delete("/api/v2/{plural}/{uid}")
def delete_any(plural: str, uid: str, p=Depends(current_principal), db=Depends(db_dep)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    kind = _kind(plural)
    result = delete_resource(db, kind, uid)
    db.commit()
    notify_config_change(kind, uid)
    return result


def _media_target(path: str):
    relative = Path(path)
    roots = [Path(os.getenv("MEDIA_ROOT", "./media")).resolve()]
    fallback = os.getenv("MEDIA_FALLBACK_ROOT")
    if fallback:
        roots.append(Path(fallback).resolve())
    for root in roots:
        target = (root / relative).resolve()
        if root not in target.parents and target != root:
            continue
        if target.is_file():
            return target
    return None


@app.get("/media/{path:path}")
def media(path: str, p=Depends(current_principal), db=Depends(db_dep)):
    target = _media_target(path)
    if target is None:
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
