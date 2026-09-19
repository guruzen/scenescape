import json
from datetime import datetime, timezone

from .database import Event, Incident, Observation


def _ts(payload):
    raw = payload.get("timestamp")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def scene_id_from_topic(topic: str) -> str:
    """Return authoritative scene id encoded by SceneScape MQTT topic templates.

    The regulated analytics payload inherits id from its upstream detector
    message, so payload id can be a camera/source id. The topic is the source
    of truth for scene identity.
    """
    parts = [part for part in str(topic).split("/") if part]
    if len(parts) >= 4 and parts[:3] == ["scenescape", "regulated", "scene"]:
        return parts[3]
    if len(parts) >= 4 and parts[:3] == ["scenescape", "data", "scene"]:
        return parts[3]
    if len(parts) >= 4 and parts[:2] == ["scenescape", "event"]:
        return parts[3]
    return ""


def persist(db, topic: str, raw: bytes):
    payload = json.loads(raw.decode() if isinstance(raw, (bytes, bytearray)) else raw)
    scene_id = scene_id_from_topic(topic) or str(payload.get("scene_id") or payload.get("id") or "")
    stamp = _ts(payload)
    if "/event/" in topic:
        event = Event(scene_id=scene_id, topic=topic, observed_at=stamp, payload=payload)
        db.add(event)
        db.flush()
        title = f"{payload.get('region_name') or 'Scene event'} · {topic.rsplit('/', 1)[-1]}"
        db.add(Incident(event_id=event.id, scene_id=scene_id, title=title, status="new", notes=[], audit=[{"action": "created", "at": stamp.isoformat()}]))
        return event
    obs = Observation(scene_id=scene_id, topic=topic, observed_at=stamp, payload=payload)
    db.add(obs)
    return obs
