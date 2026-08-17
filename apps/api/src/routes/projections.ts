import { and, desc, eq, gte } from "drizzle-orm";
import { Hono } from "hono";
import { z } from "zod";
import { createDb, schema } from "../db/client";
import type { Env } from "../env";
import { envelope } from "../http/envelope";
import { problem } from "../http/problem";
import { snapshotId } from "../lib/snapshot";

export const projectionsRoute = new Hono<{ Bindings: Env }>();

const Query = z.object({
  direction: z.enum(["EL->NBA", "GL->NBA"]).default("EL->NBA"),
  /** Restrict to recent seasons. A projection off a 2012 line is a curiosity. */
  sinceSeason: z.coerce.number().int().min(2000).max(2100).optional(),
  /** Out-of-support rows top the ranking, so hiding them is opt-in, not default. */
  inSupportOnly: z
    .enum(["true", "false"])
    .default("false")
    .transform((v) => v === "true"),
  limit: z.coerce.number().int().min(1).max(200).default(50),
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
  });
  if (!parsed.success) {
    return problem(c, {
      status: 422,
      code: "INVALID_QUERY",
      title: "Invalid projection parameters",
      detail: parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; "),
      extensions: { directions: ["EL->NBA", "GL->NBA"] },
    });
  }

  const { direction, sinceSeason, inSupportOnly, limit } = parsed.data;
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
      modelVersion: schema.hypotheticalProjections.modelVersion,
    })
    .from(schema.hypotheticalProjections)
    .leftJoin(schema.persons, eq(schema.persons.personId, schema.hypotheticalProjections.personId))
    .where(and(...filters))
    .orderBy(desc(schema.hypotheticalProjections.predicted))
    .limit(limit);

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

  return c.json(
    envelope(c, rows, {
      snapshot: await snapshotId(db),
      warnings: [
        "These players have not transferred. The estimate is conditional on a transfer " +
          "happening and is fitted on players who were signed, who sit about half a standard " +
          "deviation above their league. It ranks a shortlist; it does not price a contract.",
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
