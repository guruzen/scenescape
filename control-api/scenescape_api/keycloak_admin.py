from __future__ import annotations

import json
import os
import re
import time
from functools import lru_cache
from urllib.parse import quote

import requests
from fastapi import HTTPException

SCENESCAPE_ROLES = {"scenescape-viewer", "scenescape-admin"}
ACL_ATTRIBUTE = "scenescape_acls"
SCENE_ATTRIBUTE = "scenescape_scenes"

TOPIC_TEMPLATES = {
    "CHANNEL": "scenescape/channel/${channel}",
    "CMD_CAMERA": "scenescape/cmd/camera/${camera_id}",
    "CMD_DATABASE": "scenescape/cmd/database",
    "CMD_KUBECLIENT": "scenescape/cmd/kubeclient",
    "CMD_SCENE_UPDATE": "scenescape/cmd/scene/update/${scene_id}",
    "DATA_AUTOCALIB_CAM_POSE": "scenescape/autocalibration/camera/pose/${camera_id}",
    "DATA_CAMERA": "scenescape/data/camera/${camera_id}",
    "DATA_EXTERNAL": "scenescape/external/${scene_id}/${thing_type}",
    "DATA_REGION": "scenescape/data/region/${scene_id}/${region_id}/${thing_type}",
    "DATA_REGULATED": "scenescape/regulated/scene/${scene_id}",
    "DATA_SCENE": "scenescape/data/scene/${scene_id}/${thing_type}",
    "DATA_SENSOR": "scenescape/data/sensor/${sensor_id}",
    "EVENT": "scenescape/event/${region_type}/${scene_id}/${region_id}/${event_type}",
    "IMAGE_CALIBRATE": "scenescape/image/calibration/camera/${camera_id}",
    "IMAGE_CAMERA": "scenescape/image/camera/${camera_id}",
    "SYS_CHILDSCENE_STATUS": "scenescape/sys/child/status/${scene_id}",
    "DATA_CHILD_TRIPWIRES": "scenescape/data/child/tripwires/${scene_id}",
    "DATA_CHILD_ROIS": "scenescape/data/child/rois/${scene_id}",
}
VALID_ACCESS = {0, 1, 2, 3}

SERVICE_ACL_POLICY = {
    "browser": [
        ("DATA_CAMERA", 1), ("CHANNEL", 1), ("IMAGE_CAMERA", 1), ("IMAGE_CALIBRATE", 1),
        ("CMD_DATABASE", 3), ("CMD_CAMERA", 3), ("DATA_AUTOCALIB_CAM_POSE", 1),
        ("CMD_KUBECLIENT", 3), ("EVENT", 1), ("SYS_CHILDSCENE_STATUS", 3),
        ("DATA_REGULATED", 1), ("DATA_EXTERNAL", 1),
    ],
    "calibration": [
        ("IMAGE_CALIBRATE", 1), ("CMD_SCENE_UPDATE", 1), ("DATA_AUTOCALIB_CAM_POSE", 2),
    ],
    "controller": [
        ("CMD_CAMERA", 3), ("IMAGE_CALIBRATE", 1), ("CMD_DATABASE", 3), ("DATA_REGULATED", 2),
        ("DATA_SCENE", 2), ("DATA_AUTOCALIB_CAM_POSE", 2), ("CMD_KUBECLIENT", 3),
        ("CMD_SCENE_UPDATE", 3), ("DATA_EXTERNAL", 3), ("DATA_REGION", 2), ("DATA_SENSOR", 1),
        ("EVENT", 3), ("SYS_CHILDSCENE_STATUS", 3), ("DATA_CAMERA", 1),
    ],
}


def _service_identities() -> dict[str, dict]:
    result = {}
    for item in filter(None, os.getenv("SERVICE_AUTH_FILES", "").replace(",", os.pathsep).split(os.pathsep)):
        path = os.path.basename(item).lower()
        policy = "controller" if "controller" in path else "calibration" if "calibration" in path else "browser" if "browser" in path else ""
        if not policy:
            continue
        try:
            data = json.loads(open(item, encoding="utf-8").read())
        except Exception:
            continue
        username = str(data.get("user") or "").strip()
        if username:
            result[username] = {
                "uid": f"service:{policy}",
                "username": username,
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
                "first_name": "",
                "last_name": "",
                "email": "",
                "service_type": policy,
                "roles": ["scenescape-service"],
                "scenes": ["*"],
                "acls": [{"topic": topic, "access": access} for topic, access in SERVICE_ACL_POLICY[policy]],
            }
    return result


def list_service_identities() -> list[dict]:
    return list(_service_identities().values())


