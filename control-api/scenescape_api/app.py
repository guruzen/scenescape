import asyncio
import base64
import io
import json
import os
import re
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from sqlalchemy import func, or_, select

from .auth import Principal, current_principal, issue_token, service_principal, verify_service
from .asset_service import cleanup_replaced_asset_media, create_asset, delete_asset, update_asset
from .camera_io import CameraSnapshotError, fetch_camera_snapshot
from .contracts import normalize_resource
from .mqtt_commands import notify_camera_change, notify_config_change
from .database import Event, Heartbeat, Incident, Observation, Resource, sessions
from .hierarchy import cascade_scene_links, child_to_dict, create_child_link, resolve_child_link, transform_dict, update_child_link
from .intrinsics import calculate_camera_intrinsics
from .markers import marker_to_dict, normalize_marker, resolve_marker
from .media_files import delete_media, media_path, save_upload, store_bytes
from .scene_config import apply_uploaded_map_semantics
from .scene_import_native import import_scene_archive
from .mapping_service import mapping_health, mesh_generation_status, start_mesh_generation
from .scene_service import cleanup_scene_media, create_scene, delete_scene, delete_scene_media, update_scene
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


def _nonnull(value: dict):
    # manager.serializers.NonNullSerializer: omit null values and empty
    # list/tuple values while retaining false/zero/empty-string scalars.
    return {
        key: item for key, item in value.items()
        if (item is not None and not isinstance(item, (list, tuple))) or item
    }


def _legacy_clean(row):
    value = to_dict(row) if isinstance(row, Resource) else dict(row)
    value.pop("kind", None)
    value.pop("revision", None)
    return _nonnull(value)


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


def _legacy_scene(db, row, seen=None):
    scene = _legacy_clean(row)
    scene_id = str(scene.get("uid") or "")
    seen = set(seen or ())
    seen.add(scene_id)

    for link_row in _legacy_rows(db, "child"):
        payload = link_row.payload or {}
        if str(payload.get("child_type") or "local") == "local" and str(payload.get("child") or "") == scene_id:
            scene["parent"] = str(payload.get("parent") or "")
            scene["transform"] = transform_dict(payload)
            break

    for plural, kind in (("cameras","camera"),("sensors","sensor"),("regions","region"),("tripwires","tripwire")):
        nested = []
        for item in _legacy_rows(db, kind):
            payload = item.payload or {}
            if str(payload.get("scene") or payload.get("scene_id") or "") == scene_id:
                nested.append(_legacy_clean(item))
        scene[plural] = nested

    children = []
    for link_row in _legacy_rows(db, "child"):
        payload = link_row.payload or {}
        if str(payload.get("parent") or payload.get("scene") or "") != scene_id:
            continue
        link = child_to_dict(db, link_row)
        if str(payload.get("child_type") or "local") == "remote":
            children.append({"name": link.get("name", "")})
            continue
        child_id = str(payload.get("child") or "")
        child_row = db.scalar(select(Resource).where(Resource.kind == "scene", Resource.uid == child_id))
        if child_row is None or child_id in seen:
            continue
        child_scene = _legacy_scene(db, child_row, seen)
        child_scene["link"] = link
        children.append(child_scene)
    scene["children"] = children
    if scene.get("trs_matrix") is None or scene.get("output_lla") is False:
        scene.pop("trs_matrix", None)
    return _nonnull(scene)


@app.get("/api/v1/scenes")
def legacy_scenes(request: Request, p=Depends(service_principal), db=Depends(db_dep)):
    rows = [_legacy_scene(db, row) for row in _legacy_rows(db, "scene")]
    rows = _legacy_filter(rows, request)
    return {"count": len(rows), "next": None, "previous": None, "results": rows}


@app.get("/api/v1/scenes/child")
def legacy_children(request: Request, p=Depends(service_principal), db=Depends(db_dep)):
    rows = _legacy_filter([child_to_dict(db, row) for row in _legacy_rows(db, "child")], request)
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
    if kind == "marker":
        source = [marker_to_dict(row) for row in _legacy_rows(db, kind)]
    else:
        source = _legacy_rows(db, kind)
    rows = _legacy_filter(source, request)
    return {"count": len(rows), "next": None, "previous": None, "results": rows}


@app.get("/api/v1/database-ready")
def legacy_database_ready(db=Depends(db_dep)):
    db.execute(select(1))
    return {"databaseReady": True}




def _decode_form_value(value):
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


