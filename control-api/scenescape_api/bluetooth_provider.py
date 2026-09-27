# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Vendor-neutral real ranging provider boundary and scheduler (BT-12).

This module intentionally contains no vendor SDK imports. A concrete adapter
process implements the JSON contract and keeps proprietary/native dependencies
outside SceneScape core.
"""

from __future__ import annotations

import abc
import json
import math
import os
import subprocess
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .bluetooth_ingest import RangeEnvelope
from .bluetooth_telemetry import DeviceTelemetryEnvelope, normalize_provider_device_payload


def _utc(value: datetime) -> datetime:
  if value.tzinfo is None:
    return value.replace(tzinfo=timezone.utc)
  return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class ProviderCapabilities:
  provider_id: str
  hardware: str
  firmware: str
  sdk: str
  methods: tuple[str, ...]
  max_sessions: int
  max_update_hz: float
  diagnostics: tuple[str, ...] = ()
  adapter_version: str = "1"

  def __post_init__(self):
    if not self.provider_id:
      raise ValueError("provider_id is required")
    if self.max_sessions < 1:
      raise ValueError("max_sessions must be >=1")
    if not math.isfinite(self.max_update_hz) or self.max_update_hz <= 0:
      raise ValueError("max_update_hz must be positive")
    unsupported = set(self.methods) - {"channel_sounding", "aoa", "rssi"}
    if unsupported:
      raise ValueError(f"unsupported ranging methods: {sorted(unsupported)}")


@dataclass(frozen=True)
class RangingSessionRequest:
  scene_id: str
  anchor_id: str
  tag_id: str
  method: str = "channel_sounding"
  requested_hz: float = 1.0
  priority: int = 100

  def __post_init__(self):
    if not all((self.scene_id, self.anchor_id, self.tag_id)):
      raise ValueError("scene, anchor and tag IDs are required")
    if self.method not in {"channel_sounding", "aoa", "rssi"}:
      raise ValueError("unsupported ranging method")
    if not math.isfinite(self.requested_hz) or self.requested_hz <= 0:
      raise ValueError("requested_hz must be positive")


@dataclass
class SessionRuntime:
  request: RangingSessionRequest
  state: str = "queued"
  started_at: datetime | None = None
  last_sample_at: datetime | None = None
  failures: int = 0
  samples: int = 0
  reason: str | None = None


class RangingProvider(abc.ABC):
  """Core provider abstraction. Concrete adapters must not leak vendor types."""

  @property
  @abc.abstractmethod
  def capabilities(self) -> ProviderCapabilities:
    raise NotImplementedError

  @abc.abstractmethod
  def configure_role(
      self,
      *,
      device_id: str,
      role: str,
      settings: Mapping[str, Any] | None = None,
  ) -> None:
    raise NotImplementedError

  @abc.abstractmethod
  def start_session(self, request: RangingSessionRequest) -> str:
    raise NotImplementedError

  @abc.abstractmethod
  def stop_session(self, session_id: str) -> None:
    raise NotImplementedError

  @abc.abstractmethod
  def poll(self, timeout_s: float = 0.0) -> list[dict[str, Any]]:
    """Return normalized adapter events (measurement/telemetry/health)."""
    raise NotImplementedError

  @abc.abstractmethod
  def reconnect(self) -> None:
    raise NotImplementedError

  @abc.abstractmethod
  def close(self) -> None:
    raise NotImplementedError


class JsonLineAdapterError(RuntimeError):
  pass


class JsonLineRangingProvider(RangingProvider):
  """SDK-isolated subprocess adapter using a strict JSON-lines protocol.

  The adapter command is supplied by deployment config. SceneScape never loads
  vendor libraries into the API/worker process.
  """

  def __init__(
      self,
      *,
      command: list[str],
      capabilities: ProviderCapabilities,
      secrets_file: str | None = None,
      process_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
  ):
    if not command or any(not str(part) for part in command):
      raise ValueError("adapter command is required")
    if secrets_file is not None:
      path = Path(secrets_file)
      if not path.is_file():
        raise ValueError("provider secrets file does not exist")
    self._command = [str(part) for part in command]
    self._capabilities = capabilities
    self._secrets_file = secrets_file
    self._process_factory = process_factory
    self._process: subprocess.Popen | None = None
    self._lock = threading.Lock()
    self._sequence = 0
    self._start()

  @property
  def capabilities(self) -> ProviderCapabilities:
    return self._capabilities

  def _start(self) -> None:
    env = os.environ.copy()
    if self._secrets_file:
      env["SCENESCAPE_PROVIDER_SECRETS_FILE"] = self._secrets_file
    self._process = self._process_factory(
        self._command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

  def _request(self, action: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    with self._lock:
      process = self._process
      if process is None or process.poll() is not None:
        raise JsonLineAdapterError("provider adapter is not running")
      if process.stdin is None or process.stdout is None:
        raise JsonLineAdapterError("provider adapter pipes are unavailable")
      self._sequence += 1
      request_id = self._sequence
      request = {
          "protocol_version": "1.0",
          "request_id": request_id,
          "action": action,
          "payload": dict(payload),
      }
      process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
      process.stdin.flush()
      line = process.stdout.readline()
      if not line:
        raise JsonLineAdapterError("provider adapter closed response stream")
      try:
        response = json.loads(line)
      except json.JSONDecodeError as exc:
        raise JsonLineAdapterError("provider adapter emitted invalid JSON") from exc
      if response.get("request_id") != request_id:
        raise JsonLineAdapterError("provider adapter response request_id mismatch")
      if response.get("ok") is not True:
        raise JsonLineAdapterError(str(response.get("error") or "provider adapter request failed"))
      result = response.get("result") or {}
      if not isinstance(result, dict):
        raise JsonLineAdapterError("provider adapter result must be an object")
      return result

  def configure_role(
      self,
      *,
      device_id: str,
      role: str,
      settings: Mapping[str, Any] | None = None,
  ) -> None:
    if role not in {"initiator", "reflector", "auto"}:
      raise ValueError("unsupported ranging role")
    self._request(
        "configure_role",
        {"device_id": device_id, "role": role, "settings": dict(settings or {})},
    )

  def start_session(self, request: RangingSessionRequest) -> str:
    if request.method not in self.capabilities.methods:
      raise ValueError("provider does not support requested method")
    result = self._request(
        "start_session",
        {
            "scene_id": request.scene_id,
            "anchor_id": request.anchor_id,
            "tag_id": request.tag_id,
            "method": request.method,
            "requested_hz": min(request.requested_hz, self.capabilities.max_update_hz),
        },
    )
    session_id = str(result.get("session_id") or "")
    if not session_id:
      raise JsonLineAdapterError("provider did not return session_id")
    return session_id

  def stop_session(self, session_id: str) -> None:
    self._request("stop_session", {"session_id": session_id})

  def poll(self, timeout_s: float = 0.0) -> list[dict[str, Any]]:
    result = self._request("poll", {"timeout_s": max(0.0, float(timeout_s))})
    events = result.get("events") or []
    if not isinstance(events, list) or any(not isinstance(item, dict) for item in events):
      raise JsonLineAdapterError("provider events must be a list of objects")
    return events

  def reconnect(self) -> None:
    self.close()
    self._start()
    self._request("health", {})

  def close(self) -> None:
    with self._lock:
      process = self._process
      self._process = None
      if process is None:
        return
      if process.poll() is None:
        process.terminate()
        try:
          process.wait(timeout=3)
        except subprocess.TimeoutExpired:
          process.kill()
          process.wait(timeout=2)


def normalize_adapter_measurement(
    provider: ProviderCapabilities,
    event: Mapping[str, Any],
) -> RangeEnvelope:
  value = dict(event)
  if value.get("type") not in (None, "measurement"):
    raise ValueError("adapter event is not a measurement")
  provider_id = str(value.pop("provider_id", provider.provider_id))
  if provider_id != provider.provider_id:
    raise ValueError("adapter measurement provider_id mismatch")
  scene_id = str(value.pop("scene_id"))
  anchor_id = str(value.pop("anchor_id"))
  tag_id = str(value.pop("tag_id"))
  payload = dict(value.pop("payload", value))
  payload["provider_id"] = provider.provider_id
  payload.setdefault("schema_version", "1.0")
  details = dict(payload.get("provider_details") or {})
  details.setdefault("adapter_version", provider.adapter_version)
  details.setdefault("hardware", provider.hardware)
  details.setdefault("firmware", provider.firmware)
  details.setdefault("sdk", provider.sdk)
  payload["provider_details"] = details
  return RangeEnvelope.model_validate({
      "scene_id": scene_id,
      "anchor_id": anchor_id,
      "tag_id": tag_id,
      "payload": payload,
  })


def normalize_adapter_telemetry(
    provider: ProviderCapabilities,
    event: Mapping[str, Any],
) -> DeviceTelemetryEnvelope:
  value = dict(event)
  if value.get("type") not in (None, "telemetry"):
    raise ValueError("adapter event is not telemetry")
  value.pop("type", None)
  value["provider_id"] = provider.provider_id
  return normalize_provider_device_payload(value)


class ProviderScheduler:
  """Capacity-aware fair scheduler for finite Channel Sounding sessions."""

  def __init__(self, provider: RangingProvider):
    self.provider = provider
    self._queued: OrderedDict[tuple[str, str, str], SessionRuntime] = OrderedDict()
    self._active: OrderedDict[str, SessionRuntime] = OrderedDict()
    self._by_key: dict[tuple[str, str, str], str] = {}
    self.metrics = {
        "started": 0,
        "completed": 0,
        "start_failures": 0,
        "poll_failures": 0,
        "reconnects": 0,
        "capacity_limited": 0,
    }

  @staticmethod
  def _key(request: RangingSessionRequest) -> tuple[str, str, str]:
    return (request.scene_id, request.anchor_id, request.tag_id)

  def submit(self, request: RangingSessionRequest) -> None:
    key = self._key(request)
    if key in self._queued or key in self._by_key:
      return
    self._queued[key] = SessionRuntime(request=request)
    self._queued = OrderedDict(
        sorted(
            self._queued.items(),
            key=lambda item: (item[1].request.priority, item[0]),
        )
    )

  def cancel(self, request: RangingSessionRequest) -> None:
    key = self._key(request)
    self._queued.pop(key, None)
    session_id = self._by_key.pop(key, None)
    if session_id is not None:
      try:
        self.provider.stop_session(session_id)
      finally:
        self._active.pop(session_id, None)
        self.metrics["completed"] += 1

  def reconcile(self) -> None:
    capacity = self.provider.capabilities.max_sessions
    while self._queued and len(self._active) < capacity:
      key, runtime = self._queued.popitem(last=False)
      try:
        session_id = self.provider.start_session(runtime.request)
      except Exception as exc:
        runtime.failures += 1
        runtime.reason = type(exc).__name__
        runtime.state = "queued"
        self.metrics["start_failures"] += 1
        self._queued[key] = runtime
        break
      runtime.state = "ranging"
      runtime.started_at = datetime.now(timezone.utc)
      runtime.reason = None
      self._active[session_id] = runtime
      self._by_key[key] = session_id
      self.metrics["started"] += 1
    if self._queued and len(self._active) >= capacity:
      self.metrics["capacity_limited"] += len(self._queued)

  def poll(self, timeout_s: float = 0.0) -> list[dict[str, Any]]:
    try:
      events = self.provider.poll(timeout_s)
    except Exception:
      self.metrics["poll_failures"] += 1
      raise
    now = datetime.now(timezone.utc)
    for event in events:
      session_id = str(event.get("session_id") or "")
      runtime = self._active.get(session_id)
      if runtime is not None and event.get("type") == "measurement":
        runtime.last_sample_at = now
        runtime.samples += 1
    return events

  def reconnect(self) -> None:
    requests = [runtime.request for runtime in self._active.values()]
    requests.extend(runtime.request for runtime in self._queued.values())
    self._active.clear()
    self._queued.clear()
    self._by_key.clear()
    self.provider.reconnect()
    self.metrics["reconnects"] += 1
    for request in requests:
      self.submit(request)
    self.reconcile()

  def diagnostics(self) -> dict[str, Any]:
    capabilities = self.provider.capabilities
    return {
        "provider_id": capabilities.provider_id,
        "hardware": capabilities.hardware,
        "firmware": capabilities.firmware,
        "sdk": capabilities.sdk,
        "adapter_version": capabilities.adapter_version,
        "capacity": {
            "max_sessions": capabilities.max_sessions,
            "active": len(self._active),
            "queued": len(self._queued),
            "available": max(0, capabilities.max_sessions - len(self._active)),
            "max_update_hz": capabilities.max_update_hz,
        },
        "sessions": [
            {
                "session_id": session_id,
                "scene_id": runtime.request.scene_id,
                "anchor_id": runtime.request.anchor_id,
                "tag_id": runtime.request.tag_id,
                "requested_hz": runtime.request.requested_hz,
                "state": runtime.state,
                "samples": runtime.samples,
                "failures": runtime.failures,
                "last_sample_at": runtime.last_sample_at,
            }
            for session_id, runtime in self._active.items()
        ],
        "metrics": dict(self.metrics),
    }


def reconnect_with_backoff(
    action: Callable[[], None],
    *,
    attempts: int = 5,
    initial_delay_s: float = 0.25,
    maximum_delay_s: float = 5.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
  if attempts < 1:
    raise ValueError("attempts must be >=1")
  delay = max(0.0, initial_delay_s)
  last: Exception | None = None
  for attempt in range(attempts):
    try:
      action()
      return
    except Exception as exc:
      last = exc
      if attempt == attempts - 1:
        break
      sleep_fn(delay)
      delay = min(maximum_delay_s, max(delay * 2.0, 0.01))
  assert last is not None
  raise last
