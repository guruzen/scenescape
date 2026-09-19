from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from .database import Resource


SCENE_ALLOWED_FIELDS = {
    "uid", "name", "map_type", "use_tracker", "output_lla", "trs_matrix",
    "map_corners_lla", "map", "thumbnail", "cameras", "sensors", "regions",
    "tripwires", "parent", "transform", "mesh_translation", "mesh_rotation",
    "mesh_scale", "scale", "children", "regulated_rate", "external_update_rate",
    "camera_calibration", "apriltag_size", "map_processed", "polycam_data",
    "number_of_localizations", "global_feature", "local_feature", "matcher",
    "minimum_number_of_matches", "inlier_threshold", "geospatial_provider",
    "map_zoom", "map_center_lat", "map_center_lng", "map_bearing",
}

SCENE_DEFAULTS = {
    "map_type": "map_upload",
    "use_tracker": True,
    "output_lla": False,
    "mesh_translation": [0.0, 0.0, 0.0],
    "mesh_rotation": [0.0, 0.0, 0.0],
    "mesh_scale": [1.0, 1.0, 1.0],
    "regulated_rate": 30.0,
    "external_update_rate": 30.0,
    "camera_calibration": "Manual",
    "apriltag_size": 0.162,
    "number_of_localizations": 50,
    "global_feature": "netvlad",
    "local_feature": {"sift": {}},
    "matcher": {"NN-ratio": {}},
    "minimum_number_of_matches": 20,
    "inlier_threshold": 0.5,
    "geospatial_provider": "google",
    "map_zoom": 15.0,
    "map_bearing": 0.0,
}

CAMERA_ALLOWED_FIELDS = {
    "uid", "name", "sensor_id", "intrinsics", "transform_type", "transforms",
    "distortion", "translation", "rotation", "scale", "resolution", "scene",
    "threshold", "aspect", "cv_subsystem", "undistort", "modelconfig",
    "use_camera_pipeline", "detection_labels", "command", "camerachain",
    "camera_pipeline",
}


ASSET_ALLOWED_FIELDS = {
    "uid", "name", "x_size", "y_size", "z_size", "tracking_radius",
    "shift_type", "mark_color", "model_3d", "scale", "project_to_map",
    "rotation_from_velocity", "rotation_x", "rotation_y", "rotation_z",
    "translation_x", "translation_y", "translation_z", "x_buffer_size",
    "y_buffer_size", "z_buffer_size", "geometric_center", "mass",
    "center_of_mass", "is_static", "ttl", "linear_damping",
    "angular_damping", "coefficient_of_restitution", "friction_coefficients",
}

ASSET_DEFAULTS = {
    "x_size": 1.0, "y_size": 1.0, "z_size": 1.0,
    "x_buffer_size": 0.0, "y_buffer_size": 0.0, "z_buffer_size": 0.0,
    "tracking_radius": 2.0, "shift_type": 1, "mark_color": "#888888",
    "scale": 1.0, "project_to_map": False, "rotation_from_velocity": False,
    "rotation_x": 0.0, "rotation_y": 0.0, "rotation_z": 0.0,
    "translation_x": 0.0, "translation_y": 0.0, "translation_z": 0.0,
    "geometric_center": [0.0, 0.0, 0.0], "mass": 1.0,
    "center_of_mass": [0.0, 0.0, 0.0], "is_static": False, "ttl": 0.0,
    "linear_damping": 0.05, "angular_damping": 0.05,
    "coefficient_of_restitution": 0.5, "friction_coefficients": [0.5, 0.4],
}

CAMERA_DEFAULTS = {
    "intrinsics": {"fx": 570.0, "fy": 570.0, "cx": 320.0, "cy": 240.0},
    "transform_type": "3d-2d point correspondence",
    "translation": [0.0, 0.0, 0.0],
    "rotation": [0.0, 0.0, 0.0],
    "scale": [1.0, 1.0, 1.0],
    "resolution": [640, 480],
    "cv_subsystem": "AUTO",
    "undistort": False,
    "modelconfig": "model_config.json",
    "use_camera_pipeline": False,
}