async def _scene_request_payload(request: Request):
    content_type = request.headers.get("content-type", "").lower()
    uploads = {}
    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        body = {}
        for key, value in form.multi_items():
            if hasattr(value, "filename") and hasattr(value, "read"):
                uploads[key] = value
            else:
                body[key] = _decode_form_value(value)
        return body, uploads
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, "Invalid JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(400, "Resource payload must be an object")
    return body, uploads


async def _apply_scene_uploads(body: dict, uploads: dict, existing: dict | None = None):
    uploaded_map = False
    uploaded_polycam = False
    created = []
    if "map" in uploads:
        body["map"] = await save_upload(uploads["map"], kind="scene-map")
        created.append(body["map"]); uploaded_map = True
    if "polycam_data" in uploads:
        body["polycam_data"] = await save_upload(uploads["polycam_data"], kind="polycam")
        created.append(body["polycam_data"]); uploaded_polycam = True
    if "thumbnail" in uploads:
        body["thumbnail"] = await save_upload(uploads["thumbnail"], kind="thumbnail")
        created.append(body["thumbnail"])
    apply_uploaded_map_semantics(existing, body, uploaded_map=uploaded_map, uploaded_polycam=uploaded_polycam)
    if uploaded_map or uploaded_polycam:
        for field in ("map", "polycam_data", "thumbnail"):
            value = body.get(field)
            if value and value not in created:
                created.append(value)
    return created


async def _apply_asset_uploads(body: dict, uploads: dict, existing: dict | None = None):
    unknown = set(uploads) - {"model_3d"}
    if unknown:
        raise HTTPException(400, {sorted(unknown)[0]: ["Unknown file field."]})
    created = []
    if "model_3d" in uploads:
        body["model_3d"] = await save_upload(uploads["model_3d"], kind="asset-model")
        created.append(body["model_3d"])
    return created


@app.post("/api/v1/calculateintrinsics")
def legacy_calculate_intrinsics(body: dict, p=Depends(service_principal)):
    return calculate_camera_intrinsics(body)


@app.post("/api/v1/import-scene/")
async def legacy_import_scene(zipFile: UploadFile = File(...), p=Depends(service_principal), db=Depends(db_dep)):
    raw = await zipFile.read(int(os.getenv("MAX_UPLOAD_BYTES", str(512 * 1024 * 1024))) + 1)
    await zipFile.close()
    before = {row.uid for row in _legacy_rows(db, "scene")}
    result = import_scene_archive(db, raw, p)
    after = {row.uid for row in _legacy_rows(db, "scene")}
    for scene_uid in sorted(after - before):
        notify_config_change("scene", scene_uid)
    return Response(content=json.dumps(result, default=str), media_type="application/json", status_code=201)


@app.post("/api/v1/scene")
async def legacy_scene_create(request: Request, p=Depends(service_principal), db=Depends(db_dep)):
    body, uploads = await _scene_request_payload(request)
    created = []
    try:
        created = await _apply_scene_uploads(body, uploads)
        row, notify = create_scene(db, body, p, legacy=True)
        db.commit()
    except Exception:
        db.rollback()
        for value in created:
            delete_media(value)
        raise
    value = _legacy_scene(db, row)
    if notify:
        notify_config_change("scene", row.uid)
    return Response(content=json.dumps(value), media_type="application/json", status_code=201)


@app.post("/api/v1/scene/{uid}")
@app.put("/api/v1/scene/{uid}")
async def legacy_scene_update(uid: str, request: Request, p=Depends(service_principal), db=Depends(db_dep)):
    current = get_resource(db, "scene", uid)
    before = dict(current.payload or {})
    body, uploads = await _scene_request_payload(request)
    created = []
    try:
        created = await _apply_scene_uploads(body, uploads, before)
        row, notify, before = update_scene(db, uid, body, p, legacy=True, expected_revision=current.revision)
        db.commit()
    except Exception:
        db.rollback()
        for value in created:
            if value not in set(before.get(field) for field in ("map", "thumbnail", "polycam_data")):
                delete_media(value)
        raise
    cleanup_scene_media(before, row.payload or {})
    value = _legacy_scene(db, row)
    if notify:
        notify_config_change("scene", row.uid)
    return value


@app.post("/api/v1/asset")
async def legacy_asset_create(request: Request, p=Depends(service_principal), db=Depends(db_dep)):
    body, uploads = await _scene_request_payload(request)
    created = []
    try:
        created = await _apply_asset_uploads(body, uploads)
        row = create_asset(db, body, p, legacy=True)
        db.commit()
    except Exception:
        db.rollback()
        for value in created:
            delete_media(value)
        raise
    value = _legacy_clean(row)
    notify_config_change("asset", row.uid)
    return Response(content=json.dumps(value), media_type="application/json", status_code=201)


