from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from fastapi import HTTPException

from .hierarchy import create_child_link, resolve_child_link, update_child_link
from .media_files import delete_media, extract_raw_glb
from .map_processing import process_uploaded_mesh

CALIBRATION_FIELDS = {
    'camera_calibration', 'matcher', 'number_of_localizations', 'global_feature',
    'local_feature', 'minimum_number_of_matches', 'scale', 'apriltag_size',
    'inlier_threshold',
}


def split_scene_relation(data: dict) -> tuple[dict, object, object]:
    value = deepcopy(data)
    parent = value.pop('parent', None) if 'parent' in value else _MISSING
    transform = value.pop('transform', None) if 'transform' in value else _MISSING
    # Nested resources are representation-only in SceneSerializer. They are not
    # mutated when a Scene itself is saved.
    value.pop('children', None)
    value.pop('cameras', None)
    value.pop('sensors', None)
    value.pop('regions', None)
    value.pop('tripwires', None)
    return value, parent, transform


_MISSING = object()


def apply_scene_relation(db, scene_uid: str, parent, transform, actor, *, legacy: bool) -> str | None:
    existing = resolve_child_link(db, scene_uid, required=False)
    body: dict = {}
    if parent is not _MISSING and parent not in (None, ''):
        body.update(child_type='local', parent=str(parent), child=str(scene_uid))
    elif parent is not _MISSING and parent in (None, ''):
        # 2026.2 SceneSerializer allows null but does not unlink the relation in
        # create_update(); preserve that behavior.
        pass
    if transform is not _MISSING and transform is not None:
        body['transform'] = transform
    if not body:
        return existing.uid if existing else None
    if existing is None:
        if 'parent' not in body:
            raise HTTPException(400, {'parent': ['A parent is required before setting a child transform.']})
        row = create_child_link(db, body, actor, legacy=legacy)
        return row.uid
    row, _ = update_child_link(db, existing, body, actor, legacy=legacy)
    return row.uid


def reset_map_processed(existing: dict | None, update: dict) -> None:
    if not existing:
        return
    for field in CALIBRATION_FIELDS:
        if field in update and update.get(field) != existing.get(field):
            update['map_processed'] = None
            return


def apply_uploaded_map_semantics(existing: dict | None, update: dict, *, uploaded_map: bool = False, uploaded_polycam: bool = False) -> None:
    if uploaded_map or uploaded_polycam:
        update['map_processed'] = None
    map_value = update.get('map') if 'map' in update else (existing or {}).get('map')
    scene_name = str(update.get('name') or (existing or {}).get('name') or 'scene')

    if uploaded_map and map_value:
        suffix = Path(str(map_value)).suffix.lower()
        if suffix == '.zip':
            update['polycam_data'] = map_value
            update['camera_calibration'] = 'Markerless'
            glb = extract_raw_glb(map_value, scene_name)
            if glb:
                update['map'] = glb
                map_value = glb
                suffix = '.glb'
        if suffix in {'.glb', '.ply'}:
            processed = process_uploaded_mesh(str(map_value), scene_name, auto_align=True)
            update.update(processed)
            map_value = update.get('map')
        else:
            # The 2026.2 model clears 3D pose for non-mesh maps.
            update['mesh_rotation'] = [0.0, 0.0, 0.0]
            update['mesh_translation'] = [0.0, 0.0, 0.0]
            update['thumbnail'] = None

    if uploaded_polycam:
        source = update.get('polycam_data')
        if source:
            glb = extract_raw_glb(str(source), scene_name)
            if glb:
                update['map'] = glb
                update.update(process_uploaded_mesh(glb, scene_name, auto_align=True))
            else:
                # 2026.2 keeps the old map when a polycam_data ZIP has no raw.glb
                # and still refreshes the existing GLB's aligned thumbnail.
                old_map = (existing or {}).get('map')
                if isinstance(old_map, str) and old_map.lower().endswith('.glb'):
                    update.update(process_uploaded_mesh(old_map, scene_name, auto_align=True))


def cleanup_replaced_media(existing: dict | None, update: dict) -> None:
    if not existing:
        return
    for field in ('map', 'thumbnail', 'polycam_data'):
        if field in update and update.get(field) != existing.get(field):
            old = existing.get(field)
            if old and old not in update.values():
                delete_media(str(old))
