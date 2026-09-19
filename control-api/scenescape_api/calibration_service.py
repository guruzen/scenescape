from __future__ import annotations

import os
from pathlib import Path

import requests
from fastapi import HTTPException


def _base_url() -> str:
    return os.getenv("AUTOCALIBRATION_URL", "https://autocalibration.scenescape.intel.com:8443").rstrip("/")


def _verify():
    ca = os.getenv("UPSTREAM_CA_FILE") or os.getenv("MQTT_CA_FILE")
    return ca if ca and Path(ca).is_file() else True


def _request(method: str, path: str, payload: dict | None = None) -> tuple[dict, int]:
    try:
        response = requests.request(
            method,
            f"{_base_url()}/v1/{path.lstrip('/')}",
            json=payload,
            timeout=int(os.getenv("AUTOCALIBRATION_REQUEST_TIMEOUT", "30")),
            verify=_verify(),
        )
    except requests.Timeout as exc:
        raise HTTPException(504, "Auto-calibration service request timed out") from exc
    except requests.ConnectionError as exc:
        raise HTTPException(503, "Could not connect to auto-calibration service") from exc
    try:
        body = response.json()
    except Exception:
        body = {"message": response.text or f"HTTP {response.status_code}"}
    if response.status_code >= 400:
        raise HTTPException(response.status_code, body)
    return body, response.status_code


def service_status() -> dict:
    return _request("GET", "status")[0]


def scene_registration(scene_id: str, method: str) -> dict:
    method = method.upper()
    if method not in {"GET", "POST", "PATCH"}:
        raise HTTPException(405, "Unsupported auto-calibration registration method")
    return _request(method, f"scenes/{scene_id}/registration", {})[0]


def camera_calibration(camera_id: str, method: str, payload: dict | None = None) -> dict:
    method = method.upper()
    if method not in {"GET", "POST"}:
        raise HTTPException(405, "Unsupported auto-calibration camera method")
    return _request(method, f"cameras/{camera_id}/calibration", payload if method == "POST" else None)[0]