def get_service_identity(username: str) -> dict | None:
    return _service_identities().get(username)


def _base_url() -> str:
    explicit = os.getenv("KEYCLOAK_ADMIN_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    jwks = os.getenv("OIDC_JWKS_URL", "")
    marker = "/realms/"
    if marker in jwks:
        return jwks.split(marker, 1)[0].rstrip("/")
    return os.getenv("KEYCLOAK_URL", "http://keycloak:8080/auth").rstrip("/")


def _realm() -> str:
    return os.getenv("KEYCLOAK_REALM", "scenescape")


def _admin_credentials() -> tuple[str, str]:
    username = os.getenv("KEYCLOAK_ADMIN_USERNAME", "").strip()
    password = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "")
    if not username or not password:
        raise HTTPException(503, "Keycloak administration credentials are not configured")
    return username, password


@lru_cache(maxsize=8)
def _admin_token_bucket(bucket: int, base_url: str, username: str, password: str) -> str:
    try:
        response = requests.post(
            f"{base_url}/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": username,
                "password": password,
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        raise HTTPException(503, f"Keycloak administration unavailable: {exc}") from exc
    if response.status_code != 200:
        raise HTTPException(503, "Keycloak administration authentication failed")
    token = response.json().get("access_token")
    if not token:
        raise HTTPException(503, "Keycloak administration token was not returned")
    return str(token)


def _admin_token() -> str:
    username, password = _admin_credentials()
    ttl = max(10, int(os.getenv("KEYCLOAK_ADMIN_TOKEN_CACHE_SECONDS", "30")))
    return _admin_token_bucket(int(time.monotonic() // ttl), _base_url(), username, password)


def _request(method: str, path: str, *, json_body=None, params=None, expected=(200, 201, 204)):
    headers = {"Authorization": f"Bearer {_admin_token()}"}
    try:
        response = requests.request(
            method,
            f"{_base_url()}/admin/realms/{quote(_realm(), safe='')}/{path.lstrip('/')}",
            headers=headers,
            json=json_body,
            params=params,
            timeout=12,
        )
    except requests.RequestException as exc:
        raise HTTPException(503, f"Keycloak administration unavailable: {exc}") from exc
    if response.status_code not in expected:
        detail = response.text.strip()
        try:
            payload = response.json()
            detail = payload.get("errorMessage") or payload.get("error") or detail
        except Exception:
            pass
        status = 400 if response.status_code in {400, 409} else response.status_code
        raise HTTPException(status, detail or f"Keycloak returned HTTP {response.status_code}")
    if response.status_code == 204 or not response.content:
        return None, response.headers
    return response.json(), response.headers


def _attrs(rep: dict) -> dict[str, list[str]]:
    raw = rep.get("attributes") or {}
    result: dict[str, list[str]] = {}
    for key, value in raw.items():
        if isinstance(value, list):
            result[str(key)] = [str(item) for item in value]
        elif value is not None:
            result[str(key)] = [str(value)]
    return result


def _decode_acls(rep: dict) -> list[dict]:
    values = _attrs(rep).get(ACL_ATTRIBUTE, [])
    result = []
    for value in values:
        try:
            item = json.loads(value)
        except Exception:
            continue
        if isinstance(item, dict) and item.get("topic") in TOPIC_TEMPLATES:
            try:
                access = int(item.get("access"))
            except (TypeError, ValueError):
                continue
            if access in VALID_ACCESS:
                result.append({"topic": str(item["topic"]), "access": access})
    return result


def _normalize_acls(value) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HTTPException(400, {"acls": ["Must be a list."]})
    seen = set()
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise HTTPException(400, {"acls": ["Each ACL must be an object."]})
        topic = str(item.get("topic") or "")
        if topic not in TOPIC_TEMPLATES:
            raise HTTPException(400, {"acls": [f"Invalid topic template: {topic}"]})
        try:
            access = int(item.get("access"))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, {"acls": ["Access must be an integer."]}) from exc
        if access not in VALID_ACCESS:
            raise HTTPException(400, {"acls": [f"Invalid access value: {access}"]})
        if topic in seen:
            raise HTTPException(400, {"acls": [f"Duplicate topic: {topic}"]})
        seen.add(topic)
        result.append({"topic": topic, "access": access})
    return result


def _normalize_scenes(value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HTTPException(400, {"scenes": ["Must be a list."]})
    return list(dict.fromkeys(str(item) for item in value if str(item).strip()))


def _validate_email(value: str) -> str:
    value = str(value or "")
    if value and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
        raise HTTPException(400, {"email": ["Enter a valid email address."]})
    return value


def _get_user_rep(username: str) -> dict:
    users, _ = _request("GET", "users", params={"username": username, "exact": "true"})
    matches = [item for item in users or [] if str(item.get("username")) == username]
    if not matches:
        raise HTTPException(404, "User not found")
    return matches[0]


def _realm_roles_for_user(user_id: str) -> list[dict]:
    roles, _ = _request("GET", f"users/{quote(user_id, safe='')}/role-mappings/realm")
    return list(roles or [])


@lru_cache(maxsize=8)
def _realm_role(name: str) -> dict:
    role, _ = _request("GET", f"roles/{quote(name, safe='')}")
    return role


def _set_roles(user_id: str, requested: list[str]) -> None:
    desired = {role for role in requested if role in SCENESCAPE_ROLES}
    existing = [role for role in _realm_roles_for_user(user_id) if role.get("name") in SCENESCAPE_ROLES]
    existing_names = {str(role.get("name")) for role in existing}
    remove = [role for role in existing if role.get("name") not in desired]
    add = [_realm_role(name) for name in sorted(desired - existing_names)]
    if remove:
        _request("DELETE", f"users/{quote(user_id, safe='')}/role-mappings/realm", json_body=remove, expected=(204,))
    if add:
        _request("POST", f"users/{quote(user_id, safe='')}/role-mappings/realm", json_body=add, expected=(204,))


def user_to_dict(rep: dict) -> dict:
    roles = sorted(
        str(role.get("name")) for role in _realm_roles_for_user(str(rep["id"]))
        if role.get("name") in SCENESCAPE_ROLES
    )
    attrs = _attrs(rep)
    return {
        "uid": str(rep.get("id") or ""),
        "username": str(rep.get("username") or ""),
        "is_active": bool(rep.get("enabled", True)),
        "is_staff": "scenescape-admin" in roles,
        "is_superuser": "scenescape-admin" in roles,
        "first_name": str(rep.get("firstName") or ""),
        "last_name": str(rep.get("lastName") or ""),
        "email": str(rep.get("email") or ""),
        "roles": roles,
        "scenes": attrs.get(SCENE_ATTRIBUTE, []),
        "acls": _decode_acls(rep),
    }


def list_users() -> list[dict]:
    reps, _ = _request("GET", "users", params={"max": 1000})
    return [user_to_dict(rep) for rep in reps or []]


def get_user(username: str) -> dict:
    return user_to_dict(_get_user_rep(username))


def create_user(body: dict) -> dict:
    if not isinstance(body, dict):
        raise HTTPException(400, "Request body is required")
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    if not username:
        raise HTTPException(400, {"username": ["This field is required."]})
    if get_service_identity(username) is not None:
        raise HTTPException(400, {"username": ["This username is reserved for a mounted service identity."]})
    if not password:
        raise HTTPException(400, {"password": ["This field is required."]})
    email = _validate_email(body.get("email", ""))
    roles = body.get("roles")
    if roles is None:
        roles = ["scenescape-viewer"]
    if not isinstance(roles, list):
        raise HTTPException(400, {"roles": ["Must be a list."]})
    role_names = [str(item) for item in roles]
    invalid_roles = [item for item in role_names if item not in SCENESCAPE_ROLES]
    if invalid_roles:
        raise HTTPException(400, {"roles": [f"Invalid SceneScape role: {invalid_roles[0]}"]})
    roles = role_names or ["scenescape-viewer"]
    scenes = _normalize_scenes(body.get("scenes", []))
    acls = _normalize_acls(body.get("acls", []))
    attrs = {
        SCENE_ATTRIBUTE: scenes,
        ACL_ATTRIBUTE: [json.dumps(item, separators=(",", ":")) for item in acls],
    }
    rep = {
        "username": username,
        "enabled": bool(body.get("is_active", True)),
        "firstName": str(body.get("first_name") or ""),
        "lastName": str(body.get("last_name") or ""),
        "email": email,
        "emailVerified": False,
        "attributes": attrs,
        "credentials": [{"type": "password", "value": password, "temporary": bool(body.get("temporary_password", False))}],
    }
    _, headers = _request("POST", "users", json_body=rep, expected=(201,))
    location = str(headers.get("Location") or headers.get("location") or "")
    user_id = location.rstrip("/").split("/")[-1]
    if not user_id:
        user_id = str(_get_user_rep(username)["id"])
    _set_roles(user_id, roles)
    _clear_acl_cache()
    return get_user(username)


def update_user(username: str, body: dict) -> dict:
    if not isinstance(body, dict):
        raise HTTPException(400, "Request body is required")
    rep = _get_user_rep(username)
    user_id = str(rep["id"])
    attrs = _attrs(rep)
    if "email" in body:
        rep["email"] = _validate_email(body.get("email", ""))
    if "first_name" in body:
        rep["firstName"] = str(body.get("first_name") or "")
    if "last_name" in body:
        rep["lastName"] = str(body.get("last_name") or "")
    if "is_active" in body:
        rep["enabled"] = bool(body.get("is_active"))
    if "username" in body:
        new_username = str(body.get("username") or "").strip()
        if not new_username:
            raise HTTPException(400, {"username": ["This field may not be blank."]})
        rep["username"] = new_username
    if "scenes" in body:
        attrs[SCENE_ATTRIBUTE] = _normalize_scenes(body.get("scenes"))
    if "acls" in body:
        attrs[ACL_ATTRIBUTE] = [json.dumps(item, separators=(",", ":")) for item in _normalize_acls(body.get("acls"))]
    rep["attributes"] = attrs
    rep.pop("credentials", None)
    _request("PUT", f"users/{quote(user_id, safe='')}", json_body=rep, expected=(204,))
    if "password" in body:
        password = str(body.get("password") or "")
        if not password:
            raise HTTPException(400, {"password": ["This field may not be blank."]})
        _request(
            "PUT",
            f"users/{quote(user_id, safe='')}/reset-password",
            json_body={"type": "password", "value": password, "temporary": bool(body.get("temporary_password", False))},
            expected=(204,),
        )
    if "roles" in body:
        if not isinstance(body["roles"], list):
            raise HTTPException(400, {"roles": ["Must be a list."]})
        role_names = [str(item) for item in body["roles"]]
        invalid_roles = [item for item in role_names if item not in SCENESCAPE_ROLES]
        if invalid_roles:
            raise HTTPException(400, {"roles": [f"Invalid SceneScape role: {invalid_roles[0]}"]})
        _set_roles(user_id, role_names)
    _clear_acl_cache()
    return user_to_dict(_request("GET", f"users/{quote(user_id, safe='')}")[0])


def delete_user(username: str) -> dict:
    rep = _get_user_rep(username)
    _request("DELETE", f"users/{quote(str(rep['id']), safe='')}", expected=(204,))
    _clear_acl_cache()
    return {"success": True}


def match_topic(template: str, topic: str) -> bool:
    if template == topic:
        return True
    regex = re.escape(template)
    for name in ("thing_type", "camera_id", "scene_id", "channel", "scene_name", "region_id", "sensor_id", "region_type", "event_type"):
        regex = regex.replace(re.escape("${" + name + "}"), r"([^/]+)")
    return re.fullmatch(regex, topic, flags=re.IGNORECASE) is not None


@lru_cache(maxsize=1024)
def _acl_identity_snapshot(username: str, time_bucket: int) -> tuple[frozenset[str], tuple[tuple[str, int], ...]]:
    rep = _get_user_rep(username)
    roles = frozenset(str(role.get("name")) for role in _realm_roles_for_user(str(rep["id"])))
    acls = tuple((str(item["topic"]), int(item["access"])) for item in _decode_acls(rep))
    return roles, acls


def _clear_acl_cache() -> None:
    _acl_identity_snapshot.cache_clear()


def _acl_decision(acl_pairs, topic: str, access: int) -> tuple[bool, int | None]:
    matched = None
    for acl_topic, acl_access in acl_pairs:
        template = TOPIC_TEMPLATES.get(str(acl_topic))
        if template and match_topic(template, topic):
            matched = {"topic": acl_topic, "access": int(acl_access)}
    if not matched:
        return False, None
    granted = int(matched["access"])
    requested = int(access)
    if granted == requested:
        return True, requested
    if granted == 3 and requested in {1, 2, 4}:
        return True, 4 if requested == 1 else requested
    if granted == 4 and requested == 1:
        return True, 4
    if granted == 1 and requested == 4:
        return True, 4
    return False, None


def service_acl_check(username: str, topic: str, access: int) -> tuple[bool, int | None] | None:
    identity = get_service_identity(username)
    if identity is None:
        return None
    return _acl_decision(
        [(item["topic"], item["access"]) for item in identity["acls"]],
        topic,
        access,
    )


def acl_check(username: str, topic: str, access: int) -> tuple[bool, int | None]:
    service_result = service_acl_check(username, topic, access)
    if service_result is not None:
        return service_result
    ttl = max(1, int(os.getenv("MQTT_ACL_CACHE_SECONDS", "5")))
    roles, acl_pairs = _acl_identity_snapshot(username, int(time.monotonic() // ttl))
    if "scenescape-admin" in roles:
        return True, 3
    return _acl_decision(acl_pairs, topic, access)
