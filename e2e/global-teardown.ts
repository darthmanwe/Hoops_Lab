import { probeApi } from "./servers";

/**
 * Say so if the API died during the run.
 *
 * The case `global-setup.ts` cannot catch. In CI on 2026-09-04 and again on
 * 2026-09-07, `wrangler dev` came up, passed the health check Playwright waits
 * on, and then exited about twenty-five seconds later printing an empty
 * `✘ [ERROR]`. Every subsequent test failed on missing page content, so the
 * report described sixty-four broken pages and nothing described the one dead
 * process that caused them.
 *
 * This runs before Playwright stops the servers it started, so an API that is
 * silent here exited on its own.
 */
export default async function globalTeardown(): Promise<void> {
  const probe = await probeApi();
  if (probe.ok) return;

  console.error(
    [
      "",
      "  The API was not answering when the suite finished.",
      `  ${probe.why}`,
      "",
      "  It answered at the start of the run, so it exited during it, and any",
      "  failure above about missing page content is a symptom of that rather",
      "  than of the page. The Worker's own log is the place to look:",
      "  ~/.config/.wrangler/logs/ locally, and the `wrangler-logs` artifact",
      "  on a CI run.",
      "",
    ].join("\n")
  );
}
