import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";

type Row = {
  personId: string;
  displayName: string | null;
  sourceLeague: string;
  predicted: number;
  pi80Low: number;
  pi80High: number;
  inSupport: boolean;
  sourceValue: number;
  supportNMovers: number;
};
type Page = { total: number; limit: number; offset: number; returned: number };
type Body = { data: Row[]; meta: { warnings: string[]; page?: Page } };

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

  it("serves every direction with observed transfers behind it", async () => {
    // Restricting to NBA destinations excluded the entire NBA player pool from
    // a feature about players who have not moved, and dropped the two
    // best-evidenced directions in the data along with it.
    for (const direction of ["EL->NBA", "GL->NBA", "NBA->EL", "NBA->GL", "GL->EL", "EL->GL"]) {
      const response = await projections(`?direction=${encodeURIComponent(direction)}`);
      expect(response.status, `${direction} should be served`).toBe(200);
    }
  });

  it("covers players from all three leagues", async () => {
    const leagues = new Set<string>();
    for (const direction of ["EL->NBA", "NBA->EL", "GL->NBA"]) {
      const body = (await (
        await projections(`?direction=${encodeURIComponent(direction)}`)
      ).json()) as Body;
      for (const row of body.data) leagues.add(row.sourceLeague);
    }
    expect(leagues).toEqual(new Set(["EL", "NBA", "GL"]));
  });

  it("rejects a direction with no observed transfers", async () => {
    const response = await projections("?direction=NBA-%3ENBA");
    expect(response.status).toBe(422);

    const body = (await response.json()) as Record<string, unknown>;
    expect(body.code).toBe("INVALID_QUERY");
  });

  it("reports the full match count, not just what it returned", async () => {
    // A page of a ranking and the whole pool look identical without this, and
    // reading the first 60 of 196 as "the 196" is the mistake it prevents.
    const body = (await (await projections("?limit=5")).json()) as Body;
    expect(body.meta.page).toBeDefined();
    expect(body.meta.page!.returned).toBe(body.data.length);
    expect(body.meta.page!.total).toBeGreaterThanOrEqual(body.data.length);
  });

  it("warns when the list is truncated", async () => {
    const body = (await (await projections("?limit=1")).json()) as Body;
    if (body.meta.page!.total > 1) {
      expect(body.meta.warnings.join(" ")).toMatch(/Showing 1 of \d+ eligible players/);
    }
  });

  it("pages without repeating or skipping a row", async () => {
    const first = (await (await projections("?limit=4&offset=0")).json()) as Body;
    const second = (await (await projections("?limit=4&offset=4")).json()) as Body;
    const overlap = first.data.filter((row) =>
      second.data.some((other) => other.personId === row.personId)
    );
    expect(overlap).toHaveLength(0);

    const all = (await (await projections("?limit=8&offset=0")).json()) as Body;
    expect(all.data.map((r) => r.personId)).toEqual([
      ...first.data.map((r) => r.personId),
      ...second.data.map((r) => r.personId),
    ]);
  });

  it("states how many observed transfers the direction rests on", async () => {
    // 134 for NBA to the G League, 14 for EuroLeague to the G League. A reader
    // deciding how much weight a row deserves needs that more than any other
    // single number.
    const body = (await (await projections()).json()) as Body;
    expect(body.data[0]!.supportNMovers).toBeGreaterThan(0);
    expect(body.meta.warnings.join(" ")).toMatch(/Fitted from \d+ observed .+ transfers/);
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
