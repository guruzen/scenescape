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
  sensor = upsert(db, "sensor", None, {"name": "Test temperature", "sensor_id": "test-temperature-01", "scene": scene_id,
      "singleton_type": "environmental", "area": "circle", "center": [4, 4], "radius": 0.8, "visible": True}, actor)
  region = upsert(db, "region", None, {"name": "Packing safety area", "scene": scene_id, "visible": True, "points": [[1,1],[5,1],[5,4],[1,4]]}, actor)
  region_id = region.uid
  upsert(db, "tripwire", None, {"name": "Packing exit line", "scene": scene_id, "visible": True, "points": [[5.5,1],[5.5,4]], "direction": "positive"}, actor)
  db.commit()

def tick():
  for n in range(1800):
    now = datetime.now(timezone.utc)
    data = {"id": scene_id, "timestamp": now.isoformat(), "rate": {"test-camera-01": 12},
        "objects": [{"id": "test-track-1", "category": "person", "translation": [2+n%30/20, 3, 0], "velocity": [0.75, 0.15, 0], "confidence": .9,
                     "visibility": [camera.uid], "persistent_data": {"badge": {"id": "fixture-A7"}}},
                    {"id": "test-track-2", "category": "vehicle", "translation": [6, 2+n%20/20, 0], "velocity": [0, 0.5, 0]}]}
    with sessions()() as db:
      db.merge(Heartbeat(key="mqtt", state="connected", details={"synthetic_fixture": True}, updated_at=now))
      persist(db, f"scenescape/regulated/scene/{scene_id}", json.dumps(data).encode())
      persist(db, f"scenescape/data/camera/{camera.uid}", json.dumps({
          "scene_id": scene_id, "timestamp": now.isoformat(), "objects": {"person": [data["objects"][0]], "vehicle": [data["objects"][1]]}
      }).encode())
      persist(db, f"scenescape/data/sensor/{sensor.uid}", json.dumps({
          "timestamp": now.isoformat(), "type": "temperature", "subtype": "ambient", "value": round(21.5 + (n % 6) * 0.1, 1)
      }).encode())
      if n == 0:
        event = {"scene_id": scene_id, "region_id": region_id, "region_name": "Packing safety area",
                 "timestamp": now.isoformat(), "entered": [data["objects"][0]], "exited": [], "objects": data["objects"], "counts": {"person": 1}}
        persist(db, f"scenescape/event/region/{scene_id}/{region_id}/occupancy", json.dumps(event).encode())
      db.commit()
    time.sleep(1)
threading.Thread(target=tick, daemon=True).start()
import io
import scenescape_api.app as app_module

def synthetic_snapshot(_camera_id):
  frame = Image.new("RGB", (640, 360), "#13262c")
  frame_draw = ImageDraw.Draw(frame)
  frame_draw.ellipse((270, 130, 370, 230), fill="#4ed1ce")
  frame_draw.text((18, 18), "SYNTHETIC CAMERA FRAME", fill="#ffffff")
  output = io.BytesIO()
  frame.save(output, format="JPEG")
  return output.getvalue()

app_module.fetch_camera_snapshot = synthetic_snapshot
app = app_module.app
import uvicorn
uvicorn.run(app, host="127.0.0.1", port=8765, access_log=False)
