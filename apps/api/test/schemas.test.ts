/**
 * The zod schemas must describe what the builders actually produce.
 *
 * `schemas.ts` mirrors `envelope.ts` and `problem.ts` rather than replacing
 * them, which buys a runtime that stays cheap and costs the usual risk of a
 * mirror: it can stop matching without anything failing. A generated OpenAPI
 * document built from a stale mirror is worse than no document, because it is
 * wrong with authority.
 *
 * So these tests do not check the schemas against a hand-written fixture. They
 * run the real builders and parse the real output.
 */

import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { Hono } from "hono";
import { envelope } from "../src/http/envelope";
import { problem, PROBLEM_CONTENT_TYPE } from "../src/http/problem";
import { EnvelopeSchema, ERROR_CODES, MetaSchema, ProblemSchema } from "../src/http/schemas";
import { z } from "@hono/zod-openapi";

/** Runs a handler through a real Hono context, since both builders need one. */
async function render(handler: (c: Parameters<typeof envelope>[0]) => unknown): Promise<unknown> {
  const app = new Hono();
  app.get("/", (c) => {
    const result = handler(c);
    return result instanceof Response ? result : c.json(result as object);
  });
  const res = await app.request("/");
  return res.json();
}

describe("the envelope schema describes the envelope", () => {
  it("accepts a minimal envelope", async () => {
    const body = await render((c) => envelope(c, { rows: [] }));
    const parsed = EnvelopeSchema(z.object({ rows: z.array(z.unknown()) })).safeParse(body);

    expect(parsed.success, JSON.stringify(parsed.error?.issues)).toBe(true);
  });

  it("accepts every optional block the builder can attach", async () => {
    // All three at once. Each is spread conditionally in `envelope()` to
    // satisfy exactOptionalPropertyTypes, so a schema that got one of them
    // wrong would still pass on a response that happened to omit it.
    const body = await render((c) =>
      envelope(c, [], {
        snapshot: "ee6b530f0aa0",
        warnings: ["the top rows are outside the fitted range"],
        resolved: {
          season_id: "NBA_2024",
          requested_season_id: null,
          resolution: "latest_available",
        },
        model: {
          name: "translation",
          version: "translation-v1.0",
          primary_metric: "usg_pct",
          primary_value: 0.0332,
          primary_ci: [0.0301, 0.0364],
          card: "docs/model-card.md",
        },
        page: { total: 196, limit: 100, offset: 0, returned: 100 },
      })
    );

    const parsed = EnvelopeSchema(z.array(z.unknown())).safeParse(body);
    expect(parsed.success, JSON.stringify(parsed.error?.issues)).toBe(true);
  });

  it("rejects a meta that lost its warnings array", () => {
    // `warnings` is the one non-optional field a caller might reasonably think
    // is optional, and it is how a route says "this answer has a caveat".
    const parsed = MetaSchema.safeParse({
      request_id: "abc",
      snapshot: null,
      generated_at: new Date().toISOString(),
    });

    expect(parsed.success).toBe(false);
  });
});

describe("the problem schema describes every problem", () => {
  it("accepts a bare problem document", async () => {
    const body = await render((c) =>
      problem(c, {
        status: 404,
        code: "PERSON_NOT_FOUND",
        title: "No such person",
        detail: "nobody by that id",
      })
    );

    const parsed = ProblemSchema.safeParse(body);
    expect(parsed.success, JSON.stringify(parsed.error?.issues)).toBe(true);
  });

  it("keeps the extension members rather than stripping them", async () => {
    // The default zod object would drop `directions`, and the schema would then
    // describe a response that omits the only field telling the caller what to
    // ask for instead. `.catchall` is what makes RFC 9457 extensions survive.
    const body = await render((c) =>
      problem(c, {
        status: 404,
        code: "NO_PREDICTIONS_FOR_FILTER",
        title: "No predictions match that filter",
        detail: "nothing for that direction",
        extensions: { directions: ["EL->NBA", "NBA->EL"] },
      })
    );

    const parsed = ProblemSchema.parse(body);
    expect(parsed.directions).toEqual(["EL->NBA", "NBA->EL"]);
  });
});

