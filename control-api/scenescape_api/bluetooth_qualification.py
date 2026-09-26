# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Ground-truth alignment and Bluetooth accuracy qualification (BT-13)."""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

import numpy as np


def _utc(value: datetime | str) -> datetime:
  if isinstance(value, str):
    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
  if value.tzinfo is None:
    return value.replace(tzinfo=timezone.utc)
  return value.astimezone(timezone.utc)


def _position(value: Mapping[str, Any]) -> tuple[float, float, float] | None:
  source = value.get("position")
  if not isinstance(source, Mapping):
    return None
  try:
    point = (
        float(source["x_m"]),
        float(source["y_m"]),
        float(source["z_m"]),
    )
  except (KeyError, TypeError, ValueError):
    return None
  return point if all(math.isfinite(component) for component in point) else None


def _percentiles(values: list[float]) -> dict[str, float | None]:
  if not values:
    return {"p50": None, "p90": None, "p95": None, "p99": None, "mean": None, "max": None}
  data = np.asarray(values, dtype=float)
  return {
      "p50": float(np.percentile(data, 50)),
      "p90": float(np.percentile(data, 90)),
      "p95": float(np.percentile(data, 95)),
      "p99": float(np.percentile(data, 99)),
      "mean": float(np.mean(data)),
      "max": float(np.max(data)),
  }


@dataclass(frozen=True)
class QualificationConfig:
  alignment_tolerance_ms: float = 100.0
  accepted_states: tuple[str, ...] = ("good", "degraded")
  latency_source_field: str = "ingested_at"

  def __post_init__(self):
    if self.alignment_tolerance_ms <= 0:
      raise ValueError("alignment_tolerance_ms must be >0")


def align_truth_and_positions(
    truth: Iterable[Mapping[str, Any]],
    positions: Iterable[Mapping[str, Any]],
    config: QualificationConfig | None = None,
) -> list[dict[str, Any]]:
  config = config or QualificationConfig()
  truth_rows = sorted(
      [dict(row) for row in truth],
      key=lambda row: _utc(row["source_timestamp"]),
  )
  position_rows = sorted(
      [dict(row) for row in positions],
      key=lambda row: _utc(row["source_timestamp"]),
  )
  by_tag: dict[str, list[dict[str, Any]]] = {}
  for row in position_rows:
    by_tag.setdefault(str(row.get("tag_id") or ""), []).append(row)

  tolerance_s = config.alignment_tolerance_ms / 1000.0
  aligned: list[dict[str, Any]] = []
  for truth_row in truth_rows:
    tag_id = str(truth_row.get("tag_id") or "")
    truth_time = _utc(truth_row["source_timestamp"])
    candidates = by_tag.get(tag_id, [])
    nearest = None
    nearest_delta = math.inf
    for position_row in candidates:
      delta = abs((_utc(position_row["source_timestamp"]) - truth_time).total_seconds())
      if delta < nearest_delta:
        nearest = position_row
        nearest_delta = delta
      if _utc(position_row["source_timestamp"]) > truth_time and delta > nearest_delta:
        break
    aligned.append({
        "tag_id": tag_id,
        "truth": truth_row,
        "position": nearest if nearest_delta <= tolerance_s else None,
        "alignment_error_ms": (
            nearest_delta * 1000.0 if nearest is not None and nearest_delta <= tolerance_s else None
        ),
    })
  return aligned


