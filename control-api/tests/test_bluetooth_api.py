import json
import time

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


def _browser_token(*, subject="admin", roles=None, scenes=None):
  roles = roles if roles is not None else ["scenescape-admin"]
  scenes = scenes if scenes is not None else ["*"]
  return jwt.encode(
      {
          "sub": subject,
          "name": subject,
          "roles": roles,
          "scenes": scenes,
          "iat": int(time.time()),
          "exp": int(time.time()) + 600,
          "aud": "scenescape-api",
      },
      "test-signing-key-abcdefghijklmnopqrstuvwxyz",
      algorithm="HS256",
  )


def _headers(**kwargs):
  return {"Authorization": "Bearer " + _browser_token(**kwargs)}


@pytest.fixture
def api(tmp_path, monkeypatch):
  monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/bluetooth-api.db")
  monkeypatch.setenv("API_SIGNING_KEY", "test-signing-key-abcdefghijklmnopqrstuvwxyz")
  auth_file = tmp_path / "service.json"
  auth_file.write_text(json.dumps({"user": "svc", "password": "pw"}))
  monkeypatch.setenv("SERVICE_AUTH_FILES", str(auth_file))

  import scenescape_api.database as database

  if database._engine is not None:
    database._engine.dispose()
  database._engine = None
  database._Session = None

  import scenescape_api.app as app_module

  monkeypatch.setattr(app_module, "notify_config_change", lambda kind, uid=None: {"ok": True})
  monkeypatch.setattr(app_module, "notify_camera_change", lambda camera, action, previous=None: {"ok": True})
  database.Base.metadata.create_all(database.get_engine())
  client = TestClient(app_module.app)
  yield client, database

  database.get_engine().dispose()
  database._engine = None
  database._Session = None


def _scene(client, uid, name=None):
  response = client.post(
      "/api/v2/scenes",
      headers=_headers(),
      json={"uid": uid, "name": name or uid},
  )
  assert response.status_code == 200, response.text


def test_bt02_anchor_crud_filters_lifecycle_and_pagination(api):
  client, database = api
  _scene(client, "scene-a")
  _scene(client, "scene-b")

  first = client.post(
      "/api/v2/bluetooth/anchors",
      headers=_headers(),
      json={
          "uid": "anchor-a",
          "serial_number": "ANCHOR-A",
          "scene_id": "scene-a",
          "capabilities": ["channel_sounding"],
      },
  )
  assert first.status_code == 200, first.text
  assert first.json()["revision"] == 1
  second = client.post(
      "/api/v2/bluetooth/anchors",
      headers=_headers(),
      json={"uid": "anchor-b", "serial_number": "ANCHOR-B", "scene_id": "scene-b"},
  )
  assert second.status_code == 200, second.text

  page = client.get(
      "/api/v2/bluetooth/anchors?limit=1&offset=0&serial=ANCHOR",
      headers=_headers(),
  )
  assert page.status_code == 200
  assert page.json()["total"] == 2
  assert len(page.json()["items"]) == 1

  changed = client.patch(
      "/api/v2/bluetooth/anchors/anchor-a?revision=1",
      headers=_headers(),
      json={"model": "Locator X"},
  )
  assert changed.status_code == 200
  assert changed.json()["revision"] == 2

  stale = client.patch(
      "/api/v2/bluetooth/anchors/anchor-a?revision=1",
      headers=_headers(),
      json={"model": "stale"},
  )
  assert stale.status_code == 409
  assert stale.json()["detail"]["code"] == "revision_conflict"

  direct_state = client.patch(
      "/api/v2/bluetooth/anchors/anchor-a?revision=2",
      headers=_headers(),
      json={"state": "active"},
  )
  assert direct_state.status_code == 422
  assert direct_state.json()["detail"]["code"] == "state_transition_required"

  active = client.post(
      "/api/v2/bluetooth/anchors/anchor-a/activate?revision=2",
      headers=_headers(),
  )
  assert active.status_code == 200
  assert active.json()["state"] == "active"
  assert active.json()["revision"] == 3

  disabled = client.post(
      "/api/v2/bluetooth/anchors/anchor-a/deactivate?revision=3",
      headers=_headers(),
  )
  assert disabled.status_code == 200
  assert disabled.json()["state"] == "disabled"

  retired = client.post(
      "/api/v2/bluetooth/anchors/anchor-a/retire?revision=4",
      headers=_headers(),
  )
  assert retired.status_code == 200
  assert retired.json()["state"] == "retired"

  invalid = client.post(
      "/api/v2/bluetooth/anchors/anchor-a/activate?revision=5",
      headers=_headers(),
  )
  assert invalid.status_code == 409
  assert invalid.json()["detail"]["code"] == "invalid_state_transition"

  oversized = client.get("/api/v2/bluetooth/anchors?limit=201", headers=_headers())
  assert oversized.status_code == 422

  with database.sessions()() as db:
    from scenescape_api.database import BluetoothAudit
    actions = [
        row.action
        for row in db.scalars(
            select(BluetoothAudit)
            .where(BluetoothAudit.resource_uid == "anchor-a")
            .order_by(BluetoothAudit.id)
        ).all()
    ]
  assert actions == ["create", "update", "state:active", "state:disabled", "state:retired"]