SCENE_CHOICES = {
    "map_type": {"map_upload", "geospatial_map"},
    "camera_calibration": {"AprilTag", "Markerless", "Manual"},
    "geospatial_provider": {"google", "mapbox"},
}
CAMERA_CHOICES = {
    "transform_type": {"matrix", "euler", "quaternion", "3d-2d point correspondence"},
    "cv_subsystem": {"AUTO", "GPU", "CPU"},
}

CALIBRATION_FIELDS = {
    "camera_calibration", "matcher", "number_of_localizations", "global_feature",
    "local_feature", "minimum_number_of_matches", "scale", "apriltag_size",
    "inlier_threshold",
}


def _bad(field: str, message: str) -> None:
    raise HTTPException(400, detail={field: [message]})


def _existing(db, kind: str, uid: str | None) -> Resource | None:
    if not uid:
        return None
    return db.scalar(select(Resource).where(Resource.kind == kind, Resource.uid == str(uid)))


def _name_conflict(db, kind: str, name: str, exclude_uid: str | None = None) -> bool:
    rows = db.scalars(select(Resource).where(Resource.kind == kind)).all()
    for row in rows:
        if exclude_uid is not None and row.uid == str(exclude_uid):
            continue
        if str((row.payload or {}).get("name", "")) == name:
            return True
    return False


def _scene_exists(db, uid: str) -> bool:
    return db.scalar(select(Resource.id).where(Resource.kind == "scene", Resource.uid == str(uid)).limit(1)) is not None


def _vec3(field: str, value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        _bad(field, "Must be a list of exactly 3 numeric values [x, y, z].")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, (int, float)):
            axis = "xyz"[index]
            _bad(field, f'Axis "{axis}" must be a number, got {type(item).__name__}.')
        result.append(float(item))
    return result


