"""Isolated SQLite browser-test API with synthetic observations; never deploy."""
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

folder = Path(tempfile.mkdtemp(prefix="scenescape-browser-"))
os.environ.update(DATABASE_URL=f"sqlite:///{folder}/test.db", MEDIA_ROOT=str(folder / "media"),
                  API_SIGNING_KEY="browser-fixture-key-not-for-production-123456789", SERVICE_AUTH_FILES=str(folder / "service.json"))
(folder / "service.json").write_text(json.dumps({"user": "browser-fixture", "password": "fixture-only"}))
(folder / "media").mkdir()
from PIL import Image, ImageDraw
image = Image.new("RGB", (1000, 700), "#e7edf0")
draw = ImageDraw.Draw(image)
draw.rectangle((25, 25, 975, 675), outline="#7d949f", width=8)
for x in (150, 350, 550, 750):
    draw.rectangle((x, 120, x+100, 420), fill="#b8c8ce", outline="#8da3ae", width=3)
draw.text((60, 50), "SYNTHETIC TEST FLOOR - NOT LIVE CAMERA DATA", fill="#253c45")
image.save(folder / "media/floor.png")
from scenescape_api.database import Base, Heartbeat, get_engine, sessions
from scenescape_api.auth import Principal
from scenescape_api.resources import upsert
from scenescape_api.ingest import persist
Base.metadata.create_all(get_engine())
actor = Principal("fixture", "Fixture", frozenset({"scenescape-admin"}), frozenset({"*"}), 9999999999)
with sessions()() as db:
    scene = upsert(db, "scene", None, {"name": "Test distribution floor", "map": "/media/floor.png", "scale": 100}, actor)
    scene_id = scene.uid
    camera = upsert(db, "camera", None, {"name": "Test camera 01", "sensor_id": "test-camera-01", "scene": scene_id,
        "translation": [2, 2, 3], "rotation": [0, 0, 0], "resolution": [1920, 1080],
        "intrinsics": {"fx": 1000, "fy": 1000, "cx": 960, "cy": 540}}, actor)
    region = upsert(db, "region", None, {"name": "Packing safety area", "scene": scene_id, "points": [[1,1],[5,1],[5,4],[1,4]]}, actor)
    region_id = region.uid
    db.commit()

def tick():
    for n in range(1800):
        now = datetime.now(timezone.utc)
        data = {"id": scene_id, "timestamp": now.isoformat(), "rate": {"test-camera-01": 12},
            "objects": [{"id": "test-track-1", "category": "person", "translation": [2+n%30/20, 3, 0], "confidence": .9},
                        {"id": "test-track-2", "category": "vehicle", "translation": [6, 2+n%20/20, 0]}]}
        with sessions()() as db:
            db.merge(Heartbeat(key="mqtt", state="connected", details={"synthetic_fixture": True}, updated_at=now))
            persist(db, f"scenescape/regulated/scene/{scene_id}", json.dumps(data).encode())
            if n == 0:
                event = {"scene_id": scene_id, "region_id": region_id, "region_name": "Packing safety area",
                         "timestamp": now.isoformat(), "entered": [data["objects"][0]], "exited": [], "objects": data["objects"], "counts": {"person": 1}}
                persist(db, f"scenescape/event/region/{scene_id}/{region_id}/occupancy", json.dumps(event).encode())
            db.commit()
        time.sleep(1)
threading.Thread(target=tick, daemon=True).start()
from scenescape_api.app import app
import uvicorn
uvicorn.run(app, host="127.0.0.1", port=8765, access_log=False)
