/* SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import assert from "node:assert/strict"
import test from "node:test"

import { deriveSceneStatus } from "../src/ux/sceneStatus.ts"
import { deriveSceneTelemetry, emptyLiveSceneState } from "../src/ux/sceneTelemetry.ts"
import { controlsForRenderer, summarizeLiveObjectAvailability } from "../src/ux/sceneViewControls.ts"
import { buildInspectorModel, refreshObjectSelection } from "../src/ux/sceneInspector.ts"

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


test("unit: renderer controls are contextual", () => {
  const controls2d = controlsForRenderer("2d")
  assert.ok(controls2d.includes("labels"))
  assert.ok(!controls2d.includes("floor"))
  assert.ok(!controls2d.includes("camera-frames"))

  const controls3d = controlsForRenderer("3d")
  assert.ok(!controls3d.includes("labels"))
  assert.ok(controls3d.includes("floor"))
  assert.ok(controls3d.includes("camera-frames"))
  assert.ok(controls3d.includes("lighting"))
  for (const common of ["objects", "trails", "heatmap", "velocity", "spatial", "telemetry"]) {
    assert.ok(controls2d.includes(common))
    assert.ok(controls3d.includes(common))
  }
})

test("unit: data-dependent layer availability reports velocity coverage", () => {
  const availability = summarizeLiveObjectAvailability([
    { id: 1, velocity: [1, 0] },
    { id: 2, velocity: ["0.5", "0.2"] },
    { id: 3 },
    { id: 4, velocity: ["bad", 1] },
  ])
  assert.deepEqual(availability, {
    total: 4, velocityVectors: 2, trailsAvailable: true, heatmapAvailable: true, velocityAvailable: true,
  })
  assert.deepEqual(summarizeLiveObjectAvailability([]), {
    total: 0, velocityVectors: 0, trailsAvailable: false, heatmapAvailable: false, velocityAvailable: false,
  })
})


test("unit: object inspector derives current speed dwell visibility and persistent data", () => {
  const selection = { kind: "object", id: "42", value: { id: 42, category: "person", translation: [1, 2, 0], velocity: [3, 4], regions: { checkout: { dwell: 12.5 } }, visibility: ["cam-a"], persistent_data: { badge: "A7" } } }
  const model = buildInspectorModel(selection)
  assert.equal(model.title, "Object 42")
  assert.equal(model.fields.find((field) => field.label === "Speed").value, "5.00 m/s")
  assert.equal(model.fields.find((field) => field.label === "Dwell").value, "12.5 s")
  assert.equal(model.fields.find((field) => field.label === "Visible cameras").value, "cam-a")
  assert.match(model.persistentData, /A7/)
})

test("unit: inspector preserves Unknown for unavailable optional data", () => {
  const camera = buildInspectorModel({ kind: "camera", id: "cam-1", value: { name: "Camera 1" } })
  assert.equal(camera.fields.find((field) => field.label === "FPS").value, "Unknown")
  assert.equal(camera.fields.find((field) => field.label === "Feed").value, "Unknown")
  const sensor = buildInspectorModel({ kind: "sensor", id: "s1", value: { name: "Temp" } })
  assert.equal(sensor.fields.find((field) => field.label === "Latest value").value, "Unknown")
})

test("regression: selected tracked object refreshes from the latest live observation", () => {
  const previous = { kind: "object", id: "7", value: { id: 7, translation: [1, 1] } }
  const refreshed = refreshObjectSelection(previous, [{ id: 7, translation: [2, 3] }])
  assert.deepEqual(refreshed.value.translation, [2, 3])
  const retained = refreshObjectSelection(previous, [])
  assert.deepEqual(retained.value.translation, [1, 1])
})


test("unit: scene telemetry preserves unknown rates and computes freshness", () => {
  const telemetry = deriveSceneTelemetry({
    scene_rate: 29.95,
    objects: [{}, {}],
    stale: false,
    observed_at: "2026-09-20T03:00:00Z",
    rate: { camB: 29.5, camA: "30" },
  }, Date.parse("2026-09-20T03:00:01.500Z"))
  assert.equal(telemetry.sceneRate, 29.95)
  assert.equal(telemetry.objectCount, 2)
  assert.equal(telemetry.freshness, "Receiving")
  assert.equal(telemetry.ageSeconds, 1.5)
  assert.deepEqual(telemetry.cameraRates, [
    { camera: "camA", fps: 30 },
    { camera: "camB", fps: 29.5 },
  ])

  const unknown = deriveSceneTelemetry({ objects: [], stale: true })
  assert.equal(unknown.sceneRate, null)
  assert.equal(unknown.freshness, "Stale")
  assert.deepEqual(unknown.cameraRates, [])
})

test("regression: scene changes reset live telemetry instead of retaining the prior scene", () => {
  assert.deepEqual(emptyLiveSceneState(), { objects: [], stale: true })
  assert.notEqual(emptyLiveSceneState(), emptyLiveSceneState())
})
