from __future__ import annotations

import base64
import io
import json
import math
import os
import ssl
import threading
import time
import uuid
from pathlib import Path

import numpy as np
import requests
import trimesh
from fastapi import HTTPException
from sqlalchemy import select

from .database import Resource
from .map_processing import process_uploaded_mesh
from .media_files import store_bytes
from .resources import get_resource, to_dict, upsert

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
VIDEO_MIME_TYPES = {
    "video/mp4", "video/quicktime", "video/x-matroska",
    "video/webm", "video/x-msvideo",
}


def _mapping_url() -> str:
    return os.getenv("MAPPING_SERVICE_URL", "https://mapping.scenescape.intel.com:8444/v1").rstrip("/")


def _verify():
    ca = os.getenv("UPSTREAM_CA_FILE") or os.getenv("MQTT_CA_FILE")
    return ca if ca and Path(ca).is_file() else True


def mapping_health() -> dict:
    try:
        response = requests.get(f"{_mapping_url()}/health", timeout=5, verify=_verify())
        if response.status_code not in (200, 202):
            return {"available": False, "error": f"HTTP {response.status_code}"}
        payload = response.json()
        details = payload.get("details") or {}
        models = details.get("models") or {}
        if not models and "model_loaded" in payload:
            models = {"loaded": bool(payload.get("model_loaded")), "active": payload.get("model", "unknown")}
        return {
            "available": True,
            "status": payload.get("status", "unknown"),
            "ready": bool(payload.get("ready", False)),
            "models": models,
        }
    except requests.Timeout:
        return {"available": False, "error": "Health check timed out"}
    except requests.ConnectionError:
        return {"available": False, "error": "Could not connect to mapping service"}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def _broker_settings():
    host = os.getenv("MQTT_HOST", "broker.scenescape.intel.com")
    port = int(os.getenv("MQTT_PORT", "1883"))
    auth = {}
    auth_file = os.getenv("MQTT_AUTH_FILE")
    if auth_file and Path(auth_file).is_file():
        auth = json.loads(Path(auth_file).read_text())
    return host, port, auth


def _collect_calibration_images(cameras: list[dict]) -> dict[str, dict]:
    import paho.mqtt.client as mqtt

    if not cameras:
        return {}
    host, port, auth = _broker_settings()
    collected: dict[str, dict] = {}
    condition = threading.Condition()
    connected = threading.Event()
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"scenescape-api-mapping-{uuid.uuid4().hex[:10]}",
    )
    if auth.get("user"):
        client.username_pw_set(auth.get("user"), auth.get("password"))
    ca = os.getenv("MQTT_CA_FILE")
    if ca:
        client.tls_set(ca_certs=ca, cert_reqs=ssl.CERT_REQUIRED)

    wanted = {str(camera["uid"]) for camera in cameras}

    def on_connect(c, userdata, flags, reason_code, properties):
        if getattr(reason_code, "is_failure", False):
            return
        for camera_id in wanted:
            c.subscribe(f"scenescape/image/calibration/camera/{camera_id}", qos=2)
        connected.set()

    def on_message(c, userdata, message):
        camera_id = message.topic.rsplit("/", 1)[-1]
        if camera_id not in wanted:
            return
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            encoded = payload.get("image")
            if not encoded:
                return
            with condition:
                collected[camera_id] = {
                    "data": encoded,
                    "timestamp": payload.get("timestamp", ""),
                    "filename": f"{camera_id}_calibration.jpg",
                }
                condition.notify_all()
        except Exception:
            return

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, port, keepalive=30)
    client.loop_start()
    try:
        if not connected.wait(timeout=5):
            raise HTTPException(504, "Could not connect to MQTT broker for camera image collection")
        time.sleep(0.15)
        for camera_id in wanted:
            client.publish(f"scenescape/cmd/camera/{camera_id}", "getcalibrationimage", qos=2)
        deadline = time.monotonic() + max(5, 5 * len(wanted))
        with condition:
            while len(collected) < len(wanted):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                condition.wait(timeout=remaining)
        missing = sorted(wanted - set(collected))
        if missing:
            raise HTTPException(504, {"cameras": [f"Failed to collect calibration images from: {', '.join(missing)}"]})
        return collected
    finally:
        try:
            client.disconnect()
        finally:
            client.loop_stop()


def _camera_rows(db, scene_id: str) -> list[Resource]:
    rows = db.scalars(select(Resource).where(Resource.kind == "camera").order_by(Resource.id)).all()
    return [row for row in rows if str((row.payload or {}).get("scene") or "") == str(scene_id)]


