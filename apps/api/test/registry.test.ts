import { describe, expect, it } from "vitest";
import { ENDPOINTS, GONE_ENDPOINTS, PENDING_ENDPOINTS, toHonoPath } from "../src/routes/registry";

describe("endpoint registry", () => {
  it("declares every path exactly once", () => {
    const paths = ENDPOINTS.map((e) => e.path);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it("declares at least one live endpoint", () => {
    expect(ENDPOINTS.filter((e) => e.state === "live").length).toBeGreaterThan(0);
  });

  it("partitions cleanly into live, pending and gone", () => {
    const live = ENDPOINTS.filter((e) => e.state === "live").length;
    expect(live + PENDING_ENDPOINTS.length + GONE_ENDPOINTS.length).toBe(ENDPOINTS.length);
  });

  it("uses absolute paths throughout", () => {
    for (const endpoint of ENDPOINTS) {
      expect(endpoint.path.startsWith("/")).toBe(true);
    }
  });
});

describe("pending endpoints", () => {
  it.each(PENDING_ENDPOINTS.map((e) => [e.path, e] as const))(
    "%s explains what it will serve, what blocks it, and what it used to do",
    (_path, endpoint) => {
      expect(endpoint.willServe.length).toBeGreaterThan(20);
      expect(endpoint.blockedOn).toMatch(/^phase-\d/);
      // The honesty requirement: a withdrawn endpoint has to say what it was
      // doing before, or the removal reads as a refactor rather than a retraction.
      expect(endpoint.previously.length).toBeGreaterThan(20);
    }
  );
});

describe("withdrawn endpoints", () => {
  it.each(GONE_ENDPOINTS.map((e) => [e.path, e] as const))(
    "%s gives a reason the metric cannot exist and points somewhere honest instead",
    (_path, endpoint) => {
      expect(endpoint.reason.length).toBeGreaterThan(40);
      expect(endpoint.instead.length).toBeGreaterThan(20);
    }
  );

  it("does not put withdrawn metrics on the roadmap", () => {
    for (const endpoint of GONE_ENDPOINTS) {
      expect(endpoint).not.toHaveProperty("blockedOn");
    }
  });
});

describe("toHonoPath", () => {
  it("rewrites OpenAPI placeholders to Hono parameters", () => {
    expect(toHonoPath("/players/{playerId}")).toBe("/players/:playerId");
  });

  it("rewrites every placeholder in a multi-parameter path", () => {
    expect(toHonoPath("/teams/{teamId}/games/{gameId}")).toBe("/teams/:teamId/games/:gameId");
  });

  it("leaves literal paths untouched", () => {
    expect(toHonoPath("/leaderboards/gravity")).toBe("/leaderboards/gravity");
  });

  it("is idempotent on already-converted paths", () => {
    expect(toHonoPath(toHonoPath("/players/{playerId}"))).toBe("/players/:playerId");
  });
});
