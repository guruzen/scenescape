# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

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
from .calibration_service import camera_calibration as proxy_camera_calibration, scene_registration as proxy_scene_registration, service_status as proxy_calibration_status
from .camera_io import CameraSnapshotError, fetch_camera_calibration, fetch_camera_snapshot, request_camera_frame, request_camera_video, update_camera_runtime
from .camera_service import update_camera_resource
from .contracts import normalize_resource
from .mqtt_commands import notify_camera_change, notify_config_change
from .database import Event, Heartbeat, Incident, Observation, Resource, sessions
from .hierarchy import cascade_scene_links, child_metadata_for_parent, child_to_dict, create_child_link, resolve_child_link, transform_dict, update_child_link
from .intrinsics import calculate_camera_intrinsics
from .keycloak_admin import TOPIC_TEMPLATES, acl_check, create_user as keycloak_create_user, delete_user as keycloak_delete_user, get_service_identity, get_user as keycloak_get_user, list_service_identities, list_users as keycloak_list_users, update_user as keycloak_update_user
from .markers import marker_to_dict, normalize_marker, resolve_marker
from .media_files import delete_media, save_upload, store_bytes
from .scene_config import apply_uploaded_map_semantics
from .scene_import_native import import_scene_archive
from .mapping_service import mapping_health, mesh_generation_status, start_mesh_generation
from .model_library import (
    create_directory as create_model_directory,
    delete_entry as delete_model_entry,
    download_target as model_download_target,
    extract_zip as extract_model_zip,
    list_directory as list_model_directory,
    upload_files as upload_model_files,
)
from .pipeline_generation import list_model_configs, pipeline_preview
from .scene_service import cleanup_scene_media, create_scene, delete_scene, delete_scene_media, update_scene
from .sensor_service import update_sensor_resource
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


@app.post("/api/v1/aclcheck")
async def legacy_aclcheck(request: Request):
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
    else:
        try:
            payload = dict(await request.form())
        except Exception:
            payload = {}
    username = str(payload.get("username") or "")
    topic = str(payload.get("topic") or "")
    if not username or not topic:
        raise HTTPException(400, "Missing required parameters.")
    try:
        access = int(payload.get("acc"))
    except (TypeError, ValueError):
        raise HTTPException(400, "Missing or invalid acc parameter.")
    try:
        allowed, granted = acl_check(username, topic, access)
    except HTTPException as exc:
        if exc.status_code == 404:
            return Response(content=json.dumps({"result": "deny"}), media_type="application/json", status_code=403)
        raise
    if not allowed:
        return Response(content=json.dumps({"result": "deny"}), media_type="application/json", status_code=403)
    return {"result": "allow", "acc": granted}


def _legacy_user_value(value: dict) -> dict:
    result = {
        key: value.get(key)
        for key in ("uid", "username", "is_active", "is_staff", "is_superuser", "first_name", "last_name", "email")
        if value.get(key) is not None
    }
    if value.get("acls"):
        result["acls"] = value["acls"]
    return result


@app.get("/api/v1/users")
def legacy_users(p=Depends(service_principal)):
    rows = [_legacy_user_value(row) for row in [*list_service_identities(), *keycloak_list_users()]]
    return {"count": len(rows), "next": None, "previous": None, "results": rows}


@app.get("/api/v1/user/{username}")
def legacy_user_get(username: str, p=Depends(service_principal)):
    service = get_service_identity(username)
    return _legacy_user_value(service if service is not None else keycloak_get_user(username))


@app.post("/api/v1/user")
def legacy_user_create(body: dict, p=Depends(service_principal)):
    value = _legacy_user_value(keycloak_create_user(body))
    return Response(content=json.dumps(value), media_type="application/json", status_code=201)


@app.post("/api/v1/user/{username}")
@app.put("/api/v1/user/{username}")
def legacy_user_update(username: str, body: dict, p=Depends(service_principal)):
    if get_service_identity(username) is not None:
        raise HTTPException(400, "Service identities are managed by mounted auth secrets")
    legacy = dict(body)
    # Django serializer treated privilege flags as read-only.
    legacy.pop("is_staff", None)
    legacy.pop("is_superuser", None)
    legacy.pop("roles", None)
    return _legacy_user_value(keycloak_update_user(username, legacy))


@app.delete("/api/v1/user/{username}")
def legacy_user_delete(username: str, p=Depends(service_principal)):
    if get_service_identity(username) is not None:
        raise HTTPException(400, "Service identities are managed by mounted auth secrets")
    keycloak_delete_user(username)
    return {"username": username}


