import json
import os
import ssl
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


def notify_config_change(kind: str, uid: str | None = None) -> dict:
    """Best-effort 2026.2-compatible configuration invalidation.

    Manager writes historically published scenescape/cmd/database so long-lived
    services invalidated their REST cache. Scene writes additionally published
    scenescape/cmd/scene/update/<scene-id>. Notification failure must not roll
    back an already committed configuration write.
    """
    try:
        import paho.mqtt.client as mqtt

        host, port, auth = _broker_settings()
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"scenescape-api-config-{uuid.uuid4().hex[:10]}",
        )
        if auth.get("user"):
            client.username_pw_set(auth.get("user"), auth.get("password"))
        ca = os.getenv("MQTT_CA_FILE")
        if ca:
            client.tls_set(ca_certs=ca, cert_reqs=ssl.CERT_REQUIRED)

        client.connect(host, port, keepalive=20)
        client.loop_start()
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
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
