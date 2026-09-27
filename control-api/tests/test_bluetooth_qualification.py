# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math
from datetime import datetime, timedelta, timezone

import pytest

from scenescape_api.bluetooth_qualification import (
    QualificationConfig,
    compare_raw_and_tracked,
    qualification_csv,
    qualification_report,
    scenario_matrix_summary,
)


BASE = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)


def _truth(count=100, dt=0.1):
  return [
      {
          "tag_id": "tag-a",
          "source_timestamp": BASE + timedelta(seconds=index * dt),
          "position": {
              "x_m": index * dt,
              "y_m": 2.0 + math.sin(index * dt) * 0.2,
              "z_m": 1.0,
          },
      }
      for index in range(count)
  ]


def _positions(truth, *, error_x=0.05, drop_every=None, state="good", latency_ms=25):
  rows = []
  for index, item in enumerate(truth):
    if drop_every and index % drop_every == 0:
      continue
    timestamp = item["source_timestamp"]
    truth_position = item["position"]
    rows.append({
        "tag_id": item["tag_id"],
        "source_timestamp": timestamp,
        "ingested_at": timestamp + timedelta(milliseconds=latency_ms),
        "position": {
            "x_m": truth_position["x_m"] + error_x,
            "y_m": truth_position["y_m"],
            "z_m": truth_position["z_m"],
        },
        "quality": {"state": state},
    })
  return rows


def test_bt13_static_or_dynamic_percentiles_are_deterministic():
  truth = _truth()
  positions = _positions(truth, error_x=0.08)
  first = qualification_report(truth, positions)
  second = qualification_report(truth, positions)

  assert first == second
  horizontal = first["accuracy_when_accepted"]["horizontal_m"]
  assert horizontal["p50"] == pytest.approx(0.08, abs=1e-9)
  assert horizontal["p95"] == pytest.approx(0.08, abs=1e-9)
  assert first["availability"]["accepted_fix_fraction"] == 1.0
  assert first["update_rate_hz"] == pytest.approx(10.0, rel=1e-6)
  assert first["latency_ms"]["p95"] == pytest.approx(25.0, abs=1e-6)


def test_bt13_accuracy_when_good_is_separate_from_availability():
  truth = _truth(count=20)
  positions = _positions(truth, error_x=0.02, drop_every=2)
  report = qualification_report(truth, positions)

  assert report["availability"]["accepted_fix_fraction"] == pytest.approx(0.5)
  assert report["accuracy_when_accepted"]["horizontal_m"]["p95"] == pytest.approx(0.02)


def test_bt13_degraded_can_be_included_or_excluded_by_documented_config():
  truth = _truth(count=10)
  positions = _positions(truth, error_x=0.03, state="degraded")

  default = qualification_report(truth, positions)
  strict = qualification_report(
      truth,
      positions,
      config=QualificationConfig(accepted_states=("good",)),
  )
  assert default["availability"]["accepted_fix_fraction"] == 1.0
  assert strict["availability"]["accepted_fix_fraction"] == 0.0
  assert strict["accuracy_when_accepted"]["horizontal_m"]["p95"] is None


def test_bt13_alignment_tolerance_prevents_cherry_picking_far_samples():
  truth = _truth(count=5, dt=1.0)
  positions = []
  for item in truth:
    timestamp = item["source_timestamp"] + timedelta(milliseconds=300)
    positions.append({
        "tag_id": "tag-a",
        "source_timestamp": timestamp,
        "position": item["position"],
        "quality": {"state": "good"},
    })
  report = qualification_report(
      truth,
      positions,
      config=QualificationConfig(alignment_tolerance_ms=100),
  )
  assert report["samples"]["aligned"] == 0
  assert report["availability"]["accepted_fix_fraction"] == 0.0


def test_bt13_raw_vs_tracked_comparison_keeps_both_reports_traceable():
  truth = _truth(count=50)
  raw = _positions(truth, error_x=0.25)
  tracked = _positions(truth, error_x=0.08)
  result = compare_raw_and_tracked(
      truth,
      raw,
      tracked,
      environment={"site": "simulator", "condition": "los"},
      system={"commit": "abc123", "hardware": "simulated"},
  )

  assert result["raw"]["accuracy_when_accepted"]["horizontal_m"]["p95"] > result["tracked"]["accuracy_when_accepted"]["horizontal_m"]["p95"]
  assert result["raw"]["system"]["stage"] == "raw"
  assert result["tracked"]["system"]["stage"] == "tracked"
  assert result["tracked"]["environment"]["condition"] == "los"


def test_bt13_csv_contains_aligned_artifacts_without_identifying_person():
  truth = _truth(count=3)
  report = qualification_report(truth, _positions(truth))
  value = qualification_csv(report)

  assert "tag_id,truth_timestamp" in value
  assert "tag-a" in value
  assert "horizontal_error_m" in value
  assert "display_name" not in value


def test_bt13_scenario_matrix_keeps_poor_conditions_visible():
  truth = _truth(count=20)
  reports = {
      "los": qualification_report(truth, _positions(truth, error_x=0.04)),
      "nlos": qualification_report(
          truth,
          _positions(truth, error_x=0.40, drop_every=4),
          environment={"condition": "nlos"},
      ),
  }
  matrix = scenario_matrix_summary(reports)
  assert [row["scenario"] for row in matrix] == ["los", "nlos"]
  los = matrix[0]
  nlos = matrix[1]
  assert nlos["horizontal_p95_m"] > los["horizontal_p95_m"]
  assert nlos["accepted_fix_fraction"] < los["accepted_fix_fraction"]
