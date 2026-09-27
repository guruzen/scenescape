# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Deterministic Bluetooth solver load benchmark for BT-16.

This is a software processing benchmark, not a Bluetooth radio/provider
capacity or accuracy claim. It deliberately uses synthetic truth-known range
observations to measure the solver path independently of hardware.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from .bluetooth_positioning import SolverConfig, solve_ranges


def _anchors(count: int) -> list[tuple[float, float, float]]:
  if count < 4:
    raise ValueError("benchmark requires at least four anchors")
  perimeter = [
      (0.0, 0.0, 3.0),
      (20.0, 0.0, 3.0),
      (20.0, 12.0, 3.0),
      (0.0, 12.0, 3.0),
      (10.0, 0.0, 3.0),
      (20.0, 6.0, 3.0),
      (10.0, 12.0, 3.0),
      (0.0, 6.0, 3.0),
  ]
  if count <= len(perimeter):
    return perimeter[:count]
  values = list(perimeter)
  rng = random.Random(1616)
  while len(values) < count:
    values.append((20.0 * rng.random(), 12.0 * rng.random(), 3.0))
  return values


def _calibrations(anchors: list[tuple[float, float, float]]) -> list[dict[str, Any]]:
  return [
      {
          "anchor_id": f"a{index}",
          "state": "active",
          "x_m": point[0],
          "y_m": point[1],
          "z_m": point[2],
      }
      for index, point in enumerate(anchors, start=1)
  ]


def _percentile(values: list[float], percentile: float) -> float | None:
  if not values:
    return None
  return float(np.percentile(np.asarray(values, dtype=float), percentile))


def run_benchmark(
    *,
    tags: int = 20,
    anchors: int = 4,
    update_hz: float = 5.0,
    duration_s: float = 5.0,
    seed: int = 1616,
    noise_stddev_m: float = 0.05,
) -> dict[str, Any]:
  if tags < 1:
    raise ValueError("tags must be >= 1")
  if not math.isfinite(update_hz) or update_hz <= 0:
    raise ValueError("update_hz must be positive")
  if not math.isfinite(duration_s) or duration_s <= 0:
    raise ValueError("duration_s must be positive")
  if noise_stddev_m < 0 or not math.isfinite(noise_stddev_m):
    raise ValueError("noise_stddev_m must be finite and >= 0")

  points = _anchors(anchors)
  calibrations = _calibrations(points)
  rng = random.Random(seed)
  steps = max(1, int(round(update_hz * duration_s)))
  period_s = 1.0 / update_hz
  origin = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)

  latencies_ms: list[float] = []
  horizontal_errors_m: list[float] = []
  unavailable = 0
  invalid_numeric = 0
  solves = 0
  observations = 0
  started = time.perf_counter()

  for step in range(steps):
    stamp = origin + timedelta(seconds=step * period_s)
    phase = step / max(steps - 1, 1)
    for tag_index in range(tags):
      tag_phase = (tag_index + 1) / (tags + 1)
      truth = (
          1.0 + 18.0 * ((phase + tag_phase * 0.37) % 1.0),
          1.0 + 10.0 * ((phase * 0.61 + tag_phase) % 1.0),
          1.0,
      )
      measurements: list[dict[str, Any]] = []
      for anchor_index, anchor in enumerate(points, start=1):
        measurements.append({
            "anchor_id": f"a{anchor_index}",
            "tag_id": f"tag-{tag_index}",
            "scene_id": "benchmark-scene",
            "source_timestamp": stamp,
            "method": "channel_sounding",
            "distance_m": max(
                0.0,
                math.dist(anchor, truth) + rng.gauss(0.0, noise_stddev_m),
            ),
            "distance_stddev_m": max(noise_stddev_m, 0.01),
            "quality": 0.98,
            "nlos_probability": 0.02,
            "sequence": step * tags * anchors + tag_index * anchors + anchor_index,
        })
      observations += len(measurements)
      solve_started = time.perf_counter()
      result = solve_ranges(
          measurements,
          calibrations,
          SolverConfig(fixed_z_m=truth[2]),
      )
      latencies_ms.append((time.perf_counter() - solve_started) * 1000.0)
      solves += 1
      position = result.get("position")
      if not isinstance(position, dict):
        unavailable += 1
        continue
      try:
        solved = (
            float(position["x_m"]),
            float(position["y_m"]),
            float(position["z_m"]),
        )
      except (KeyError, TypeError, ValueError):
        invalid_numeric += 1
        continue
      if not all(math.isfinite(value) for value in solved):
        invalid_numeric += 1
        continue
      horizontal_errors_m.append(math.hypot(solved[0] - truth[0], solved[1] - truth[1]))

  elapsed_s = time.perf_counter() - started
  valid = solves - unavailable - invalid_numeric
  report = {
      "schema_version": "1.0",
      "benchmark": "synthetic-solver-core",
      "scope": (
          "Software solver processing only; excludes Bluetooth radio/provider "
          "capacity, MQTT/database I/O and real-site accuracy."
      ),
      "workload": {
          "tags": tags,
          "anchors": anchors,
          "update_hz_per_tag": update_hz,
          "duration_s": duration_s,
          "fixes": solves,
          "range_observations": observations,
          "offered_fix_rate_hz": tags * update_hz,
          "offered_range_rate_hz": tags * update_hz * anchors,
          "noise_stddev_m": noise_stddev_m,
          "seed": seed,
      },
      "runtime": {
          "elapsed_s": elapsed_s,
          "fix_throughput_hz": solves / elapsed_s if elapsed_s else None,
          "range_throughput_hz": observations / elapsed_s if elapsed_s else None,
          "solve_latency_ms": {
              "p50": _percentile(latencies_ms, 50),
              "p95": _percentile(latencies_ms, 95),
              "p99": _percentile(latencies_ms, 99),
              "max": max(latencies_ms) if latencies_ms else None,
          },
      },
      "quality": {
          "available_fraction": valid / solves if solves else 0.0,
          "unavailable": unavailable,
          "invalid_numeric": invalid_numeric,
          "horizontal_error_m": {
              "p50": _percentile(horizontal_errors_m, 50),
              "p95": _percentile(horizontal_errors_m, 95),
              "p99": _percentile(horizontal_errors_m, 99),
          },
      },
  }
  return report


