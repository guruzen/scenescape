/* SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import { expect, test, type Page, type TestInfo } from "@playwright/test";

const scene = {
  uid: "scene-a",
  id: "scene-a",
  name: "Retail Lab",
  scale: 100,
  map: "",
  thumbnail: "/media/floor.png",
  revision: 3,
  camera_calibration: "Manual",
};

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
};

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
};

const region = {
  uid: "region-1",
  id: "region-1",
  name: "Checkout",
  scene: "scene-a",
  visible: true,
  points: [
    [0.5, 0.5],
    [3, 0.5],
    [3, 2.5],
    [0.5, 2.5],
  ],
  height: 1.2,
  threshold: 4,
  revision: 1,
};

const tripwire = {
  uid: "tripwire-1",
  id: "tripwire-1",
  name: "Exit line",
  scene: "scene-a",
  visible: true,
  points: [
    [3.5, 0.5],
    [3.5, 3],
  ],
  height: 1,
  direction: "positive",
  revision: 1,
};

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
};

const bundle = {
  scene,
  cameras: [camera],
  sensors: [sensor],
  regions: [region],
  tripwires: [tripwire],
  children: [],
  markers: [],
  child_regions: [
    {
      ...region,
      uid: "child-region-1",
      id: "child-region-1",
      name: "Child zone",
    },
  ],
  child_tripwires: [
    {
      ...tripwire,
      uid: "child-trip-1",
      id: "child-trip-1",
      name: "Child line",
    },
  ],
  child_sensors: [
    {
      ...sensor,
      uid: "child-sensor-1",
      id: "child-sensor-1",
      name: "Child temperature",
      from_child_scene: "child-a",
    },
  ],
};

const sensorTelemetry = [
  {
    id: 1,
    timestamp: "2026-09-20T03:44:59Z",
    value: 22.5,
    payload: { type: "temperature", subtype: "ambient", value: 22.5 },
  },
];

const history = [
  {
    id: 101,
    timestamp: "2026-09-20T03:44:58Z",
    payload: { objects: live.objects },
  },
];

const trends = [
  {
    bucket: "2026-09-20T03:00:00Z",
    average_objects: 2.5,
    samples: 120,
  },
];

const overview = {
  generated_at: "2026-09-20T03:45:00Z",
  counts: {
    scenes: 1,
    cameras: 1,
    sensors: 1,
    regions: 1,
    tripwires: 1,
    incidents: 0,
    observations: 120,
  },
  health: {
    database: "connected",
    mqtt: "connected",
    last_observation: "2026-09-20T03:45:00Z",
  },
};

async function mockNativeApi(page: Page) {
  let btAnchors: any[] = [];
  let btTags: any[] = [];
  let btAssignments: any[] = [];
  await page.route("**/media/floor.png", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="500"><rect width="800" height="500" fill="#17282d"/><path d="M40 40H760V460H40Z" fill="#203a40" stroke="#4ed1ce" stroke-width="4"/><path d="M400 40V460M40 250H760" stroke="#49646a" stroke-width="2"/></svg>',
    });
  });
  await page.route("**/api/v2/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (value: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(value),
      });

    if (path === "/api/v2/bluetooth/anchors" && request.method() === "GET") {
      const serial = (url.searchParams.get("serial") || "").toLowerCase();
      const items = btAnchors.filter((row) =>
        String(row.serial_number).toLowerCase().includes(serial),
      );
      return json({ items, total: items.length, offset: 0, limit: 100 });
    }
    if (path === "/api/v2/bluetooth/anchors" && request.method() === "POST") {
      const body = request.postDataJSON();
      const row = { uid: `anchor-${btAnchors.length + 1}`, state: "commissioned", revision: 1, ...body };
      btAnchors.push(row);
      return json(row);
    }
    if (/^\/api\/v2\/bluetooth\/anchors\/[^/]+\/(activate|deactivate|maintenance|retire)$/.test(path)) {
      const [, , , , , id, action] = path.split("/");
      const row = btAnchors.find((item) => item.uid === id);
      if (!row) return json({ detail: { code: "anchor_not_found", message: "Bluetooth anchor not found" } }, 404);
      row.state =
        action === "activate"
          ? "active"
          : action === "deactivate"
            ? "disabled"
            : action === "retire"
              ? "retired"
              : "maintenance";
      row.revision += 1;
      return json(row);
    }
    if (path === "/api/v2/bluetooth/tags" && request.method() === "GET") {
      const serial = (url.searchParams.get("serial") || "").toLowerCase();
      const items = btTags.filter((row) =>
        String(row.serial_number).toLowerCase().includes(serial),
      );
      return json({ items, total: items.length, offset: 0, limit: 100 });
    }
    if (path === "/api/v2/bluetooth/tags" && request.method() === "POST") {
      const body = request.postDataJSON();
      const row = {
        uid: `tag-${btTags.length + 1}`,
        state: "commissioned",
        revision: 1,
        battery: { percent: null, status: "unknown", source: null, observed_at: null },
        last_seen_at: null,
        ...body,
      };
      btTags.push(row);
      return json(row);
    }
    if (path === "/api/v2/bluetooth/assignments" && request.method() === "GET")
      return json({ items: btAssignments, total: btAssignments.length, offset: 0, limit: 200 });
    if (path === "/api/v2/bluetooth/assignments" && request.method() === "POST") {
      const body = request.postDataJSON();
      const row = {
        uid: `assignment-${btAssignments.length + 1}`,
        revision: 1,
        valid_from: "2026-09-25T14:30:00Z",
        valid_to: null,
        created_by: "ux-test",
        closed_by: null,
        ...body,
      };
      btAssignments.push(row);
      return json(row);
    }
    if (path === "/api/v2/bluetooth/diagnostics")
      return json({
        anchors: {
          total: btAnchors.length,
          by_state: btAnchors.reduce((acc: Record<string, number>, row) => {
            acc[row.state] = (acc[row.state] || 0) + 1;
            return acc;
          }, {}),
          unassigned_scene: btAnchors.filter((row) => !row.scene_id).length,
        },
        tags: {
          visible: true,
          total: btTags.length,
          by_state: {},
          battery: { unknown: btTags.length },
        },
        scope: { all_scenes: true, scenes: ["*"] },
      });

    if (path === "/api/v2/scenes/scene-a/live/stream") {
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        headers: { "cache-control": "no-cache" },
        body: `data: ${JSON.stringify(live)}\n\n`,
      });
    }
    if (path === "/api/v2/overview") return json(overview);
    if (path === "/api/v2/scenes") return json([scene]);
    if (path === "/api/v2/scenes/scene-a/bundle") return json(bundle);
    if (path === "/api/v2/scenes/scene-a/live") return json(live);
    if (path === "/api/v2/scenes/scene-a/history") return json(history);
    if (path === "/api/v2/scenes/scene-a/trends") return json(trends);
    if (path === "/api/v2/cameras") return json([camera]);
    if (path === "/api/v2/sensors") return json([sensor]);
    if (path === "/api/v2/regions") return json([region]);
    if (path === "/api/v2/tripwires") return json([tripwire]);
    if (path === "/api/v2/children") return json([]);
    if (path === "/api/v2/markers") return json([]);
    if (path === "/api/v2/assets") return json([]);
    if (path === "/api/v2/models/configs") return json({ configs: [] });
    if (path === "/api/v2/autocalibration/status")
      return json({ status: "available" });
    if (path === "/api/v2/cameras/cam-1/telemetry")
      return json({
        fps: 25.2,
        detections: 1,
        stale: false,
        last_observation: "2026-09-20T03:45:00Z",
      });
    if (path === "/api/v2/sensors/sensor-1/telemetry")
      return json(sensorTelemetry);
    if (path === "/api/v2/cameras/cam-1/snapshot") {
      return route.fulfill({
        status: 200,
        contentType: "image/svg+xml",
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#13262c"/><circle cx="320" cy="180" r="42" fill="#4ed1ce"/></svg>',
      });
    }
    if (path === "/api/v2/regions/region-1" && request.method() === "PUT") {
      const body = request.postDataJSON();
      return json({ ...region, ...body, revision: 2 });
    }
    if (path === "/api/v2/tripwires/tripwire-1" && request.method() === "PUT") {
      const body = request.postDataJSON();
      return json({ ...tripwire, ...body, revision: 2 });
    }

    if (request.method() === "GET") return json([]);
    return json({ ok: true });
  });
}