def _video_part(video: tuple[str, str, bytes] | None):
    if not video:
        return None
    filename, content_type, raw = video
    suffix = Path(filename or "").suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        raise HTTPException(400, {"map": ["Unsupported video file type."]})
    if content_type and content_type.lower() not in VIDEO_MIME_TYPES:
        raise HTTPException(400, {"map": [f"Uploaded file must be a video. Got content-type: {content_type}"]})
    header = raw[:16]
    valid = (
        (len(header) >= 12 and header[4:8] == b"ftyp")
        or header.startswith(b"\x1a\x45\xdf\xa3")
        or (header.startswith(b"RIFF") and b"AVI" in header)
    )
    if not valid:
        raise HTTPException(400, {"map": ["Uploaded file does not look like a valid video"]})
    return filename, raw, content_type or "application/octet-stream"


def start_mesh_generation(db, scene_id: str, actor, *, mesh_type: str = "mesh", video=None) -> dict:
    if mesh_type not in {"mesh", "pointcloud"}:
        raise HTTPException(400, {"mesh_type": ["mesh_type must be mesh or pointcloud"]})
    scene = get_resource(db, "scene", scene_id)
    cameras = _camera_rows(db, scene_id)
    if not cameras:
        raise HTTPException(400, {"cameras": ["At least one camera is required to generate a mesh."]})
    camera_values = [to_dict(row) for row in cameras]
    images = _collect_calibration_images(camera_values)

    files = []
    for camera in camera_values:
        camera_id = str(camera["uid"])
        image = images[camera_id]
        files.append(("images", (image["filename"], base64.b64decode(image["data"]), "image/jpeg")))
        files.append(("camera_ids", (None, camera_id)))
        pose = {
            "translation": list(camera.get("translation") or [0, 0, 0]),
            "rotation": list(camera.get("rotation") or [0, 0, 0]),
            "scale": list(camera.get("scale") or [1, 1, 1]),
        }
        files.append(("camera_locations", (None, json.dumps(pose))))
    video_part = _video_part(video)
    if video_part:
        files.append(("video", video_part))

    try:
        response = requests.post(
            f"{_mapping_url()}/reconstruction",
            data={"output_format": "glb", "mesh_type": mesh_type},
            files=files,
            timeout=int(os.getenv("MAPPING_REQUEST_TIMEOUT", "300")),
            verify=_verify(),
        )
    except requests.Timeout as exc:
        raise HTTPException(504, "Mapping service request timed out") from exc
    except requests.ConnectionError as exc:
        raise HTTPException(503, "Could not connect to mapping service") from exc
    try:
        payload = response.json()
    except Exception:
        payload = {}
    if not response.ok:
        raise HTTPException(502, payload.get("error") or f"Mapping service returned HTTP {response.status_code}")
    request_id = payload.get("request_id")
    if not request_id:
        raise HTTPException(502, "Mapping service did not return request_id")

    before = dict(scene.payload or {})
    upsert(db, "scene", scene_id, {"mesh_request_id": str(request_id), "mesh_state": "processing"}, actor, scene.revision)
    return {"success": True, "request_id": str(request_id), "processing_time": payload.get("processing_time", 0), "_before_scene": before}


def _quat_matrix(q):
    x, y, z, w = [float(v) for v in q]
    norm = math.sqrt(x*x + y*y + z*z + w*w)
    if norm <= 1e-12:
        return np.eye(3)
    x, y, z, w = x/norm, y/norm, z/norm, w/norm
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
    ], dtype=float)


def _euler_xyz_degrees(matrix3):
    matrix4 = np.eye(4)
    matrix4[:3, :3] = matrix3
    values = trimesh.transformations.euler_from_matrix(matrix4, axes="sxyz")
    return [float(math.degrees(v)) for v in values]


def _align_generated_mesh(mesh):
    to_origin, extents = trimesh.bounds.oriented_bounds(mesh)
    from_origin = np.linalg.inv(to_origin)
    axes = from_origin[:3, :3]
    center = from_origin[:3, 3]
    areas = [extents[1]*extents[2], extents[0]*extents[2], extents[0]*extents[1]]
    faces = []
    for axis_index in range(3):
        normal = axes[:, axis_index]
        for direction in (-1, 1):
            face_center = center + direction * (extents[axis_index] / 2.0) * normal
            faces.append((float(areas[axis_index]), float(face_center[2]), normal * direction))
    faces.sort(key=lambda item: (-item[0], item[1]))
    normal = np.asarray(faces[0][2], dtype=float)
    normal /= np.linalg.norm(normal)
    if normal[2] < 0:
        normal = -normal
    z_axis = np.array([0.0, 0.0, 1.0])
    cross = np.cross(normal, z_axis)
    cross_norm = np.linalg.norm(cross)
    if cross_norm > 1e-6:
        axis = cross / cross_norm
        angle = math.acos(float(np.clip(np.dot(normal, z_axis), -1.0, 1.0)))
        rotation4 = trimesh.transformations.rotation_matrix(angle, axis)
        rotation = rotation4[:3, :3]
    elif normal[2] > 0:
        rotation = np.eye(3)
        rotation4 = np.eye(4)
    else:
        rotation = np.diag([1.0, 1.0, -1.0])
        rotation4 = np.eye(4)
        rotation4[:3, :3] = rotation
    result = mesh.copy()
    result.apply_transform(rotation4)
    minimum = np.asarray(result.bounds[0], dtype=float)
    translation = -minimum
    result.apply_translation(translation)
    return result, rotation, translation


