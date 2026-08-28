import { createRoute, OpenAPIHono, z } from "@hono/zod-openapi";
import { and, count, desc, eq, gte } from "drizzle-orm";
// The re-exported `z` above carries `.openapi()` but loses `safeParse`'s return
// type to `any`, which would make the parsed query untyped from here down —
// the exact hole the rest of this rewrite closed. Schemas that reach the
// document use the re-export; schemas that are parsed use zod itself.
import { z as zRuntime } from "zod";
import { createDb, schema } from "../db/client";
import type { Env } from "../env";
import { envelope } from "../http/envelope";
import { PROBLEM_CONTENT_TYPE, problem } from "../http/problem";
import { EnvelopeSchema, ProblemSchema } from "../http/schemas";
import { snapshotId } from "../lib/snapshot";

export const projectionsRoute = new OpenAPIHono<{ Bindings: Env }>();

/** Every direction with observed transfers behind it. */
const DIRECTIONS = ["EL->NBA", "GL->NBA", "NBA->EL", "NBA->GL", "GL->EL", "EL->GL"] as const;

const Query = zRuntime.object({
  direction: zRuntime.enum(DIRECTIONS).default("EL->NBA"),
  /** Restrict to recent seasons. A projection off a 2012 line is a curiosity. */
  sinceSeason: zRuntime.coerce.number().int().min(2000).max(2100).optional(),
  /** Out-of-support rows top the ranking, so hiding them is opt-in, not default. */
  inSupportOnly: zRuntime
    .enum(["true", "false"])
    .default("false")
    .transform((v) => v === "true"),
  /**
   * 500 covers every projection in the largest direction, so a caller who
   * wants the whole pool can have it in one request. The ceiling exists
   * because the response is materialised in memory, not to curate the list.
   */
  limit: zRuntime.coerce.number().int().min(1).max(500).default(50),
  offset: zRuntime.coerce.number().int().min(0).default(0),
});

/**
 * The query as the document describes it, which is deliberately not the schema
 * above.
 *
 * `Query` runs inside the handler so a bad parameter comes back as
 * problem+json with an INVALID_QUERY code. Handing it to `request.query`
 * instead would move the rejection into the framework's validator, which
 * answers in its own shape and would put one endpoint's errors outside the
 * catalogue every other error in this API belongs to.
 */
const DocumentedQuery = z.object({
  direction: z
    .string()
    .optional()
    .openapi({
      param: { name: "direction", in: "query" },
      description: `One of ${DIRECTIONS.join(", ")}. Defaults to EL->NBA.`,
      example: "EL->NBA",
    }),
  sinceSeason: z
    .string()
    .optional()
    .openapi({
      param: { name: "sinceSeason", in: "query" },
      description: "Season order floor, 2000-2100. A projection off a 2012 line is a curiosity.",
      example: "2022",
    }),
  inSupportOnly: z
    .string()
    .optional()
    .openapi({
      param: { name: "inSupportOnly", in: "query" },
      description:
        "`true` drops rows the model is extrapolating for. Off by default: those rows " +
        "top the ranking, so hiding them is something a caller asks for.",
      example: "false",
    }),
  limit: z
    .string()
    .optional()
    .openapi({
      param: { name: "limit", in: "query" },
      description: "1-500, default 50.",
      example: "50",
    }),
  offset: z
    .string()
    .optional()
    .openapi({
      param: { name: "offset", in: "query" },
      description: "Row offset into the ranking, default 0.",
      example: "0",
    }),
});

/**
 * `inSupport` and `movedBefore` are on the row rather than in the metadata
 * because they qualify one player's number, not the response as a whole.
 */
const ProjectionSchema = z.object({
  personId: z.string(),
  displayName: z.string().nullable(),
  sourceSeasonId: z.string(),
  sourceLeague: z.string(),
  targetSeasonId: z.string(),
  direction: z.string(),
  metric: z.string(),
  sourceValue: z.number(),
  zSource: z.number(),
  predicted: z.number(),
  pi80Low: z.number(),
  pi80High: z.number(),
  pi95Low: z.number(),
  pi95High: z.number(),
  inSupport: z.boolean().openapi({
    description:
      "False means the player's standing sits outside the range where transferring " +
      "players were observed, so the interval understates the uncertainty.",
  }),
  movedBefore: z.boolean(),
  minutes: z.number(),
  age: z.number().nullable(),
  supportNMovers: z.number().int().openapi({
    description: "Observed transfers behind this direction's intercept.",
  }),
  modelVersion: z.string(),
});

/**
 * Projections for players who have not changed league.
 *
 * The counterfactual the whole project is built to answer: if this player were
 * signed, what does history say about players who were signed with production
 * like his?
 *
 * Ordered by projected usage, which puts the least trustworthy rows first —
 * the highest-usage players in a league are routinely outside the range where
 * transferring players were observed, so the model is extrapolating for exactly
 * the names that look most interesting. That is a property of the data, not a
 * bug to sort away, so `inSupport` rides on every row and filtering them out is
 * something a caller asks for rather than something the API decides.
 */