async function openScene(page: Page) {
  await page.goto("/tests/e2e/index.html#/scene/scene-a");
  await expect(
    page.locator('[aria-label="Scene operational status"]'),
  ).toBeVisible();
  await expect(
    page.getByText("Retail Lab", { exact: true }).first(),
  ).toBeVisible();
}

async function screenshot(page: Page, testInfo: TestInfo, name: string) {
  await page.screenshot({ path: testInfo.outputPath(name), fullPage: true });
}

test.beforeEach(async ({ page }) => {
  await mockNativeApi(page);
});

test("UX-120 Liquid Glass theme smoke: selectable, persistent and rendered", async ({
  page,
}, testInfo) => {
  await page.goto("/tests/e2e/index.html#/overview");
  const theme = page.getByLabel("Visual theme");
  await expect(theme).toBeVisible();
  await expect(theme.locator('option[value="liquid-glass"]')).toHaveText(
    "Liquid Glass",
  );
  await theme.selectOption("liquid-glass");
  await expect(page.locator("html")).toHaveAttribute(
    "data-theme",
    "liquid-glass",
  );
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("scenescape-theme")))
    .toBe("liquid-glass");

  const glass = page.locator(".panel").first();
  await expect(glass).toBeVisible();
  const backdropFilter = await glass.evaluate(
    (element) => getComputedStyle(element).backdropFilter,
  );
  expect(backdropFilter).toContain("blur");

  await screenshot(page, testInfo, "ux120-liquid-glass.png");
});

