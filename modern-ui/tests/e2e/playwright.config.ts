/* SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "sceneWorkspace.spec.ts",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:4173",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: {
      args: ["--enable-webgl", "--use-gl=swiftshader"],
    },
  },
  webServer: {
    command: "npx vite --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173/tests/e2e/index.html",
    reuseExistingServer: false,
    timeout: 120000,
  },
});
