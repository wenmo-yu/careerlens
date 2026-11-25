import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end configuration.
 *
 * The suite runs against a real backend and a production build; mocking the API
 * would test nothing that the 245 unit tests do not already cover. Start the
 * API and `next start` first (scripts/e2e-local.sh does both).
 *
 * Locally set PW_CHANNEL=msedge (or chrome) to reuse an installed browser
 * instead of downloading Chromium.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }]]
    : [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    video: "off",
    screenshot: "only-on-failure",
    channel: process.env.PW_CHANNEL || undefined,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