def _positive(field: str, value: Any, *, allow_zero: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        _bad(field, "A valid number is required.")
    if (number < 0 if allow_zero else number <= 0):
        _bad(field, "Ensure this value is greater than or equal to 0." if allow_zero else "Ensure this value is greater than 0.")
    return number


def _choice(field: str, value: Any, choices: set[str]) -> str:
    text = str(value)
    if text not in choices:
        _bad(field, f'"{text}" is not a valid choice.')
    return text


def _map_corners(value: Any) -> list[list[float]]:
    if not isinstance(value, list):
        _bad("map_corners_lla", "map_corners_lla must be a JSON array of coordinates.")
    if len(value) != 4:
        _bad("map_corners_lla", "map_corners_lla must contain exactly 4 corner coordinates.")
    result: list[list[float]] = []
    for index, corner in enumerate(value):
        if not isinstance(corner, list) or len(corner) != 3:
            _bad("map_corners_lla", f"Corner {index + 1} must be an array of [latitude, longitude, altitude].")
        try:
            lat, lon, alt = float(corner[0]), float(corner[1]), float(corner[2])
        except (TypeError, ValueError):
            _bad("map_corners_lla", f"Corner {index + 1} coordinates must be numeric values.")
        if not -90 <= lat <= 90:
            _bad("map_corners_lla", f"Corner {index + 1} latitude ({lat}) must be between -90 and 90 degrees.")
        if not -180 <= lon <= 180:
            _bad("map_corners_lla", f"Corner {index + 1} longitude ({lon}) must be between -180 and 180 degrees.")
        result.append([lat, lon, alt])
    return result


def _intrinsics(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        _bad("intrinsics", f'Invalid intrinsics: "{value}"')
    if all(key in value for key in ("fx", "fy", "cx", "cy")):
        keys = ("fx", "fy", "cx", "cy")
    elif all(key in value for key in ("hfov", "vfov")):
        keys = ("hfov", "vfov")
    elif "fov" in value:
        keys = ("fov",)
    else:
        _bad("intrinsics", f'Invalid intrinsics: "{value}"')
    result = dict(value)
    for key in keys:
        try:
            number = float(value[key])
        except (TypeError, ValueError):
            _bad("intrinsics", f'Invalid intrinsics: "{value}"')
        if key in {"fx", "fy", "cx", "cy"} and number <= 0:
            _bad("intrinsics", f'Invalid intrinsics: "{value}"')
        result[key] = number
    return result


def _distortion(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        _bad("distortion", f'Invalid distortion: "{value}"')
    allowed = {"k1", "k2", "p1", "p2", "k3", "k4", "k5", "k6", "s1", "s2", "s3", "s4", "taux", "tauy"}
    result: dict[str, float] = {}
    for key, item in value.items():
        if key not in allowed:
            continue
        try:
            result[key] = float(item)
        except (TypeError, ValueError):
            _bad("distortion", f'Invalid distortion: "{value}"')
    return result


def _resolution(value: Any) -> list[int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        _bad("resolution", "Resolution must contain [width, height].")
    try:
        width, height = int(value[0]), int(value[1])
    except (TypeError, ValueError):
        _bad("resolution", "Resolution must contain integer width and height values.")
    if width <= 0 or height <= 0:
        _bad("resolution", "Resolution width and height must be greater than 0.")
    return [width, height]


def _number(field: str, value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        _bad(field, "A valid number is required.")


def _bounded(field: str, value: Any, low: float | None = None, high: float | None = None) -> float:
    number = _number(field, value)
    if low is not None and number < low:
        _bad(field, f"Ensure this value is greater than or equal to {low}.")
    if high is not None and number > high:
        _bad(field, f"Ensure this value is less than or equal to {high}.")
    return number


def _numeric_list(field: str, value: Any, length: int) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        _bad(field, f"Must contain exactly {length} numeric values.")
    return [_number(field, item) for item in value]


def normalize_asset(db, body: dict, *, uid: str | None, creating: bool, legacy: bool) -> tuple[dict, str | None]:
    if not isinstance(body, dict) or (not body and creating):
        _bad("body", "Request body is required.")
    data = deepcopy(body)
    resolved_uid = uid
    # Asset3DSerializer exposes uid read-only; DRF ignores it on input. Native
    # metadata may also round-trip through the React JSON editor.
    data.pop("uid", None)
    if not legacy:
        data.pop("kind", None)
        data.pop("revision", None)
    data = {key: value for key, value in data.items() if key in ASSET_ALLOWED_FIELDS - {"uid"}}
    existing = _existing(db, "asset", uid) if not creating else None

    if creating and "name" not in data:
        _bad("name", "This field is required.")
    if "name" in data:
        name = str(data["name"])
        if not name.strip():
            _bad("name", "This field may not be blank.")
        if len(name) > 150:
            _bad("name", "Ensure this field has no more than 150 characters.")
        if _name_conflict(db, "asset", name, exclude_uid=uid if not creating else None):
            _bad("name", f"An object library with the name '{name}' already exists.")
        data["name"] = name

    for field in ("x_size", "y_size", "z_size", "mass", "ttl"):
        if field in data and data[field] is not None:
            data[field] = _bounded(field, data[field], 0.0)
    for field in ("linear_damping", "angular_damping", "coefficient_of_restitution"):
        if field in data and data[field] is not None:
            data[field] = _bounded(field, data[field], 0.0, 1.0)
    for field in (
        "tracking_radius", "scale", "rotation_x", "rotation_y", "rotation_z",
        "translation_x", "translation_y", "translation_z", "x_buffer_size",
        "y_buffer_size", "z_buffer_size",
    ):
        if field in data and data[field] is not None:
            data[field] = _number(field, data[field])
    if "shift_type" in data and data["shift_type"] is not None:
        try:
            data["shift_type"] = int(data["shift_type"])
        except (TypeError, ValueError):
            _bad("shift_type", "A valid integer is required.")
    for field in ("geometric_center", "center_of_mass"):
        if field in data and data[field] is not None:
            data[field] = _numeric_list(field, data[field], 3)
    if "friction_coefficients" in data and data["friction_coefficients"] is not None:
        data["friction_coefficients"] = _numeric_list("friction_coefficients", data["friction_coefficients"], 2)
    for field in ("project_to_map", "rotation_from_velocity", "is_static"):
        if field in data and data[field] is not None:
            data[field] = bool(data[field])
    if "mark_color" in data and data["mark_color"] is not None:
        data["mark_color"] = str(data["mark_color"])
    if "model_3d" in data and data["model_3d"] not in (None, ""):
        data["model_3d"] = str(data["model_3d"])

    if creating:
        merged = deepcopy(ASSET_DEFAULTS)
        merged.update(data)
        data = merged
    elif existing is None:
        raise HTTPException(404, "Resource not found")
    return data, resolved_uid

def normalize_scene(db, body: dict, *, uid: str | None, creating: bool, legacy: bool) -> tuple[dict, str | None]:
    if not isinstance(body, dict) or not body:
        _bad("body", "Request body is required.")
    data = deepcopy(body)
    resolved_uid = uid
    if not legacy:
        if creating and data.get("uid") not in (None, ""):
            resolved_uid = str(data.pop("uid"))
        else:
            data.pop("uid", None)
        data.pop("kind", None)
        data.pop("revision", None)
    elif "uid" in data:
        _bad("uid", "This field is read-only.")
    unknown = set(data) - (SCENE_ALLOWED_FIELDS - {"uid"})
    if unknown:
        _bad(sorted(unknown)[0], "Unknown field.")
    existing = _existing(db, "scene", uid) if not creating else None
    if creating and "name" not in data:
        _bad("name", "This field is required.")
    if "name" in data:
        name = str(data["name"])
        if not name.strip():
            _bad("name", "This field is required.")
        if len(name) > 150:
            _bad("name", "Ensure this field has no more than 150 characters.")
        if _name_conflict(db, "scene", name, exclude_uid=uid if not creating else None):
            _bad("name", f'A scene with the name "{name}" already exists.')
        data["name"] = name
    for field in ("mesh_translation", "mesh_rotation", "mesh_scale"):
        if field in data:
            data[field] = _vec3(field, data[field])
    for field, choices in SCENE_CHOICES.items():
        if field in data and data[field] is not None:
            data[field] = _choice(field, data[field], choices)
    for field in ("scale", "regulated_rate", "external_update_rate"):
        if field in data and data[field] is not None:
            data[field] = _positive(field, data[field])
    for field in ("map_zoom", "inlier_threshold"):
        if field in data and data[field] is not None:
            data[field] = _positive(field, data[field], allow_zero=True)
    if "map_corners_lla" in data and data["map_corners_lla"] is not None:
        data["map_corners_lla"] = _map_corners(data["map_corners_lla"])
    if data.get("output_lla") is True:
        existing_corners = (existing.payload or {}).get("map_corners_lla") if existing else None
        if data.get("map_corners_lla") is None and existing_corners is None:
            _bad("map_corners_lla", "This field must be set when enabling output_lla.")
    if existing:
        previous = existing.payload or {}
        if any(field in data and data.get(field) != previous.get(field) for field in CALIBRATION_FIELDS):
            data["map_processed"] = None
    if creating:
        merged = deepcopy(SCENE_DEFAULTS)
        merged.update(data)
        data = merged
    return data, resolved_uid


def normalize_camera(db, body: dict, *, uid: str | None, creating: bool, legacy: bool) -> tuple[dict, str | None]:
    if not isinstance(body, dict) or not body:
        _bad("body", "Request body is required.")
    data = deepcopy(body)
    resolved_uid = uid
    if not legacy:
        if creating and data.get("uid") not in (None, ""):
            resolved_uid = str(data.pop("uid"))
        else:
            data.pop("uid", None)
        data.pop("kind", None)
        data.pop("revision", None)
    else:
        data.pop("uid", None)
    data = {key: value for key, value in data.items() if key in CAMERA_ALLOWED_FIELDS - {"uid"}}
    if "name" not in data:
        _bad("name", "This field is required.")
    name = str(data["name"])
    if not name.strip():
        _bad("name", "This field may not be blank.")
    if len(name) > 150:
        _bad("name", "Ensure this field has no more than 150 characters.")
    if creating and _name_conflict(db, "camera", name):
        _bad("name", f'A camera with the name "{name}" already exists.')
    data["name"] = name
    sensor_id = data.pop("sensor_id", None)
    if sensor_id not in (None, ""):
        resolved_uid = str(sensor_id)
    elif creating and resolved_uid is None:
        resolved_uid = name.replace(" ", "_")
    if creating and resolved_uid is not None and _existing(db, "camera", resolved_uid) is not None:
        _bad("sensor_id", f"A camera with ID '{resolved_uid}' already exists.")
    if "scene" in data and data["scene"] not in (None, ""):
        scene_uid = str(data["scene"])
        if not _scene_exists(db, scene_uid):
            _bad("scene", "Scene with given UUID does not exist.")
        data["scene"] = scene_uid
    if "intrinsics" in data and data["intrinsics"] is not None:
        data["intrinsics"] = _intrinsics(data["intrinsics"])
    if "distortion" in data and data["distortion"] is not None:
        data["distortion"] = _distortion(data["distortion"])
    if "resolution" in data and data["resolution"] is not None:
        data["resolution"] = _resolution(data["resolution"])
    if "translation" in data and data["translation"] is not None:
        data["translation"] = _vec3("translation", data["translation"])
    if "scale" in data and data["scale"] is not None:
        data["scale"] = _vec3("scale", data["scale"])
    if "transform_type" in data and data["transform_type"] is not None:
        data["transform_type"] = _choice("transform_type", data["transform_type"], CAMERA_CHOICES["transform_type"])
    transform_type = data.get("transform_type")
    if "rotation" in data and data["rotation"] is not None:
        if transform_type == "quaternion":
            value = data["rotation"]
            if not isinstance(value, (list, tuple)) or len(value) != 4:
                _bad("rotation", "Quaternion rotation must contain exactly 4 numeric values [x, y, z, w].")
            try:
                from scipy.spatial.transform import Rotation
                data["rotation"] = Rotation.from_quat([float(item) for item in value]).as_euler("XYZ", degrees=True).tolist()
            except (TypeError, ValueError) as exc:
                _bad("rotation", f"Invalid quaternion rotation: {exc}")
            # 2026.2 CamSerializer normalizes quaternion API input to Euler storage.
            data["transform_type"] = "euler"
        else:
            data["rotation"] = _vec3("rotation", data["rotation"])
    for field, choices in CAMERA_CHOICES.items():
        if field == "transform_type":
            continue
        if field in data and data[field] is not None:
            data[field] = _choice(field, data[field], choices)
    if data.get("use_camera_pipeline") is True and not data.get("camera_pipeline"):
        _bad("camera_pipeline", "camera_pipeline cannot be empty when use_camera_pipeline is true.")
    if creating:
        merged = deepcopy(CAMERA_DEFAULTS)
        merged.update(data)
        data = merged
    return data, resolved_uid


def normalize_resource(db, kind: str, body: dict, *, uid: str | None = None, creating: bool, legacy: bool = False) -> tuple[dict, str | None]:
    if kind == "scene":
        return normalize_scene(db, body, uid=uid, creating=creating, legacy=legacy)
    if kind == "camera":
        return normalize_camera(db, body, uid=uid, creating=creating, legacy=legacy)
    if kind == "asset":
        return normalize_asset(db, body, uid=uid, creating=creating, legacy=legacy)
    if not isinstance(body, dict):
        raise HTTPException(400, "Resource payload must be an object")
    data = deepcopy(body)
    resolved_uid = uid
    if not legacy:
        if creating and data.get("uid") not in (None, ""):
            resolved_uid = str(data.pop("uid"))
        else:
            data.pop("uid", None)
        data.pop("kind", None)
        data.pop("revision", None)
    return data, resolved_uid
