import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { ENDPOINTS, GONE_ENDPOINTS, PENDING_ENDPOINTS, toHonoPath } from "../src/routes/registry";

/** Substitutes a sample value for every `:param` so a path can be requested. */
function concretise(path: string): string {
  return toHonoPath(path).replace(/:(\w+)/g, "sample-id");
}

describe("GET /", () => {
  it("lists every registered endpoint", async () => {
    const res = await SELF.fetch("https://api.test/");
    expect(res.status).toBe(200);

    const body = (await res.json()) as { endpoints: { path: string }[]; status: string };
    expect(body.status).toBe("live");
    expect(body.endpoints.map((e) => e.path).sort()).toEqual(ENDPOINTS.map((e) => e.path).sort());
  });

  it("reports counts that match the registry", async () => {
    const res = await SELF.fetch("https://api.test/");
    const body = (await res.json()) as {
      counts: { live: number; pending: number; withdrawn: number };
    };

    expect(body.counts.pending).toBe(PENDING_ENDPOINTS.length);
    expect(body.counts.withdrawn).toBe(GONE_ENDPOINTS.length);
  });
});

describe("GET /health", () => {
  it("probes D1 and KV rather than reporting a bare ok", async () => {
    const res = await SELF.fetch("https://api.test/health");
    expect(res.status).toBe(200);

    const body = (await res.json()) as {
      status: string;
      dependencies: { d1: { ok: boolean }; kv: { ok: boolean } };
    };
    expect(body.status).toBe("ok");
    expect(body.dependencies.d1.ok).toBe(true);
    expect(body.dependencies.kv.ok).toBe(true);
  });
});

describe("withdrawn analytics endpoints", () => {
  it.each(PENDING_ENDPOINTS.map((e) => [e.path] as const))(
    "%s returns 501 problem+json naming what it previously served",
    async (path) => {
      const res = await SELF.fetch(`https://api.test${concretise(path)}`);

      expect(res.status).toBe(501);
      expect(res.headers.get("content-type")).toContain("application/problem+json");

      const body = (await res.json()) as Record<string, unknown>;
      expect(body.code).toBe("UNDER_RECONSTRUCTION");
      expect(body.previously).toBeTruthy();
      expect(body.blocked_on).toBeTruthy();
    }
  );

  it.each(GONE_ENDPOINTS.map((e) => [e.path] as const))(
    "%s returns 410 because the metric is not coming back",
    async (path) => {
      const res = await SELF.fetch(`https://api.test${concretise(path)}`);

      expect(res.status).toBe(410);

      const body = (await res.json()) as Record<string, unknown>;
      expect(body.code).toBe("METRIC_WITHDRAWN");
      expect(body.instead).toBeTruthy();
    }
  );
});

describe("unknown routes", () => {
  it("404s rather than being swallowed by the reconstruction handlers", async () => {
    const res = await SELF.fetch("https://api.test/does-not-exist");
    expect(res.status).toBe(404);

    const body = (await res.json()) as Record<string, unknown>;
    expect(body.code).toBe("ROUTE_NOT_FOUND");
  });

  it("distinguishes a withdrawn endpoint from one that never existed", async () => {
    const withdrawnRes = await SELF.fetch("https://api.test/leaderboards/gravity");
    const unknownRes = await SELF.fetch("https://api.test/leaderboards/nonsense");

    expect(withdrawnRes.status).toBe(410);
    expect(unknownRes.status).toBe(404);
  });
});

describe("cross-cutting response guarantees", () => {
  const allPaths = ENDPOINTS.map((e) => concretise(e.path));

  it.each(allPaths.map((p) => [p] as const))("%s carries a request id", async (path) => {
    const res = await SELF.fetch(`https://api.test${path}`);
    expect(res.headers.get("X-Request-Id")).toBeTruthy();
  });

  it("never advertises an Authorization header it does not accept", async () => {
    const res = await SELF.fetch("https://api.test/health");
    expect(res.headers.get("access-control-allow-headers") ?? "").not.toContain("Authorization");
  });

  /**
   * The phase 0 exit criterion, encoded as a test: no endpoint may answer 200
   * with data. Only the service listing and the health probe are live, and
   * neither reports a basketball statistic. If a future change re-enables a
   * data route before it is backed by a fitted model over real data, this
   * fails.
   */
  /**
   * The guarantee that survives from phase 0: an endpoint serves data only
   * once it is backed by real, fitted output. Anything still marked pending or
   * withdrawn must fail loudly rather than return a plausible number.
   */
  it("serves nothing that is not backed by a model or real data", async () => {
    const notLive = ENDPOINTS.filter((e) => e.state !== "live").map((e) => concretise(e.path));

    for (const path of notLive) {
      const res = await SELF.fetch(`https://api.test${path}`);
      expect(res.ok, `${path} answered ${res.status}; it must not serve data yet`).toBe(false);
    }
  });

  it("every live endpoint actually answers", async () => {
    const live = ENDPOINTS.filter((e) => e.state === "live").map((e) => e.path);

    for (const path of live) {
      // Parameterised live paths need a real id, which the dedicated suites
      // cover; here we only require that the route is reachable.
      if (path.includes("{")) continue;
      const res = await SELF.fetch(`https://api.test${path}`);
      expect([200, 404, 422]).toContain(res.status);
    }
  });
});
