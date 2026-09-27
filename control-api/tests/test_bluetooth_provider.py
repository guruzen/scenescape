# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timezone

import pytest

from scenescape_api.bluetooth_provider import (
    ProviderCapabilities,
    ProviderScheduler,
    RangingProvider,
    RangingSessionRequest,
    normalize_adapter_measurement,
    normalize_adapter_telemetry,
    reconnect_with_backoff,
)


class FakeProvider(RangingProvider):
  def __init__(self, max_sessions=2):
    self._capabilities = ProviderCapabilities(
        provider_id="svc",
        hardware="fake-cs",
        firmware="1.0",
        sdk="fake-sdk-2",
        methods=("channel_sounding",),
        max_sessions=max_sessions,
        max_update_hz=20.0,
        diagnostics=("pbr", "rtt"),
    )
    self.started = []
    self.stopped = []
    self.events = []
    self.reconnect_count = 0

  @property
  def capabilities(self):
    return self._capabilities

  def configure_role(self, *, device_id, role, settings=None):
    return None

  def start_session(self, request):
    session_id = f"s{len(self.started)+1}"
    self.started.append((session_id, request))
    return session_id

  def stop_session(self, session_id):
    self.stopped.append(session_id)

  def poll(self, timeout_s=0):
    events = list(self.events)
    self.events.clear()
    return events

  def reconnect(self):
    self.reconnect_count += 1

  def close(self):
    return None


def test_bt12_measurement_normalization_preserves_core_contract_and_provider_diagnostics():
  capabilities = FakeProvider().capabilities
  envelope = normalize_adapter_measurement(
      capabilities,
      {
          "type": "measurement",
          "scene_id": "scene-a",
          "anchor_id": "anchor-a",
          "tag_id": "tag-a",
          "payload": {
              "session_id": "vendor-session-1",
              "sequence": 7,
              "source_timestamp": datetime.now(timezone.utc).isoformat(),
              "method": "channel_sounding",
              "distance_m": 4.25,
              "distance_stddev_m": 0.08,
              "nlos_probability": 0.1,
              "quality": 0.9,
              "provider_details": {
                  "pbr_quality": 0.88,
                  "rtt_quality": 0.91,
              },
          },
      },
  )
  assert envelope.scene_id == "scene-a"
  assert envelope.payload.provider_id == "svc"
  assert envelope.payload.method == "channel_sounding"
  assert envelope.payload.provider_details["hardware"] == "fake-cs"
  assert envelope.payload.provider_details["sdk"] == "fake-sdk-2"
  assert envelope.payload.provider_details["pbr_quality"] == 0.88


def test_bt12_telemetry_normalization_keeps_core_device_contract():
  capabilities = FakeProvider().capabilities
  telemetry = normalize_adapter_telemetry(
      capabilities,
      {
          "type": "telemetry",
          "source_timestamp": datetime.now(timezone.utc).isoformat(),
          "device_type": "tag",
          "device_id": "tag-a",
          "battery": {"percent": 64, "source": "vendor"},
          "firmware_revision": "3.2",
          "session_capacity": 4,
      },
  )
  assert telemetry.provider_id == "svc"
  assert telemetry.device_id == "tag-a"
  assert telemetry.battery_percent == 64
  assert telemetry.firmware_revision == "3.2"
  assert telemetry.details["session_capacity"] == 4


def test_bt12_scheduler_respects_capacity_and_starts_queued_sessions_fairly():
  provider = FakeProvider(max_sessions=2)
  scheduler = ProviderScheduler(provider)
  requests = [
      RangingSessionRequest(
          scene_id="scene-a",
          anchor_id="anchor-a",
          tag_id=f"tag-{index}",
          requested_hz=10,
          priority=index,
      )
      for index in range(4)
  ]
  for request in requests:
    scheduler.submit(request)
  scheduler.reconcile()

  diagnostics = scheduler.diagnostics()
  assert diagnostics["capacity"]["active"] == 2
  assert diagnostics["capacity"]["queued"] == 2
  assert diagnostics["capacity"]["available"] == 0
  assert scheduler.metrics["capacity_limited"] == 2
  assert [request.tag_id for _, request in provider.started] == ["tag-0", "tag-1"]

  scheduler.cancel(requests[0])
  scheduler.reconcile()
  assert scheduler.diagnostics()["capacity"]["active"] == 2
  assert provider.started[-1][1].tag_id == "tag-2"


def test_bt12_scheduler_records_measurement_activity_and_recovers_after_reconnect():
  provider = FakeProvider(max_sessions=1)
  scheduler = ProviderScheduler(provider)
  request = RangingSessionRequest(
      scene_id="scene-a",
      anchor_id="anchor-a",
      tag_id="tag-a",
  )
  scheduler.submit(request)
  scheduler.reconcile()
  provider.events = [{"type": "measurement", "session_id": "s1"}]
  scheduler.poll()

  first = scheduler.diagnostics()["sessions"][0]
  assert first["samples"] == 1
  assert first["last_sample_at"] is not None

  scheduler.reconnect()
  assert provider.reconnect_count == 1
  assert scheduler.metrics["reconnects"] == 1
  assert scheduler.diagnostics()["capacity"]["active"] == 1


def test_bt12_reconnect_backoff_is_bounded_and_stops_after_success():
  calls = {"count": 0}
  sleeps = []

  def action():
    calls["count"] += 1
    if calls["count"] < 3:
      raise RuntimeError("offline")

  reconnect_with_backoff(
      action,
      attempts=5,
      initial_delay_s=0.1,
      maximum_delay_s=0.25,
      sleep_fn=sleeps.append,
  )
  assert calls["count"] == 3
  assert sleeps == [0.1, 0.2]


def test_bt12_reconnect_backoff_surfaces_final_failure():
  with pytest.raises(RuntimeError, match="offline"):
    reconnect_with_backoff(
        lambda: (_ for _ in ()).throw(RuntimeError("offline")),
        attempts=2,
        initial_delay_s=0,
        sleep_fn=lambda _: None,
    )
