import { defineConfig, devices } from "@playwright/test";

/**
 * End to end, in a real browser.
 * - `pnpm e2e`: on the dev server and its mock API (started if needed).
 * - `E2E_BASE=http://localhost:5199 pnpm e2e`: on a dev server already running.
 * - `NESTOR_URL=http://localhost:8090 pnpm e2e:live`: against a real Nestor (see e2e/live).
 */
const base = process.env.E2E_BASE ?? process.env.NESTOR_URL;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  use: { baseURL: base ?? "http://localhost:5173", locale: "fr-FR", trace: "on-first-retry" },
  projects: [
    { name: "light", use: { ...devices["Desktop Chrome"], colorScheme: "light" }, testIgnore: /\/e2e\/live\// },
    {
      name: "dark",
      use: { ...devices["Desktop Chrome"], colorScheme: "dark" },
      testIgnore: /\/e2e\/live\//,
      testMatch: /\/e2e\/(open-states|home|overflow)\.spec\.ts$/,
    },
    { name: "live", use: { ...devices["Desktop Chrome"] }, testMatch: /\/e2e\/live\/.+\.spec\.ts$/ },
  ],
  webServer: base ? undefined : { command: "pnpm dev", url: "http://localhost:5173", reuseExistingServer: true },
});
