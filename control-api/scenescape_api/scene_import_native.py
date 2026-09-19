from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

from fastapi import HTTPException

from .auth import Principal
from .contracts import normalize_resource
from .hierarchy import create_child_link, resolve_child_link, update_child_link
from .media_files import delete_media, read_scene_import_zip, store_bytes
from .resources import upsert
from .scene_config import apply_uploaded_map_semantics, split_scene_relation

SUMMARY_KEYS = (
    'scene', 'cameras', 'tripwires', 'regions', 'sensors',
    'cameras_created', 'tripwires_created', 'regions_created', 'sensors_created',
)


def empty_summary() -> dict[str, Any]:
    return {key: None for key in SUMMARY_KEYS}


def _error_summary(section: str, value: Any) -> dict[str, Any]:
    result = empty_summary()
    result[section] = value
    return result


def _uid(item: dict, kind: str) -> str | None:
    if kind == 'camera':
        value = item.get('uid') or item.get('sensor_id')
    elif kind in {'region', 'tripwire'}:
        value = item.get('uuid') or item.get('uid')
    else:
        value = item.get('uid') or item.get('sensor_id') or item.get('id')
    return str(value) if value not in (None, '') else None


def _summary_error(exc: Exception) -> Any:
    if isinstance(exc, HTTPException):
        return exc.detail
    return {'error': [str(exc)]}


def _find_resource(resources: dict[str, bytes], scene_name: str) -> tuple[str, bytes] | None:
    return next(((name, data) for name, data in resources.items() if scene_name in name), None)


def _camera_import_payload(item: dict, scene_uid: str) -> dict:
    data = deepcopy(item)
    data.pop('scene', None)
    # ImportScene.build_camera_items maps exported uid back to sensor_id.
    if data.get('uid') and not data.get('sensor_id'):
        data['sensor_id'] = data.pop('uid')
    transform_type = data.get('transform_type')
    if transform_type and transform_type != '3d-2d point correspondence':
        data['transform_type'] = 'euler'
    data['scene'] = scene_uid
    return data


def _bulk_create(db, items: list[dict] | None, scene_uid: str, kind: str, actor: Principal) -> tuple[list[dict] | None, list | None]:
    created: list[dict] = []
    errors: list = []
    for raw in items or []:
        item = deepcopy(raw)
        item['scene'] = scene_uid
        try:
            if kind == 'camera':
                item = _camera_import_payload(item, scene_uid)
                normalized, resolved_uid = normalize_resource(db, 'camera', item, creating=True, legacy=True)
                row = upsert(db, 'camera', resolved_uid, normalized, actor)
            else:
                # Region/sensor/tripwire parity is completed in Part 4. For the
                # Scene import contract, retain the exported payload and bind it
                # to the newly-created Scene without destructively rewriting it.
                resolved_uid = _uid(item, kind)
                row = upsert(db, kind, resolved_uid, item, actor)
            db.commit()
            created.append(dict(row.payload or {}))
        except Exception as exc:
            db.rollback()
            errors.append((_summary_error(exc), raw))
    return created or None, errors or None


def import_scene_archive(db, upload_bytes: bytes, actor: Principal) -> dict[str, Any]:
    """Import a 2026.2 Scene ZIP without invoking Django.

    The operation is additive. A Scene failure aborts that Scene; individual
    camera/region/tripwire/sensor failures are reported in the same summary
    shape as the tagged importer and do not delete pre-existing configuration.
    """
    try:
        root_scene, resources = read_scene_import_zip(upload_bytes)
    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict) and 'scene' in detail:
            return _error_summary('scene', detail)
        return _error_summary('scene', {'scene': [str(detail)]})

    media_created: list[str] = []

    def import_one(scene_json: dict, parent_uid: str | None = None) -> dict[str, Any]:
        summary = empty_summary()
        if not isinstance(scene_json, dict) or not scene_json.get('name'):
            summary['scene'] = {'scene': ['Failed to parse JSON']}
            return summary
        match = _find_resource(resources, str(scene_json['name']))
        if match is None:
            summary['scene'] = {'scene': ['No matching resource file']}
            return summary

        resource_name, resource_bytes = match
        try:
            map_url = store_bytes(resource_name, resource_bytes, kind='scene-map')
            media_created.append(map_url)
            create_data = {
                'name': scene_json['name'],
                'scale': scene_json.get('scale'),
                'map': map_url,
            }
            create_data = {k: v for k, v in create_data.items() if v is not None}
            normalized, _ = normalize_resource(db, 'scene', create_data, uid=None, creating=True, legacy=True)
            apply_uploaded_map_semantics(None, normalized, uploaded_map=True)
            scene_uid = str(uuid.uuid4())
            scene_row = upsert(db, 'scene', scene_uid, normalized, actor)

            update_fields = [
                'external_update_rate', 'camera_calibration', 'apriltag_size',
                'number_of_localizations', 'global_feature',
                'minimum_number_of_matches', 'inlier_threshold', 'output_lla',
                'map_corners_lla', 'mesh_translation', 'mesh_rotation', 'mesh_scale',
            ]
            update_data = {key: deepcopy(scene_json.get(key)) for key in update_fields if scene_json.get(key) is not None}
            if update_data:
                normalized_update, _ = normalize_resource(db, 'scene', update_data, uid=scene_uid, creating=False, legacy=True)
                scene_row = upsert(db, 'scene', scene_uid, normalized_update, actor, scene_row.revision)

            if parent_uid:
                link_body = {'child_type': 'local', 'parent': parent_uid, 'child': scene_uid}
                link = create_child_link(db, link_body, actor, legacy=True)
                exported_link = deepcopy(scene_json.get('link') or {})
                if exported_link:
                    exported_link.pop('uid', None)
                    exported_link.pop('transform', None)
                    exported_link['parent'] = parent_uid
                    exported_link['child'] = scene_uid
                    link, _ = update_child_link(db, link, exported_link, actor, legacy=True)

            # Tagged ImportScene performs independent REST mutations. Commit the
            # Scene/link before bulk child resources so an orphaned camera or
            # sensor is reported without rolling the successfully-created Scene back.
            db.commit()
            cameras, camera_errors = _bulk_create(db, scene_json.get('cameras'), scene_uid, 'camera', actor)
            regions, region_errors = _bulk_create(db, scene_json.get('regions'), scene_uid, 'region', actor)
            tripwires, tripwire_errors = _bulk_create(db, scene_json.get('tripwires'), scene_uid, 'tripwire', actor)
            sensors, sensor_errors = _bulk_create(db, scene_json.get('sensors'), scene_uid, 'sensor', actor)
            summary.update(
                cameras=camera_errors, cameras_created=cameras,
                regions=region_errors, regions_created=regions,
                tripwires=tripwire_errors, tripwires_created=tripwires,
                sensors=sensor_errors, sensors_created=sensors,
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            summary['scene'] = _summary_error(exc)
            return summary

        for child in scene_json.get('children') or []:
            if not isinstance(child, dict) or not child.get('uid'):
                # Tagged importer only recurses embedded local Scene objects;
                # remote child stubs have only a name and are not importable.
                continue
            child_summary = import_one(child, scene_uid)
            if any(child_summary.get(key) for key in ('scene', 'cameras', 'tripwires', 'regions', 'sensors')):
                return child_summary
        return summary

    result = import_one(root_scene)
    if result.get('scene'):
        for value in media_created:
            delete_media(value)
    return result