def _threshold_failures(
    report: dict[str, Any],
    *,
    min_fix_throughput_hz: float,
    max_solve_p95_ms: float,
    min_available_fraction: float,
) -> list[str]:
  failures: list[str] = []
  throughput = float(report["runtime"]["fix_throughput_hz"] or 0.0)
  p95 = float(report["runtime"]["solve_latency_ms"]["p95"] or math.inf)
  available = float(report["quality"]["available_fraction"])
  if min_fix_throughput_hz > 0 and throughput < min_fix_throughput_hz:
    failures.append(
        f"fix throughput {throughput:.2f}/s < required {min_fix_throughput_hz:.2f}/s"
    )
  if max_solve_p95_ms > 0 and p95 > max_solve_p95_ms:
    failures.append(
        f"solve p95 {p95:.2f} ms > required {max_solve_p95_ms:.2f} ms"
    )
  if available < min_available_fraction:
    failures.append(
        f"availability {available:.4f} < required {min_available_fraction:.4f}"
    )
  return failures


def main() -> None:
  parser = argparse.ArgumentParser()
  parser.add_argument("--tags", type=int, default=20)
  parser.add_argument("--anchors", type=int, default=4)
  parser.add_argument("--hz", type=float, default=5.0)
  parser.add_argument("--duration", type=float, default=5.0)
  parser.add_argument("--seed", type=int, default=1616)
  parser.add_argument("--noise-stddev-m", type=float, default=0.05)
  parser.add_argument("--min-fix-throughput-hz", type=float, default=0.0)
  parser.add_argument("--max-solve-p95-ms", type=float, default=0.0)
  parser.add_argument("--min-available-fraction", type=float, default=1.0)
  args = parser.parse_args()

  report = run_benchmark(
      tags=args.tags,
      anchors=args.anchors,
      update_hz=args.hz,
      duration_s=args.duration,
      seed=args.seed,
      noise_stddev_m=args.noise_stddev_m,
  )
  print(json.dumps(report, indent=2, sort_keys=True))
  failures = _threshold_failures(
      report,
      min_fix_throughput_hz=args.min_fix_throughput_hz,
      max_solve_p95_ms=args.max_solve_p95_ms,
      min_available_fraction=args.min_available_fraction,
  )
  if failures:
    raise SystemExit("BT-16 benchmark failed: " + "; ".join(failures))


if __name__ == "__main__":
  main()
