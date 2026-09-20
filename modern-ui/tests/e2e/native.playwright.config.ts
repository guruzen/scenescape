/* SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import { defineConfig, devices } from "@playwright/test"

export default defineConfig({
  testDir: ".",
  testMatch: "nativeSceneWorkspace.spec.ts",
  outputDir: "../../test-results-native",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:4174",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: {
      args: ["--enable-webgl", "--use-gl=swiftshader"],
    },
  },
  webServer: {
    command: "cd ../.. && npx vite --config vite.native-tests.config.ts",
    url: "http://127.0.0.1:4174/tests/harness.html",
    reuseExistingServer: false,
    timeout: 120000,
  },
})
