import base64
import json
import os
import queue
import ssl
import uuid
from pathlib import Path


class CameraSnapshotError(RuntimeError):
    pass


def _broker_settings():
    host = os.getenv("MQTT_HOST", "broker.scenescape.intel.com")
    port = int(os.getenv("MQTT_PORT", "1883"))
    auth_file = os.getenv("MQTT_AUTH_FILE")
    auth = {}
    if auth_file and Path(auth_file).is_file():
        auth = json.loads(Path(auth_file).read_text())
    return host, port, auth


def fetch_camera_snapshot(camera_id: str, timeout: float = 4.0) -> bytes:
    """Request one camera JPEG using the same MQTT command/image topics as legacy UI."""
    import paho.mqtt.client as mqtt

    host, port, auth = _broker_settings()
    result: queue.Queue[bytes | Exception] = queue.Queue(maxsize=1)
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"scenescape-api-snapshot-{uuid.uuid4().hex[:10]}",
    )
    if auth.get("user"):
        client.username_pw_set(auth.get("user"), auth.get("password"))
    ca = os.getenv("MQTT_CA_FILE")
    if ca:
        client.tls_set(ca_certs=ca, cert_reqs=ssl.CERT_REQUIRED)

    image_topic = f"scenescape/image/camera/{camera_id}"
    command_topic = f"scenescape/cmd/camera/{camera_id}"

    def on_connect(c, userdata, flags, reason_code, properties):
        if getattr(reason_code, "is_failure", False):
            try:
                result.put_nowait(CameraSnapshotError(f"MQTT connect failed: {reason_code}"))
            except queue.Full:
                pass
            return
        c.subscribe(image_topic, qos=1)

    def on_subscribe(c, userdata, mid, reason_code_list, properties):
        c.publish(command_topic, "getimage", qos=1)

    def on_message(c, userdata, message):
        if message.topic != image_topic:
            return
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            encoded = payload.get("image")
            if not encoded:
                raise CameraSnapshotError("Camera response did not contain an image")
            data = base64.b64decode(encoded, validate=True)
            if not data:
                raise CameraSnapshotError("Camera returned an empty image")
            result.put_nowait(data)
        except Exception as exc:
            try:
                result.put_nowait(exc)
            except queue.Full:
                pass

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    client.connect(host, port, keepalive=20)
    client.loop_start()
    try:
        try:
            value = result.get(timeout=timeout)
        except queue.Empty as exc:
            raise CameraSnapshotError(f"Timed out waiting for camera {camera_id}") from exc
        if isinstance(value, Exception):
            raise CameraSnapshotError(str(value)) from value
        return value
    finally:
        try:
            client.disconnect()
        finally:
            client.loop_stop()
