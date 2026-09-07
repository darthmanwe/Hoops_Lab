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
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // No retries, deliberately. A retry cannot help the failure this suite
  // actually has in CI - the API Worker exiting mid-run - because Playwright
  // does not restart a `webServer` that dies, so every retry would fail against
  // the same dead process. What it would do is turn a real regression into a
  // flake that passes on the second attempt.
  retries: 0,
  // One worker, including in CI - and this used to say two there.
  //
  // The reason given for one worker locally was that parallel workers against a
  // single miniflare D1 file produced flaky reads rather than faster runs. That
  // reason does not stop applying on a runner: there is still one D1 file and
  // still one `wrangler dev` serving it, on a smaller machine. CI ran two
  // anyway, and the e2e job has since failed twice with the API Worker exiting
  // partway through the run for no reason it was willing to print.
  //
  // Whether the concurrency caused those exits is not established. What is
  // established is that the config carried a finding and then contradicted it
  // in the one environment nobody watches interactively. The suite takes about
  // forty seconds serially, against a job that spends minutes on `npm ci` and
  // installing a browser, so the second worker was not buying much to begin
  // with.
  workers: 1,
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
      // Piped on CI, ignored locally. When this Worker exited mid-run the only
      // trace in the job log was an empty `✘ [ERROR]` on stderr; whatever
      // context preceded it went to stdout and was discarded by this line.
      stdout: process.env.CI ? "pipe" : "ignore",
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
