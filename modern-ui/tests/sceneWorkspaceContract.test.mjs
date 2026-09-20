import assert from "node:assert/strict"
import test from "node:test"

import { deriveSceneStatus } from "../src/ux/sceneStatus.ts"

import {
  DEFAULT_SCENE_DESTINATION,
  DEFAULT_VIEW_BY_MODE,
  LEGACY_SCENE_TABS,
  PRIMARY_MODES,
  ROUTE_BY_DESTINATION_KEY,
  SCENE_DESTINATION_BY_LEGACY_TAB,
  SCENE_WORKSPACE_CAPABILITIES,
  SECONDARY_VIEWS_BY_MODE,
  defaultDestinationForMode,
  destinationForLegacyTab,
  destinationKey,
  initialLegacyTabForSceneSuffix,
  legacyTabForDestination,
  routeForDestination,
} from "../src/ux/sceneWorkspaceContract.ts"

test("unit: every legacy tab resolves to an explicit UX 2.0 destination", () => {
  for (const tab of LEGACY_SCENE_TABS) {
    const destination = destinationForLegacyTab(tab)
    assert.ok(destination, `missing destination for ${tab}`)
    assert.ok(PRIMARY_MODES.includes(destination.mode))
    assert.ok(destination.view.length > 0)
    assert.equal(legacyTabForDestination(destination), tab)
  }
  assert.equal(destinationForLegacyTab("not-a-scene-tab"), null)
  assert.equal(legacyTabForDestination({ mode: "Configure", view: "Scene" }), null)
})

test("unit: primary-mode changes choose stable workspace defaults", () => {
  assert.deepEqual(defaultDestinationForMode("Monitor"), { mode: "Monitor", view: "2D Scene" })
  assert.deepEqual(defaultDestinationForMode("Analyze"), { mode: "Analyze", view: "History" })
  assert.deepEqual(defaultDestinationForMode("Configure"), { mode: "Configure", view: "Geometry" })
  for (const mode of PRIMARY_MODES) {
    assert.ok(SECONDARY_VIEWS_BY_MODE[mode].includes(DEFAULT_VIEW_BY_MODE[mode]))
  }
})

test("unit: direct scene route suffixes preserve legacy entry behavior", () => {
  assert.equal(initialLegacyTabForSceneSuffix("geometry"), "Geometry")
  assert.equal(initialLegacyTabForSceneSuffix("hierarchy"), "Hierarchy")
  assert.equal(initialLegacyTabForSceneSuffix(undefined), "Live 2D")
  assert.equal(initialLegacyTabForSceneSuffix("unknown"), "Live 2D")
})

test("integrity: destination mapping is one-to-one and complete", () => {
  assert.equal(Object.keys(SCENE_DESTINATION_BY_LEGACY_TAB).length, LEGACY_SCENE_TABS.length)
  const keys = LEGACY_SCENE_TABS.map((tab) => destinationKey(SCENE_DESTINATION_BY_LEGACY_TAB[tab]))
  assert.equal(new Set(keys).size, keys.length, "two legacy destinations collapse into one UX destination")
  assert.deepEqual(new Set(PRIMARY_MODES), new Set(["Monitor", "Analyze", "Configure"]))
  for (const mode of PRIMARY_MODES) assert.ok(SECONDARY_VIEWS_BY_MODE[mode].length > 0)
})

test("integrity: route-out destinations are explicit and configuration-only", () => {
  assert.deepEqual(ROUTE_BY_DESTINATION_KEY, {
    "Configure:Scene": "scenes",
    "Configure:Cameras": "cameras",
    "Configure:Sensors": "sensors",
  })
  assert.equal(routeForDestination({ mode: "Monitor", view: "Cameras" }), null)
  assert.equal(routeForDestination({ mode: "Configure", view: "Cameras" }), "cameras")
})

test("regression: the pre-overhaul scene workspace capability baseline is locked", () => {
  const required = [
    "live-2d",
    "live-3d",
    "camera-feeds",
    "sensor-telemetry",
    "geometry-editor",
    "hierarchy-editor",
    "camera-calibration",
    "runtime-status",
    "history-replay",
    "trends-analytics",
    "trails",
    "telemetry",
    "heatmap",
    "velocity",
    "roi-visualization",
    "fullscreen",
  ]
  assert.deepEqual([...SCENE_WORKSPACE_CAPABILITIES].sort(), required.sort())
  assert.deepEqual(DEFAULT_SCENE_DESTINATION, { mode: "Monitor", view: "2D Scene" })
})


test("unit: scene status distinguishes live degraded stale and unknown health", () => {
  const live = deriveSceneStatus({
    stale: false, observedAt: "2026-09-20T03:00:00Z", nowMs: Date.parse("2026-09-20T03:00:02Z"),
    sceneRate: 29.8, objectCount: 85, cameraCount: 2, cameraRates: { cam1: 30, cam2: 29.7 }, mqttState: "connected",
  })
  assert.equal(live.state, "LIVE")
  assert.equal(live.cameraHealthy, 2)
  assert.equal(live.ageSeconds, 2)

  const degradedMqtt = deriveSceneStatus({ stale: false, cameraCount: 0, mqttState: "disconnected" })
  assert.equal(degradedMqtt.state, "DEGRADED")

  const degradedCamera = deriveSceneStatus({ stale: false, cameraCount: 2, cameraRates: { cam1: 30 }, mqttState: "connected" })
  assert.equal(degradedCamera.state, "DEGRADED")
  assert.equal(degradedCamera.cameraHealthy, 1)

  const stale = deriveSceneStatus({ stale: true, cameraCount: 2, mqttState: "connected" })
  assert.equal(stale.state, "STALE/OFFLINE")

  const unknown = deriveSceneStatus({ stale: false, cameraCount: 2, cameraRates: null, mqttState: null })
  assert.equal(unknown.state, "LIVE")
  assert.equal(unknown.cameraHealthy, null)
  assert.equal(unknown.mqtt, "Unknown")
})
