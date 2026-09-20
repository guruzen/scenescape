/* SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

export const HEATMAP_RANGES = ["Current"] as const

export function heatmapOpacityValue(value: unknown): number {
  const number = Number(value)
  if (!Number.isFinite(number)) return 0.65
  return Math.min(1, Math.max(0.1, number))
}

export function velocityArrow2D(velocity: unknown, scale: number) {
  if (!Array.isArray(velocity) || velocity.length < 2) return null
  const vx = Number(velocity[0])
  const vy = Number(velocity[1])
  if (!Number.isFinite(vx) || !Number.isFinite(vy)) return null
  const magnitude = Math.hypot(vx, vy)
  if (magnitude <= 0.001) return null
  const safeScale = Math.max(1, Number.isFinite(scale) ? scale : 1)
  const lengthPixels = Math.min(2.5, Math.max(0.4, magnitude)) * safeScale
  return {
    magnitude,
    lengthPixels,
    dx: (vx / magnitude) * lengthPixels,
    dy: -(vy / magnitude) * lengthPixels,
  }
}

export function velocityLength3D(magnitude: unknown): number {
  const value = Number(magnitude)
  if (!Number.isFinite(value) || value <= 0.01) return 0
  return Math.min(4, Math.max(0.5, value))
}
