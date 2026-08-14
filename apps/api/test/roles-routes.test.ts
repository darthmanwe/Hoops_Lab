import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";

async function get(path: string) {
  const res = await SELF.fetch(`https://api.test${path}`);
  return { res, body: (await res.json()) as Record<string, never> };
}

async function anyPersonId(): Promise<string> {
  const { body } = await get("/players/search?q=micic&limit=1");
  return (body as never as { data: { personId: string }[] }).data[0]!.personId;
}

describe("GET /archetypes", () => {
  it("returns the clusters with their exemplars", async () => {
    const { res, body } = await get("/archetypes");
    const rows = (
      body as never as { data: { cluster: number; exemplars: string; nMembers: number }[] }
    ).data;

    expect(res.status).toBe(200);
    expect(rows.length).toBeGreaterThan(2);
    expect(rows[0]!.exemplars).toBeTruthy();
    expect(rows[0]!.nMembers).toBeGreaterThan(0);
  });

  /**
   * Stability travels with the label. A clustering presented as five named
   * types, without saying that one of them barely survives resampling, claims
   * a crispness the method does not have.
   */
  it("publishes bootstrap stability for every cluster", async () => {
    const { body } = await get("/archetypes");
    const rows = (body as never as { data: { stabilityJaccard: number; reportable: boolean }[] })
      .data;

    for (const row of rows) {
      expect(row.stabilityJaccard).toBeGreaterThan(0);
      expect(row.stabilityJaccard).toBeLessThanOrEqual(1);
      expect(typeof row.reportable).toBe("boolean");
    }
  });

  it("warns when a cluster is too unstable to read as a type", async () => {
    const { body } = await get("/archetypes");
    const payload = body as never as {
      data: { reportable: boolean }[];
      meta: { warnings: string[] };
    };

    if (payload.data.some((r) => !r.reportable)) {
      expect(payload.meta.warnings.join(" ")).toContain("unclassified");
    }
  });
});

describe("GET /players/:personId/archetype", () => {
  it("returns an assignment carrying the cluster's own stability", async () => {
    const { res, body } = await get(`/players/${await anyPersonId()}/archetype`);
    const rows = (
      body as never as { data: { cluster: number; stabilityJaccard: number; exemplars: string }[] }
    ).data;

    expect(res.status).toBe(200);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows[0]!.stabilityJaccard).toBeGreaterThan(0);
  });

  it("explains itself for a player below the minutes floor", async () => {
    const { res, body } = await get("/players/nba_not_a_real_person/archetype");

    expect(res.status).toBe(404);
    expect((body as never as { code: string }).code).toBe("NO_ARCHETYPE_FOR_PLAYER");
    expect((body as never as { detail: string }).detail).toContain("500-minute");
  });
});

describe("GET /players/:personId/comps", () => {
  it("returns precomputed comparables ordered by distance", async () => {
    const { res, body } = await get(`/players/${await anyPersonId()}/comps`);
    const rows = (
      body as never as { data: { rank: number; distance: number; neighbourName: string }[] }
    ).data;

    expect(res.status).toBe(200);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows[0]!.neighbourName).toBeTruthy();
    for (let i = 1; i < rows.length; i += 1) {
      if (rows[i]!.rank > rows[i - 1]!.rank) {
        expect(rows[i]!.distance).toBeGreaterThanOrEqual(rows[i - 1]!.distance);
      }
    }
  });

  it("never returns a player as his own comparable", async () => {
    const personId = await anyPersonId();
    const { body } = await get(`/players/${personId}/comps`);
    const rows = (body as never as { data: { neighbourPersonId: string }[] }).data;

    expect(rows.every((r) => r.neighbourPersonId !== personId)).toBe(true);
  });
});

describe("GET /players/:personId/shooting", () => {
  it("exposes the shrinkage weight alongside the shrunk rate", async () => {
    const { res, body } = await get(`/players/${await anyPersonId()}/shooting`);
    const rows = (
      body as never as {
        data: { fg3PctShrunk: number; shrinkageWeight: number; priorMean: number }[];
      }
    ).data;

    expect(res.status).toBe(200);
    for (const row of rows) {
      expect(row.shrinkageWeight).toBeGreaterThanOrEqual(0);
      expect(row.shrinkageWeight).toBeLessThanOrEqual(1);
      expect(row.fg3PctShrunk).toBeGreaterThan(0);
      expect(row.fg3PctShrunk).toBeLessThan(1);
    }
  });

  /**
   * The property shrinkage exists for: a low-volume shooter's number must sit
   * near the prior rather than at his observed rate, so a 2-for-3 season does
   * not read as elite.
   */
  it("pulls low-volume seasons toward the prior", async () => {
    const { body } = await get(`/players/${await anyPersonId()}/shooting`);
    const rows = (
      body as never as {
        data: { fg3a: number; fg3PctRaw: number | null; fg3PctShrunk: number; priorMean: number }[];
      }
    ).data;

    const lowVolume = rows.filter((r) => r.fg3a > 0 && r.fg3a < 20 && r.fg3PctRaw !== null);
    for (const row of lowVolume) {
      const distanceToPrior = Math.abs(row.fg3PctShrunk - row.priorMean);
      const rawDistanceToPrior = Math.abs(row.fg3PctRaw! - row.priorMean);
      expect(distanceToPrior).toBeLessThanOrEqual(rawDistanceToPrior + 1e-9);
    }
  });
});

describe("GET /leaderboards/shooting", () => {
  it("ranks by spacing score and excludes small samples", async () => {
    const { body: seasons } = await get(`/players/${await anyPersonId()}/shooting`);
    const season = (seasons as never as { data: { seasonId: string }[] }).data[0]!.seasonId;

    const { res, body } = await get(`/leaderboards/shooting?season=${season}&limit=10`);
    if (res.status === 404) return; // fixture may not carry that season's cohort

    const rows = (body as never as { data: { spacingScore: number; fg3a: number }[] }).data;
    for (let i = 1; i < rows.length; i += 1) {
      expect(rows[i - 1]!.spacingScore).toBeGreaterThanOrEqual(rows[i]!.spacingScore);
    }
    // Ranking on a mostly-prior number would put tiny samples on top, which is
    // the exact failure shrinkage is there to prevent.
    expect(rows.every((r) => r.fg3a >= 20)).toBe(true);
  });
});
