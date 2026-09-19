import json
import os
import ssl
import urllib.request
import uuid
from pathlib import Path


def _broker_settings():
    host = os.getenv("MQTT_HOST", "broker.scenescape.intel.com")
    port = int(os.getenv("MQTT_PORT", "1883"))
    auth = {}
    auth_file = os.getenv("MQTT_AUTH_FILE")
    if auth_file and Path(auth_file).is_file():
        auth = json.loads(Path(auth_file).read_text())
    return host, port, auth


def _client(prefix: str):
    import paho.mqtt.client as mqtt

    host, port, auth = _broker_settings()
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"scenescape-api-{prefix}-{uuid.uuid4().hex[:10]}",
    )
    if auth.get("user"):
        client.username_pw_set(auth.get("user"), auth.get("password"))
    ca = os.getenv("MQTT_CA_FILE")
    if ca:
        client.tls_set(ca_certs=ca, cert_reqs=ssl.CERT_REQUIRED)
    client.connect(host, port, keepalive=20)
    client.loop_start()
    return client


def _autocalibration_scene_update(scene_id: str) -> None:
    base = os.getenv("AUTOCALIBRATION_URL", "").rstrip("/")
    if not base:
        return
    url = f"{base}/v1/scenes/{scene_id}/registration"
    request = urllib.request.Request(
        url,
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    ca = os.getenv("UPSTREAM_CA_FILE")
    context = ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, context=context, timeout=10):
            pass
    except Exception:
        # 2026.2 treats calibration refresh as best effort. A committed scene
        # mutation remains valid even when the optional service is unavailable.
        pass


def notify_config_change(kind: str, uid: str | None = None) -> dict:
    """Best-effort 2026.2-compatible configuration invalidation.

    Manager writes historically published scenescape/cmd/database so long-lived
    services invalidated their REST cache. Scene writes additionally published
    scenescape/cmd/scene/update/<scene-id> and refreshed Auto Calibration scene
    registration. Notification failure must not roll back an already committed
    configuration write.
    """
    try:
        client = _client("config")
        try:
            if kind == "scene" and uid:
                client.publish(
                    f"scenescape/cmd/scene/update/{uid}", "update", qos=1
                ).wait_for_publish(timeout=3)
            client.publish(
                "scenescape/cmd/database", "update", qos=1
            ).wait_for_publish(timeout=3)
        finally:
            try:
                client.disconnect()
            finally:
                client.loop_stop()
        if kind == "scene" and uid:
            _autocalibration_scene_update(uid)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _camera_message(camera: dict, action: str, previous: dict | None = None) -> dict:
    if action not in {"save", "delete"}:
        raise ValueError("camera action must be save or delete")
    current = {
        key: value for key, value in dict(camera).items()
        if key not in {"kind", "revision"}
    }
    uid = str(current.get("uid") or current.get("sensor_id") or "")
    current["uid"] = uid
    current["sensor_id"] = uid
    current["previous_sensor_id"] = str((previous or {}).get("uid") or (previous or {}).get("sensor_id") or "")
    current["previous_name"] = str((previous or {}).get("name") or "")
    current["action"] = action
    return current


def notify_camera_change(camera: dict, action: str, previous: dict | None = None) -> dict:
    """Publish the 2026.2 kubeclient camera mutation message, best effort."""
    try:
        payload = _camera_message(camera, action, previous)
        client = _client("camera")
        try:
            client.publish(
                "scenescape/cmd/kubeclient",
                json.dumps(payload, separators=(",", ":")),
                qos=2,
            ).wait_for_publish(timeout=3)
        finally:
            try:
                client.disconnect()
            finally:
                client.loop_stop()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