test("UX-93 Live 2D smoke: live overlays, diagnostics and keyboard inspector", async ({
  page,
}, testInfo) => {
  await openScene(page);
  await expect(page.locator(".native-map")).toBeVisible();
  await expect(page.locator(".native-map image")).toBeVisible();
  await expect(page.getByText("LIVE", { exact: true })).toBeVisible();

  await page.getByRole("checkbox", { name: /Trails/ }).check();
  await page.getByRole("checkbox", { name: /Telemetry/ }).check();
  await page.getByRole("checkbox", { name: /Heatmap/ }).check();
  await page.getByRole("checkbox", { name: /Velocity/ }).check();

  await expect(
    page.locator('[aria-label="Live scene telemetry"]'),
  ).toBeVisible();
  await expect(
    page.locator('[aria-label="Visualization legend"]'),
  ).toBeVisible();
  await expect(page.locator(".child-region-shape")).toHaveCount(1);
  await expect(page.locator(".child-tripwire-line")).toHaveCount(1);

  const object = page.getByRole("button", { name: "Inspect tracked object 1" });
  await object.focus();
  await object.press("Enter");
  await expect(page.locator('[aria-label="Scene inspector"]')).toContainText(
    "Object 1",
  );
  await expect(page.locator('[aria-label="Scene inspector"]')).toContainText(
    "0.85 m/s",
  );
  const fullscreen = page.getByRole("button", { name: "Fullscreen" });
  await fullscreen.click();
  await expect
    .poll(() => page.evaluate(() => Boolean(document.fullscreenElement)))
    .toBe(true);
  await page.evaluate(async () => {
    if (document.fullscreenElement) await document.exitFullscreen();
  });
  await expect
    .poll(() => page.evaluate(() => Boolean(document.fullscreenElement)))
    .toBe(false);

  await screenshot(page, testInfo, "ux93-live-2d.png");
});

test("UX-94 Live 3D smoke: WebGL view and renderer-specific controls", async ({
  page,
}, testInfo) => {
  await openScene(page);
  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "3D Scene" })
    .click();

  await expect(page.locator(".three-canvas")).toBeVisible();
  const floor = page.getByRole("checkbox", { name: /Floor plane/ });
  const cameraFrames = page.getByRole("checkbox", { name: /Camera frames/ });
  await expect(floor).toBeChecked();
  await floor.uncheck();
  await expect(floor).not.toBeChecked();
  await cameraFrames.check();
  await expect(cameraFrames).toBeChecked();

  const objectSelector = page.getByLabel("Select tracked object for inspector");
  await expect(objectSelector).toBeVisible();
  await objectSelector.selectOption("1");
  await expect(page.locator('[aria-label="Scene inspector"]')).toContainText(
    "Object 1",
  );

  const viewControls = page.getByRole("group", { name: "3D view" });
  const cameraSelector = viewControls.locator("select").nth(1);
  await cameraSelector.selectOption("cam-1");
  const cameraView = viewControls.getByRole("checkbox", {
    name: /Camera view/,
  });
  await cameraView.check();
  await expect(cameraView).toBeChecked();

  const opacity = page.getByRole("slider", { name: /Camera opacity/ });
  const light = page.getByRole("slider", { name: /Light/ });
  await opacity.fill("60");
  await light.fill("150");
  await expect(opacity).toHaveValue("60");
  await expect(light).toHaveValue("150");

  await screenshot(page, testInfo, "ux94-live-3d.png");
});