def test_bt02_scene_scope_filters_anchor_inventory_and_diagnostics(api):
  client, _ = api
  _scene(client, "scene-a")
  _scene(client, "scene-b")
  assert client.post(
      "/api/v2/bluetooth/anchors",
      headers=_headers(),
      json={"uid": "scope-a", "serial_number": "SCOPE-A", "scene_id": "scene-a"},
  ).status_code == 200
  assert client.post(
      "/api/v2/bluetooth/anchors",
      headers=_headers(),
      json={"uid": "scope-b", "serial_number": "SCOPE-B", "scene_id": "scene-b"},
  ).status_code == 200

  viewer = _headers(subject="viewer-a", roles=["scenescape-viewer"], scenes=["scene-a"])
  listed = client.get("/api/v2/bluetooth/anchors", headers=viewer)
  assert listed.status_code == 200
  assert [row["uid"] for row in listed.json()["items"]] == ["scope-a"]

  assert client.get("/api/v2/bluetooth/anchors/scope-a", headers=viewer).status_code == 200
  denied = client.get("/api/v2/bluetooth/anchors/scope-b", headers=viewer)
  assert denied.status_code == 403
  assert denied.json()["detail"]["code"] == "scene_scope_denied"
  assert client.get("/api/v2/bluetooth/anchors?scene_id=scene-b", headers=viewer).status_code == 403

  diagnostics = client.get("/api/v2/bluetooth/diagnostics", headers=viewer)
  assert diagnostics.status_code == 200
  assert diagnostics.json()["anchors"]["total"] == 1
  assert diagnostics.json()["tags"] == {"visible": False}


def test_bt02_tag_assignment_history_lifecycle_and_delete_guard(api):
  client, _ = api
  tag = client.post(
      "/api/v2/bluetooth/tags",
      headers=_headers(),
      json={
          "uid": "tag-a",
          "serial_number": "TAG-A",
          "capabilities": ["channel_sounding", "battery_service"],
      },
  )
  assert tag.status_code == 200, tag.text
  assert tag.json()["battery"]["percent"] is None
  assert tag.json()["battery"]["status"] == "unknown"

  active = client.post("/api/v2/bluetooth/tags/tag-a/activate?revision=1", headers=_headers())
  assert active.status_code == 200 and active.json()["state"] == "active"

  assignment = client.post(
      "/api/v2/bluetooth/assignments",
      headers=_headers(),
      json={
          "uid": "assignment-a",
          "tag_uid": "tag-a",
          "entity_type": "asset",
          "entity_id": "forklift-27",
          "display_name": "Forklift 27",
          "reason": "commissioning",
      },
  )
  assert assignment.status_code == 200, assignment.text

  overlap = client.post(
      "/api/v2/bluetooth/assignments",
      headers=_headers(),
      json={
          "tag_uid": "tag-a",
          "entity_type": "asset",
          "entity_id": "forklift-28",
      },
  )
  assert overlap.status_code == 409
  assert overlap.json()["detail"]["code"] == "assignment_overlap"

  history = client.get("/api/v2/bluetooth/tags/tag-a/assignments", headers=_headers())
  assert history.status_code == 200
  assert history.json()["total"] == 1
  assert history.json()["items"][0]["entity_id"] == "forklift-27"

  closed = client.post(
      "/api/v2/bluetooth/assignments/assignment-a/close?revision=1",
      headers=_headers(),
      json={},
  )
  assert closed.status_code == 200
  assert closed.json()["closed_by"] == "admin"

  delete_conflict = client.delete(
      "/api/v2/bluetooth/tags/tag-a?revision=2",
      headers=_headers(),
  )
  assert delete_conflict.status_code == 409
  assert delete_conflict.json()["detail"]["code"] == "tag_has_assignment_history"

  retired = client.post("/api/v2/bluetooth/tags/tag-a/retire?revision=2", headers=_headers())
  assert retired.status_code == 200
  assert retired.json()["state"] == "retired"