@app.post("/api/v1/asset/{uid}")
@app.put("/api/v1/asset/{uid}")
async def legacy_asset_update(uid: str, request: Request, p=Depends(service_principal), db=Depends(db_dep)):
    current = get_resource(db, "asset", uid)
    before = dict(current.payload or {})
    body, uploads = await _scene_request_payload(request)
    created = []
    try:
        created = await _apply_asset_uploads(body, uploads, before)
        row, before = update_asset(db, uid, body, p, legacy=True, expected_revision=current.revision)
        db.commit()
    except Exception:
        db.rollback()
        for value in created:
            if value != before.get("model_3d"):
                delete_media(value)
        raise
    cleanup_replaced_asset_media(before, row.payload or {})
    value = _legacy_clean(row)
    notify_config_change("asset", row.uid)
    return value


@app.get("/api/v1/{thing}/{uid}")
def legacy_get(thing: str, uid: str, p=Depends(service_principal), db=Depends(db_dep)):
    kind = LEGACY_V1.get(thing)
    if not kind:
        raise HTTPException(404)
    if kind == "child":
        row = resolve_child_link(db, uid)
    elif kind == "marker":
        row = resolve_marker(db, uid)
    else:
        row = get_resource(db, kind, uid)
    if kind == "scene":
        return _legacy_scene(db, row)
    if kind == "child":
        return child_to_dict(db, row)
    if kind == "marker":
        return marker_to_dict(row)
    return _legacy_clean(row)


@app.post("/api/v1/{thing}/{uid}")
@app.put("/api/v1/{thing}/{uid}")
def legacy_update(thing: str, uid: str, body: dict, p=Depends(service_principal), db=Depends(db_dep)):
    kind = LEGACY_V1.get(thing)
    if not kind:
        raise HTTPException(404)
    if kind == "child":
        current = resolve_child_link(db, uid)
        row, notify = update_child_link(db, current, body, p, legacy=True, expected_revision=current.revision)
        db.commit()
        value = child_to_dict(db, row)
        if notify:
            notify_config_change(kind, row.uid)
        return value
    if kind == "marker":
        current = resolve_marker(db, uid)
        payload, marker_id = normalize_marker(db, body, row=current, creating=False)
        row = upsert(db, "marker", current.uid, payload, p, current.revision)
        db.commit(); notify_config_change(kind, row.uid)
        return marker_to_dict(row)

    current = get_resource(db, kind, uid)
    previous = _legacy_clean(current) if kind == "camera" else None
    body, resolved_uid = normalize_resource(db, kind, body, uid=uid, creating=False, legacy=True)
    row = upsert(db, kind, resolved_uid or uid, body, p, current.revision)
    db.commit()
    value = _legacy_scene(db, row) if kind == "scene" else _legacy_clean(row)
    notify_config_change(kind, row.uid)
    if kind == "camera":
        notify_camera_change(value, "save", previous)
    return value


@app.post("/api/v1/{thing}")
def legacy_create(thing: str, body: dict, p=Depends(service_principal), db=Depends(db_dep)):
    kind = LEGACY_V1.get(thing)
    if not kind:
        raise HTTPException(404)
    if kind == "child":
        row = create_child_link(db, body, p, legacy=True)
        db.commit()
        value = child_to_dict(db, row)
        notify_config_change(kind, row.uid)
        return Response(content=json.dumps(value), media_type="application/json", status_code=201)
    if kind == "marker":
        payload, marker_id = normalize_marker(db, body, creating=True)
        row = upsert(db, "marker", marker_id, payload, p)
        db.commit(); notify_config_change(kind, row.uid)
        return Response(content=json.dumps(marker_to_dict(row)), media_type="application/json", status_code=201)

    body, resolved_uid = normalize_resource(db, kind, body, uid=None, creating=True, legacy=True)
    row = upsert(db, kind, resolved_uid, body, p)
    db.commit()
    value = _legacy_scene(db, row) if kind == "scene" else _legacy_clean(row)
    notify_config_change(kind, row.uid)
    if kind == "camera":
        notify_camera_change(value, "save")
    return Response(content=json.dumps(value), media_type="application/json", status_code=201)


