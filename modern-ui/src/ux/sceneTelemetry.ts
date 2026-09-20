/* SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

export type SceneTelemetryModel = {
  sceneRate: number | null
  objectCount: number
  cameraRates: Array<{ camera: string; fps: number }>
  freshness: "Receiving" | "Stale" | "Unknown"
  ageSeconds: number | null
}

const finite = (value: unknown): number | null => {
  if (value === null || value === undefined || value === "") return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function emptyLiveSceneState(): Record<string, any> {
  return { objects: [], stale: true }
}

export function deriveSceneTelemetry(live: Record<string, any>, nowMs = Date.now()): SceneTelemetryModel {
  const rates = live.rate && typeof live.rate === "object" ? live.rate : null
  const cameraRates = rates
    ? Object.entries(rates).flatMap(([camera, value]) => {
        const fps = finite(value)
        return fps === null ? [] : [{ camera, fps }]
      }).sort((a, b) => a.camera.localeCompare(b.camera))
    : []

  let ageSeconds: number | null = null
  if (live.observed_at) {
    const observed = new Date(String(live.observed_at)).getTime()
    if (Number.isFinite(observed)) ageSeconds = Math.max(0, (nowMs - observed) / 1000)
  }

  return {
    sceneRate: finite(live.scene_rate),
    objectCount: Array.isArray(live.objects) ? live.objects.length : 0,
    cameraRates,
    freshness: live.stale === true ? "Stale" : live.stale === false ? "Receiving" : "Unknown",
    ageSeconds,
  }
}
