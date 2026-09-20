/* SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import { expect, test, type Page, type TestInfo } from "@playwright/test"

const scene = {
  uid: "scene-a",
  id: "scene-a",
  name: "Retail Lab",
  scale: 100,
  map: "",
  thumbnail: "",
  revision: 3,
  camera_calibration: "Manual",
}

const camera = {
  uid: "cam-1",
  id: "cam-1",
  name: "Entry Camera",
  scene: "scene-a",
  translation: [1.2, 1.4, 1.8],
  rotation: [0, 0, 0],
  resolution: [640, 480],
  intrinsics: { fx: 570, fy: 570, cx: 320, cy: 240 },
  distortion: { k1: 0, k2: 0, p1: 0, p2: 0, k3: 0 },
  revision: 2,
}

const sensor = {
  uid: "sensor-1",
  id: "sensor-1",
  sensor_id: "sensor-1",
  name: "Temperature",
  scene: "scene-a",
  visible: true,
  area: "circle",
  singleton_type: "environmental",
  center: [2.3, 2.1],
  radius: 0.7,
  revision: 1,
}

const region = {
  uid: "region-1",
  id: "region-1",
  name: "Checkout",
  scene: "scene-a",
  visible: true,
  points: [[0.5, 0.5], [3, 0.5], [3, 2.5], [0.5, 2.5]],
  height: 1.2,
  threshold: 4,
  revision: 1,
}

const tripwire = {
  uid: "tripwire-1",
  id: "tripwire-1",
  name: "Exit line",
  scene: "scene-a",
  visible: true,
  points: [[3.5, 0.5], [3.5, 3]],
  height: 1,
  direction: "positive",
  revision: 1,
}

const live = {
  stale: false,
  observed_at: "2026-09-20T03:45:00Z",
  scene_rate: 29.8,
  rate: { "cam-1": 25.2 },
  objects: [
    {
      id: 1,
      category: "person",
      translation: [1.8, 1.6, 0],
      velocity: [0.8, 0.3, 0],
      tracking_radius: 0.55,
      visibility: ["cam-1"],
      regions: { Checkout: { entered: true, dwell: 8.4 } },
      persistent_data: { badge: { id: "A7" } },
    },
  ],
}

const bundle = {
  scene,
  cameras: [camera],
  sensors: [sensor],
  regions: [region],
  tripwires: [tripwire],
  children: [],
  markers: [],
  child_regions: [{ ...region, uid: "child-region-1", id: "child-region-1", name: "Child zone" }],
  child_tripwires: [{ ...tripwire, uid: "child-trip-1", id: "child-trip-1", name: "Child line" }],
  child_sensors: [{ ...sensor, uid: "child-sensor-1", id: "child-sensor-1", name: "Child temperature", from_child_scene: "child-a" }],
}

const sensorTelemetry = [
  {
    id: 1,
    timestamp: "2026-09-20T03:44:59Z",
    value: 22.5,
    payload: { type: "temperature", subtype: "ambient", value: 22.5 },
  },
]

const history = [
  {
    id: 101,
    timestamp: "2026-09-20T03:44:58Z",
    payload: { objects: live.objects },
  },
]

const trends = [
  {
    bucket: "2026-09-20T03:00:00Z",
    average_objects: 2.5,
    samples: 120,
  },
]

const overview = {
  generated_at: "2026-09-20T03:45:00Z",
  counts: { scenes: 1, cameras: 1, sensors: 1, regions: 1, tripwires: 1, incidents: 0, observations: 120 },
  health: { database: "connected", mqtt: "connected", last_observation: "2026-09-20T03:45:00Z" },
}

async function mockNativeApi(page: Page) {
  await page.route("**/api/v2/**", async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const json = (value: unknown, status = 200) => route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(value),
    })

    if (path === "/api/v2/scenes/scene-a/live/stream") {
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        headers: { "cache-control": "no-cache" },
        body: `data: ${JSON.stringify(live)}\n\n`,
      })
    }
    if (path === "/api/v2/overview") return json(overview)
    if (path === "/api/v2/scenes") return json([scene])
    if (path === "/api/v2/scenes/scene-a/bundle") return json(bundle)
    if (path === "/api/v2/scenes/scene-a/live") return json(live)
    if (path === "/api/v2/scenes/scene-a/history") return json(history)
    if (path === "/api/v2/scenes/scene-a/trends") return json(trends)
    if (path === "/api/v2/cameras") return json([camera])
    if (path === "/api/v2/sensors") return json([sensor])
    if (path === "/api/v2/regions") return json([region])
    if (path === "/api/v2/tripwires") return json([tripwire])
    if (path === "/api/v2/children") return json([])
    if (path === "/api/v2/markers") return json([])
    if (path === "/api/v2/assets") return json([])
    if (path === "/api/v2/models/configs") return json({ configs: [] })
    if (path === "/api/v2/autocalibration/status") return json({ status: "available" })
    if (path === "/api/v2/cameras/cam-1/telemetry") return json({
      fps: 25.2,
      detections: 1,
      stale: false,
      last_observation: "2026-09-20T03:45:00Z",
    })
    if (path === "/api/v2/sensors/sensor-1/telemetry") return json(sensorTelemetry)
    if (path === "/api/v2/cameras/cam-1/snapshot") {
      return route.fulfill({
        status: 200,
        contentType: "image/svg+xml",
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#13262c"/><circle cx="320" cy="180" r="42" fill="#4ed1ce"/></svg>',
      })
    }

    if (request.method() === "GET") return json([])
    return json({ ok: true })
  })
}

async function openScene(page: Page) {
  await page.goto("/tests/e2e/index.html#/scene/scene-a")
  await expect(page.locator('[aria-label="Scene operational status"]')).toBeVisible()
  await expect(page.getByText("Retail Lab", { exact: true }).first()).toBeVisible()
}

async function screenshot(page: Page, testInfo: TestInfo, name: string) {
  await page.screenshot({ path: testInfo.outputPath(name), fullPage: true })
}

test.beforeEach(async ({ page }) => {
  await mockNativeApi(page)
})

test("UX-93 Live 2D smoke: live overlays, diagnostics and keyboard inspector", async ({ page }, testInfo) => {
  await openScene(page)
  await expect(page.locator(".native-map")).toBeVisible()
  await expect(page.getByText("LIVE", { exact: true })).toBeVisible()

  await page.getByRole("checkbox", { name: /Trails/ }).check()
  await page.getByRole("checkbox", { name: /Telemetry/ }).check()
  await page.getByRole("checkbox", { name: /Heatmap/ }).check()
  await page.getByRole("checkbox", { name: /Velocity/ }).check()

  await expect(page.locator('[aria-label="Live scene telemetry"]')).toBeVisible()
  await expect(page.locator('[aria-label="Visualization legend"]')).toBeVisible()
  await expect(page.locator(".child-region-shape")).toHaveCount(1)
  await expect(page.locator(".child-tripwire-line")).toHaveCount(1)

  const object = page.getByRole("button", { name: "Inspect tracked object 1" })
  await object.focus()
  await object.press("Enter")
  await expect(page.locator('[aria-label="Scene inspector"]')).toContainText("Object 1")
  await expect(page.locator('[aria-label="Scene inspector"]')).toContainText("0.85 m/s")
  await expect(page.getByRole("button", { name: "Fullscreen" })).toBeVisible()

  await screenshot(page, testInfo, "ux93-live-2d.png")
})

test("UX-94 Live 3D smoke: WebGL view and renderer-specific controls", async ({ page }, testInfo) => {
  await openScene(page)
  await page.locator(".scene-secondary-nav").getByRole("button", { name: "3D Scene" }).click()

  await expect(page.locator(".three-canvas")).toBeVisible()
  await expect(page.getByRole("checkbox", { name: /Floor plane/ })).toBeVisible()
  await expect(page.getByRole("checkbox", { name: /Camera frames/ })).toBeVisible()
  await expect(page.getByLabel("Select tracked object for inspector")).toBeVisible()
  await expect(page.getByRole("slider", { name: /Camera opacity/ })).toBeVisible()
  await expect(page.getByRole("slider", { name: /Light/ })).toBeVisible()

  await page.getByLabel("Select tracked object for inspector").selectOption("1")
  await expect(page.locator('[aria-label="Scene inspector"]')).toContainText("Object 1")

  await screenshot(page, testInfo, "ux94-live-3d.png")
})

test("UX-95 Cameras smoke: live snapshot and camera telemetry", async ({ page }, testInfo) => {
  await openScene(page)
  await page.locator(".scene-secondary-nav").getByRole("button", { name: "Cameras" }).click()

  await expect(page.getByRole("heading", { name: "Entry Camera" })).toBeVisible()
  await page.getByRole("checkbox", { name: "Show Telemetry" }).check()
  await expect(page.locator(".camera-telemetry-strip")).toContainText("25.2")
  await expect(page.locator(".camera-telemetry-strip")).toContainText("Receiving")
  await expect(page.getByAltText("Entry Camera live view")).toBeVisible()

  await screenshot(page, testInfo, "ux95-cameras.png")
})

test("UX-96 Sensors smoke: retained native sensor telemetry", async ({ page }, testInfo) => {
  await openScene(page)
  await page.locator(".scene-secondary-nav").getByRole("button", { name: "Sensors" }).click()

  await expect(page.getByRole("heading", { name: "Sensors & telemetry" })).toBeVisible()
  await expect(page.getByText("Temperature", { exact: true })).toBeVisible()
  await expect(page.getByText("22.5", { exact: true })).toBeVisible()

  await screenshot(page, testInfo, "ux96-sensors.png")
})

test("UX-97 Analyze smoke: history, trends and runtime", async ({ page }, testInfo) => {
  await openScene(page)
  await page.locator(".scene-primary-nav").getByRole("button", { name: "Analyze" }).click()

  await expect(page.getByRole("heading", { name: "Persisted observations" })).toBeVisible()
  await page.getByRole("button", { name: "Load history" }).click()
  await expect(page.getByText("2026-09-20T03:44:58Z", { exact: true })).toBeVisible()

  await page.locator(".scene-secondary-nav").getByRole("button", { name: "Trends" }).click()
  await page.getByRole("button", { name: "Apply range" }).click()
  await expect(page.getByRole("cell", { name: "2.5" })).toBeVisible()

  await page.locator(".scene-secondary-nav").getByRole("button", { name: "Runtime" }).click()
  await expect(page.getByText("MQTT ingestion", { exact: true })).toBeVisible()

  await screenshot(page, testInfo, "ux97-analyze.png")
})

test("UX-98 Configure smoke: geometry, hierarchy, calibration and inventory routes", async ({ page }, testInfo) => {
  await openScene(page)
  await page.locator(".scene-primary-nav").getByRole("button", { name: "Configure" }).click()
  await expect(page.getByRole("heading", { name: "Spatial analytics" })).toBeVisible()

  await page.locator(".scene-secondary-nav").getByRole("button", { name: "Hierarchy" }).click()
  await expect(page.getByRole("heading", { name: "Scene hierarchy" }).first()).toBeVisible()

  await page.locator(".scene-secondary-nav").getByRole("button", { name: "Calibration" }).click()
  await expect(page.getByRole("heading", { name: "Camera calibration" })).toBeVisible()
  await screenshot(page, testInfo, "ux98-configure-calibration.png")

  await openScene(page)
  await page.locator(".scene-primary-nav").getByRole("button", { name: "Configure" }).click()
  await page.locator(".scene-secondary-nav").getByRole("button", { name: "Scene" }).click()
  await expect(page.getByPlaceholder("Search Sites, floors & scenes")).toBeVisible()

  await openScene(page)
  await page.locator(".scene-primary-nav").getByRole("button", { name: "Configure" }).click()
  await page.locator(".scene-secondary-nav").getByRole("button", { name: "Cameras" }).click()
  await expect(page.getByPlaceholder("Search cameras")).toBeVisible()

  await openScene(page)
  await page.locator(".scene-primary-nav").getByRole("button", { name: "Configure" }).click()
  await page.locator(".scene-secondary-nav").getByRole("button", { name: "Sensors" }).click()
  await expect(page.getByPlaceholder("Search sensors")).toBeVisible()

  await screenshot(page, testInfo, "ux98-configure-inventories.png")
})


test("UX-80–85 Accessibility smoke: keyboard navigation, controls, focus and scoped announcements", async ({ page }, testInfo) => {
  await openScene(page)

  const analyze = page.locator(".scene-primary-nav").getByRole("button", { name: "Analyze" })
  await analyze.focus()
  await analyze.press("Enter")
  await expect(page.getByRole("heading", { name: "Persisted observations" })).toBeVisible()

  const configure = page.locator(".scene-primary-nav").getByRole("button", { name: "Configure" })
  await configure.focus()
  await configure.press("Enter")
  await expect(page.getByRole("heading", { name: "Spatial analytics" })).toBeVisible()

  const monitor = page.locator(".scene-primary-nav").getByRole("button", { name: "Monitor" })
  await monitor.focus()
  await monitor.press("Enter")
  await expect(page.locator(".native-map")).toBeVisible()

  const view3d = page.locator(".scene-secondary-nav").getByRole("button", { name: "3D Scene" })
  await view3d.focus()
  await view3d.press("Enter")
  await expect(page.locator(".three-canvas")).toBeVisible()

  const view2d = page.locator(".scene-secondary-nav").getByRole("button", { name: "2D Scene" })
  await view2d.focus()
  await view2d.press("Enter")
  await expect(page.locator(".native-map")).toBeVisible()

  const trails = page.getByRole("checkbox", { name: /Trails/ })
  await trails.focus()
  await trails.press(" ")
  await expect(trails).toBeChecked()

  const telemetry = page.getByRole("checkbox", { name: /Telemetry/ })
  await telemetry.focus()
  await telemetry.press(" ")
  await expect(telemetry).toBeChecked()
  await expect(page.locator('[aria-label="Live scene telemetry"]')).toHaveAttribute("aria-live", "off")

  const object = page.getByRole("button", { name: "Inspect tracked object 1" })
  await object.focus()
  const focusStyle = await object.evaluate((element) => {
    const style = getComputedStyle(element)
    return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth }
  })
  expect(focusStyle.outlineStyle === "none" && focusStyle.outlineWidth === "0px").toBeFalsy()
  await object.press(" ")
  await expect(page.locator('[aria-label="Scene inspector"]')).toContainText("Object 1")

  const status = page.getByRole("status")
  await expect(status).toContainText("LIVE")
  await expect(status).toHaveAttribute("aria-live", "polite")

  await screenshot(page, testInfo, "ux80-85-accessibility.png")
})
