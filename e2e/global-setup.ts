import { PAGES } from "./pages";
import { API, FIXTURE_SNAPSHOT, WEB, get, probeApi } from "./servers";

/**
 * Prove the stack is real, then compile it, before a browser exists.
 *
 * Three jobs, in order, and each one exists because of something that has
 * actually happened here.
 *
 * **The API is answering.** Playwright waits for `/health` before running
 * anything, so this should never fire — which is why it is cheap. What it costs
 * one request, it saves in a failure that reads as sixty-four browser
 * assertions finding no text, which is what a dead API looks like from inside a
 * suite whose pages render an explanation card instead of an error.
 *
 * **It is the local API.** Every page renders the snapshot id it was served,
 * and `hoopslab fixture` writes a distinctive one. If a build ever picks up
 * `apps/web/.env.production` — which points `NEXT_PUBLIC_API_BASE` at the
 * deployed Worker — this suite would quietly grade the live site instead of the
 * committed fixture, pass, and mean nothing. Asserting on the id is the cheapest
 * way to make that impossible rather than merely unlikely.
 *
 * **The routes are compiled.** `next dev` compiles a route the first time it is
 * requested, so under the old arrangement the compiler ran while Chromium was
 * already up. The API Worker has died mid-run three times on CI, killed with no
 * error of its own on a 7 GB runner, and a compile spike beside a browser is
 * the largest thing in that box. Warming here moves the spike to a moment when
 * nothing else is running, and costs a few seconds of what would have been the
 * first test's latency anyway.
 */
export default async function globalSetup(): Promise<void> {
  const probe = await probeApi();
  if (!probe.ok) {
    throw new Error(
      `The API at ${API} is not serving data, so every assertion below would fail ` +
        `as "element not found" rather than saying this.\n  ${probe.why}`
    );
  }

  let sawFixture = false;

  for (const page of PAGES) {
    const res = await get(`${WEB}${page.path}`);

    if (res instanceof Error) {
      throw new Error(`${WEB}${page.path} did not answer while warming: ${res.message}`);
    }
    if (res.status !== 200) {
      throw new Error(`${WEB}${page.path} answered ${res.status} while warming.`);
    }
    if (res.text.includes(FIXTURE_SNAPSHOT)) sawFixture = true;
  }

  if (!sawFixture) {
    throw new Error(
      `No page reported snapshot "${FIXTURE_SNAPSHOT}", so the web app is not reading the ` +
        `fixture-seeded API at ${API}.\n` +
        "  The likeliest cause is NEXT_PUBLIC_API_BASE resolving to the deployed Worker, " +
        "which would make this suite grade production and pass without testing anything here.\n" +
        "  Reseed with `npm run db:migrate && npm run db:load:fixture` if the database is the " +
        "problem instead."
    );
  }
}