test("UX-95 Cameras smoke: live snapshot and camera telemetry", async ({
  page,
}, testInfo) => {
  await openScene(page);
  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "Cameras" })
    .click();

  await expect(
    page.getByRole("heading", { name: "Entry Camera" }),
  ).toBeVisible();
  await page.getByRole("checkbox", { name: "Show Telemetry" }).check();
  await expect(page.locator(".camera-telemetry-strip")).toContainText("25.2");
  await expect(page.locator(".camera-telemetry-strip")).toContainText(
    "Receiving",
  );
  await expect(page.getByAltText("Entry Camera live view")).toBeVisible();

  await screenshot(page, testInfo, "ux95-cameras.png");
});

test("UX-96 Sensors smoke: retained native sensor telemetry", async ({
  page,
}, testInfo) => {
  await openScene(page);
  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "Sensors" })
    .click();

  await expect(
    page.getByRole("heading", { name: "Sensors & telemetry" }),
  ).toBeVisible();
  await expect(page.getByText("Temperature", { exact: true })).toBeVisible();
  await expect(page.getByText("22.5", { exact: true })).toBeVisible();

  await screenshot(page, testInfo, "ux96-sensors.png");
});

test("UX-97 Analyze smoke: history, trends and runtime", async ({
  page,
}, testInfo) => {
  await openScene(page);
  await page
    .locator(".scene-primary-nav")
    .getByRole("button", { name: "Analyze" })
    .click();

  await expect(
    page.getByRole("heading", { name: "Persisted observations" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Load history" }).click();
  await expect(
    page.getByText("2026-09-20T03:44:58Z", { exact: true }),
  ).toBeVisible();

  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "Trends" })
    .click();
  await page.getByRole("button", { name: "Apply range" }).click();
  await expect(page.getByRole("cell", { name: "2.5" })).toBeVisible();

  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "Runtime" })
    .click();
  await expect(page.getByText("MQTT ingestion", { exact: true })).toBeVisible();

  await screenshot(page, testInfo, "ux97-analyze.png");
});

test("UX-98 Configure smoke: geometry, hierarchy, calibration and inventory routes", async ({
  page,
}, testInfo) => {
  await openScene(page);
  await page
    .locator(".scene-primary-nav")
    .getByRole("button", { name: "Configure" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Spatial analytics" }),
  ).toBeVisible();

  await page
    .getByRole("button", { name: /Checkout/ })
    .first()
    .click();
  await page.getByLabel("Name").fill("Checkout updated");
  await page.getByRole("button", { name: "Save region" }).click();
  await expect(page.getByText("Region saved.", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /Tripwires \(1\)/ }).click();
  await page
    .getByRole("button", { name: /Exit line/ })
    .first()
    .click();
  await page.getByLabel("Name").fill("Exit updated");
  await page.getByRole("button", { name: "Reverse direction" }).click();
  await page.getByRole("button", { name: "Save tripwire" }).click();
  await expect(
    page.getByText("Tripwire saved.", { exact: true }),
  ).toBeVisible();

  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "Hierarchy" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Scene hierarchy" }).first(),
  ).toBeVisible();

  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "Calibration" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Camera calibration" }),
  ).toBeVisible();
  await screenshot(page, testInfo, "ux98-configure-calibration.png");

  await openScene(page);
  await page
    .locator(".scene-primary-nav")
    .getByRole("button", { name: "Configure" })
    .click();
  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "Scene" })
    .click();
  await expect(
    page.getByPlaceholder("Search Sites, floors & scenes"),
  ).toBeVisible();

  await openScene(page);
  await page
    .locator(".scene-primary-nav")
    .getByRole("button", { name: "Configure" })
    .click();
  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "Cameras" })
    .click();
  await expect(page.getByPlaceholder("Search cameras")).toBeVisible();

  await openScene(page);
  await page
    .locator(".scene-primary-nav")
    .getByRole("button", { name: "Configure" })
    .click();
  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "Sensors" })
    .click();
  await expect(page.getByPlaceholder("Search sensors")).toBeVisible();

  await screenshot(page, testInfo, "ux98-configure-inventories.png");
});