def test_bt02_role_and_service_token_boundaries(api):
  client, _ = api
  _scene(client, "scene-a")
  viewer = _headers(subject="viewer", roles=["scenescape-viewer"], scenes=["scene-a"])

  forbidden_create = client.post(
      "/api/v2/bluetooth/anchors",
      headers=viewer,
      json={"serial_number": "NOPE", "scene_id": "scene-a"},
  )
  assert forbidden_create.status_code == 403
  assert forbidden_create.json()["detail"]["code"] == "admin_required"

  assert client.get("/api/v2/bluetooth/tags", headers=viewer).status_code == 403
  assert client.get("/api/v2/bluetooth/assignments", headers=viewer).status_code == 403
  assert client.get("/api/v2/bluetooth/anchors").status_code == 401

  service = client.post("/api/v1/auth", data={"username": "svc", "password": "pw"})
  assert service.status_code == 200
  service_bearer = {"Authorization": "Bearer " + service.json()["token"]}
  denied = client.get("/api/v2/bluetooth/diagnostics", headers=service_bearer)
  assert denied.status_code == 403
  assert "Service tokens cannot access" in denied.json()["detail"]


def test_bt02_validation_conflicts_delete_and_existing_api_regression(api):
  client, _ = api
  _scene(client, "scene-a", "Scene A")

  created = client.post(
      "/api/v2/bluetooth/anchors",
      headers=_headers(),
      json={"uid": "delete-me", "serial_number": "DELETE-ME", "scene_id": "scene-a"},
  )
  assert created.status_code == 200

  duplicate = client.post(
      "/api/v2/bluetooth/anchors",
      headers=_headers(),
      json={"serial_number": "DELETE-ME", "scene_id": "scene-a"},
  )
  assert duplicate.status_code == 409
  assert duplicate.json()["detail"]["code"] == "duplicate_serial"

  too_long = client.post(
      "/api/v2/bluetooth/tags",
      headers=_headers(),
      json={"serial_number": "X" * 129},
  )
  assert too_long.status_code == 422

  removed = client.delete("/api/v2/bluetooth/anchors/delete-me?revision=1", headers=_headers())
  assert removed.status_code == 200
  assert removed.json()["deleted"] is True
  assert client.get("/api/v2/bluetooth/anchors/delete-me", headers=_headers()).status_code == 404

  existing = client.get("/api/v2/scenes/scene-a", headers=_headers())
  assert existing.status_code == 200
  assert existing.json()["name"] == "Scene A"


def test_bt02_openapi_documents_routes_and_examples(api):
  client, _ = api
  spec = client.get("/openapi.json").json()
  paths = spec["paths"]
  assert "/api/v2/bluetooth/anchors" in paths
  assert "/api/v2/bluetooth/tags" in paths
  assert "/api/v2/bluetooth/assignments" in paths
  assert "/api/v2/bluetooth/diagnostics" in paths

  anchor_post = paths["/api/v2/bluetooth/anchors"]["post"]
  examples = anchor_post["requestBody"]["content"]["application/json"]["examples"]
  assert "channel-sounding-anchor" in examples
