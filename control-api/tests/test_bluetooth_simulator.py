# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import math

import pytest
from pydantic import ValidationError

from scenescape_api.bluetooth_simulator import (
    Position3D,
    SimulatorScenario,
    assert_simulator_runtime_allowed,
    interpolate_trajectory,
    load_scenario_bundle,
    scenario_from_dict,
    simulate,
)


def base_scenario(**overrides):
  value = {
      "name": "walk-square",
      "scene_id": "scene-bt",
      "seed": 4242,
      "duration_s": 2.0,
      "step_s": 1.0,
      "anchors": [
          {"anchor_id": "a1", "x_m": 0.0, "y_m": 0.0, "z_m": 3.0},
          {"anchor_id": "a2", "x_m": 10.0, "y_m": 0.0, "z_m": 3.0},
          {"anchor_id": "a3", "x_m": 10.0, "y_m": 10.0, "z_m": 3.0},
          {"anchor_id": "a4", "x_m": 0.0, "y_m": 10.0, "z_m": 3.0},
      ],
      "tags": [{
          "tag_id": "tag-1",
          "battery_start_percent": 75.0,
          "battery_drain_percent_per_hour": 3.0,
          "trajectory": [
              {"t_s": 0.0, "x_m": 1.0, "y_m": 1.0, "z_m": 1.0},
              {"t_s": 2.0, "x_m": 5.0, "y_m": 3.0, "z_m": 1.0},
          ],
      }],
      "faults": {
          "noise_stddev_m": 0.05,
          "nlos_probability": 0.0,
          "outlier_probability": 0.0,
          "packet_loss_probability": 0.0,
      },
  }
  value.update(overrides)
  return scenario_from_dict(value)


def test_bt05_seed_reproducibility_and_truth_isolation():
  scenario = base_scenario()
  first = simulate(scenario)
  second = simulate(scenario)

  assert first == second
  assert len(first.truth) == 3
  assert len(first.measurements) == 12
  assert len(first.telemetry) == 3

  measurement_text = json.dumps(first.measurements)
  assert '"position"' not in measurement_text
  assert "ideal_distance" not in measurement_text
  assert all(item["payload"]["provider_details"]["synthetic"] for item in first.measurements)
  assert all(item["synthetic"] for item in first.truth)


def test_bt05_exact_zero_noise_ranges_match_geometry():
  scenario = base_scenario(
      duration_s=1.0,
      step_s=1.0,
      faults={
          "noise_stddev_m": 0.0,
          "nlos_probability": 0.0,
          "outlier_probability": 0.0,
          "packet_loss_probability": 0.0,
      },
  )
  result = simulate(scenario)
  first = next(
      item
      for item in result.measurements
      if item["tag_id"] == "tag-1" and item["anchor_id"] == "a1"
  )
  # Tag=(1,1,1), anchor=(0,0,3): sqrt(1 + 1 + 4)
  assert first["payload"]["distance_m"] == pytest.approx(math.sqrt(6), abs=1e-6)
  assert first["payload"]["distance_stddev_m"] == pytest.approx(0.001)


def test_bt05_interpolates_truth_linearly():
  scenario = base_scenario(duration_s=2.0, step_s=0.5)
  tag = scenario.tags[0]
  midpoint = interpolate_trajectory(tag, 1.0)
  assert midpoint == Position3D(x_m=3.0, y_m=2.0, z_m=1.0)


def test_bt05_nlos_outlier_loss_and_anchor_outage_are_available():
  scenario = base_scenario(
      duration_s=2.0,
      step_s=1.0,
      faults={
          "noise_stddev_m": 0.0,
          "nlos_probability": 1.0,
          "nlos_bias_m": 1.25,
          "outlier_probability": 1.0,
          "outlier_bias_m": 2.5,
          "packet_loss_probability": 0.0,
          "outage_windows": [{"anchor_id": "a4", "start_s": 0.0, "end_s": 1.5}],
      },
  )
  result = simulate(scenario)
  assert len(result.measurements) == 10
  assert all("nlos" in item["payload"]["provider_details"]["faults"] for item in result.measurements)
  assert all("outlier" in item["payload"]["provider_details"]["faults"] for item in result.measurements)
  assert all(item["payload"]["quality"] <= 0.15 for item in result.measurements)
  # a4 is absent at t=0 and t=1, but returns at t=2.
  assert sum(item["anchor_id"] == "a4" for item in result.measurements) == 1

  loss = base_scenario(
      faults={
          "noise_stddev_m": 0.0,
          "packet_loss_probability": 1.0,
      },
  )
  assert simulate(loss).measurements == []


