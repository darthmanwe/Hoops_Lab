import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";

/** Every response carries provenance; this pulls it out for assertions. */
async function get(path: string) {
  const res = await SELF.fetch(`https://api.test${path}`);
  return { res, body: (await res.json()) as Record<string, never> };
}

describe("GET /players/search", () => {
  it("finds a player by name", async () => {
    const { res, body } = await get("/players/search?q=micic");

    expect(res.status).toBe(200);
    expect((body as never as { data: unknown[] }).data.length).toBeGreaterThan(0);
  });

  /**
   * The reason the normalised column exists: nobody types the diacritics, and
   * an accent-sensitive search silently loses every player who has them.
   *
   * Note what is asserted. The *display* name keeps its diacritics — the feed
   * really does say "Luka Dončić" — so the match has to be checked against the
   * de-accented form. Comparing the raw display name to an ASCII needle would
   * fail even though the search worked, which is how this test was first
   * written and what it taught.
   */
  it("finds an accented name typed without accents", async () => {
    const { body } = await get("/players/search?q=doncic");
    const names = (body as never as { data: { displayName: string }[] }).data.map(
      (p) => p.displayName
    );

    const deaccented = names.join(" ").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();

    expect(names.length).toBeGreaterThan(0);
    expect(deaccented).toContain("doncic");
    // And the accented spelling really is preserved for display.
    expect(names.some((n) => n !== n.normalize("NFKD").replace(/[̀-ͯ]/g, ""))).toBe(true);
  });

  it("ranks cross-league players first", async () => {
    const { body } = await get("/players/search?q=a&limit=10");
    const rows = (body as never as { data: { leagues: string }[] }).data;

    expect(rows[0]?.leagues).toContain("+");
  });

  it("rejects an empty query with problem+json", async () => {
    const { res, body } = await get("/players/search?q=");

    expect(res.status).toBe(422);
    expect((body as never as { code: string }).code).toBe("INVALID_QUERY");
  });

  it("caps the page size rather than trusting the caller", async () => {
    const { res } = await get("/players/search?q=a&limit=9999");
    expect(res.status).toBe(422);
  });

  it("reports the data snapshot it served from", async () => {
    const { body } = await get("/players/search?q=micic");
    expect((body as never as { meta: { snapshot: string } }).meta.snapshot).toBeTruthy();
  });
});

describe("GET /players/:personId", () => {
  async function anyPersonId(): Promise<string> {
    const { body } = await get("/players/search?q=micic&limit=1");
    return (body as never as { data: { personId: string }[] }).data[0]!.personId;
  }

  it("returns a career spanning every league the person played in", async () => {
    const { res, body } = await get(`/players/${await anyPersonId()}`);
    const data = (
      body as never as { data: { seasons: { league: string }[]; identities: unknown[] } }
    ).data;

    expect(res.status).toBe(200);
    expect(new Set(data.seasons.map((s) => s.league)).size).toBeGreaterThan(1);
    expect(data.identities.length).toBeGreaterThan(0);
  });

  it("orders seasons chronologically across leagues", async () => {
    const { body } = await get(`/players/${await anyPersonId()}`);
    const orders = (
      body as never as { data: { seasons: { seasonOrder: number }[] } }
    ).data.seasons.map((s) => s.seasonOrder);

    expect(orders).toEqual([...orders].sort((a, b) => a - b));
  });

  it("404s with a pointer to search for an unknown person", async () => {
    const { res, body } = await get("/players/nba_does_not_exist");

    expect(res.status).toBe(404);
    expect((body as never as { code: string }).code).toBe("PERSON_NOT_FOUND");
  });
});