def qualification_report(
    truth: Iterable[Mapping[str, Any]],
    positions: Iterable[Mapping[str, Any]],
    *,
    config: QualificationConfig | None = None,
    environment: Mapping[str, Any] | None = None,
    system: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
  config = config or QualificationConfig()
  truth_rows = [dict(row) for row in truth]
  position_rows = [dict(row) for row in positions]
  aligned = align_truth_and_positions(truth_rows, position_rows, config)

  horizontal_errors: list[float] = []
  vertical_errors: list[float] = []
  three_d_errors: list[float] = []
  latencies_ms: list[float] = []
  accepted = 0
  aligned_count = 0
  state_counts: dict[str, int] = {}
  rows_out: list[dict[str, Any]] = []

  for item in aligned:
    truth_row = item["truth"]
    position_row = item["position"]
    truth_position = _position(truth_row)
    state = "missing"
    horizontal = vertical = error_3d = None
    latency_ms = None
    if position_row is not None:
      aligned_count += 1
      quality = position_row.get("quality")
      if isinstance(quality, Mapping):
        state = str(quality.get("state") or position_row.get("state") or "unknown")
      else:
        state = str(position_row.get("state") or "unknown")
      state_counts[state] = state_counts.get(state, 0) + 1
      measured = _position(position_row)
      if truth_position is not None and measured is not None and state in config.accepted_states:
        accepted += 1
        dx = measured[0] - truth_position[0]
        dy = measured[1] - truth_position[1]
        dz = measured[2] - truth_position[2]
        horizontal = math.hypot(dx, dy)
        vertical = abs(dz)
        error_3d = math.sqrt(dx * dx + dy * dy + dz * dz)
        horizontal_errors.append(horizontal)
        vertical_errors.append(vertical)
        three_d_errors.append(error_3d)

      latency_raw = position_row.get(config.latency_source_field)
      if latency_raw is not None:
        try:
          latency = (
              _utc(latency_raw) - _utc(position_row["source_timestamp"])
          ).total_seconds() * 1000.0
        except (TypeError, ValueError):
          latency = math.nan
        if math.isfinite(latency) and latency >= 0:
          latency_ms = latency
          latencies_ms.append(latency)

    rows_out.append({
        "tag_id": item["tag_id"],
        "truth_timestamp": _utc(truth_row["source_timestamp"]).isoformat(),
        "position_timestamp": (
            _utc(position_row["source_timestamp"]).isoformat()
            if position_row is not None
            else None
        ),
        "alignment_error_ms": item["alignment_error_ms"],
        "state": state,
        "horizontal_error_m": horizontal,
        "vertical_error_m": vertical,
        "error_3d_m": error_3d,
        "latency_ms": latency_ms,
    })

  times = sorted(
      _utc(row["source_timestamp"])
      for row in position_rows
      if row.get("source_timestamp") is not None
  )
  intervals = [
      (right - left).total_seconds()
      for left, right in zip(times, times[1:])
      if (right - left).total_seconds() > 0
  ]
  update_hz = (
      1.0 / float(np.median(np.asarray(intervals, dtype=float)))
      if intervals
      else None
  )

  total_truth = len(truth_rows)
  return {
      "schema_version": "1.0",
      "configuration": {
          "alignment_tolerance_ms": config.alignment_tolerance_ms,
          "accepted_states": list(config.accepted_states),
          "latency_source_field": config.latency_source_field,
      },
      "environment": dict(environment or {}),
      "system": dict(system or {}),
      "samples": {
          "truth": total_truth,
          "positions": len(position_rows),
          "aligned": aligned_count,
          "accepted_fixes": accepted,
      },
      "availability": {
          "aligned_fraction": (aligned_count / total_truth) if total_truth else 0.0,
          "accepted_fix_fraction": (accepted / total_truth) if total_truth else 0.0,
          "state_counts": state_counts,
      },
      "accuracy_when_accepted": {
          "horizontal_m": _percentiles(horizontal_errors),
          "vertical_m": _percentiles(vertical_errors),
          "three_d_m": _percentiles(three_d_errors),
      },
      "latency_ms": _percentiles(latencies_ms),
      "update_rate_hz": update_hz,
      "rows": rows_out,
  }


def compare_raw_and_tracked(
    truth: Iterable[Mapping[str, Any]],
    raw_positions: Iterable[Mapping[str, Any]],
    tracked_positions: Iterable[Mapping[str, Any]],
    *,
    config: QualificationConfig | None = None,
    environment: Mapping[str, Any] | None = None,
    system: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
  truth_rows = [dict(row) for row in truth]
  raw_rows = [dict(row) for row in raw_positions]
  tracked_rows = [dict(row) for row in tracked_positions]
  return {
      "raw": qualification_report(
          truth_rows,
          raw_rows,
          config=config,
          environment=environment,
          system={**dict(system or {}), "stage": "raw"},
      ),
      "tracked": qualification_report(
          truth_rows,
          tracked_rows,
          config=config,
          environment=environment,
          system={**dict(system or {}), "stage": "tracked"},
      ),
  }


def qualification_csv(report: Mapping[str, Any]) -> str:
  output = io.StringIO()
  fields = [
      "tag_id",
      "truth_timestamp",
      "position_timestamp",
      "alignment_error_ms",
      "state",
      "horizontal_error_m",
      "vertical_error_m",
      "error_3d_m",
      "latency_ms",
  ]
  writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
  writer.writeheader()
  for row in report.get("rows") or []:
    writer.writerow(dict(row))
  return output.getvalue()


def scenario_matrix_summary(
    reports: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
  rows = []
  for name, report in sorted(reports.items()):
    horizontal = (
        report.get("accuracy_when_accepted", {})
        .get("horizontal_m", {})
    )
    availability = report.get("availability", {})
    rows.append({
        "scenario": name,
        "truth_samples": report.get("samples", {}).get("truth", 0),
        "accepted_fix_fraction": availability.get("accepted_fix_fraction", 0.0),
        "horizontal_p50_m": horizontal.get("p50"),
        "horizontal_p90_m": horizontal.get("p90"),
        "horizontal_p95_m": horizontal.get("p95"),
        "horizontal_p99_m": horizontal.get("p99"),
        "latency_p95_ms": report.get("latency_ms", {}).get("p95"),
        "update_rate_hz": report.get("update_rate_hz"),
    })
  return rows
