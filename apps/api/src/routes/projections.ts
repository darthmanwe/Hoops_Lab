import { and, count, desc, eq, gte } from "drizzle-orm";
import { Hono } from "hono";
import { z } from "zod";
import { createDb, schema } from "../db/client";
import type { Env } from "../env";
import { envelope } from "../http/envelope";
import { problem } from "../http/problem";
import { snapshotId } from "../lib/snapshot";

export const projectionsRoute = new Hono<{ Bindings: Env }>();

/** Every direction with observed transfers behind it. */
const DIRECTIONS = ["EL->NBA", "GL->NBA", "NBA->EL", "NBA->GL", "GL->EL", "EL->GL"] as const;

const Query = z.object({
  direction: z.enum(DIRECTIONS).default("EL->NBA"),
  /** Restrict to recent seasons. A projection off a 2012 line is a curiosity. */
  sinceSeason: z.coerce.number().int().min(2000).max(2100).optional(),
  /** Out-of-support rows top the ranking, so hiding them is opt-in, not default. */
  inSupportOnly: z
    .enum(["true", "false"])
    .default("false")
    .transform((v) => v === "true"),
  /**
   * 500 covers every projection in the largest direction, so a caller who
   * wants the whole pool can have it in one request. The ceiling exists
   * because the response is materialised in memory, not to curate the list.
   */
  limit: z.coerce.number().int().min(1).max(500).default(50),
  offset: z.coerce.number().int().min(0).default(0),
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
projectionsRoute.get("/projections", async (c) => {
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
    });
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
    .leftJoin(schema.persons, eq(schema.persons.personId, schema.hypotheticalProjections.personId))
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
    });
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
  );
});
