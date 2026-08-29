import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against a local stack seeded from committed data.
 *
 * Two servers, not one. The web app is entirely server components, so every
 * page fetches from the API Worker during render rather than in the browser —
 * and `apiGetOptional` turns a failed fetch into a rendered "could not reach
 * the API" card rather than an error. A suite pointed at a dead backend
 * therefore gets HTTP 200 and a complete-looking page on every route, and would
 * pass while asserting nothing. The API is booted here so the assertions mean
 * something, and every spec checks for content only a real response produces.
 *
 * Seeded from `apps/api/test/fixtures/seed.sql`, the same committed slice the
 * Worker suite loads, so a passing run does not depend on the developer's
 * `data/` directory or on anything being deployed.
 */

const WEB = "http://127.0.0.1:3710";
const API = "http://127.0.0.1:8710";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  // One worker locally. The two dev servers are the bottleneck, not the tests,
  // and parallel workers against a single miniflare D1 file produced flaky
  // reads rather than faster runs.
  workers: process.env.CI ? 2 : 1,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"]],

  use: {
    baseURL: WEB,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "dark",
      use: { ...devices["Desktop Chrome"], colorScheme: "dark" },
    },
    {
      // The same suite in the other theme. Light mode is not a separate feature
      // with separate tests: it is the same pages, and the way it breaks is by
      // rendering something unreadable rather than by throwing.
      name: "light",
      use: { ...devices["Desktop Chrome"], colorScheme: "light" },
    },
  ],

  webServer: [
    {
      command: "npm run dev -w hoopslab-api",
      url: `${API}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      command: "npm run dev -w hoopslab-web",
      url: WEB,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: "ignore",
      stderr: "pipe",
    },
  ],
});
