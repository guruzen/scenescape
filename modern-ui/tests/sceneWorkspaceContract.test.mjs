import assert from "node:assert/strict"
import test from "node:test"

import {
  DEFAULT_SCENE_DESTINATION,
  LEGACY_SCENE_TABS,
  PRIMARY_MODES,
  SCENE_DESTINATION_BY_LEGACY_TAB,
  SCENE_WORKSPACE_CAPABILITIES,
  destinationForLegacyTab,
  destinationKey,
} from "../src/ux/sceneWorkspaceContract.ts"

test("unit: every legacy tab resolves to an explicit UX 2.0 destination", () => {
  for (const tab of LEGACY_SCENE_TABS) {
    const destination = destinationForLegacyTab(tab)
    assert.ok(destination, `missing destination for ${tab}`)
    assert.ok(PRIMARY_MODES.includes(destination.mode))
    assert.ok(destination.view.length > 0)
  }
  assert.equal(destinationForLegacyTab("not-a-scene-tab"), null)
})

test("integrity: destination mapping is one-to-one and complete", () => {
  assert.equal(Object.keys(SCENE_DESTINATION_BY_LEGACY_TAB).length, LEGACY_SCENE_TABS.length)
  const keys = LEGACY_SCENE_TABS.map((tab) => destinationKey(SCENE_DESTINATION_BY_LEGACY_TAB[tab]))
  assert.equal(new Set(keys).size, keys.length, "two legacy destinations collapse into one UX destination")
  assert.deepEqual(new Set(PRIMARY_MODES), new Set(["Monitor", "Analyze", "Configure"]))
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