test("UX-80–85 Accessibility smoke: keyboard navigation, controls, focus and scoped announcements", async ({
  page,
}, testInfo) => {
  await openScene(page);

  const analyze = page
    .locator(".scene-primary-nav")
    .getByRole("button", { name: "Analyze" });
  await analyze.focus();
  await analyze.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Persisted observations" }),
  ).toBeVisible();

  const configure = page
    .locator(".scene-primary-nav")
    .getByRole("button", { name: "Configure" });
  await configure.focus();
  await configure.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Spatial analytics" }),
  ).toBeVisible();

  const monitor = page
    .locator(".scene-primary-nav")
    .getByRole("button", { name: "Monitor" });
  await monitor.focus();
  await monitor.press("Enter");
  await expect(page.locator(".native-map")).toBeVisible();

  const view3d = page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "3D Scene" });
  await view3d.focus();
  await view3d.press("Enter");
  await expect(page.locator(".three-canvas")).toBeVisible();

  const view2d = page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "2D Scene" });
  await view2d.focus();
  await view2d.press("Enter");
  await expect(page.locator(".native-map")).toBeVisible();

  const trails = page.getByRole("checkbox", { name: /Trails/ });
  await trails.focus();
  await trails.press(" ");
  await expect(trails).toBeChecked();

  const telemetry = page.getByRole("checkbox", { name: /Telemetry/ });
  await telemetry.focus();
  await telemetry.press(" ");
  await expect(telemetry).toBeChecked();
  await expect(
    page.locator('[aria-label="Live scene telemetry"]'),
  ).toHaveAttribute("aria-live", "off");

  const object = page.getByRole("button", { name: "Inspect tracked object 1" });
  await object.focus();
  const focusStyle = await object.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      outlineStyle: style.outlineStyle,
      outlineWidth: style.outlineWidth,
    };
  });
  expect(
    focusStyle.outlineStyle === "none" && focusStyle.outlineWidth === "0px",
  ).toBeFalsy();
  await object.press(" ");
  await expect(page.locator('[aria-label="Scene inspector"]')).toContainText(
    "Object 1",
  );

  const status = page.getByRole("status");
  await expect(status).toContainText("LIVE");
  await expect(status).toHaveAttribute("aria-live", "polite");

  await screenshot(page, testInfo, "ux80-85-accessibility.png");
});


test("BT-03 Bluetooth management smoke: navigation, anchor, tag, assignment and honest telemetry", async ({
  page,
}, testInfo) => {
  await page.goto("/tests/e2e/index.html#/bluetooth");
  await expect(
    page.getByRole("heading", { name: "Bluetooth positioning" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "New anchor" }).click();
  await page.getByLabel("Serial number").fill("ANCHOR-UX-01");
  await page.locator(".bt-editor-panel").getByLabel("Scene").selectOption("scene-a");
  await page.getByRole("button", { name: "Commission anchor" }).click();
  await expect(page.getByText("ANCHOR-UX-01", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Anchor commissioned.", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Activate" }).click();
  await expect(page.locator(".bt-editor-panel .bt-status")).toHaveText(/active/i);

  await page.getByRole("tab", { name: "Tags" }).click();
  await page.getByRole("button", { name: "New tag" }).click();
  await page.getByLabel("Serial number").fill("TAG-UX-01");
  await page.getByRole("button", { name: "Commission tag" }).click();
  await expect(page.getByText("TAG-UX-01", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Unknown", { exact: true }).first()).toBeVisible();

  await page.getByLabel("Assignment entity ID").fill("forklift-27");
  await page.getByLabel("Display name").fill("Forklift 27");
  await page.getByRole("button", { name: "Assign tag" }).click();
  await expect(page.getByText("Forklift 27", { exact: true }).first()).toBeVisible();

  await page.getByRole("tab", { name: "Diagnostics" }).click();
  await expect(page.getByText("Anchors visible", { exact: true })).toBeVisible();
  await expect(page.getByText("Tags visible", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: "Calibration" }).click();
  await expect(
    page.getByRole("heading", { name: "Anchor calibration" }),
  ).toBeVisible();
  await expect(page.getByText("BT-04", { exact: true })).toBeVisible();

  await screenshot(page, testInfo, "bt03-bluetooth-management.png");
});
