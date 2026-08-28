import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";

/**
 * The report route against a snapshot that contains no reports.
 *
 * That is the state the fixture is in, and it is the state worth testing
 * hardest: reports exist only where a model actually wrote one, so "no report
 * for this player" is a normal answer the API has to give well rather than an
 * error condition. A route that invented prose here — or that 500'd — would be
 * the same defect this project was rebuilt to remove, wearing a different hat.
 */
describe("GET /players/:personId/report", () => {
  it("explains the absence rather than fabricating a report", async () => {
    const response = await SELF.fetch("https://api.test/players/nba_1628426/report");

    expect(response.status).toBe(404);
    expect(response.headers.get("content-type")).toContain("application/problem+json");

    const body = (await response.json()) as Record<string, unknown>;
    expect(body.code).toBe("NO_REPORT_FOR_PLAYER");
    // The reader is told how a report comes to exist, not just that one does not.
    expect(String((body.how as string) ?? "")).toContain("hoopslab report");
  });

  it("answers the same way for an unknown player", async () => {
    const response = await SELF.fetch("https://api.test/players/not-a-person/report");
    expect(response.status).toBe(404);

    const body = (await response.json()) as Record<string, unknown>;
    expect(body.code).toBe("NO_REPORT_FOR_PLAYER");
  });

  it("treats the named variant as a separate lookup", async () => {
    // Anonymized and named reports are different rows with different audits, so
    // asking for one must never fall back to serving the other.
    const response = await SELF.fetch("https://api.test/players/nba_1628426/report?named=true");
    expect(response.status).toBe(404);
  });

  it("is listed in the endpoint registry", async () => {
    const response = await SELF.fetch("https://api.test/");
    const body = (await response.json()) as { endpoints: { path: string }[] };
    const paths = body.endpoints.map((endpoint) => endpoint.path);

    expect(paths).toContain("/players/{personId}/report");
  });
});
