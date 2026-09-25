/* SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import { deriveSceneStatus } from "../src/ux/sceneStatus.ts";
import {
  deriveSceneTelemetry,
  emptyLiveSceneState,
  normalizeLiveSceneState,
} from "../src/ux/sceneTelemetry.ts";
import {
  HEATMAP_RANGES,
  heatmapOpacityValue,
  velocityArrow2D,
  velocityLength3D,
} from "../src/ux/sceneVisualization.ts";
import {
  SCENE_LAYOUT_BREAKPOINTS,
  SCENE_VISUAL_HIERARCHY,
  SUPPORTED_UI_THEMES,
  layoutModeForWidth,
} from "../src/ux/sceneLayout.ts";
import {
  LIVE_REGION_POLICY,
  isSelectionActivationKey,
  selectionAriaLabel,
} from "../src/ux/sceneAccessibility.ts";
import {
  controlsForRenderer,
  summarizeLiveObjectAvailability,
} from "../src/ux/sceneViewControls.ts";
import {
  buildInspectorModel,
  refreshObjectSelection,
} from "../src/ux/sceneInspector.ts";

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
} from "../src/ux/sceneWorkspaceContract.ts";

test("unit: every legacy tab resolves to an explicit UX 2.0 destination", () => {
  for (const tab of LEGACY_SCENE_TABS) {
    const destination = destinationForLegacyTab(tab);
    assert.ok(destination, `missing destination for ${tab}`);
    assert.ok(PRIMARY_MODES.includes(destination.mode));
    assert.ok(destination.view.length > 0);
    assert.equal(legacyTabForDestination(destination), tab);
  }
  assert.equal(destinationForLegacyTab("not-a-scene-tab"), null);
  assert.equal(
    legacyTabForDestination({ mode: "Configure", view: "Scene" }),
    null,
  );
});

test("unit: primary-mode changes choose stable workspace defaults", () => {
  assert.deepEqual(defaultDestinationForMode("Monitor"), {
    mode: "Monitor",
    view: "2D Scene",
  });
  assert.deepEqual(defaultDestinationForMode("Analyze"), {
    mode: "Analyze",
    view: "History",
  });
  assert.deepEqual(defaultDestinationForMode("Configure"), {
    mode: "Configure",
    view: "Geometry",
  });
  for (const mode of PRIMARY_MODES) {
    assert.ok(
      SECONDARY_VIEWS_BY_MODE[mode].includes(DEFAULT_VIEW_BY_MODE[mode]),
    );
  }
});

test("unit: direct scene route suffixes preserve legacy entry behavior", () => {
  assert.equal(initialLegacyTabForSceneSuffix("geometry"), "Geometry");
  assert.equal(initialLegacyTabForSceneSuffix("hierarchy"), "Hierarchy");
  assert.equal(initialLegacyTabForSceneSuffix(undefined), "Live 2D");
  assert.equal(initialLegacyTabForSceneSuffix("unknown"), "Live 2D");
});

test("integrity: destination mapping is one-to-one and complete", () => {
  assert.equal(
    Object.keys(SCENE_DESTINATION_BY_LEGACY_TAB).length,
    LEGACY_SCENE_TABS.length,
  );
  const keys = LEGACY_SCENE_TABS.map((tab) =>
    destinationKey(SCENE_DESTINATION_BY_LEGACY_TAB[tab]),
  );
  assert.equal(
    new Set(keys).size,
    keys.length,
    "two legacy destinations collapse into one UX destination",
  );
  assert.deepEqual(
    new Set(PRIMARY_MODES),
    new Set(["Monitor", "Analyze", "Configure"]),
  );
  for (const mode of PRIMARY_MODES)
    assert.ok(SECONDARY_VIEWS_BY_MODE[mode].length > 0);
});

test("integrity: route-out destinations are explicit and configuration-only", () => {
  assert.deepEqual(ROUTE_BY_DESTINATION_KEY, {
    "Configure:Scene": "scenes",
    "Configure:Cameras": "cameras",
    "Configure:Sensors": "sensors",
  });
  assert.equal(routeForDestination({ mode: "Monitor", view: "Cameras" }), null);
  assert.equal(
    routeForDestination({ mode: "Configure", view: "Cameras" }),
    "cameras",
  );
});

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
  ];
  assert.deepEqual([...SCENE_WORKSPACE_CAPABILITIES].sort(), required.sort());
  assert.deepEqual(DEFAULT_SCENE_DESTINATION, {
    mode: "Monitor",
    view: "2D Scene",
  });
});

test("unit: scene status distinguishes live degraded stale and unknown health", () => {
  const live = deriveSceneStatus({
    stale: false,
    observedAt: "2026-09-20T03:00:00Z",
    nowMs: Date.parse("2026-09-20T03:00:02Z"),
    sceneRate: 29.8,
    objectCount: 85,
    cameraCount: 2,
    cameraRates: { cam1: 30, cam2: 29.7 },
    mqttState: "connected",
  });
  assert.equal(live.state, "LIVE");
  assert.equal(live.cameraHealthy, 2);
  assert.equal(live.ageSeconds, 2);

  const degradedMqtt = deriveSceneStatus({
    stale: false,
    cameraCount: 0,
    mqttState: "disconnected",
  });
  assert.equal(degradedMqtt.state, "DEGRADED");

  const degradedCamera = deriveSceneStatus({
    stale: false,
    cameraCount: 2,
    cameraRates: { cam1: 30 },
    mqttState: "connected",
  });
  assert.equal(degradedCamera.state, "DEGRADED");
  assert.equal(degradedCamera.cameraHealthy, 1);

  const stale = deriveSceneStatus({
    stale: true,
    cameraCount: 2,
    mqttState: "connected",
  });
  assert.equal(stale.state, "STALE/OFFLINE");

  const unknown = deriveSceneStatus({
    stale: false,
    cameraCount: 2,
    cameraRates: null,
    mqttState: null,
  });
  assert.equal(unknown.state, "LIVE");
  assert.equal(unknown.cameraHealthy, null);
  assert.equal(unknown.mqtt, "Unknown");
});

test("unit: renderer controls are contextual", () => {
  const controls2d = controlsForRenderer("2d");
  assert.ok(controls2d.includes("labels"));
  assert.ok(!controls2d.includes("floor"));
  assert.ok(!controls2d.includes("camera-frames"));

  const controls3d = controlsForRenderer("3d");
  assert.ok(!controls3d.includes("labels"));
  assert.ok(controls3d.includes("floor"));
  assert.ok(controls3d.includes("camera-frames"));
  assert.ok(controls3d.includes("lighting"));
  for (const common of [
    "objects",
    "trails",
    "heatmap",
    "velocity",
    "spatial",
    "telemetry",
  ]) {
    assert.ok(controls2d.includes(common));
    assert.ok(controls3d.includes(common));
  }
});

test("unit: data-dependent layer availability reports velocity coverage", () => {
  const availability = summarizeLiveObjectAvailability([
    { id: 1, velocity: [1, 0] },
    { id: 2, velocity: ["0.5", "0.2"] },
    { id: 3 },
    { id: 4, velocity: ["bad", 1] },
  ]);
  assert.deepEqual(availability, {
    total: 4,
    velocityVectors: 2,
    trailsAvailable: true,
    heatmapAvailable: true,
    velocityAvailable: true,
  });
  assert.deepEqual(summarizeLiveObjectAvailability([]), {
    total: 0,
    velocityVectors: 0,
    trailsAvailable: false,
    heatmapAvailable: false,
    velocityAvailable: false,
  });
});

test("unit: object inspector derives current speed dwell visibility and persistent data", () => {
  const selection = {
    kind: "object",
    id: "42",
    value: {
      id: 42,
      category: "person",
      translation: [1, 2, 0],
      velocity: [3, 4],
      regions: { checkout: { dwell: 12.5 } },
      visibility: ["cam-a"],
      persistent_data: { badge: "A7" },
    },
  };
  const model = buildInspectorModel(selection);
  assert.equal(model.title, "Object 42");
  assert.equal(
    model.fields.find((field) => field.label === "Speed").value,
    "5.00 m/s",
  );
  assert.equal(
    model.fields.find((field) => field.label === "Dwell").value,
    "12.5 s",
  );
  assert.equal(
    model.fields.find((field) => field.label === "Visible cameras").value,
    "cam-a",
  );
  assert.match(model.persistentData, /A7/);
});

test("unit: inspector preserves Unknown for unavailable optional data", () => {
  const camera = buildInspectorModel({
    kind: "camera",
    id: "cam-1",
    value: { name: "Camera 1" },
  });
  assert.equal(
    camera.fields.find((field) => field.label === "FPS").value,
    "Unknown",
  );
  assert.equal(
    camera.fields.find((field) => field.label === "Feed").value,
    "Unknown",
  );
  const sensor = buildInspectorModel({
    kind: "sensor",
    id: "s1",
    value: { name: "Temp" },
  });
  assert.equal(
    sensor.fields.find((field) => field.label === "Latest value").value,
    "Unknown",
  );
});

test("regression: selected tracked object refreshes from the latest live observation", () => {
  const previous = {
    kind: "object",
    id: "7",
    value: { id: 7, translation: [1, 1] },
  };
  const refreshed = refreshObjectSelection(previous, [
    { id: 7, translation: [2, 3] },
  ]);
  assert.deepEqual(refreshed.value.translation, [2, 3]);
  const retained = refreshObjectSelection(previous, []);
  assert.deepEqual(retained.value.translation, [1, 1]);
});

test("unit: scene telemetry preserves unknown rates and computes freshness", () => {
  const telemetry = deriveSceneTelemetry(
    {
      scene_rate: 29.95,
      objects: [{}, {}],
      stale: false,
      observed_at: "2026-09-20T03:00:00Z",
      rate: { camB: 29.5, camA: "30" },
    },
    Date.parse("2026-09-20T03:00:01.500Z"),
  );
  assert.equal(telemetry.sceneRate, 29.95);
  assert.equal(telemetry.objectCount, 2);
  assert.equal(telemetry.freshness, "Receiving");
  assert.equal(telemetry.ageSeconds, 1.5);
  assert.deepEqual(telemetry.cameraRates, [
    { camera: "camA", fps: 30 },
    { camera: "camB", fps: 29.5 },
  ]);

  const unknown = deriveSceneTelemetry({ objects: [], stale: true });
  assert.equal(unknown.sceneRate, null);
  assert.equal(unknown.freshness, "Stale");
  assert.deepEqual(unknown.cameraRates, []);
});

test("regression: scene changes reset live telemetry instead of retaining the prior scene", () => {
  assert.deepEqual(emptyLiveSceneState(), { objects: [], stale: true });
  assert.notEqual(emptyLiveSceneState(), emptyLiveSceneState());
});

test("unit: velocity geometry is bounded and rejects invalid vectors", () => {
  assert.equal(velocityArrow2D(null, 100), null);
  assert.equal(velocityArrow2D([0, 0], 100), null);
  assert.equal(velocityArrow2D(["bad", 1], 100), null);

  const slow = velocityArrow2D([0.1, 0], 100);
  assert.equal(slow.lengthPixels, 40);
  assert.equal(slow.dx, 40);
  assert.equal(slow.dy, 0);

  const fast = velocityArrow2D([10, 0], 100);
  assert.equal(fast.lengthPixels, 250);
  assert.equal(velocityLength3D(0.1), 0.5);
  assert.equal(velocityLength3D(10), 4);
});

test("unit: heatmap opacity is bounded and only current density is advertised", () => {
  assert.equal(heatmapOpacityValue(-1), 0.1);
  assert.equal(heatmapOpacityValue(0.65), 0.65);
  assert.equal(heatmapOpacityValue(4), 1);
  assert.deepEqual(HEATMAP_RANGES, ["Current"]);
});

test("unit: scene layout breakpoints select desktop drawer and narrow modes", () => {
  assert.equal(layoutModeForWidth(1540), "desktop");
  assert.equal(layoutModeForWidth(1101), "desktop");
  assert.equal(layoutModeForWidth(1100), "drawer");
  assert.equal(layoutModeForWidth(700), "drawer");
  assert.equal(layoutModeForWidth(600), "narrow");
  assert.equal(layoutModeForWidth(320), "narrow");
  assert.deepEqual(SCENE_LAYOUT_BREAKPOINTS, { drawer: 1100, narrow: 600 });
});

test("integrity: visual hierarchy and supported themes remain explicit", () => {
  assert.deepEqual(SCENE_VISUAL_HIERARCHY, [
    "status",
    "primary-navigation",
    "secondary-navigation",
    "view-controls",
    "visualization",
    "inspector",
  ]);
  assert.deepEqual(
    SUPPORTED_UI_THEMES.map((theme) => theme.value),
    ["light", "light-air", "dark", "dark-command", "liquid-glass"],
  );
});

test("integrity: visual design system uses neutral surfaces and restrained theme labels", () => {
  assert.deepEqual(
    SUPPORTED_UI_THEMES.map((theme) => theme.label),
    [
      "Spatial Light",
      "Soft Light",
      "Spatial Dark",
      "Dense Dark",
      "Liquid Glass",
    ],
  );

  const css = readFileSync(
    new URL("../src/index.css", import.meta.url),
    "utf8",
  );
  assert.match(css, /--panel-raised:/);
  assert.match(css, /--surface-hover:/);
  assert.match(css, /--accent-soft:/);
  assert.match(css, /--info:/);
  assert.match(
    css,
    /\.nav-item\.active[^]*?inset 2px 0 0 rgb\(var\(--accent\)\)/,
  );
  assert.match(css, /\.incident-layout\.has-detail/);
  assert.match(css, /\.brand b \{[^]*?font-size: 15px/);
  assert.match(css, /\.nav-label \{[^]*?font-size: 11px/);
  assert.match(css, /\.nav-item \{[^]*?font-size: 13px[^]*?line-height: 1\.35/);

  const themeCss = readFileSync(
    new URL("../src/themes.css", import.meta.url),
    "utf8",
  );
  assert.match(
    themeCss,
    /dark-command[^]*?\.nav-label \{[^]*?font-size: 10\.5px/,
  );
  assert.match(themeCss, /dark-command[^]*?\.nav-item \{[^]*?font-size: 12px/);

  const appSource = readFileSync(
    new URL("../src/App.tsx", import.meta.url),
    "utf8",
  );
  assert.match(appSource, /Spatial operations/);
  assert.match(appSource, />Operations<\/div>/);
  assert.match(appSource, />Configuration<\/div>/);
  assert.doesNotMatch(appSource, /Operations · data plane/);
  assert.doesNotMatch(appSource, /Configuration · control plane/);
});

test("integrity: Liquid Glass keeps glass on chrome and visual content crisp", () => {
  const themeCss = readFileSync(
    new URL("../src/themes.css", import.meta.url),
    "utf8",
  );
  assert.match(
    themeCss,
    /data-theme="liquid-glass"[^]*?backdrop-filter: blur\(30px\)/,
  );
  assert.match(
    themeCss,
    /data-theme="liquid-glass"[^]*?\.panel[^]*?backdrop-filter: blur\(22px\)/,
  );
  assert.match(
    themeCss,
    /data-theme="liquid-glass"[^]*?\.map-frame[^]*?backdrop-filter: none/,
  );
  assert.match(themeCss, /@supports not \(\(backdrop-filter: blur\(1px\)\)\)/);
});

test("unit: keyboard selection uses native activation keys only", () => {
  assert.equal(isSelectionActivationKey("Enter"), true);
  assert.equal(isSelectionActivationKey(" "), true);
  assert.equal(isSelectionActivationKey("Spacebar"), false);
  assert.equal(isSelectionActivationKey("ArrowRight"), false);
  assert.equal(isSelectionActivationKey("Escape"), false);
});

test("integrity: scene accessibility labels and live-region policy are explicit", () => {
  assert.equal(selectionAriaLabel("object", "42"), "Inspect tracked object 42");
  assert.equal(selectionAriaLabel("camera", "Entry"), "Inspect camera Entry");
  assert.equal(selectionAriaLabel("tripwire", ""), "Inspect tripwire");
  assert.deepEqual(LIVE_REGION_POLICY, {
    sceneState: "polite",
    telemetryMetrics: "off",
  });
});

test("integrity: navigation controls and scene selections remain native keyboard-operable elements", () => {
  const appSource = readFileSync(
    new URL("../src/App.tsx", import.meta.url),
    "utf8",
  );
  assert.match(
    appSource,
    /scene-primary-nav-item[^]*?<button|<button[^]*?scene-primary-nav-item/,
  );
  assert.match(appSource, /scene-secondary-nav-item/);
  assert.match(appSource, /<input\s+[^>]*type="checkbox"/);
  assert.match(appSource, /role="button"\s+tabIndex=\{0\}/);
  assert.match(appSource, /aria-label=\{selectionAriaLabel\(\s*["']object["']/);
  assert.match(appSource, /aria-label="Select tracked object for inspector"/);
});

test("integrity: incident workspace exposes operational context and filters", () => {
  const appSource = readFileSync(
    new URL("../src/App.tsx", import.meta.url),
    "utf8",
  );
  assert.match(appSource, /aria-label="Search incidents"/);
  assert.match(appSource, /aria-label="Filter incidents by scene"/);
  assert.match(appSource, /aria-label="Filter incidents by rule type"/);
  assert.match(
    appSource,
    /aria-label="Filter incidents by region or tripwire"/,
  );
  assert.match(appSource, /aria-label="Filter incidents by event type"/);
  assert.match(appSource, /aria-label="Filter incidents by object type"/);
  assert.match(appSource, /aria-label="Filter incidents by status"/);
  assert.match(appSource, /aria-label="Filter incidents by time"/);
  assert.match(appSource, /incident-context-grid/);
  assert.match(appSource, /row\.scene_name/);
  assert.match(appSource, /row\.rule_name/);
  assert.match(appSource, /row\.object_types/);
});

test("integrity: focus and live-region policies stay narrowly scoped", () => {
  const cssSource = readFileSync(
    new URL("../src/native/native.css", import.meta.url),
    "utf8",
  );
  const statusSource = readFileSync(
    new URL("../src/ux/SceneStatusHeader.tsx", import.meta.url),
    "utf8",
  );
  const telemetrySource = readFileSync(
    new URL("../src/ux/SceneTelemetryHud.tsx", import.meta.url),
    "utf8",
  );
  assert.match(cssSource, /:focus-visible/);
  assert.match(statusSource, /role="status"/);
  assert.match(statusSource, /LIVE_REGION_POLICY\.sceneState/);
  assert.match(telemetrySource, /LIVE_REGION_POLICY\.telemetryMetrics/);
});

test("integrity: inspector and diagnostics never surface credential fields", () => {
  const inspectorSource = readFileSync(
    new URL("../src/ux/sceneInspector.ts", import.meta.url),
    "utf8",
  );
  const appSource = readFileSync(
    new URL("../src/App.tsx", import.meta.url),
    "utf8",
  );
  const telemetrySource = readFileSync(
    new URL("../src/ux/SceneTelemetryHud.tsx", import.meta.url),
    "utf8",
  );
  const diagnosticSurface = inspectorSource + "\n" + telemetrySource;
  assert.doesNotMatch(diagnosticSurface, /mqtt_password|password|secret/i);
  assert.doesNotMatch(
    appSource.slice(
      appSource.indexOf("function Map2D"),
      appSource.indexOf("function SceneSensorTelemetry"),
    ),
    /password|secret/i,
  );
});

test("regression: live scene normalization rejects non-array object payloads without crashing", () => {
  const malformed = normalizeLiveSceneState({
    stale: false,
    scene_rate: 10,
    objects: { person: [{ id: "camera-detection" }] },
  });
  assert.equal(malformed.stale, false);
  assert.equal(malformed.scene_rate, 10);
  assert.deepEqual(malformed.objects, []);

  const liveObjects = [{ id: "track-1" }];
  const valid = normalizeLiveSceneState({ stale: false, objects: liveObjects });
  assert.deepEqual(valid.objects, liveObjects);

  assert.deepEqual(normalizeLiveSceneState(null), { objects: [], stale: true });
});

test("BT-03 contract: Bluetooth management UI is explicit, accessible and quality-honest", () => {
  const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
  const ui = readFileSync(
    new URL("../src/native/BluetoothPositioning.tsx", import.meta.url),
    "utf8",
  );
  const client = readFileSync(
    new URL("../src/native/bluetoothApi.ts", import.meta.url),
    "utf8",
  );
  assert.match(app, /Bluetooth positioning/);
  assert.match(app, /<BluetoothPositioning/);
  assert.match(ui, /role="tablist"/);
  assert.match(ui, /Anchors/);
  assert.match(ui, /Tags/);
  assert.match(ui, /Diagnostics/);
  assert.match(ui, /Calibration/);
  assert.match(ui, /Battery/);
  assert.match(ui, /Unknown/);
  assert.match(ui, /Assignment history/);
  assert.match(ui, /BT-04/);
  assert.match(ui, /does not\s+fabricate anchor coordinates/i);
  assert.match(client, /\/api\/v2\/bluetooth\/anchors/);
  assert.match(client, /\/api\/v2\/bluetooth\/tags/);
  assert.match(client, /\/api\/v2\/bluetooth\/assignments/);
  assert.match(client, /\/api\/v2\/bluetooth\/diagnostics/);
});

test("BT-04 contract: calibration stores scene-local metres with reversible revisions", () => {
  const ui = readFileSync(
    new URL("../src/native/BluetoothCalibration.tsx", import.meta.url),
    "utf8",
  );
  const client = readFileSync(
    new URL("../src/native/bluetoothApi.ts", import.meta.url),
    "utf8",
  );
  assert.match(ui, /Bluetooth anchor calibration map/);
  assert.match(ui, /scene-local metres/i);
  assert.match(ui, /Y axis\s+is inverted from image pixels/i);
  assert.match(ui, /Save new draft/);
  assert.match(ui, /Publish draft/);
  assert.match(ui, /Restore/);
  assert.match(ui, /Geometry quality/);
  assert.match(ui, /Parent projection/);
  assert.match(client, /\/api\/v2\/bluetooth\/calibrations\/geometry/);
  assert.match(client, /\/publish\?revision=/);
  assert.match(client, /\/restore\?revision=/);
});
