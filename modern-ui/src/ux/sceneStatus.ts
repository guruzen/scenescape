export type SceneOperationalState = "LIVE" | "DEGRADED" | "STALE/OFFLINE"

export type SceneStatusInput = {
  stale?: boolean
  observedAt?: string | null
  sceneRate?: unknown
  objectCount?: number
  cameraCount?: number
  cameraRates?: Record<string, unknown> | null
  mqttState?: string | null
  nowMs?: number
}

export type SceneStatusModel = {
  state: SceneOperationalState
  objectCount: number
  sceneRate: number | null
  cameraHealthy: number | null
  cameraTotal: number
  mqtt: string
  ageSeconds: number | null
}

const finiteNumber = (value: unknown): number | null => {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function deriveSceneStatus(input: SceneStatusInput): SceneStatusModel {
  const cameraTotal = Math.max(0, Number(input.cameraCount || 0))
  const cameraRates = input.cameraRates && typeof input.cameraRates === "object" ? input.cameraRates : null
  const rateValues = cameraRates ? Object.values(cameraRates).map(finiteNumber).filter((value): value is number => value !== null) : []
  const cameraHealthy = cameraRates ? rateValues.filter((value) => value > 0).length : null
  const mqtt = String(input.mqttState || "Unknown")
  const normalizedMqtt = mqtt.toLowerCase()
  const explicitMqttFailure = !["unknown", "connected"].includes(normalizedMqtt)
  const partialCameraHealth = cameraHealthy !== null && cameraTotal > 0 && cameraHealthy < cameraTotal

  let ageSeconds: number | null = null
  if (input.observedAt) {
    const observed = new Date(input.observedAt).getTime()
    if (Number.isFinite(observed)) {
      ageSeconds = Math.max(0, ((input.nowMs ?? Date.now()) - observed) / 1000)
    }
  }

  const state: SceneOperationalState = input.stale
    ? "STALE/OFFLINE"
    : explicitMqttFailure || partialCameraHealth
      ? "DEGRADED"
      : "LIVE"

  return {
    state,
    objectCount: Math.max(0, Number(input.objectCount || 0)),
    sceneRate: finiteNumber(input.sceneRate),
    cameraHealthy,
    cameraTotal,
    mqtt,
    ageSeconds,
  }
}
