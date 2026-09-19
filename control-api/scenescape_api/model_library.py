# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Filesystem-backed model library for the native SceneScape control plane."""

from __future__ import annotations

import inspect
import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import HTTPException

_FORBIDDEN = re.compile(r'[\\:*?"<>|\x00-\x1f]')
_CHUNK = 1024 * 1024


def model_root() -> Path:
  """Return the configured model-library root."""
  return Path(os.getenv("MODEL_ROOT", "/models")).resolve()


def _limit(name: str, default: int) -> int:
  try:
    value = int(os.getenv(name, str(default)))
  except ValueError as exc:
    raise HTTPException(500, f"Invalid {name} configuration") from exc
  if value <= 0:
    raise HTTPException(500, f"Invalid {name} configuration")
  return value


def _parts(value: str | None, *, empty: bool) -> tuple[str, ...]:
  raw = str(value or "")
  if raw.startswith("/") or "\\" in raw:
    raise HTTPException(400, "Model paths must be relative POSIX paths")
  raw = raw.rstrip("/")
  if not raw:
    if empty:
      return ()
    raise HTTPException(400, "Path is required")
  parts = tuple(raw.split("/"))
  if any(part in {"", ".", ".."} or _FORBIDDEN.search(part) for part in parts):
    raise HTTPException(400, "Invalid model path")
  return parts


def _target(value: str | None, *, root_ok: bool = False) -> Path:
  root = model_root()
  target = root.joinpath(*_parts(value, empty=root_ok)).resolve(strict=False)
  try:
    target.relative_to(root)
  except ValueError as exc:
    raise HTTPException(400, "Model path escapes the model directory") from exc
  if target == root and not root_ok:
    raise HTTPException(400, "The model-library root cannot be modified directly")
  return target


def _relative(path: Path) -> str:
  try:
    rel = path.relative_to(model_root())
  except ValueError as exc:
    raise HTTPException(500, "Model entry is outside the configured root") from exc
  return rel.as_posix() if rel.parts else ""


def _entry(path: Path) -> dict[str, Any]:
  if path.is_symlink():
    kind, size = "symlink", path.lstat().st_size
  elif path.is_dir():
    kind, size = "directory", None
  else:
    kind, size = "file", path.stat().st_size
  return {"name": path.name, "path": _relative(path), "type": kind, "size": size}


def list_directory(path: str | None = "") -> dict[str, Any]:
  """List one model-directory level."""
  root = model_root()
  if not root.exists():
    if path:
      raise HTTPException(404, "Model directory not found")
    return {"path": "", "entries": []}
  target = _target(path, root_ok=True)
  if not target.exists():
    raise HTTPException(404, "Model directory not found")
  if target.is_symlink() or not target.is_dir():
    raise HTTPException(400, "Requested model path is not a directory")
  entries = []
  for child in target.iterdir():
    try:
      child.resolve(strict=False).relative_to(root)
    except (OSError, ValueError):
      continue
    entries.append(_entry(child))
  entries.sort(key=lambda item: (item["type"] != "directory", item["name"].lower()))
  return {"path": _relative(target), "entries": entries}


def create_directory(path: str | None, name: str) -> dict[str, Any]:
  """Create a directory under an existing model directory."""
  if "/" in str(name) or "\\" in str(name):
    raise HTTPException(400, "Directory name must be a single path component")
  name_parts = _parts(str(name), empty=False)
  parent = _target(path, root_ok=True)
  if not parent.exists() or not parent.is_dir() or parent.is_symlink():
    raise HTTPException(404, "Parent model directory not found")
  target = _target("/".join((*_parts(path, empty=True), name_parts[0])))
  if target.exists() or target.is_symlink():
    raise HTTPException(409, "Model directory already exists")
  target.mkdir()
  return _entry(target)


def delete_entry(path: str) -> dict[str, str]:
  """Delete a model file or directory recursively."""
  target = _target(path)
  if not target.exists() and not target.is_symlink():
    raise HTTPException(404, "Model path not found")
  if target.is_symlink() or target.is_file():
    target.unlink()
  else:
    shutil.rmtree(target)
  return {"deleted": path}


def download_target(path: str) -> Path:
  """Resolve a downloadable regular model file."""
  target = _target(path)
  if not target.exists() or target.is_symlink() or not target.is_file():
    raise HTTPException(404, "Model file not found")
  return target


async def _close(upload: Any) -> None:
  close = getattr(upload, "close", None)
  if close is None:
    return
  result = close()
  if inspect.isawaitable(result):
    await result


