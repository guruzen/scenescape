/* SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import { expect, test, type Page, type TestInfo } from "@playwright/test";

async function openNativeScene(page: Page) {
  await page.goto("/tests/harness.html#/overview");
  const sceneId = (
    await page.locator(".scene-row span").first().textContent()
  )?.trim();
  expect(sceneId).toBeTruthy();
  await page.goto(`/tests/harness.html#/scene/${sceneId}`);
  await expect(
    page.getByRole("heading", { name: "Test distribution floor", exact: true }),
  ).toBeVisible({ timeout: 20_000 });
  await expect(
    page.locator('[aria-label="Scene operational status"]'),
  ).toBeVisible();
}

async function capture(page: Page, testInfo: TestInfo, name: string) {
  await page.screenshot({ path: testInfo.outputPath(name), fullPage: true });
}

test("UX-93 integrated Live 2D uses the native API and live observation stream", async ({
  page,
}, testInfo) => {
  await openNativeScene(page);
  await expect(page.locator(".native-map")).toBeVisible();
  await expect(page.locator(".native-map image")).toBeVisible();
  await expect(page.getByRole("status")).toContainText("LIVE");

  await expect
    .poll(
      async () =>
        page
          .getByRole("button", { name: /Inspect tracked object test-track-1/ })
          .count(),
      { timeout: 15_000 },
    )
    .toBe(1);
  const object = page.getByRole("button", {
    name: /Inspect tracked object test-track-1/,
  });
  const movingDot = object.locator(".track-dot");
  const initialCx = await movingDot.getAttribute("cx");
  await expect
    .poll(async () => movingDot.getAttribute("cx"), { timeout: 6_000 })
    .not.toBe(initialCx);

  await page.getByRole("checkbox", { name: /Trails/ }).check();
  await page.getByRole("checkbox", { name: /Telemetry/ }).check();
  await page.getByRole("checkbox", { name: /Heatmap/ }).check();
  await page.getByRole("checkbox", { name: /Velocity/ }).check();

  await expect(
    page.locator('[aria-label="Live scene telemetry"]'),
  ).toBeVisible();
  await expect(
    page.locator('[aria-label="Visualization legend"]'),
  ).toContainText("2/2 vectors");
  await expect(page.locator(".region-shape")).toHaveCount(1);
  await expect(page.locator(".tripwire-line")).toHaveCount(1);
  await expect(page.locator(".object-heatmap")).toHaveCount(2);
  await expect(page.locator(".object-heatmap-core")).toHaveCount(2);
  await expect(page.locator(".object-velocity")).toHaveCount(2);
  await expect
    .poll(async () => page.locator(".object-trail").count(), { timeout: 6_000 })
    .toBeGreaterThan(0);

  await object.focus();
  await object.press("Enter");
  await expect(page.locator('[aria-label="Scene inspector"]')).toContainText(
    "Object test-track-1",
  );
  await expect(page.locator('[aria-label="Scene inspector"]')).toContainText(
    "fixture-A7",
  );
  await capture(page, testInfo, "native-ux93-live-2d.png");
});

test("UX-94 integrated Live 3D renders and keeps object inspection available", async ({
  page,
}, testInfo) => {
  await openNativeScene(page);
  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "3D Scene" })
    .click();
  await expect(page.locator(".three-canvas")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("group", { name: "3D view" })).toBeVisible();
  await expect
    .poll(
      async () =>
        page
          .getByLabel("Select tracked object for inspector")
          .locator("option")
          .count(),
      { timeout: 15_000 },
    )
    .toBeGreaterThan(1);
  await page
    .getByLabel("Select tracked object for inspector")
    .selectOption("test-track-1");
  await expect(page.locator('[aria-label="Scene inspector"]')).toContainText(
    "Object test-track-1",
  );
  await page.getByRole("checkbox", { name: /Heatmap/ }).check();
  await page.getByRole("checkbox", { name: /Velocity/ }).check();
  await expect(
    page.locator('[aria-label="Visualization legend"]'),
  ).toContainText("2/2 vectors");
  await capture(page, testInfo, "native-ux94-live-3d.png");
});

test("UX-95 integrated Cameras uses native snapshot and telemetry endpoints", async ({
  page,
}, testInfo) => {
  await openNativeScene(page);
  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "Cameras" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Test camera 01" }),
  ).toBeVisible();
  await page.getByRole("checkbox", { name: "Show Telemetry" }).check();
  await expect(page.getByAltText("Test camera 01 live view")).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.locator(".camera-telemetry-strip")).toContainText(
    "Receiving",
    { timeout: 15_000 },
  );
  await expect(page.locator(".camera-telemetry-strip")).toContainText("2");
  await capture(page, testInfo, "native-ux95-cameras.png");
});

test("UX-96 integrated Sensors reads retained native sensor telemetry", async ({
  page,
}, testInfo) => {
  await openNativeScene(page);
  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "Sensors" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Sensors & telemetry" }),
  ).toBeVisible();
  await expect(
    page.getByText("Test temperature", { exact: true }),
  ).toBeVisible();
  await expect
    .poll(
      async () => {
        const body = await page.locator("body").innerText();
        return /21\.[5-9]|22\.0/.test(body);
      },
      { timeout: 15_000 },
    )
    .toBe(true);
  await capture(page, testInfo, "native-ux96-sensors.png");
});

test("UX-97 integrated Analyze uses persisted observation/history/runtime data", async ({
  page,
}, testInfo) => {
  await openNativeScene(page);
  await page
    .locator(".scene-primary-nav")
    .getByRole("button", { name: "Analyze" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Persisted observations" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Load history" }).click();
  await expect(page.locator(".history-list > div").first()).toBeVisible({
    timeout: 15_000,
  });

  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "Trends" })
    .click();
  await page.getByRole("button", { name: "Apply range" }).click();
  await expect(page.locator(".table-wrap tbody tr").first()).toBeVisible({
    timeout: 15_000,
  });

  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "Runtime" })
    .click();
  await expect(page.getByText("MQTT ingestion", { exact: true })).toBeVisible();
  await expect(
    page.getByText("connected", { exact: true }).first(),
  ).toBeVisible();
  await capture(page, testInfo, "native-ux97-analyze.png");
});

test("UX-98 integrated Configure keeps native editors and inventory routes reachable", async ({
  page,
}, testInfo) => {
  await openNativeScene(page);
  await page
    .locator(".scene-primary-nav")
    .getByRole("button", { name: "Configure" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Spatial analytics" }),
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
  await capture(page, testInfo, "native-ux98-calibration.png");

  await openNativeScene(page);
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

  await openNativeScene(page);
  await page
    .locator(".scene-primary-nav")
    .getByRole("button", { name: "Configure" })
    .click();
  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "Cameras" })
    .click();
  await expect(page.getByPlaceholder("Search cameras")).toBeVisible();

  await openNativeScene(page);
  await page
    .locator(".scene-primary-nav")
    .getByRole("button", { name: "Configure" })
    .click();
  await page
    .locator(".scene-secondary-nav")
    .getByRole("button", { name: "Sensors" })
    .click();
  await expect(page.getByPlaceholder("Search sensors")).toBeVisible();
  await capture(page, testInfo, "native-ux98-inventories.png");
});

test("BT-03 integrated Bluetooth control-plane CRUD uses the real FastAPI API", async ({
  page,
}, testInfo) => {
  await page.goto("/tests/harness.html#/bluetooth");
  await expect(
    page.getByRole("heading", { name: "Bluetooth positioning" }),
  ).toBeVisible({ timeout: 20_000 });

  await page.getByRole("button", { name: "New anchor" }).click();
  await page.getByLabel("Serial number").fill("ANCHOR-INTEGRATED-01");
  const sceneSelect = page.locator(".bt-editor-panel").getByLabel("Scene");
  await expect(sceneSelect.locator("option")).toHaveCount(2);
  await sceneSelect.selectOption({ index: 1 });
  await page.getByRole("button", { name: "Commission anchor" }).click();
  await expect(
    page.getByText("ANCHOR-INTEGRATED-01", { exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Activate" }).click();
  await expect(page.locator(".bt-editor-panel .bt-status")).toHaveText(
    /active/i,
  );

  await page.getByRole("tab", { name: "Tags" }).click();
  await page.getByRole("button", { name: "New tag" }).click();
  await page.getByLabel("Serial number").fill("TAG-INTEGRATED-01");
  await page.getByRole("button", { name: "Commission tag" }).click();
  await expect(
    page.getByText("TAG-INTEGRATED-01", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("Unknown", { exact: true }).first(),
  ).toBeVisible();

  await page.getByLabel("Assignment entity type").selectOption("asset");
  await page.getByLabel("Assignment entity ID").fill("forklift-integrated-27");
  await page.getByLabel("Display name").fill("Integrated Forklift 27");
  await page.getByRole("button", { name: "Assign tag" }).click();
  await expect(
    page.getByText("Integrated Forklift 27", { exact: true }).first(),
  ).toBeVisible();

  await page.getByRole("tab", { name: "Diagnostics" }).click();
  await expect(
    page.getByText("Anchors visible", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Tags visible", { exact: true })).toBeVisible();
  await capture(page, testInfo, "bt03-integrated-control-plane.png");
});

test("BT-04 integrated calibration persists scene-local metres through real FastAPI", async ({
  page,
}, testInfo) => {
  const tokenResponse = await page.request.get("/api/test/browser-token");
  const token = (await tokenResponse.json()).token;
  const headers = { Authorization: `Bearer ${token}` };
  const scenesResponse = await page.request.get("/api/v2/scenes", { headers });
  const scenes = await scenesResponse.json();
  const sceneId = String(scenes[0].uid || scenes[0].id);

  for (let index = 1; index <= 4; index += 1) {
    const response = await page.request.post("/api/v2/bluetooth/anchors", {
      headers,
      data: {
        uid: `bt04-integrated-anchor-${index}`,
        serial_number: `BT04-INTEGRATED-${index}`,
        scene_id: sceneId,
        capabilities: ["channel_sounding"],
      },
    });
    expect(response.ok()).toBeTruthy();
  }

  await page.goto("/tests/harness.html#/bluetooth");
  await page.getByRole("tab", { name: "Calibration" }).click();
  await expect(
    page.getByRole("heading", { name: "Anchor calibration" }),
  ).toBeVisible({ timeout: 20_000 });
  await page
    .getByLabel("Calibration anchor")
    .selectOption("bt04-integrated-anchor-1");

  const map = page.getByLabel("Bluetooth anchor calibration map");
  const box = await map.boundingBox();
  expect(box).not.toBeNull();
  await map.click({
    position: {
      x: (box?.width || 1) * 0.2,
      y: (box?.height || 1) * 0.4,
    },
  });
  const clickedX = Number(
    await page.getByLabel("Calibration X metres").inputValue(),
  );
  const clickedY = Number(
    await page.getByLabel("Calibration Y metres").inputValue(),
  );
  expect(Math.abs(clickedX - 2)).toBeLessThanOrEqual(0.01);
  expect(Math.abs(clickedY - 4.2)).toBeLessThanOrEqual(0.01);

  // Persist exact surveyed coordinates after validating map conversion.
  await page.getByLabel("Calibration X metres").fill("2");
  await page.getByLabel("Calibration Y metres").fill("4.2");
  await page.getByLabel("Calibration Z metres").fill("3.4");
  await page.getByLabel("Calibration Z provenance").selectOption("surveyed");
  await page.getByRole("button", { name: "Save new draft" }).click();
  await expect(page.getByText(/Draft revision 1 saved/)).toBeVisible();

  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Publish draft r1" }).click();
  await expect(
    page.getByText(/Calibration revision 1 is now active/),
  ).toBeVisible();

  const apiHistory = await page.request.get(
    "/api/v2/bluetooth/anchors/bt04-integrated-anchor-1/calibrations",
    { headers },
  );
  expect(apiHistory.ok()).toBeTruthy();
  const payload = await apiHistory.json();
  expect(payload.items[0].position).toEqual({
    x_m: 2,
    y_m: 4.2,
    z_m: 3.4,
  });
  expect(payload.items[0].coordinate_frame).toBe("scene_local_m");

  await page.reload();
  await page.getByRole("tab", { name: "Calibration" }).click();
  await page
    .getByLabel("Calibration anchor")
    .selectOption("bt04-integrated-anchor-1");
  await expect(page.getByLabel("Calibration X metres")).toHaveValue("2");
  await expect(page.getByLabel("Calibration Y metres")).toHaveValue("4.2");
  await capture(page, testInfo, "bt04-integrated-calibration.png");
});

test("BT-11 integrated survey diagnostics render observed RF and theoretical GDOP", async ({
  page,
}, testInfo) => {
  const tokenResponse = await page.request.get("/api/test/browser-token");
  const token = (await tokenResponse.json()).token;
  const headers = { Authorization: `Bearer ${token}` };
  const scenesResponse = await page.request.get("/api/v2/scenes", { headers });
  const scenes = await scenesResponse.json();
  const sceneId = String(scenes[0].uid || scenes[0].id);

  const anchorPositions = [
    { id: "bt11-a1", x: 0, y: 0, z: 3, bias: 0.25 },
    { id: "bt11-a2", x: 10, y: 0, z: 3, bias: -0.15 },
    { id: "bt11-a3", x: 10, y: 8, z: 3, bias: 0.2 },
    { id: "bt11-a4", x: 0, y: 8, z: 3, bias: -0.1 },
  ];

  for (const anchor of anchorPositions) {
    const created = await page.request.post("/api/v2/bluetooth/anchors", {
      headers,
      data: {
        uid: anchor.id,
        serial_number: anchor.id.toUpperCase(),
        scene_id: sceneId,
        capabilities: ["channel_sounding"],
      },
    });
    expect(created.ok()).toBeTruthy();

    const calibration = await page.request.post(
      "/api/v2/bluetooth/calibrations",
      {
        headers,
        data: {
          uid: `cal-${anchor.id}`,
          anchor_uid: anchor.id,
          scene_id: sceneId,
          x_m: anchor.x,
          y_m: anchor.y,
          z_m: anchor.z,
          yaw_deg: 0,
          pitch_deg: 0,
          roll_deg: 0,
          z_source: "surveyed",
          details: {},
        },
      },
    );
    expect(calibration.ok()).toBeTruthy();
    const calibrationBody = await calibration.json();
    const published = await page.request.post(
      `/api/v2/bluetooth/calibrations/${encodeURIComponent(calibrationBody.uid)}/publish?revision=${calibrationBody.revision}`,
      { headers },
    );
    expect(published.ok()).toBeTruthy();
  }

  const surveyPoint = { x: 4, y: 3, z: 1 };
  const pointResponse = await page.request.post(
    "/api/v2/bluetooth/surveys/points",
    {
      headers,
      data: {
        uid: "bt11-survey-p1",
        scene_id: sceneId,
        name: "Survey P1",
        x_m: surveyPoint.x,
        y_m: surveyPoint.y,
        z_m: surveyPoint.z,
      },
    },
  );
  expect(pointResponse.ok()).toBeTruthy();

  for (const anchor of anchorPositions) {
    const geometric = Math.hypot(
      anchor.x - surveyPoint.x,
      anchor.y - surveyPoint.y,
      anchor.z - surveyPoint.z,
    );
    for (const noise of [-0.01, 0, 0.01]) {
      const sample = await page.request.post(
        "/api/v2/bluetooth/surveys/points/bt11-survey-p1/samples",
        {
          headers,
          data: {
            anchor_uid: anchor.id,
            distance_m: geometric + anchor.bias + noise,
            distance_stddev_m: 0.04,
            quality: 0.98,
          },
        },
      );
      expect(sample.ok()).toBeTruthy();
    }
  }

  await page.goto("/tests/harness.html#/bluetooth");
  await page.getByRole("tab", { name: "Calibration" }).click();
  await expect(
    page.getByRole("heading", { name: "Anchor calibration" }),
  ).toBeVisible({ timeout: 20_000 });

  await expect(page.locator(".bt-cal-survey-point")).toHaveCount(1);
  await expect(page.getByText("Survey bias & coverage")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Create bias-corrected drafts" }),
  ).toBeEnabled();

  await page.getByRole("checkbox", { name: "Theoretical GDOP" }).check();
  await expect(page.locator(".bt-cal-gdop-cell").first()).toBeVisible();
  await page.getByRole("checkbox", { name: "Survey-anchor links" }).check();
  await expect(page.locator(".bt-cal-survey-link").first()).toBeVisible();

  await capture(page, testInfo, "bt11-survey-coverage.png");
});