@app.delete("/api/v1/{thing}/{uid}")
def legacy_delete(thing: str, uid: str, p=Depends(service_principal), db=Depends(db_dep)):
    kind = LEGACY_V1.get(thing)
    if not kind:
        raise HTTPException(404)
    if kind == "child":
        row = resolve_child_link(db, uid)
        link_uid = row.uid
        db.delete(row)
        db.commit()
        notify_config_change(kind, link_uid)
        return {"pk": link_uid}

    if kind == "marker":
        current = resolve_marker(db, uid)
        marker_id = marker_to_dict(current)["marker_id"]
        db.delete(current); db.commit(); notify_config_change(kind, current.uid)
        return {"marker_id": marker_id}
    current = get_resource(db, kind, uid)
    previous = _legacy_clean(current) if kind == "camera" else None
    media_values = []
    asset_media = ""
    if kind == "scene":
        result, media_values = delete_scene(db, uid)
    elif kind == "asset":
        result, asset_media = delete_asset(db, uid)
    else:
        result = delete_resource(db, kind, uid)
    db.commit()
    if media_values:
        delete_scene_media(media_values)
    if asset_media:
        delete_media(asset_media)
    notify_config_change(kind, uid)
    if kind == "camera" and previous is not None:
        notify_camera_change(previous, "delete")
    return result




@app.post("/api/v2/scenes/{scene_id}/files")
async def native_scene_files(scene_id: str, request: Request, p=Depends(current_principal), db=Depends(db_dep)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    current = get_resource(db, "scene", scene_id)
    before = dict(current.payload or {})
    body, uploads = await _scene_request_payload(request)
    if not uploads:
        raise HTTPException(400, "At least one map, polycam_data or thumbnail file is required")
    created = []
    try:
        created = await _apply_scene_uploads(body, uploads, before)
        row, notify, before = update_scene(db, scene_id, body, p, legacy=False, expected_revision=current.revision)
        db.commit()
    except Exception:
        db.rollback()
        for value in created:
            if value not in set(before.get(field) for field in ("map", "thumbnail", "polycam_data")):
                delete_media(value)
        raise
    cleanup_scene_media(before, row.payload or {})
    if notify:
        notify_config_change("scene", row.uid)
    return to_dict(row)


@app.post("/api/v2/scenes/import")
async def native_import_scene(zipFile: UploadFile = File(...), p=Depends(current_principal), db=Depends(db_dep)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    raw = await zipFile.read(int(os.getenv("MAX_UPLOAD_BYTES", str(512 * 1024 * 1024))) + 1)
    await zipFile.close()
    before = {row.uid for row in _legacy_rows(db, "scene")}
    result = import_scene_archive(db, raw, p)
    after = {row.uid for row in _legacy_rows(db, "scene")}
    for scene_uid in sorted(after - before):
        notify_config_change("scene", scene_uid)
    return result


@app.post("/api/v2/geospatial/snapshot")
def native_geospatial_snapshot(body: dict, p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    value = str(body.get("image_data") or "")
    if value.startswith("data:image/png;base64,"):
        value = value.split(",", 1)[1]
    if not value:
        raise HTTPException(400, "No image data provided")
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise HTTPException(400, "Failed to decode image data") from exc
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(400, "Geospatial snapshot must be a PNG image")
    name = f"geospatial_map_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.png"
    url = store_bytes(name, raw, kind="thumbnail")
    return {"success": True, "filename": Path(url).name, "media_url": url}


def _archive_media(zip_file, scene: dict, seen: set[str]):
    map_value = str(scene.get("map") or "")
    if map_value and map_value not in seen:
        target = media_path(map_value)
        if target is not None and target.is_file():
            seen.add(map_value)
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(scene.get("name") or "scene"))
            zip_file.writestr(f"{safe_name}{target.suffix.lower()}", target.read_bytes())
    for child in scene.get("children") or []:
        if isinstance(child, dict):
            _archive_media(zip_file, child, seen)


@app.get("/api/v2/scenes/{scene_id}/export")
def native_export_scene(scene_id: str, p=Depends(current_principal), db=Depends(db_dep)):
    _scene_allowed(p, scene_id)
    row = get_resource(db, "scene", scene_id)
    scene = _legacy_scene(db, row)
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(scene.get("name") or scene_id)) or "scene"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{name}.json", json.dumps(scene, indent=2, default=str))
        _archive_media(archive, scene, set())
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"', "Cache-Control": "no-store"},
    )


@app.get("/api/v2/mapping/health")
def native_mapping_health(p=Depends(current_principal)):
    return mapping_health()