async def upload_files(
  base_path: str | None,
  uploads: list[Any],
  relative_paths: list[str],
  *,
  overwrite: bool = False,
) -> dict[str, Any]:
  """Upload files, retaining optional browser directory-relative paths."""
  if not uploads:
    raise HTTPException(400, "At least one model file is required")
  if relative_paths and len(relative_paths) != len(uploads):
    raise HTTPException(400, "relative_paths must match uploaded files")
  parent = _target(base_path, root_ok=True)
  if not parent.exists() or not parent.is_dir() or parent.is_symlink():
    raise HTTPException(404, "Target model directory not found")

  base = _parts(base_path, empty=True)
  plans = []
  seen = set()
  for index, upload in enumerate(uploads):
    relative = relative_paths[index] if relative_paths else str(getattr(upload, "filename", ""))
    target = _target("/".join((*base, *_parts(relative, empty=False))))
    if target in seen:
      raise HTTPException(400, f"Duplicate upload target: {_relative(target)}")
    seen.add(target)
    if target.exists() or target.is_symlink():
      if target.is_dir() or target.is_symlink():
        raise HTTPException(409, f"A directory already exists at {_relative(target)}")
      if not overwrite:
        raise HTTPException(409, f"Model file already exists: {_relative(target)}")
    plans.append((upload, target))

  maximum = _limit("MODEL_UPLOAD_MAX_BYTES", 4 * 1024 * 1024 * 1024)
  saved = []
  for upload, target in plans:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
      with tempfile.NamedTemporaryFile(prefix=".scenescape-upload-", dir=target.parent, delete=False) as handle:
        temp_path = Path(handle.name)
        total = 0
        while True:
          chunk = await upload.read(_CHUNK)
          if not chunk:
            break
          total += len(chunk)
          if total > maximum:
            raise HTTPException(413, f"Model file exceeds the {maximum}-byte upload limit")
          handle.write(chunk)
      os.replace(temp_path, target)
      temp_path = None
      saved.append(_entry(target))
    finally:
      await _close(upload)
      if temp_path is not None:
        temp_path.unlink(missing_ok=True)
  return {"uploaded": saved}


def _zip_parts(info: zipfile.ZipInfo) -> tuple[str, ...]:
  raw = info.filename
  if not raw or raw.startswith("/") or "\\" in raw or "\x00" in raw:
    raise HTTPException(400, f"Unsafe ZIP member path: {raw!r}")
  parts = tuple(part for part in PurePosixPath(raw).parts if part)
  if not parts or any(part in {".", ".."} or _FORBIDDEN.search(part) for part in parts):
    raise HTTPException(400, f"Unsafe ZIP member path: {raw!r}")
  mode = (info.external_attr >> 16) & 0o170000
  if mode == stat.S_IFLNK:
    raise HTTPException(400, f"ZIP symbolic links are not supported: {raw!r}")
  return parts


async def extract_zip(
  base_path: str | None,
  upload: Any,
  *,
  folder_name: str | None = None,
  overwrite: bool = False,
) -> dict[str, Any]:
  """Safely extract a ZIP into an atomically replaced top-level directory."""
  filename = str(getattr(upload, "filename", "") or "")
  if not filename.lower().endswith(".zip"):
    raise HTTPException(400, "Only ZIP archives can be extracted")
  name = str(folder_name or Path(filename).stem)
  if len(_parts(name, empty=False)) != 1:
    raise HTTPException(400, "ZIP destination must be a single directory name")

  parent = _target(base_path, root_ok=True)
  if not parent.exists() or not parent.is_dir() or parent.is_symlink():
    raise HTTPException(404, "Target model directory not found")
  target = _target("/".join((*_parts(base_path, empty=True), name)))
  if (target.exists() or target.is_symlink()) and not overwrite:
    raise HTTPException(409, f"Model path already exists: {_relative(target)}")

  upload_max = _limit("MODEL_UPLOAD_MAX_BYTES", 4 * 1024 * 1024 * 1024)
  extract_max = _limit("MODEL_ZIP_MAX_UNCOMPRESSED_BYTES", 16 * 1024 * 1024 * 1024)
  member_max = _limit("MODEL_ZIP_MAX_MEMBERS", 10000)
  archive_path = None
  temp_dir = None
  try:
    with tempfile.NamedTemporaryFile(prefix=".scenescape-archive-", dir=parent, delete=False) as handle:
      archive_path = Path(handle.name)
      total = 0
      while True:
        chunk = await upload.read(_CHUNK)
        if not chunk:
          break
        total += len(chunk)
        if total > upload_max:
          raise HTTPException(413, f"ZIP exceeds the {upload_max}-byte upload limit")
        handle.write(chunk)

    temp_dir = Path(tempfile.mkdtemp(prefix=".scenescape-extract-", dir=parent))
    with zipfile.ZipFile(archive_path, "r") as archive:
      members = archive.infolist()
      if len(members) > member_max:
        raise HTTPException(413, f"ZIP contains more than {member_max} entries")
      if sum(info.file_size for info in members) > extract_max:
        raise HTTPException(413, f"ZIP expands beyond the {extract_max}-byte limit")
      for info in members:
        destination = temp_dir.joinpath(*_zip_parts(info)).resolve(strict=False)
        try:
          destination.relative_to(temp_dir)
        except ValueError as exc:
          raise HTTPException(400, f"Unsafe ZIP member path: {info.filename!r}") from exc
        if info.is_dir():
          destination.mkdir(parents=True, exist_ok=True)
          continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info, "r") as source, open(destination, "wb") as output:
          shutil.copyfileobj(source, output, length=_CHUNK)

    if target.exists() or target.is_symlink():
      if target.is_symlink() or target.is_file():
        target.unlink()
      else:
        shutil.rmtree(target)
    os.replace(temp_dir, target)
    temp_dir = None
    return {"extracted": _entry(target)}
  except zipfile.BadZipFile as exc:
    raise HTTPException(400, "Uploaded file is not a valid ZIP archive") from exc
  finally:
    await _close(upload)
    if archive_path is not None:
      archive_path.unlink(missing_ok=True)
    if temp_dir is not None:
      shutil.rmtree(temp_dir, ignore_errors=True)
