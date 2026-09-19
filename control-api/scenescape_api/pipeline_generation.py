# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi import HTTPException


class PipelineGenerationValueError(ValueError):
    pass


class PipelineGenerationNotImplementedError(NotImplementedError):
    pass


DEFAULT_PARAMS = {
    "scheduling-policy": "latency",
    "batch-size": "1",
    "inference-interval": "1",
}
SUPPORTED_MODEL_TYPES = {"detect", "classify", "inference", "track"}


def _config_roots() -> list[Path]:
  primary = Path(os.getenv("MODEL_CONFIGS_FOLDER", "/app/model_configs")).resolve()
  fallback = Path(os.getenv("MODEL_CONFIGS_FALLBACK_FOLDER", "/app/model_configs")).resolve()
  return list(dict.fromkeys((primary, fallback)))


def list_model_configs() -> list[str]:
  """Discover JSON model configurations, preferring the shared models PVC."""
  configs: set[str] = set()
  for root in _config_roots():
    if not root.is_dir():
      continue
    for path in root.rglob("*.json"):
      if path.is_symlink() or not path.is_file():
        continue
      try:
        resolved = path.resolve()
        resolved.relative_to(root)
      except (OSError, ValueError):
        continue
      configs.add(path.relative_to(root).as_posix())
  return sorted(configs, key=str.lower)


def _model_config_path(modelconfig_name=None) -> Path:
  name = str(modelconfig_name or "model_config.json")
  if not name or "\\" in name:
    raise PipelineGenerationValueError("Invalid model configuration filename")
  relative = Path(name)
  if relative.is_absolute() or ".." in relative.parts:
    raise PipelineGenerationValueError("Invalid model configuration filename")
  for root in _config_roots():
    path = (root / relative).resolve()
    try:
      path.relative_to(root)
    except ValueError:
      continue
    if path.is_file():
      return path
  raise PipelineGenerationValueError(f"Model configuration not found: {name}")


def load_model_config(modelconfig_name=None) -> dict:
  path = _model_config_path(modelconfig_name)
  filename = str(modelconfig_name or "model_config.json")
  try:
    value = json.loads(path.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError) as exc:
    raise PipelineGenerationValueError(f"Invalid model configuration {filename}: {exc}") from exc
  if not isinstance(value, dict):
    raise PipelineGenerationValueError("Model configuration must contain a JSON object")
  for name, entry in value.items():
    if not isinstance(entry, dict):
      raise PipelineGenerationValueError(
        f"Model config entry for '{name}' must be a JSON object."
      )
  return value

def _format_value(value):
    if isinstance(value, str) and (any(c in value for c in " ;!") or value == ""):
        return f'"{value}"'
    return str(value)


def _inference_node(expression: str, model_config: dict, region: int) -> tuple[str, str]:
    if "=" in expression:
        model_name, device = expression.split("=", 1)
        model_name, device = model_name.strip(), device.strip()
        if not device:
            raise PipelineGenerationValueError(
                f"Device name cannot be empty in model expression '{expression}'"
            )
    else:
        model_name, device = expression.strip(), None
    if not re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", model_name):
        raise PipelineGenerationValueError(
            f"Invalid model name '{model_name}'. Model name must start with a letter and contain only letters, numbers, underscores, and hyphens."
        )
    if model_name not in model_config:
        raise PipelineGenerationValueError(
            f"Model {model_name} not found in model config file."
        )
    config = model_config[model_name]
    if "params" not in config:
        raise PipelineGenerationValueError(
            f"No parameters found for model {model_name} in model config file."
        )
    model_type = config.get("type", "inference")
    if model_type not in SUPPORTED_MODEL_TYPES:
        raise PipelineGenerationValueError(
            f"Unsupported model type: {model_type}. Supported types are {', '.join(sorted(SUPPORTED_MODEL_TYPES))}."
        )
    params = dict(DEFAULT_PARAMS)
    for key, value in dict(config["params"]).items():
        if key in {"model", "model_proc"}:
            value = str(Path("/home/pipeline-server/models") / Path(str(value)))
        params[key] = value
    if device:
        params["device"] = device
    params["inference-region"] = str(region)
    metadata_policy = (
        config.get("adapter-params", {}).get("metadatagenpolicy", "detectionPolicy")
    )
    serialized = " ".join(f"{key}={_format_value(value)}" for key, value in params.items())
    return f"gva{model_type} {serialized}", metadata_policy


