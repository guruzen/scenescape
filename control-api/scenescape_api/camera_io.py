import base64
import json
import os
import queue
import ssl
import struct
import threading
import uuid
from datetime import datetime, timezone
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
    return client, host, port


def _decode_image_payload(raw: bytes) -> dict:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise CameraSnapshotError("Camera returned invalid image metadata") from exc
    encoded = payload.get("image")
    if not encoded:
        raise CameraSnapshotError("Camera response did not contain an image")
    try:
        image = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise CameraSnapshotError("Camera returned invalid base64 image data") from exc
    if not image:
        raise CameraSnapshotError("Camera returned an empty image")
    payload["_image_bytes"] = image
    return payload


def _request_topic_payload(
    camera_id: str,
    *,
    image_topic: str,
    command: str,
    timeout: float,
    qos: int = 1,
) -> dict:
    result: queue.Queue[dict | Exception] = queue.Queue(maxsize=1)
    client, host, port = _client("camera-image")

    def on_connect(c, userdata, flags, reason_code, properties):
        if getattr(reason_code, "is_failure", False):
            try:
                result.put_nowait(CameraSnapshotError(f"MQTT connect failed: {reason_code}"))
            except queue.Full:
                pass
            return
        c.subscribe(image_topic, qos=qos)

    def on_subscribe(c, userdata, mid, reason_code_list, properties):
        c.publish(f"scenescape/cmd/camera/{camera_id}", command, qos=qos)

    def on_message(c, userdata, message):
        if message.topic != image_topic:
            return
        try:
            result.put_nowait(_decode_image_payload(message.payload))
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


def fetch_camera_snapshot(camera_id: str, timeout: float = 4.0) -> bytes:
    """Request one live camera JPEG using the tagged getimage flow."""
    payload = _request_topic_payload(
        camera_id,
        image_topic=f"scenescape/image/camera/{camera_id}",
        command="getimage",
        timeout=timeout,
        qos=1,
    )
    return payload["_image_bytes"]


def fetch_camera_calibration(camera_id: str, timeout: float = 5.0) -> dict:
    """Request the calibration frame plus runtime intrinsics/distortion metadata."""
    payload = _request_topic_payload(
        camera_id,
        image_topic=f"scenescape/image/calibration/camera/{camera_id}",
        command="getcalibrationimage",
        timeout=timeout,
        qos=2,
    )
    payload.pop("_image_bytes", None)
    return payload


def request_camera_frame(
    camera_id: str,
    *,
    timestamp: str | None = None,
    frame_type: str | list[str] | None = None,
    timeout: float = 3.0,
) -> dict:
    """Mirror /api/v1/frame channel-based frame acquisition from 2026.2."""
    channel = str(uuid.uuid4())
    query = {
        "channel": channel,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
    }
    if frame_type:
        query["frame_type"] = frame_type.split() if isinstance(frame_type, str) else list(frame_type)

    result: queue.Queue[dict | Exception] = queue.Queue(maxsize=1)
    client, host, port = _client("frame")
    channel_topic = f"scenescape/channel/{channel}"

    def on_connect(c, userdata, flags, reason_code, properties):
        if getattr(reason_code, "is_failure", False):
            try:
                result.put_nowait(CameraSnapshotError(f"MQTT connect failed: {reason_code}"))
            except queue.Full:
                pass
            return
        c.subscribe(channel_topic, qos=2)

    def on_subscribe(c, userdata, mid, reason_code_list, properties):
        command = "getimage: " + json.dumps(query, separators=(",", ":"))
        c.publish(f"scenescape/cmd/camera/{camera_id}", command, qos=2)

    def on_message(c, userdata, message):
        if message.topic != channel_topic:
            return
        try:
            result.put_nowait(json.loads(message.payload.decode("utf-8")))
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
            raise CameraSnapshotError(f"No frame was returned for camera {camera_id}") from exc
        if isinstance(value, Exception):
            raise CameraSnapshotError(str(value)) from value
        return value
    finally:
        try:
            client.disconnect()
        finally:
            client.loop_stop()


def request_camera_video(camera_id: str, *, timeout: float = 10.0) -> bytes:
    """Mirror /api/v1/video chunked MQTT download from 2026.2."""
    channel = str(uuid.uuid4())
    result: queue.Queue[bytes | Exception] = queue.Queue(maxsize=1)
    client, host, port = _client("video")
    channel_topic = f"scenescape/channel/{channel}"
    chunks: dict[int, bytes] = {}
    expected_count = None
    expected_size = None
    lock = threading.Lock()
    header_format = "> LLHH"
    header_size = struct.calcsize(header_format)

    def on_connect(c, userdata, flags, reason_code, properties):
        if getattr(reason_code, "is_failure", False):
            try:
                result.put_nowait(CameraSnapshotError(f"MQTT connect failed: {reason_code}"))
            except queue.Full:
                pass
            return
        c.subscribe(channel_topic, qos=2)

    def on_subscribe(c, userdata, mid, reason_code_list, properties):
        query = {"channel": channel}
        c.publish(
            f"scenescape/cmd/camera/{camera_id}",
            "getvideo: " + json.dumps(query, separators=(",", ":")),
            qos=2,
        )

    def on_message(c, userdata, message):
        nonlocal expected_count, expected_size
        if message.topic != channel_topic:
            return
        try:
            if len(message.payload) < header_size:
                raise CameraSnapshotError("Video chunk header is invalid")
            total_size, chunk_size, chunk_count, index = struct.unpack(
                header_format, message.payload[:header_size]
            )
            data = bytes(message.payload[header_size:])
            with lock:
                expected_count = int(chunk_count)
                expected_size = int(total_size)
                chunks[int(index)] = data
                if len(chunks) == expected_count:
                    joined = b"".join(chunks[i] for i in range(expected_count))
                    result.put_nowait(joined[:expected_size])
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
            raise CameraSnapshotError(f"No video was returned for camera {camera_id}") from exc
        if isinstance(value, Exception):
            raise CameraSnapshotError(str(value)) from value
        return value
    finally:
        try:
            client.disconnect()
        finally:
            client.loop_stop()


def update_camera_runtime(camera_id: str, update: dict) -> dict:
    """Push calibration/intrinsics changes to the running VA camera pipeline."""
    client, host, port = _client("runtime-camera")
    try:
        client.connect(host, port, keepalive=20)
        client.loop_start()
        payload = json.dumps({"updatecamera": update}, separators=(",", ":"))
        info = client.publish(f"scenescape/cmd/camera/{camera_id}", payload, qos=1)
        info.wait_for_publish(timeout=3)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
        try:
            client.loop_stop()
        except Exception:
            pass