@app.get("/api/v2/users")
def native_users(p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    return keycloak_list_users()


@app.get("/api/v2/users/{username}")
def native_user_get(username: str, p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    return keycloak_get_user(username)


@app.post("/api/v2/users")
def native_user_create(body: dict, p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    return keycloak_create_user(body)


@app.put("/api/v2/users/{username}")
def native_user_update(username: str, body: dict, p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    return keycloak_update_user(username, body)


@app.delete("/api/v2/users/{username}")
def native_user_delete(username: str, p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    return keycloak_delete_user(username)


@app.get("/api/v2/security/topics")
def native_security_topics(p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    return [{"topic": name, "template": template} for name, template in TOPIC_TEMPLATES.items()]


@app.get("/api/v2/security/services")
def native_security_services(p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    return list_service_identities()


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


def _sensor_value(value: dict, *, native: bool) -> dict:
    result = dict(value)
    uid = str(result.get("uid") or result.get("sensor_id") or "")
    if uid:
        result["uid"] = uid
        result["sensor_id"] = uid
    center = result.get("center")
    if isinstance(center, (list, tuple)) and len(center) == 2 and center[0] is not None and center[1] is not None:
        result["translation"] = [center[0], center[1], 0.0]
    elif "translation" not in result:
        result["translation"] = [None, None, 0.0]
    if not native:
        result.pop("icon", None)
    return result


def _legacy_clean(row):
    kind = row.kind if isinstance(row, Resource) else str(row.get("kind") or "")
    value = to_dict(row) if isinstance(row, Resource) else dict(row)
    if kind == "sensor":
        value = _sensor_value(value, native=False)
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
    # Native-only Mapping Service lifecycle state is not part of the tagged
    # 2026.2 SceneSerializer contract and must not leak through /api/v1/export.
    scene.pop("mesh_request_id", None)
    scene.pop("mesh_state", None)
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


@app.post("/api/v2/calculateintrinsics")
def native_calculate_intrinsics(body: dict, p=Depends(current_principal)):
    return calculate_camera_intrinsics(body)


@app.get("/api/v1/frame")
def legacy_camera_frame(
    camera: str = Query(...),
    timestamp: str | None = Query(default=None),
    type: str | None = Query(default=None),
    p=Depends(service_principal),
):
    try:
        return request_camera_frame(camera, timestamp=timestamp, frame_type=type)
    except ValueError as exc:
        raise HTTPException(400, {"timestamp": "Must provide valid timestamp"}) from exc
    except CameraSnapshotError:
        raise HTTPException(404)


@app.get("/api/v1/video")
def legacy_camera_video(camera: str = Query(...), p=Depends(service_principal)):
    try:
        data = request_camera_video(camera)
    except CameraSnapshotError:
        raise HTTPException(404)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={camera}.mp4"},
    )


@app.get("/api/v1/autocalibration/status")
@app.get("/api/v2/autocalibration/status")
def autocalibration_status(p=Depends(current_principal)):
    return proxy_calibration_status()


@app.get("/api/v1/autocalibration/scenes/{scene_id}/registration")
@app.get("/api/v2/autocalibration/scenes/{scene_id}/registration")
def autocalibration_scene_registration_get(scene_id: str, p=Depends(current_principal)):
    return proxy_scene_registration(scene_id, "GET")


@app.post("/api/v1/autocalibration/scenes/{scene_id}/registration")
@app.post("/api/v2/autocalibration/scenes/{scene_id}/registration")
def autocalibration_scene_registration_post(scene_id: str, p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    return proxy_scene_registration(scene_id, "POST")


@app.patch("/api/v1/autocalibration/scenes/{scene_id}/registration")
@app.patch("/api/v2/autocalibration/scenes/{scene_id}/registration")
def autocalibration_scene_registration_patch(scene_id: str, p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    return proxy_scene_registration(scene_id, "PATCH")


@app.get("/api/v1/autocalibration/cameras/{camera_id}/calibration")
@app.get("/api/v2/autocalibration/cameras/{camera_id}/calibration")
def autocalibration_camera_get(camera_id: str, p=Depends(current_principal)):
    return proxy_camera_calibration(camera_id, "GET")


@app.post("/api/v1/autocalibration/cameras/{camera_id}/calibration")
@app.post("/api/v2/autocalibration/cameras/{camera_id}/calibration")
def autocalibration_camera_post(camera_id: str, body: dict, p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    return proxy_camera_calibration(camera_id, "POST", body)


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
    if kind == "camera":
        row, _ = update_camera_resource(db, uid, body, p, legacy=True, expected_revision=current.revision)
    elif kind == "sensor":
        row, _ = update_sensor_resource(db, uid, body, p, legacy=True, expected_revision=current.revision)
    else:
        body, resolved_uid = normalize_resource(db, kind, body, uid=uid, creating=False, legacy=True)
        row = upsert(db, kind, resolved_uid or uid, body, p, current.revision)
    db.commit()
    value = _legacy_scene(db, row) if kind == "scene" else _legacy_clean(row)
    if not (kind in {"sensor", "region", "tripwire"} and set(body.keys()) == {"visible"}):
        notify_config_change(kind, row.uid)
    if kind == "camera":
        notify_camera_change(value, "save", previous)
    return value


@app.post("/api/v1/save-geospatial-snapshot/")
async def legacy_geospatial_snapshot(request: Request, p=Depends(current_principal)):
    return await native_geospatial_snapshot(request, p)


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
    sensor_icon = str((current.payload or {}).get("icon") or "") if kind == "sensor" else ""
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
    if sensor_icon:
        delete_media(sensor_icon)
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
async def native_geospatial_snapshot(request: Request, p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    content_type = request.headers.get("content-type", "").lower()
    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        value = str(form.get("image_data") or "")
    else:
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(400, "No image data provided") from exc
        value = str((body or {}).get("image_data") or "")
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
        relative = map_value[len("/media/"):] if map_value.startswith("/media/") else map_value
        target = _media_target(relative)
        if target is not None:
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


@app.get("/mapping-service/status/")
@app.get("/api/v2/mapping/health")
def native_mapping_health(p=Depends(current_principal)):
    return mapping_health()


@app.post("/scene/generate-mesh/{scene_id}/")
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


@app.get("/scene/generate-mesh-status/{scene_id}/")
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


@app.post("/api/v2/sensors/{sensor_id}/icon")
async def native_sensor_icon_upload(
    sensor_id: str,
    icon: UploadFile = File(...),
    revision: int | None = Query(default=None),
    p=Depends(current_principal),
    db=Depends(db_dep),
):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    current = get_resource(db, "sensor", sensor_id)
    before = dict(current.payload or {})
    created = ""
    try:
        created = await save_upload(icon, kind="thumbnail")
        row, _ = update_sensor_resource(
            db, sensor_id, {"icon": created}, p, legacy=False,
            expected_revision=revision if revision is not None else current.revision,
        )
        db.commit()
    except Exception:
        db.rollback()
        if created:
            delete_media(created)
        raise
    old_icon = str(before.get("icon") or "")
    if old_icon and old_icon != created:
        delete_media(old_icon)
    notify_config_change("sensor", row.uid)
    return _sensor_value(to_dict(row), native=True)


@app.delete("/api/v2/sensors/{sensor_id}/icon")
def native_sensor_icon_delete(
    sensor_id: str,
    revision: int | None = Query(default=None),
    p=Depends(current_principal),
    db=Depends(db_dep),
):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    current = get_resource(db, "sensor", sensor_id)
    old_icon = str((current.payload or {}).get("icon") or "")
    row, _ = update_sensor_resource(
        db, sensor_id, {"icon": None}, p, legacy=False,
        expected_revision=revision if revision is not None else current.revision,
    )
    db.commit()
    if old_icon:
        delete_media(old_icon)
    notify_config_change("sensor", row.uid)
    return _sensor_value(to_dict(row), native=True)


@app.get("/api/v2/sensors/{sensor_id}/telemetry")
def native_sensor_telemetry(
    sensor_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    p=Depends(current_principal),
    db=Depends(db_dep),
):
    sensor = _sensor_value(to_dict(get_resource(db, "sensor", sensor_id)), native=True)
    scene_id = str(sensor.get("scene") or "")
    if scene_id:
        _scene_allowed(p, scene_id)
    rows = db.scalars(
        select(Observation)
        .where(
            Observation.scene_id == sensor_id,
            Observation.topic.like("scenescape/data/sensor/%"),
        )
        .order_by(Observation.observed_at.desc(), Observation.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "sensor_id": sensor_id,
            "timestamp": row.observed_at.isoformat(),
            "value": (row.payload or {}).get("value"),
            "payload": row.payload or {},
        }
        for row in rows
    ]


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
        elif plural == "sensors":
            result[plural] = [_sensor_value(to_dict(row), native=True) for row in rows if _scene_matches(row, scene_id)]
        else:
            result[plural] = [to_dict(row) for row in rows if _scene_matches(row, scene_id)]
    child_meta = child_metadata_for_parent(db, scene_id)
    result["child_regions"] = child_meta["regions"]
    result["child_tripwires"] = child_meta["tripwires"]
    result["child_sensors"] = child_meta["sensors"]
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


@app.get("/api/v2/cameras/{camera_id}/telemetry")
def native_camera_telemetry(camera_id: str, p=Depends(current_principal), db=Depends(db_dep)):
    camera = to_dict(get_resource(db, "camera", camera_id))
    scene_id = str(camera.get("scene") or camera.get("scene_id") or "")
    if scene_id:
        _scene_allowed(p, scene_id)
    topic_root = f"scenescape/data/camera/{camera_id}"
    rows = db.scalars(
        select(Observation)
        .where(or_(
            Observation.topic == topic_root,
            Observation.topic.startswith(topic_root + "/", autoescape=True),
        ))
        .order_by(Observation.observed_at.desc(), Observation.id.desc())
        .limit(60)
    ).all()
    if not rows:
        return {"camera_id": camera_id, "fps": 0.0, "stale": True, "samples": 0, "last_observation": None, "detections": 0}
    chronological = list(reversed(rows))
    span = (chronological[-1].observed_at - chronological[0].observed_at).total_seconds()
    fps = (len(chronological) - 1) / span if len(chronological) > 1 and span > 0 else 0.0
    latest = rows[0]
    objects = (latest.payload or {}).get("objects") or {}
    detections = sum(len(value) for value in objects.values() if isinstance(value, list)) if isinstance(objects, dict) else 0
    return {
        "camera_id": camera_id,
        "fps": round(fps, 2),
        "stale": _age_seconds(latest.observed_at) > 5,
        "samples": len(rows),
        "last_observation": latest.observed_at.isoformat(),
        "detections": detections,
    }


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


@app.get("/api/v2/cameras/{camera_id}/calibration-frame")
def camera_calibration_frame(camera_id: str, p=Depends(current_principal), db=Depends(db_dep)):
    camera = to_dict(get_resource(db, "camera", camera_id))
    scene_id = str(camera.get("scene") or camera.get("scene_id") or "")
    if scene_id:
        _scene_allowed(p, scene_id)
    try:
        return fetch_camera_calibration(camera_id)
    except CameraSnapshotError as exc:
        raise HTTPException(504, str(exc)) from exc


@app.get("/api/v2/cameras/{camera_id}/frame")
def native_camera_frame(
    camera_id: str,
    timestamp: str | None = Query(default=None),
    type: str | None = Query(default=None),
    p=Depends(current_principal),
    db=Depends(db_dep),
):
    camera = to_dict(get_resource(db, "camera", camera_id))
    scene_id = str(camera.get("scene") or camera.get("scene_id") or "")
    if scene_id:
        _scene_allowed(p, scene_id)
    try:
        return request_camera_frame(camera_id, timestamp=timestamp, frame_type=type)
    except ValueError as exc:
        raise HTTPException(400, {"timestamp": "Must provide valid timestamp"}) from exc
    except CameraSnapshotError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/v2/cameras/{camera_id}/video")
def native_camera_video(camera_id: str, p=Depends(current_principal), db=Depends(db_dep)):
    camera = to_dict(get_resource(db, "camera", camera_id))
    scene_id = str(camera.get("scene") or camera.get("scene_id") or "")
    if scene_id:
        _scene_allowed(p, scene_id)
    try:
        data = request_camera_video(camera_id)
    except CameraSnapshotError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={camera_id}.mp4"},
    )


@app.post("/api/v2/cameras/{camera_id}/runtime-update")
def native_camera_runtime_update(camera_id: str, body: dict, p=Depends(current_principal), db=Depends(db_dep)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    get_resource(db, "camera", camera_id)
    result = update_camera_runtime(camera_id, body)
    if not result.get("ok"):
        raise HTTPException(503, result.get("error") or "Failed to update camera runtime")
    return result


@app.post("/api/v2/camera-pipeline/preview")
def native_camera_pipeline_preview_unsaved(body: dict, p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    return pipeline_preview(body)


@app.post("/cam/generate_pipeline/{camera_id}")
@app.post("/api/v2/cameras/{camera_id}/pipeline-preview")
def native_camera_pipeline_preview(camera_id: str, body: dict, p=Depends(current_principal), db=Depends(db_dep)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    camera = to_dict(get_resource(db, "camera", camera_id))
    merged = {**camera, **body}
    return pipeline_preview(merged)


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


@app.get("/api/v2/models/configs")
def native_model_configs(p=Depends(current_principal)):
    return {"configs": list_model_configs()}


@app.get("/api/v2/models")
def native_model_list(path: str = Query(default=""), p=Depends(current_principal)):
    return list_model_directory(path)


@app.post("/api/v2/models/directories")
def native_model_create_directory(body: dict, p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    return create_model_directory(body.get("path", ""), str(body.get("name") or ""))


@app.post("/api/v2/models/files")
async def native_model_upload_files(request: Request, p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    form = await request.form()
    uploads = [item for item in form.getlist("files") if hasattr(item, "read")]
    relative_paths = [str(item) for item in form.getlist("relative_paths")]
    overwrite = str(form.get("overwrite") or "").lower() in {"1", "true", "yes", "on"}
    return await upload_model_files(
        str(form.get("path") or ""),
        uploads,
        relative_paths,
        overwrite=overwrite,
    )


@app.post("/api/v2/models/extract")
async def native_model_extract(request: Request, p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        raise HTTPException(400, "A ZIP file is required")
    overwrite = str(form.get("overwrite") or "").lower() in {"1", "true", "yes", "on"}
    return await extract_model_zip(
        str(form.get("path") or ""),
        upload,
        folder_name=str(form.get("folder_name") or "") or None,
        overwrite=overwrite,
    )


@app.get("/api/v2/models/download")
def native_model_download(path: str, p=Depends(current_principal)):
    target = model_download_target(path)
    return FileResponse(
        target,
        filename=target.name,
        media_type="application/octet-stream",
        headers={"Cache-Control": "no-store"},
    )


@app.delete("/api/v2/models")
def native_model_delete(path: str, p=Depends(current_principal)):
    if not p.is_admin:
        raise HTTPException(403, "Administrator role required")
    return delete_model_entry(path)


@app.get("/api/v2/{plural}")
def list_any(plural: str, p=Depends(current_principal), db=Depends(db_dep)):
    kind = _kind(plural)
    if kind == "child":
        db_rows = db.scalars(select(Resource).where(Resource.kind == "child").order_by(Resource.id)).all()
        rows = [child_to_dict(db, row, native=True) for row in db_rows]
    elif kind == "marker":
        db_rows = db.scalars(select(Resource).where(Resource.kind == "marker").order_by(Resource.id)).all()
        rows = [marker_to_dict(row, native=True) for row in db_rows]
    elif kind == "sensor":
        db_rows = db.scalars(select(Resource).where(Resource.kind == "sensor").order_by(Resource.id)).all()
        rows = [_sensor_value(to_dict(row), native=True) for row in db_rows]
    else:
        rows = list_resources(db, kind)
    if p.is_admin or "*" in p.scene_scopes:
        return rows
    if kind == "asset":
        # The object library is global in 2026.2 and is required to render
        # tracked categories in every authorized scene.
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
    elif kind == "sensor":
        row = _sensor_value(to_dict(get_resource(db, kind, uid)), native=True)
    else:
        row = to_dict(get_resource(db, kind, uid))
    if not (p.is_admin or "*" in p.scene_scopes) and kind != "asset":
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
    value = _sensor_value(to_dict(row), native=True) if kind == "sensor" else to_dict(row)
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
    if kind == "camera":
        row, _ = update_camera_resource(db, uid, body, p, legacy=False, expected_revision=revision)
    elif kind == "sensor":
        row, _ = update_sensor_resource(db, uid, body, p, legacy=False, expected_revision=revision)
    else:
        body, resolved_uid = normalize_resource(db, kind, body, uid=uid, creating=False, legacy=False)
        row = upsert(db, kind, resolved_uid or uid, body, p, revision)
    db.commit()
    value = _sensor_value(to_dict(row), native=True) if kind == "sensor" else to_dict(row)
    if not (kind in {"sensor", "region", "tripwire"} and set(body.keys()) == {"visible"}):
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
    sensor_icon = str((current.payload or {}).get("icon") or "") if kind == "sensor" else ""
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
    if sensor_icon:
        delete_media(sensor_icon)
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
    return {"status": "ok", "ready": True, "database": "connected"}


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"