def _model_chain(chain: str, model_config: dict) -> tuple[list[str], str]:
    if not chain or not chain.strip():
        raise PipelineGenerationValueError("model_chain string cannot be empty!")
    chain = chain.strip()
    if "[" in chain or "]" in chain:
        raise PipelineGenerationValueError(
            "Square brackets '[' and ']' are not supported in current version"
        )
    if "+" in chain and "," in chain:
        raise PipelineGenerationNotImplementedError(
            "Mixed sequential ('+') and parallel (',') chaining is not yet implemented"
        )
    if "," in chain:
        raise PipelineGenerationNotImplementedError(
            "parallel model chaining is not supported yet"
        )
    expressions = [item.strip() for item in chain.split("+") if item.strip()]
    result: list[str] = []
    policy = "detectionPolicy"
    for index, expression in enumerate(expressions):
        node, policy = _inference_node(expression, model_config, 0 if index == 0 else 1)
        result.append(node)
        if index < len(expressions) - 1:
            result.append("queue")
    return result, policy


def _source(command: str) -> list[str]:
    if command.startswith("rtsp://"):
        return [f"rtspsrc location={command} latency=200 name=source"]
    if command.startswith("file://"):
        filename = Path(command[len("file://"):])
        return [f"multifilesrc loop=TRUE location={Path('/home/pipeline-server/videos') / filename} name=source"]
    if command.startswith("http://") or command.startswith("https://"):
        return [f"souphttpsrc location={command} name=source", "multipartdemux"]
    if re.fullmatch(r"/dev/(video\d*|media\d+|v4l/by-(id|path)/.+)", command):
        return [f"v4l2src device={command} name=source"]
    raise PipelineGenerationValueError(
        f"Unsupported source type in {command}. Supported types are 'rtsp://...' (raw H.264), 'http(s)://...' (MJPEG), 'file://... (relative to video folder) and paths to V4L2 USB devices'."
    )


def _flat_settings(settings: dict) -> dict:
    value = dict(settings)
    intrinsics = value.get("intrinsics") or {}
    distortion = value.get("distortion") or {}
    for key in ("fx", "fy", "cx", "cy"):
        if key in intrinsics:
            value.setdefault(f"intrinsics_{key}", intrinsics[key])
    for key in ("k1", "k2", "p1", "p2", "k3"):
        if key in distortion:
            value.setdefault(f"distortion_{key}", distortion[key])
    return value


def generate_pipeline_string(settings: dict) -> str:
    settings = _flat_settings(settings)
    model_config = load_model_config(settings.get("modelconfig"))
    components = _source(str(settings.get("command") or ""))
    decode_device = str(settings.get("cv_subsystem") or "AUTO")
    if decode_device not in {"CPU", "GPU", "AUTO"}:
        raise PipelineGenerationValueError(
            f"Unsupported decode device: {decode_device}. Supported values are 'CPU', 'GPU', 'AUTO'."
        )
    if decode_device == "CPU":
        components.extend(["decodebin force-sw-decoders=true", "videoconvert", "video/x-raw,format=BGR"])
    else:
        components.append("decodebin3")

    if settings.get("undistort"):
        distortion_keys = ("distortion_k1", "distortion_k2", "distortion_p1", "distortion_p2", "distortion_k3")
        try:
            distortion = [float(settings[key]) for key in distortion_keys]
        except Exception:
            distortion = []
        if distortion and any(value != 0 for value in distortion):
            components.append("cameraundistort settings=cameraundistort0")

    components.append("sscape_timestamp_capture name=timesync")
    chain, _ = _model_chain(str(settings.get("camerachain") or ""), model_config)
    components.extend(chain)
    components.extend([
        "queue",
        "gvametaconvert add-tensor-data=true name=metaconvert",
        "sscape_post_inference_data_publish name=datapublisher",
        "appsink sync=true",
    ])
    return " ! ".join(components)


def pipeline_preview(settings: dict) -> dict:
    try:
        return {"success": True, "pipeline": generate_pipeline_string(settings)}
    except (PipelineGenerationValueError, PipelineGenerationNotImplementedError) as exc:
        raise HTTPException(400, {"error": str(exc)}) from exc