describe("the error catalogue matches the API", () => {
  it("documents every code the source can emit", async () => {
    // Guards the direction that actually rots: a new `problem()` call with a
    // fresh code, whose `type` link then points at an anchor docs/errors.md
    // does not contain. Eleven of fifteen were in that state before this
    // catalogue existed.
    const sources = import.meta.glob("../src/**/*.ts", { eager: true, query: "?raw" });
    const emitted = new Set<string>();
    for (const module of Object.values(sources)) {
      const text = (module as { default: string }).default;
      for (const match of text.matchAll(/code: "([A-Z_]+)"/g)) {
        if (match[1]) emitted.add(match[1]);
      }
    }

    // Without this the test passes when the glob returns nothing, which is the
    // failure mode of every scan-the-source check: it goes quiet rather than red.
    expect(emitted.size, "the source scan found no error codes at all").toBeGreaterThan(10);

    const documented = new Set(Object.keys(ERROR_CODES));
    const undocumented = [...emitted].filter((code) => !documented.has(code));

    expect(undocumented, `emitted but absent from ERROR_CODES: ${undocumented.join(", ")}`).toEqual(
      []
    );
  });

  it("parses queries with zod itself, never the re-export", () => {
    // `@hono/zod-openapi` re-exports a `z` whose `safeParse` returns `any`.
    // Verified rather than assumed: with the re-export,
    // `const s: string = Query.safeParse({}).data.limit` typechecks against a
    // schema declaring `limit` a number; with plain zod it is an error.
    //
    // So a schema built from the re-export and then parsed hands back untyped
    // data, silently reopening the `Record<string, unknown>` hole this rewrite
    // closed — and it fails open, with no error anywhere. The split imports in
    // the route files are load-bearing, and look enough like clutter that
    // someone will tidy them back into one. This is what stops that.
    const sources = import.meta.glob("../src/**/*.ts", { eager: true, query: "?raw" });
    const offenders: string[] = [];
    let parsing = 0;

    for (const [path, module] of Object.entries(sources)) {
      const text = (module as { default: string }).default;
      if (!text.includes(".safeParse(")) continue;
      parsing += 1;
      if (!/import \{ z as \w+ \} from "zod"/.test(text)) offenders.push(path);
    }

    // Four route files validate a query. Pinning the count keeps this from
    // going quiet: a scan that matches nothing reports no offenders, which
    // reads exactly like a pass.
    expect(parsing, "found no file that parses a query").toBeGreaterThanOrEqual(4);

    expect(
      offenders,
      `these parse a schema but never import zod directly, so the parsed values ` +
        `are almost certainly \`any\`: ${offenders.join(", ")}`
    ).toEqual([]);
  });

  it("gives every code a status, a cause and something to do about it", () => {
    for (const [code, entry] of Object.entries(ERROR_CODES)) {
      expect(entry.status, code).toBeGreaterThanOrEqual(400);
      expect(entry.when.length, code).toBeGreaterThan(20);
      expect(entry.action.length, code).toBeGreaterThan(20);
    }
  });

  it("serves the status the catalogue claims", async () => {
    // Spot-check against the live app rather than trusting the table: a 410
    // documented as a 501 would send a client into a retry loop over something
    // that is never coming back.
    const gone = await SELF.fetch("https://api.test/leaderboards/gravity");
    expect(gone.status).toBe(ERROR_CODES.METRIC_WITHDRAWN.status);
    expect(gone.headers.get("content-type")).toContain(PROBLEM_CONTENT_TYPE);

    const missing = await SELF.fetch("https://api.test/no-such-path");
    expect(missing.status).toBe(ERROR_CODES.ROUTE_NOT_FOUND.status);
  });
});
