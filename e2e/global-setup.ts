import { API, probeApi } from "./servers";

/**
 * Refuse to start if the API is not actually up.
 *
 * Playwright waits for `/health` to answer before running anything, so this
 * should never fire — but "should never fire" is why it is cheap. What it costs
 * one request, it saves in a failure that reads as sixty-four browser
 * assertions finding no text on the page, which is what a dead API looks like
 * from inside a suite whose pages render an explanation card instead of an
 * error. That failure has happened twice in CI and took a log archaeology dig
 * to attribute; this turns the same event into one line naming the cause.
 */
export default async function globalSetup(): Promise<void> {
  const probe = await probeApi();
  if (!probe.ok) {
    throw new Error(
      `The API at ${API} is not serving data, so every assertion below would fail ` +
        `as "element not found" rather than saying this.\n  ${probe.why}`
    );
  }
}
