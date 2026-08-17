import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";

type Row = {
  personId: string;
  displayName: string | null;
  predicted: number;
  pi80Low: number;
  pi80High: number;
  inSupport: boolean;
  sourceValue: number;
};
type Body = { data: Row[]; meta: { warnings: string[] } };

async function projections(query = ""): Promise<Response> {
  return SELF.fetch(`https://api.test/projections${query}`);
}

describe("GET /projections", () => {
  it("ranks players who have not made the move", async () => {
    const response = await projections("?direction=EL-%3ENBA");
    expect(response.status).toBe(200);

    const body = (await response.json()) as Body;
    expect(body.data.length).toBeGreaterThan(0);

    const predicted = body.data.map((row) => row.predicted);
    expect(predicted).toEqual([...predicted].sort((a, b) => b - a));
  });

  it("never serves a point estimate without an interval", async () => {
    const body = (await (await projections()).json()) as Body;
    for (const row of body.data) {
      expect(row.pi80Low).toBeLessThan(row.predicted);
      expect(row.pi80High).toBeGreaterThan(row.predicted);
    }
  });

  it("states the conditioning in every response", async () => {
    // The estimate is only meaningful conditional on a transfer happening, and
    // this endpoint is the one place that condition is counterfactual. A caller
    // must not be able to read the numbers without reading that.
    const body = (await (await projections()).json()) as Body;
    const warnings = body.meta.warnings.join(" ");
    expect(warnings).toMatch(/have not transferred/i);
    expect(warnings).toMatch(/conditional on a transfer/i);
  });

  it("warns when rows fall outside the observed range", async () => {
    const body = (await (await projections()).json()) as Body;
    const outOfSupport = body.data.filter((row) => !row.inSupport).length;
    const warnings = body.meta.warnings.join(" ");

    if (outOfSupport > 0) {
      expect(warnings).toMatch(/extrapolating/i);
      expect(warnings).toContain(String(outOfSupport));
    }
  });

  it("can filter to rows the model is entitled to speak about", async () => {
    const body = (await (await projections("?inSupportOnly=true")).json()) as Body;
    expect(body.data.every((row) => row.inSupport)).toBe(true);
  });

  it("hides out-of-support rows only when asked", async () => {
    // Ranking by projection puts the highest-usage players first, and those are
    // the ones beyond the observed range — so the default view must show them.
    const shown = (await (await projections()).json()) as Body;
    const filtered = (await (await projections("?inSupportOnly=true")).json()) as Body;
    expect(shown.data.length).toBeGreaterThanOrEqual(filtered.data.length);
  });

  it("rejects a direction it has no projections for", async () => {
    const response = await projections("?direction=NBA-%3EEL");
    expect(response.status).toBe(422);

    const body = (await response.json()) as Record<string, unknown>;
    expect(body.code).toBe("INVALID_QUERY");
  });

  it("rejects a nonsense limit rather than clamping silently", async () => {
    expect((await projections("?limit=9999")).status).toBe(422);
  });

  it("is listed in the endpoint registry", async () => {
    const body = (await (await SELF.fetch("https://api.test/")).json()) as {
      endpoints: { path: string }[];
    };
    expect(body.endpoints.map((e) => e.path)).toContain("/projections");
  });
});