describe("GET /players/:personId/translation", () => {
  async function personWithTransition(): Promise<string> {
    const { body } = await get("/leaderboards/translation?limit=1");
    return (body as never as { data: { personId: string }[] }).data[0]!.personId;
  }

  /**
   * The modelling commitment, enforced end to end: the schema makes the
   * interval columns NOT NULL, so a point estimate cannot be stored — and
   * therefore cannot be served — without one.
   */
  it("never serves a point estimate without an interval", async () => {
    const { res, body } = await get(`/players/${await personWithTransition()}/translation`);
    const rows = (
      body as never as {
        data: { predicted: number; pi80Low: number; pi80High: number; pi95Low: number }[];
      }
    ).data;

    expect(res.status).toBe(200);
    for (const row of rows) {
      expect(row.pi80Low).toBeLessThan(row.predicted);
      expect(row.pi80High).toBeGreaterThan(row.predicted);
      expect(row.pi95Low).toBeLessThan(row.pi80Low);
    }
  });

  it("attaches the model version and its measured error", async () => {
    const { body } = await get(`/players/${await personWithTransition()}/translation`);
    const model = (
      body as never as {
        meta: { model: { version: string; primary_value: number; primary_ci: number[] } };
      }
    ).meta.model;

    expect(model.version).toMatch(/^translation-v/);
    expect(model.primary_value).toBeGreaterThan(0);
    expect(model.primary_ci[0]).toBeLessThan(model.primary_ci[1]!);
  });

  it("explains itself when a player never changed league", async () => {
    const { body: search } = await get("/players/search?q=a&limit=50");
    const rows = (search as never as { data: { personId: string; leagues: string }[] }).data;
    const singleLeague = rows.find((p) => !p.leagues.includes("+"));
    if (!singleLeague) return;

    const { res, body } = await get(`/players/${singleLeague.personId}/translation`);
    expect(res.status).toBe(404);
    expect((body as never as { code: string }).code).toBe("NO_TRANSITION_FOR_PLAYER");
  });
});

describe("GET /models", () => {
  it("lists the registry with measured headline metrics", async () => {
    const { res, body } = await get("/models");
    const rows = (body as never as { data: { modelVersion: string; primaryValue: number }[] }).data;

    expect(res.status).toBe(200);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows[0]!.primaryValue).toBeGreaterThan(0);
  });

  it("serves the evaluation, its baselines and the selection analysis", async () => {
    const { body: registry } = await get("/models");
    const version = (registry as never as { data: { modelVersion: string }[] }).data[0]!
      .modelVersion;

    const { res, body } = await get(`/models/${version}/evaluation`);
    const data = (
      body as never as {
        data: {
          evaluations: { baselineName: string; mae: number; baselineMae: number }[];
          selection: { direction: string; gapSd: number }[];
          interpretation: { estimand: string };
        };
      }
    ).data;

    expect(res.status).toBe(200);
    expect(data.evaluations.length).toBeGreaterThan(0);
    expect(data.selection.length).toBeGreaterThan(0);
    // The caveat travels with the numbers rather than living only in prose.
    expect(data.interpretation.estimand).toContain("Conditional on a transition");
  });

  it("beats the folk rule, and says so in the served data", async () => {
    const { body: registry } = await get("/models");
    const version = (registry as never as { data: { modelVersion: string }[] }).data[0]!
      .modelVersion;

    const { body } = await get(`/models/${version}/evaluation`);
    const evaluations = (
      body as never as {
        data: {
          evaluations: { metric: string; baselineName: string; mae: number; baselineMae: number }[];
        };
      }
    ).data.evaluations;

    const folk = evaluations.find((e) => e.baselineName === "folk_0.75" && e.metric === "usg_pct");
    expect(folk).toBeDefined();
    expect(folk!.mae).toBeLessThan(folk!.baselineMae);
  });
});

describe("GET /leaderboards/translation", () => {
  it("returns ranked predictions with intervals", async () => {
    const { res, body } = await get("/leaderboards/translation?direction=EL->NBA&limit=5");
    const rows = (
      body as never as { data: { predicted: number; pi80Low: number; displayName: string }[] }
    ).data;

    expect(res.status).toBe(200);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows[0]!.displayName).toBeTruthy();
    // Sorted descending by prediction.
    for (let i = 1; i < rows.length; i += 1) {
      expect(rows[i - 1]!.predicted).toBeGreaterThanOrEqual(rows[i]!.predicted);
    }
  });

  it("404s on a direction that has no predictions", async () => {
    const { res, body } = await get("/leaderboards/translation?direction=NOPE");

    expect(res.status).toBe(404);
    expect((body as never as { code: string }).code).toBe("NO_PREDICTIONS_FOR_FILTER");
  });
});
