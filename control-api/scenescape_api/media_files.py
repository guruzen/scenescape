from __future__ import annotations

import io
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException, UploadFile

SCENE_MAP_EXTENSIONS = {'.glb', '.png', '.jpg', '.jpeg', '.zip', '.ply', '.mp4', '.mov', '.mkv', '.webm', '.avi'}
ASSET_EXTENSIONS = {'.glb'}
POLYCAM_EXTENSIONS = {'.zip'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg'}
MEDIA_PREFIX = '/media/'
DEFAULT_MAX_UPLOAD_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_ZIP_MEMBERS = 4096
DEFAULT_MAX_ZIP_UNCOMPRESSED = 2 * 1024 * 1024 * 1024


def media_root() -> Path:
    root = Path(os.getenv('MEDIA_ROOT', './media')).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _max_upload_bytes() -> int:
    return int(os.getenv('MAX_UPLOAD_BYTES', str(DEFAULT_MAX_UPLOAD_BYTES)))


def _safe_filename(name: str) -> str:
    base = Path(str(name or '')).name
    base = re.sub(r'[^A-Za-z0-9._-]+', '_', base).strip('._')
    if not base:
        raise HTTPException(400, {'file': ['A valid filename is required.']})
    return base[:220]


def media_url(path: Path) -> str:
    root = media_root()
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise HTTPException(400, {'file': ['Invalid media path.']})
    return MEDIA_PREFIX + resolved.relative_to(root).as_posix()


def media_path(value: str | None) -> Path | None:
    if not value:
        return None
    text = str(value)
    if text.startswith(MEDIA_PREFIX):
        text = text[len(MEDIA_PREFIX):]
    rel = Path(text)
    root = media_root()
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(400, {'file': ['Invalid media path.']})
    return target


def delete_media(value: str | None) -> None:
    try:
        target = media_path(value)
        if target and target.is_file():
            target.unlink()
    except OSError:
        pass


def _validate_image(path: Path) -> None:
    try:
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
            header = (image.format or '').lower()
    except Exception as exc:
        raise HTTPException(400, {'file': [f'Failed to read image file: {exc}']}) from exc
    ext = path.suffix.lower().lstrip('.')
    normalized_ext = 'jpeg' if ext == 'jpg' else ext
    if header != normalized_ext:
        raise HTTPException(400, {'file': [f'Mismatch between file extension {normalized_ext} and file header {header}']})


def _validate_glb(path: Path) -> None:
    # First verify the binary container, then parse geometry. 2026.2 used
    # Open3D's triangle-model reader; trimesh gives us an equivalent structural
    # guard here without requiring an EGL/rendering context just to validate.
    try:
        size = path.stat().st_size
        with path.open('rb') as handle:
            header = handle.read(12)
        if len(header) != 12 or header[:4] != b'glTF':
            raise ValueError('missing glTF binary header')
        version = int.from_bytes(header[4:8], 'little')
        declared = int.from_bytes(header[8:12], 'little')
        if version != 2 or declared != size:
            raise ValueError('invalid glTF version or length')
        try:
            import trimesh
            loaded = trimesh.load(str(path), force='scene')
            geometry = loaded.to_geometry() if hasattr(loaded, 'to_geometry') else loaded
            if not hasattr(geometry, 'vertices') or len(geometry.vertices) == 0:
                raise ValueError('GLB contains no geometry')
            if not hasattr(geometry, 'faces') or len(geometry.faces) == 0:
                raise ValueError('GLB contains no triangle geometry')
        except ImportError:
            # Runtime images pin trimesh. Keeping the header validation fallback
            # makes recovery tooling usable in minimal developer environments.
            pass
    except Exception as exc:
        raise HTTPException(400, {'file': [f'Only valid glTF binary (.glb) files are supported: {exc}']}) from exc


def _validate_ply(path: Path) -> None:
    try:
        try:
            from plyfile import PlyData
        except ImportError:
            PlyData = None
        if PlyData is not None:
            PlyData.read(str(path))
            return
        # Minimal developer fallback. Runtime images pin plyfile as in 2026.2.
        with path.open('rb') as handle:
            first = handle.readline(64)
            if first.strip() != b'ply':
                raise ValueError('missing PLY header')
            total = len(first)
            found_end = False
            while total <= 1024 * 1024:
                line = handle.readline(64 * 1024)
                if not line:
                    break
                total += len(line)
                if line.strip() == b'end_header':
                    found_end = True
                    break
            if not found_end:
                raise ValueError('missing end_header within 1 MiB')
    except Exception as exc:
        raise HTTPException(400, {'file': [f'Invalid PLY file: {exc}']}) from exc


def _zip_members(path: Path) -> list[zipfile.ZipInfo]:
    try:
        with zipfile.ZipFile(path, 'r') as archive:
            members = archive.infolist()
            if len(members) > int(os.getenv('MAX_ZIP_MEMBERS', str(DEFAULT_MAX_ZIP_MEMBERS))):
                raise HTTPException(400, {'file': ['ZIP contains too many entries.']})
            total = 0
            for info in members:
                name = info.filename.replace('\\', '/')
                parts = [part for part in name.split('/') if part not in ('', '.')]
                if name.startswith('/') or '..' in parts:
                    raise HTTPException(400, {'file': ['ZIP contains an unsafe path.']})
                total += int(info.file_size)
                if total > int(os.getenv('MAX_ZIP_UNCOMPRESSED_BYTES', str(DEFAULT_MAX_ZIP_UNCOMPRESSED))):
                    raise HTTPException(400, {'file': ['ZIP expands beyond the configured size limit.']})
            return members
    except zipfile.BadZipFile as exc:
        raise HTTPException(400, {'file': ['Invalid ZIP file.']}) from exc


def validate_polycam_zip(path: Path, *, is_map_glb: bool = False) -> None:
    members = _zip_members(path)
    names = [info.filename.replace('\\', '/') for info in members if not info.is_dir()]
    if not names:
        raise HTTPException(400, {'file': ['Empty zip file']})
    folders: set[str] = set()
    for name in names:
        first = name.split('/')[0] if '/' in name else ''
        if first != 'keyframes':
            folders.add(first)
    if not folders:
        folders = {''}
    valid = []
    errors = []
    for folder in folders:
        prefix = f'{folder}/' if folder else ''
        if f'{prefix}mesh_info.json' not in names:
            errors.append(f'Missing {prefix}mesh_info.json file')
            continue
        if not is_map_glb and f'{prefix}raw.glb' not in names:
            errors.append(f'Missing {prefix}raw.glb file. This is required unless map is a glb file.')
            continue
        keyframes = [name for name in names if name.startswith(f'{prefix}keyframes/')]
        images = [name for name in keyframes if '/images/' in name and name.endswith('.jpg')]
        depth = [name for name in keyframes if '/depth/' in name and name.endswith('.png')]
        cameras = [name for name in keyframes if '/cameras/' in name and name.endswith('.json')]
        if not keyframes:
            errors.append('Missing keyframes folder')
            continue
        if not (len(images) == len(depth) == len(cameras) > 0):
            errors.append(f'Image count mismatch: {len(images)} images, {len(depth)} depth, {len(cameras)} cameras')
            continue
        valid.append(folder)
    if len(valid) > 1:
        raise HTTPException(400, {'file': ['Zip file contains multiple polycam datasets']})
    if not valid:
        raise HTTPException(400, {'file': [errors[0] if errors else 'Zip file contains no polycam dataset']})


def validate_scene_map(path: Path) -> None:
    ext = path.suffix.lower()
    if ext not in SCENE_MAP_EXTENSIONS:
        raise HTTPException(400, {'map': [f'Unsupported scene map extension: {ext or "none"}']})
    if ext in IMAGE_EXTENSIONS:
        _validate_image(path)
    elif ext == '.glb':
        _validate_glb(path)
    elif ext == '.ply':
        _validate_ply(path)
    elif ext == '.zip':
        validate_polycam_zip(path)


def validate_asset_model(path: Path) -> None:
    if path.suffix.lower() != '.glb':
        raise HTTPException(400, {'model_3d': ['Only .glb files are supported.']})
    _validate_glb(path)


def _unique_destination(filename: str) -> Path:
    safe = _safe_filename(filename)
    root = media_root()
    target = root / safe
    if not target.exists():
        return target
    return root / f'{target.stem}_{uuid.uuid4().hex[:10]}{target.suffix}'


async def save_upload(upload: UploadFile, *, kind: str) -> str:
    if upload is None or not upload.filename:
        raise HTTPException(400, {'file': ['A file is required.']})
    destination = _unique_destination(upload.filename)
    limit = _max_upload_bytes()
    written = 0
    try:
        with destination.open('wb') as output:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    raise HTTPException(413, {'file': ['Uploaded file exceeds the configured size limit.']})
                output.write(chunk)
        if kind == 'scene-map':
            validate_scene_map(destination)
        elif kind == 'asset-model':
            validate_asset_model(destination)
        elif kind == 'polycam':
            if destination.suffix.lower() != '.zip':
                raise HTTPException(400, {'polycam_data': ['Only .zip files are supported.']})
            # Scene.polycam_data in 2026.2 has only an extension validator. Keep
            # archive safety limits here, but do not require raw.glb: calibration
            # datasets may accompany an already-existing GLB scene map.
            _zip_members(destination)
        elif kind == 'thumbnail':
            if destination.suffix.lower() not in IMAGE_EXTENSIONS:
                raise HTTPException(400, {'thumbnail': ['Only PNG/JPEG images are supported.']})
            _validate_image(destination)
        else:
            raise HTTPException(400, {'file': ['Unknown upload type.']})
        return media_url(destination)
    except Exception:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        await upload.close()


def store_bytes(filename: str, data: bytes, *, kind: str) -> str:
    destination = _unique_destination(filename)
    if len(data) > _max_upload_bytes():
        raise HTTPException(413, {'file': ['Uploaded file exceeds the configured size limit.']})
    try:
        destination.write_bytes(data)
        if kind == 'scene-map':
            validate_scene_map(destination)
        elif kind == 'asset-model':
            validate_asset_model(destination)
        elif kind == 'thumbnail':
            _validate_image(destination)
        return media_url(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def extract_raw_glb(polycam_url: str, scene_name: str) -> str | None:
    path = media_path(polycam_url)
    if path is None:
        return None
    with zipfile.ZipFile(path, 'r') as archive:
        candidates = [name for name in archive.namelist() if name.replace('\\', '/').endswith('/raw.glb') or name == 'raw.glb']
        if not candidates:
            return None
        data = archive.read(candidates[0])
    return store_bytes(f'{_safe_filename(scene_name)}.glb', data, kind='scene-map')


def read_scene_import_zip(upload_bytes: bytes) -> tuple[dict, dict[str, bytes]]:
    if len(upload_bytes) > _max_upload_bytes():
        raise HTTPException(413, {'zipFile': ['Uploaded file exceeds the configured size limit.']})
    try:
        with zipfile.ZipFile(io.BytesIO(upload_bytes), 'r') as archive:
            infos = archive.infolist()
            if not infos:
                raise HTTPException(400, {'scene': ['Cannot find resource file']})
            if len(infos) > int(os.getenv('MAX_ZIP_MEMBERS', str(DEFAULT_MAX_ZIP_MEMBERS))):
                raise HTTPException(400, {'zipFile': ['ZIP contains too many entries.']})
            files: dict[str, bytes] = {}
            total = 0
            for info in infos:
                if info.is_dir():
                    continue
                name = info.filename.replace('\\', '/')
                parts = [part for part in name.split('/') if part not in ('', '.')]
                if name.startswith('/') or '..' in parts:
                    raise HTTPException(400, {'zipFile': ['ZIP contains an unsafe path.']})
                total += int(info.file_size)
                if total > int(os.getenv('MAX_ZIP_UNCOMPRESSED_BYTES', str(DEFAULT_MAX_ZIP_UNCOMPRESSED))):
                    raise HTTPException(400, {'zipFile': ['ZIP expands beyond the configured size limit.']})
                files[Path(name).name] = archive.read(info)
    except zipfile.BadZipFile as exc:
        raise HTTPException(400, {'scene': ['Cannot find resource file']}) from exc

    json_names = [name for name in files if name.lower().endswith('.json')]
    if not json_names:
        raise HTTPException(400, {'scene': ['No JSON file found']})
    if len(json_names) > 1:
        raise HTTPException(400, {'scene': ['Multiple JSON files found']})
    try:
        scene = json.loads(files[json_names[0]].decode('utf-8'))
    except Exception as exc:
        raise HTTPException(400, {'scene': ['Failed to parse JSON']}) from exc
    resources = {name: data for name, data in files.items() if name != json_names[0]}
    if not resources:
        raise HTTPException(400, {'scene': ['No resource files found']})
    if not isinstance(scene, dict):
        raise HTTPException(400, {'scene': ['Failed to parse JSON']})
    return scene, resources