projectionsRoute.openapi(
  createRoute({
    method: "get",
    path: "/projections",
    tags: ["Projections"],
    summary: "Projected production for players who have NOT changed league.",
    description:
      "The counterfactual the model exists to answer. Ranked by projection, which puts " +
      "the least trustworthy rows first, so every row carries an out-of-support flag and " +
      "`meta.page` says how much of the pool this page is.",
    request: { query: DocumentedQuery },
    responses: {
      200: {
        description: "A page of the ranking, with the matched total in `meta.page`.",
        content: {
          "application/json": {
            schema: EnvelopeSchema(z.array(ProjectionSchema), "Projections"),
          },
        },
      },
      404: {
        description:
          "NO_PROJECTIONS: no player satisfies the direction, season and support filters " +
          "together.",
        content: { [PROBLEM_CONTENT_TYPE]: { schema: ProblemSchema } },
      },
      422: {
        description:
          "INVALID_QUERY: a parameter is malformed or outside its range. `directions` " +
          "lists the ones that exist.",
        content: { [PROBLEM_CONTENT_TYPE]: { schema: ProblemSchema } },
      },
    },
  }),
  async (c) => {
    const parsed = Query.safeParse({
      direction: c.req.query("direction"),
      sinceSeason: c.req.query("sinceSeason"),
      inSupportOnly: c.req.query("inSupportOnly"),
      limit: c.req.query("limit"),
      offset: c.req.query("offset"),
    });
    if (!parsed.success) {
      return problem(c, {
        status: 422,
        code: "INVALID_QUERY",
        title: "Invalid projection parameters",
        detail: parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; "),
        extensions: { directions: DIRECTIONS },
      }) as never;
    }

    const { direction, sinceSeason, inSupportOnly, limit, offset } = parsed.data;
    const db = createDb(c.env.DB);

    const filters = [eq(schema.hypotheticalProjections.direction, direction)];
    if (sinceSeason !== undefined) {
      filters.push(gte(schema.hypotheticalProjections.sourceSeasonOrder, sinceSeason));
    }
    if (inSupportOnly) {
      filters.push(eq(schema.hypotheticalProjections.inSupport, true));
    }

    const rows = await db
      .select({
        personId: schema.hypotheticalProjections.personId,
        displayName: schema.persons.displayName,
        sourceSeasonId: schema.hypotheticalProjections.sourceSeasonId,
        sourceLeague: schema.hypotheticalProjections.sourceLeague,
        targetSeasonId: schema.hypotheticalProjections.targetSeasonId,
        direction: schema.hypotheticalProjections.direction,
        metric: schema.hypotheticalProjections.metric,
        sourceValue: schema.hypotheticalProjections.sourceValue,
        zSource: schema.hypotheticalProjections.zSource,
        predicted: schema.hypotheticalProjections.predicted,
        pi80Low: schema.hypotheticalProjections.pi80Low,
        pi80High: schema.hypotheticalProjections.pi80High,
        pi95Low: schema.hypotheticalProjections.pi95Low,
        pi95High: schema.hypotheticalProjections.pi95High,
        inSupport: schema.hypotheticalProjections.inSupport,
        movedBefore: schema.hypotheticalProjections.movedBefore,
        minutes: schema.hypotheticalProjections.minutes,
        age: schema.hypotheticalProjections.age,
        supportNMovers: schema.hypotheticalProjections.supportNMovers,
        modelVersion: schema.hypotheticalProjections.modelVersion,
      })
      .from(schema.hypotheticalProjections)
      .leftJoin(
        schema.persons,
        eq(schema.persons.personId, schema.hypotheticalProjections.personId)
      )
      .where(and(...filters))
      .orderBy(desc(schema.hypotheticalProjections.predicted))
      .limit(limit)
      .offset(offset);

    // How many the filters actually match, which is not `rows.length` once a
    // limit is applied. Without it a caller cannot tell a short list from a
    // truncated one — the difference between "these are the players" and "these
    // are the first fifty of two hundred".
    const [counted] = await db
      .select({ total: count() })
      .from(schema.hypotheticalProjections)
      .where(and(...filters));
    const total = counted?.total ?? 0;

    if (rows.length === 0) {
      return problem(c, {
        status: 404,
        code: "NO_PROJECTIONS",
        title: "No projections for that direction",
        detail:
          `No hypothetical projections are stored for ${direction}` +
          (sinceSeason ? ` since ${sinceSeason}` : "") +
          ". Projections cover players with a qualifying season who have not made this move.",
      }) as never;
    }

    const outOfSupport = rows.filter((row) => !row.inSupport).length;

    const movers = rows[0]?.supportNMovers ?? 0;

    return c.json(
      envelope(c, rows, {
        snapshot: await snapshotId(db),
        page: { total, limit, offset, returned: rows.length },
        warnings: [
          "These players have not transferred. The estimate is conditional on a transfer " +
            "happening and is fitted on players who were signed, who sit about half a standard " +
            "deviation above their league. It ranks a shortlist; it does not price a contract.",
          `Fitted from ${movers} observed ${direction} transfers.`,
          ...(total > rows.length
            ? [
                `Showing ${rows.length} of ${total} eligible players, ranked by projection. ` +
                  "Raise `limit` or page with `offset` for the rest; this is a page of a " +
                  "ranking, not the whole pool.",
              ]
            : []),
          ...(outOfSupport > 0
            ? [
                `${outOfSupport} of ${rows.length} rows fall outside the range of source ` +
                  "production where transferring players were observed. For those the model is " +
                  "extrapolating and the interval understates the uncertainty.",
              ]
            : []),
        ],
      })
    ) as never;
  }
);
