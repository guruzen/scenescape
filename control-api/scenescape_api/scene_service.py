from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy import select

from .contracts import normalize_resource
from .hierarchy import cascade_scene_links
from .markers import cascade_scene_markers
from .media_files import delete_media
from .map_processing import process_uploaded_mesh
from .database import Resource
from .resources import delete_resource, get_resource, upsert
from .scene_config import apply_scene_relation, cleanup_replaced_media, split_scene_relation


def create_scene(db, body: dict, actor, *, legacy: bool):
    normalized, resolved_uid = normalize_resource(db, 'scene', body, uid=None, creating=True, legacy=legacy)
    scene_data, parent, transform = split_scene_relation(normalized)
    row = upsert(db, 'scene', resolved_uid, scene_data, actor)
    apply_scene_relation(db, row.uid, parent, transform, actor, legacy=legacy)
    return row, True


def update_scene(db, uid: str, body: dict, actor, *, legacy: bool, expected_revision: int | None = None):
    current = get_resource(db, 'scene', uid)
    before = deepcopy(current.payload or {})
    normalized, resolved_uid = normalize_resource(db, 'scene', body, uid=uid, creating=False, legacy=legacy)
    scene_data, parent, transform = split_scene_relation(normalized)

    # Mirror Scene.save() derived media semantics from 2026.2. Removing a map
    # clears thumbnail/processing state; changing 3D rotation/translation
    # regenerates the top-view thumbnail and pixels-per-meter scale.
    effective = {**before, **scene_data}
    if 'map' in scene_data and not scene_data.get('map'):
        scene_data['thumbnail'] = None
        scene_data['map_processed'] = None
    mesh_pose_changed = any(
        field in scene_data and scene_data.get(field) != before.get(field)
        for field in ('mesh_rotation', 'mesh_translation')
    )
    map_value = effective.get('map')
    if mesh_pose_changed and isinstance(map_value, str) and map_value.lower().endswith('.glb'):
        processed = process_uploaded_mesh(
            map_value,
            str(effective.get('name') or 'scene'),
            current_rotation=effective.get('mesh_rotation') or [0.0, 0.0, 0.0],
            current_translation=effective.get('mesh_translation') or [0.0, 0.0, 0.0],
            current_scale=effective.get('mesh_scale') or [1.0, 1.0, 1.0],
            auto_align=False,
        )
        scene_data['thumbnail'] = processed.get('thumbnail')
        scene_data['scale'] = processed.get('scale')

    row = upsert(db, 'scene', resolved_uid or uid, scene_data, actor, expected_revision)
    apply_scene_relation(db, row.uid, parent, transform, actor, legacy=legacy)
    # 2026.2 directly stores trs_matrix without sending the standard Scene
    # update command when it is the only requested field.
    notify = set(body.keys()) != {'trs_matrix'}
    return row, notify, before


def _cascade_scene_resources(db, scene_uid: str) -> None:
    """Mirror Django FK semantics when a Scene is deleted.

    Sensor.scene uses SET_NULL for both cameras and singleton sensors.
    Regions and tripwires are scene-owned and use CASCADE.
    """
    rows = db.scalars(
        select(Resource).where(Resource.kind.in_(("camera", "sensor", "region", "tripwire")))
    ).all()
    now = datetime.now(timezone.utc)
    for resource in rows:
        payload = dict(resource.payload or {})
        linked_scene = str(payload.get("scene") or payload.get("scene_id") or "")
        if linked_scene != str(scene_uid):
            continue
        if resource.kind in {"camera", "sensor"}:
            payload["scene"] = None
            payload.pop("scene_id", None)
            resource.payload = payload
            resource.revision += 1
            resource.updated_at = now
        else:
            db.delete(resource)
    db.flush()


def delete_scene(db, uid: str):
    row = get_resource(db, 'scene', uid)
    media = [str((row.payload or {}).get(field) or '') for field in ('map', 'thumbnail', 'polycam_data')]
    cascade_scene_links(db, uid)
    cascade_scene_markers(db, uid)
    _cascade_scene_resources(db, uid)
    result = delete_resource(db, 'scene', uid)
    return result, [value for value in media if value]


def cleanup_scene_media(before: dict | None, after: dict) -> None:
    cleanup_replaced_media(before, after)


def delete_scene_media(values: list[str]) -> None:
    seen = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            delete_media(value)