def test_bt05_out_of_order_changes_delivery_not_provider_sequence():
  ordered = simulate(base_scenario(faults={"noise_stddev_m": 0.0})).measurements
  shuffled = simulate(
      base_scenario(
          faults={
              "noise_stddev_m": 0.0,
              "out_of_order_probability": 1.0,
          },
      )
  ).measurements

  ordered_sequences = [item["payload"]["sequence"] for item in ordered]
  shuffled_sequences = [item["payload"]["sequence"] for item in shuffled]
  assert ordered_sequences == sorted(ordered_sequences)
  assert shuffled_sequences != sorted(shuffled_sequences)
  assert sorted(shuffled_sequences) == ordered_sequences


def test_bt05_battery_last_seen_and_synthetic_provenance():
  scenario = base_scenario(duration_s=2.0, step_s=1.0)
  result = simulate(scenario)
  first = result.telemetry[0]["payload"]
  last = result.telemetry[-1]["payload"]

  assert first["battery"]["percent"] == 75.0
  assert last["battery"]["percent"] < 75.0
  assert first["battery"]["source"] == "simulator"
  assert first["synthetic"] is True
  assert first["last_seen_at"] == first["source_timestamp"]


@pytest.mark.parametrize(
    "mutation,match",
    [
        (
            lambda value: value["anchors"].append(
                {"anchor_id": "a1", "x_m": 5.0, "y_m": 5.0, "z_m": 3.0}
            ),
            "anchor IDs must be unique",
        ),
        (
            lambda value: value["tags"][0]["trajectory"].append(
                {"t_s": 1.5, "x_m": 2.0, "y_m": 2.0, "z_m": 1.0}
            ),
            "strictly increasing",
        ),
        (
            lambda value: value["faults"].update({
                "outage_windows": [{"anchor_id": "missing", "start_s": 0.0, "end_s": 1.0}]
            }),
            "unknown anchors",
        ),
    ],
)
def test_bt05_scenario_validation_rejects_ambiguous_input(mutation, match):
  value = base_scenario().model_dump(mode="json")
  mutation(value)
  with pytest.raises(ValidationError, match=match):
    SimulatorScenario.model_validate(value)


def test_bt05_runtime_guard_is_explicit_and_production_is_always_denied():
  with pytest.raises(RuntimeError, match="requires"):
    assert_simulator_runtime_allowed({})
  assert_simulator_runtime_allowed({"SCENESCAPE_ENABLE_BLUETOOTH_SIMULATOR": "true"})
  with pytest.raises(RuntimeError, match="disabled in production"):
    assert_simulator_runtime_allowed({
        "SCENESCAPE_ENABLE_BLUETOOTH_SIMULATOR": "true",
        "SCENESCAPE_ENV": "production",
    })


def test_bt05_versioned_bundle_loads_only_when_explicitly_enabled(tmp_path):
  scenario = base_scenario().model_dump(mode="json")
  bundle = tmp_path / "scenarios.json"
  bundle.write_text(
      json.dumps({"schema_version": "1.0", "scenarios": [scenario]}),
      encoding="utf-8",
  )

  loaded = load_scenario_bundle(
      bundle,
      {"SCENESCAPE_ENABLE_BLUETOOTH_SIMULATOR": "1", "SCENESCAPE_ENV": "test"},
  )
  assert len(loaded) == 1
  assert loaded[0].seed == 4242

  bundle.write_text(
      json.dumps({"schema_version": "2.0", "scenarios": [scenario]}),
      encoding="utf-8",
  )
  with pytest.raises(ValueError, match="unsupported"):
    load_scenario_bundle(
        bundle,
        {"SCENESCAPE_ENABLE_BLUETOOTH_SIMULATOR": "1", "SCENESCAPE_ENV": "test"},
    )