def _load_generated_glb(raw: bytes):
    try:
        loaded = trimesh.load(io.BytesIO(raw), file_type="glb", force="scene")
        mesh = loaded.to_geometry() if hasattr(loaded, "to_geometry") else loaded
        if not hasattr(mesh, "vertices") or len(mesh.vertices) == 0:
            raise ValueError("mesh contains no vertices")
        return mesh
    except Exception as exc:
        raise HTTPException(502, f"Mapping service returned invalid GLB data: {exc}") from exc


def _mapping_status(request_id: str) -> dict:
    try:
        response = requests.get(
            f"{_mapping_url()}/reconstruction/status/{request_id}",
            timeout=5,
            verify=_verify(),
        )
        try:
            payload = response.json()
        except Exception:
            payload = {"success": False, "error": "Non-JSON response from mapping service"}
        payload.setdefault("success", response.ok)
        payload["status_code"] = response.status_code
        return payload
    except requests.Timeout:
        return {"success": False, "error": "Mapping service status timed out"}
    except requests.ConnectionError:
        return {"success": False, "error": "Could not connect to mapping service"}


def mesh_generation_status(db, scene_id: str, request_id: str, actor) -> dict:
    scene = get_resource(db, "scene", scene_id)
    payload = _mapping_status(request_id)
    if not payload.get("success") or payload.get("state") != "complete":
        return payload
    if (scene.payload or {}).get("mesh_request_id") == request_id and (scene.payload or {}).get("mesh_state") == "complete":
        payload["finalized"] = True
        return payload
    result = payload.get("result") or {}
    if not result.get("success"):
        upsert(db, "scene", scene_id, {"mesh_state": "failed"}, actor, scene.revision)
        return payload
    encoded = result.get("glb_data")
    if not encoded:
        raise HTTPException(502, "Mapping service did not return GLB data")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise HTTPException(502, "Mapping service returned invalid GLB data") from exc

    aligned, rotation, translation = _align_generated_mesh(_load_generated_glb(raw))
    glb = aligned.export(file_type="glb")
    scene_name = str((scene.payload or {}).get("name") or "scene")
    map_url = store_bytes(f"{scene_name}_generated_mesh.glb", glb, kind="scene-map")
    processed = process_uploaded_mesh(
        map_url, scene_name,
        current_rotation=[0.0, 0.0, 0.0],
        current_translation=[0.0, 0.0, 0.0],
        current_scale=[1.0, 1.0, 1.0],
        auto_align=False,
    )
    before_scene = dict(scene.payload or {})
    update = {
        **processed,
        "map_processed": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mesh_request_id": request_id,
        "mesh_state": "complete",
    }
    scene = upsert(db, "scene", scene_id, update, actor, scene.revision)

    poses = {}
    for item in result.get("camera_poses") or []:
        if isinstance(item, dict) and item.get("camera_id"):
            poses[str(item["camera_id"])] = item
    intrinsics = {}
    for item in result.get("intrinsics") or []:
        if isinstance(item, dict) and item.get("camera_id") and item.get("K") is not None:
            intrinsics[str(item["camera_id"])] = item["K"]

    changed = []
    for camera in _camera_rows(db, scene_id):
        camera_id = str(camera.uid)
        pose = poses.get(camera_id)
        if not pose:
            continue
        before = to_dict(camera)
        current = dict(camera.payload or {})
        position = np.asarray(pose.get("translation") or [0, 0, 0], dtype=float)
        quaternion = pose.get("rotation") or [0, 0, 0, 1]
        new_position = rotation @ position + translation
        new_rotation = rotation @ _quat_matrix(quaternion)
        update_camera = {
            "translation": [float(v) for v in new_position],
            "rotation": _euler_xyz_degrees(new_rotation),
            "scale": list(current.get("scale") or [1, 1, 1]),
            "transform_type": "euler",
        }
        K = intrinsics.get(camera_id)
        if isinstance(K, list) and len(K) >= 3 and all(isinstance(row, list) and len(row) >= 3 for row in K[:3]):
            update_camera["intrinsics"] = {
                "fx": float(K[0][0]), "fy": float(K[1][1]),
                "cx": float(K[0][2]), "cy": float(K[1][2]),
            }
        updated = upsert(db, "camera", camera_id, update_camera, actor, camera.revision)
        changed.append({"before": before, "after": to_dict(updated)})

    payload["finalized"] = True
    payload["_before_scene"] = before_scene
    payload["_after_scene"] = dict(scene.payload or {})
    payload["_changed_cameras"] = changed
    return payload