@app.post("/api/v2/scenes/{scene_id}/mesh")
async def native_generate_mesh(scene_id: str, request: Request, p=Depends(current_principal), db=Depends(db_dep)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    get_resource(db, "scene", scene_id)
    mesh_type = "mesh"
    video = None
    content_type = request.headers.get("content-type", "").lower()
    if "multipart/form-data" in content_type:
        form = await request.form()
        mesh_type = str(form.get("mesh_type") or "mesh")
        upload = form.get("map")
        if hasattr(upload, "read") and getattr(upload, "filename", ""):
            raw = await upload.read(int(os.getenv("MAX_UPLOAD_BYTES", str(512 * 1024 * 1024))) + 1)
            await upload.close()
            if len(raw) > int(os.getenv("MAX_UPLOAD_BYTES", str(512 * 1024 * 1024))):
                raise HTTPException(413, "Uploaded video exceeds the configured size limit")
            video = (str(upload.filename), str(getattr(upload, "content_type", "") or ""), raw)
    elif "application/json" in content_type:
        body = await request.json()
        mesh_type = str((body or {}).get("mesh_type") or "mesh")
    result = start_mesh_generation(db, scene_id, p, mesh_type=mesh_type, video=video)
    result.pop("_before_scene", None)
    db.commit()
    return result


@app.get("/api/v2/scenes/{scene_id}/mesh/status")
def native_generate_mesh_status(scene_id: str, request_id: str = Query(...), p=Depends(current_principal), db=Depends(db_dep)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    result = mesh_generation_status(db, scene_id, request_id, p)
    before = result.pop("_before_scene", None)
    after = result.pop("_after_scene", None)
    camera_changes = result.pop("_changed_cameras", [])
    finalized = bool(result.get("finalized")) and before is not None and after is not None
    db.commit()
    if finalized:
        cleanup_scene_media(before, after)
        notify_config_change("scene", scene_id)
        for change in camera_changes:
            notify_camera_change(change["after"], "save", change["before"])
    return result


@app.post("/api/v2/assets")
async def native_asset_create(request: Request, p=Depends(current_principal), db=Depends(db_dep)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    body, uploads = await _scene_request_payload(request)
    created = []
    try:
        created = await _apply_asset_uploads(body, uploads)
        row = create_asset(db, body, p, legacy=False)
        db.commit()
    except Exception:
        db.rollback()
        for value in created:
            delete_media(value)
        raise
    notify_config_change("asset", row.uid)
    return to_dict(row)


@app.put("/api/v2/assets/{uid}")
async def native_asset_update(uid: str, request: Request, revision: int | None = Query(default=None), p=Depends(current_principal), db=Depends(db_dep)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    current = get_resource(db, "asset", uid)
    before = dict(current.payload or {})
    body, uploads = await _scene_request_payload(request)
    created = []
    try:
        created = await _apply_asset_uploads(body, uploads, before)
        row, before = update_asset(db, uid, body, p, legacy=False, expected_revision=revision)
        db.commit()
    except Exception:
        db.rollback()
        for value in created:
            if value != before.get("model_3d"):
                delete_media(value)
        raise
    cleanup_replaced_asset_media(before, row.payload or {})
    notify_config_change("asset", row.uid)
    return to_dict(row)


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
        if plural == "children":
            result[plural] = [child_to_dict(db, row, native=True) for row in rows if _scene_matches(row, scene_id)]
        elif plural == "markers":
            result[plural] = [marker_to_dict(row, native=True) for row in rows if _scene_matches(row, scene_id)]
        else:
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
    kind = _kind(plural)
    if kind == "child":
        db_rows = db.scalars(select(Resource).where(Resource.kind == "child").order_by(Resource.id)).all()
        rows = [child_to_dict(db, row, native=True) for row in db_rows]
    elif kind == "marker":
        db_rows = db.scalars(select(Resource).where(Resource.kind == "marker").order_by(Resource.id)).all()
        rows = [marker_to_dict(row, native=True) for row in db_rows]
    else:
        rows = list_resources(db, kind)
    if p.is_admin or "*" in p.scene_scopes:
        return rows
    if plural == "scenes":
        return [row for row in rows if str(row.get("uid")) in p.scene_scopes]
    return [row for row in rows if str(row.get("scene") or row.get("scene_id") or row.get("parent") or "") in p.scene_scopes]


@app.get("/api/v2/{plural}/{uid}")
def get_any(plural: str, uid: str, p=Depends(current_principal), db=Depends(db_dep)):
    kind = _kind(plural)
    if kind == "child":
        row = child_to_dict(db, resolve_child_link(db, uid), native=True)
    elif kind == "marker":
        row = marker_to_dict(resolve_marker(db, uid), native=True)
    else:
        row = to_dict(get_resource(db, kind, uid))
    if not (p.is_admin or "*" in p.scene_scopes):
        scene_id = uid if plural == "scenes" else str(row.get("scene") or row.get("scene_id") or row.get("parent") or "")
        _scene_allowed(p, scene_id)
    return row


@app.post("/api/v2/{plural}")
def create_any(plural: str, body: dict, p=Depends(current_principal), db=Depends(db_dep)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    kind = _kind(plural)
    if kind == "child":
        row = create_child_link(db, body, p, legacy=False)
        db.commit()
        value = child_to_dict(db, row, native=True)
        notify_config_change(kind, row.uid)
        return value
    if kind == "scene":
        row, notify = create_scene(db, body, p, legacy=False)
        db.commit(); value = to_dict(row)
        if notify: notify_config_change(kind, row.uid)
        return value
    if kind == "marker":
        payload, marker_id = normalize_marker(db, body, creating=True)
        row = upsert(db, kind, marker_id, payload, p)
        db.commit(); notify_config_change(kind, row.uid)
        return marker_to_dict(row, native=True)

    body, resolved_uid = normalize_resource(db, kind, body, uid=None, creating=True, legacy=False)
    row = upsert(db, kind, resolved_uid, body, p)
    db.commit()
    value = to_dict(row)
    notify_config_change(kind, row.uid)
    if kind == "camera":
        notify_camera_change(value, "save")
    return value


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
    if kind == "child":
        current = resolve_child_link(db, uid)
        row, notify = update_child_link(db, current, body, p, legacy=False, expected_revision=revision)
        db.commit()
        value = child_to_dict(db, row, native=True)
        if notify:
            notify_config_change(kind, row.uid)
        return value
    if kind == "scene":
        row, notify, before = update_scene(db, uid, body, p, legacy=False, expected_revision=revision)
        db.commit(); cleanup_scene_media(before, row.payload or {}); value = to_dict(row)
        if notify: notify_config_change(kind, row.uid)
        return value
    if kind == "marker":
        current = resolve_marker(db, uid)
        payload, marker_id = normalize_marker(db, body, row=current, creating=False)
        row = upsert(db, kind, current.uid, payload, p, revision)
        db.commit(); notify_config_change(kind, row.uid)
        return marker_to_dict(row, native=True)

    current = get_resource(db, kind, uid)
    previous = to_dict(current) if kind == "camera" else None
    body, resolved_uid = normalize_resource(db, kind, body, uid=uid, creating=False, legacy=False)
    row = upsert(db, kind, resolved_uid or uid, body, p, revision)
    db.commit()
    value = to_dict(row)
    notify_config_change(kind, row.uid)
    if kind == "camera":
        notify_camera_change(value, "save", previous)
    return value


@app.delete("/api/v2/{plural}/{uid}")
def delete_any(plural: str, uid: str, p=Depends(current_principal), db=Depends(db_dep)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    kind = _kind(plural)
    if kind == "child":
        row = resolve_child_link(db, uid)
        link_uid = row.uid
        db.delete(row)
        db.commit()
        notify_config_change(kind, link_uid)
        return {"deleted": True, "uid": link_uid, "kind": kind}

    if kind == "marker":
        current = resolve_marker(db, uid); marker_id = marker_to_dict(current)["marker_id"]
        db.delete(current); db.commit(); notify_config_change(kind, current.uid)
        return {"deleted": True, "uid": marker_id, "kind": kind}
    current = get_resource(db, kind, uid)
    previous = to_dict(current) if kind == "camera" else None
    media_values = []
    asset_media = ""
    if kind == "scene":
        result, media_values = delete_scene(db, uid)
    elif kind == "asset":
        result, asset_media = delete_asset(db, uid)
    else:
        result = delete_resource(db, kind, uid)
    db.commit()
    if media_values:
        delete_scene_media(media_values)
    if asset_media:
        delete_media(asset_media)
    notify_config_change(kind, uid)
    if kind == "camera" and previous is not None:
        notify_camera_change(previous, "delete")
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
        owning = [row.uid for row in scenes if request_path in {str((row.payload or {}).get("map") or ""), str((row.payload or {}).get("thumbnail") or ""), str((row.payload or {}).get("polycam_data") or "")} ]
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
