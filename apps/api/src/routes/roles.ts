import { createRoute, OpenAPIHono, z } from "@hono/zod-openapi";
import { and, asc, desc, eq } from "drizzle-orm";
// See the note in projections.ts: the re-exported `z` above carries
// `.openapi()` but returns `any` from `safeParse`, so parsed queries use zod
// itself and only schemas that reach the document use the re-export.
import { z as zRuntime } from "zod";
import { createDb, schema } from "../db/client";
import type { Env } from "../env";
import { envelope } from "../http/envelope";
import { PROBLEM_CONTENT_TYPE, problem } from "../http/problem";
import { EnvelopeSchema, ProblemSchema } from "../http/schemas";
import { snapshotId } from "../lib/snapshot";

export const rolesRoute = new OpenAPIHono<{ Bindings: Env }>();

/** `reportable` is false for a cluster to be read as unclassified, not as a type. */
const ArchetypeSchema = z.object({
  modelVersion: z.string(),
  cluster: z.number().int(),
  nMembers: z.number().int(),
  topFeatures: z.string(),
  exemplars: z.string(),
  stabilityJaccard: z.number().openapi({
    description: "Bootstrap stability. Clusters are not equally real, so it is served, not hidden.",
  }),
  reportable: z.boolean(),
});

/** An assignment carries the cluster's own stability, not just its number. */
const PlayerArchetypeSchema = z.object({
  seasonId: z.string(),
  league: z.string(),
  cluster: z.number().int(),
  modelVersion: z.string(),
  topFeatures: z.string(),
  exemplars: z.string(),
  stabilityJaccard: z.number(),
  reportable: z.boolean(),
});

const CompSchema = z.object({
  seasonId: z.string(),
  rank: z.number().int(),
  distance: z.number().openapi({
    description: "Euclidean in the whitened archetype space, which is the correct metric here.",
  }),
  neighbourPersonId: z.string(),
  neighbourName: z.string().nullable(),
  modelVersion: z.string(),
});

const ShootingSchema = z.object({
  seasonId: z.string(),
  personId: z.string(),
  fg3a: z.number(),
  fg3aPer75: z.number(),
  fg3PctRaw: z.number().nullable(),
  fg3PctShrunk: z.number(),
  shrinkageWeight: z.number().openapi({
    description:
      "How much of the number is the player's own attempts rather than the league prior. " +
      "A 40-attempt shooter is mostly prior, and that is the difference between a " +
      "measurement and an impression.",
  }),
  priorMean: z.number(),
  spacingScore: z.number(),
  reportable: z.boolean(),
  modelVersion: z.string(),
});

const SpacingLeaderSchema = z.object({
  personId: z.string(),
  displayName: z.string().nullable(),
  seasonId: z.string(),
  fg3a: z.number(),
  fg3PctRaw: z.number().nullable(),
  fg3PctShrunk: z.number(),
  shrinkageWeight: z.number(),
  spacingScore: z.number(),
  modelVersion: z.string(),
});

/**
 * The archetype definitions, each with its bootstrap stability.
 *
 * Stability is part of the payload rather than a footnote. Clusters are not
 * equally real: presenting five labelled types without saying that one of them
 * barely reproduces under resampling would imply a crispness the clustering
 * does not have.
 */
rolesRoute.openapi(
  createRoute({
    method: "get",
    path: "/archetypes",
    tags: ["Roles"],
    summary: "The clusters, their distinguishing features, exemplars and stability.",
    description:
      "Ordered by stability, most reproducible first. A cluster below the floor is " +
      "flagged in the row and again in `meta.warnings`.",
    responses: {
      200: {
        description: "Every cluster in the archetype model.",
        content: {
          "application/json": { schema: EnvelopeSchema(z.array(ArchetypeSchema), "Archetypes") },
        },
      },
    },
  }),
  async (c) => {
    const db = createDb(c.env.DB);
    const rows = await db
      .select()
      .from(schema.archetypeDefinitions)
      .orderBy(desc(schema.archetypeDefinitions.stabilityJaccard));

    return c.json(
      envelope(c, rows, {
        snapshot: await snapshotId(db),
        warnings: rows.some((r) => !r.reportable)
          ? [
              "At least one cluster falls below the stability floor and should be " +
                "read as unclassified rather than as a player type.",
            ]
          : [],
      })
    ) as never;
  }
);

/** A player's archetype for a season, with the cluster's own stability. */
rolesRoute.openapi(
  createRoute({
    method: "get",
    path: "/players/{personId}/archetype",
    tags: ["Roles"],
    summary: "Archetype assignment per season, carrying that cluster's stability.",
    description:
      "Descriptive, never predictive. Only seasons clearing the 500-minute floor are " +
      "clustered, so a low-minute season has no assignment rather than one fitted on noise.",
    request: {
      params: z.object({
        personId: z.string().openapi({ param: { name: "personId", in: "path" } }),
      }),
    },
    responses: {
      200: {
        description: "One row per clustered season, in season order.",
        content: {
          "application/json": {
            schema: EnvelopeSchema(z.array(PlayerArchetypeSchema), "PlayerArchetypes"),
          },
        },
      },
      404: {
        description:
          "NO_ARCHETYPE_FOR_PLAYER: no season clears the minutes floor the model requires.",
        content: { [PROBLEM_CONTENT_TYPE]: { schema: ProblemSchema } },
      },
    },
  }),
  async (c) => {
    const personId = c.req.param("personId");
    const db = createDb(c.env.DB);

    const rows = await db
      .select({
        seasonId: schema.playerArchetypes.seasonId,
        league: schema.playerArchetypes.league,
        cluster: schema.playerArchetypes.cluster,
        modelVersion: schema.playerArchetypes.modelVersion,
        topFeatures: schema.archetypeDefinitions.topFeatures,
        exemplars: schema.archetypeDefinitions.exemplars,
        stabilityJaccard: schema.archetypeDefinitions.stabilityJaccard,
        reportable: schema.archetypeDefinitions.reportable,
      })
      .from(schema.playerArchetypes)
      .innerJoin(
        schema.archetypeDefinitions,
        and(
          eq(schema.playerArchetypes.cluster, schema.archetypeDefinitions.cluster),
          eq(schema.playerArchetypes.modelVersion, schema.archetypeDefinitions.modelVersion)
        )
      )
      .where(eq(schema.playerArchetypes.personId, personId))
      .orderBy(asc(schema.playerArchetypes.seasonId));

    if (rows.length === 0) {
      return problem(c, {
        status: 404,
        code: "NO_ARCHETYPE_FOR_PLAYER",
        title: "No archetype assigned",
        detail:
          `Player ${personId} has no season clearing the 500-minute floor used for ` +
          "clustering. A role computed from fewer minutes would not be a measurement.",
      }) as never;
    }

    return c.json(envelope(c, rows, { snapshot: await snapshotId(db) })) as never;
  }
);

/**
 * Precomputed comparables.
 *
 * Replaces a route that scanned an entire season table and ran cosine
 * similarity in the Worker on every request. Distance is Euclidean in the
 * whitened archetype space, which is also the correct metric — cosine over
 * shares on a simplex was not.
 */
rolesRoute.openapi(
  createRoute({
    method: "get",
    path: "/players/{personId}/comps",
    tags: ["Roles"],
    summary: "Nearest neighbours in the whitened archetype space.",
    description:
      "Precomputed in Python, because the Worker gets 10 ms of CPU per request. The " +
      "distance metric is stated on every row rather than left for the reader to assume.",
    request: {
      params: z.object({
        personId: z.string().openapi({ param: { name: "personId", in: "path" } }),
      }),
      query: z.object({
        season: z
          .string()
          .optional()
          .openapi({
            param: { name: "season", in: "query" },
            description: "Restrict to one season. Omitted, every clustered season is returned.",
            example: "NBA_2023",
          }),
        limit: z
          .string()
          .optional()
          .openapi({
            param: { name: "limit", in: "query" },
            description: "Default 10, capped at 25.",
            example: "10",
          }),
      }),
    },
    responses: {
      200: {
        description: "Neighbours ordered by season, then by rank.",
        content: {
          "application/json": { schema: EnvelopeSchema(z.array(CompSchema), "PlayerComps") },
        },
      },
      404: {
        description:
          "NO_COMPS_FOR_PLAYER: the player has no archetype assignment, so there is no " +
          "space to find neighbours in.",
        content: { [PROBLEM_CONTENT_TYPE]: { schema: ProblemSchema } },
      },
    },
  }),
  async (c) => {
    const personId = c.req.param("personId");
    const season = c.req.query("season");
    const limit = Math.min(Number(c.req.query("limit") ?? 10) || 10, 25);

    const db = createDb(c.env.DB);
    const filters = [eq(schema.playerComps.personId, personId)];
    if (season) filters.push(eq(schema.playerComps.seasonId, season));

    const rows = await db
      .select({
        seasonId: schema.playerComps.seasonId,
        rank: schema.playerComps.rank,
        distance: schema.playerComps.distance,
        neighbourPersonId: schema.playerComps.neighbourPersonId,
        neighbourName: schema.persons.displayName,
        modelVersion: schema.playerComps.modelVersion,
      })
      .from(schema.playerComps)
      .innerJoin(schema.persons, eq(schema.playerComps.neighbourPersonId, schema.persons.personId))
      .where(and(...filters))
      .orderBy(asc(schema.playerComps.seasonId), asc(schema.playerComps.rank))
      .limit(limit);

    if (rows.length === 0) {
      return problem(c, {
        status: 404,
        code: "NO_COMPS_FOR_PLAYER",
        title: "No comparables available",
        detail:
          `No comparables for ${personId}${season ? ` in ${season}` : ""}. ` +
          "Comparables are computed only for seasons clearing the 500-minute floor.",
      }) as never;
    }

    return c.json(envelope(c, rows, { snapshot: await snapshotId(db) })) as never;
  }
);

/**
 * Three-point shooting threat.
 *
 * What replaces the withdrawn "gravity" metric, and named for what it actually
 * measures. `shrinkageWeight` says how much of the number is the player's own
 * attempts rather than the league prior.
 */
rolesRoute.openapi(
  createRoute({
    method: "get",
    path: "/players/{personId}/shooting",
    tags: ["Roles"],
    summary: "Empirical-Bayes shrunk three-point threat, with the shrinkage weight exposed.",
    description:
      "What replaces the withdrawn gravity metric, named for what it actually measures. " +
      "Seasons below the attempt floor are served but flagged, because their value is " +
      "largely the league prior.",
    request: {
      params: z.object({
        personId: z.string().openapi({ param: { name: "personId", in: "path" } }),
      }),
    },
    responses: {
      200: {
        description: "One row per season, in season order.",
        content: {
          "application/json": {
            schema: EnvelopeSchema(z.array(ShootingSchema), "PlayerShooting"),
          },
        },
      },
      404: {
        description:
          "NO_SHOOTING_FOR_PLAYER: no season above the three-point attempt floor, below " +
          "which the estimate would be almost entirely prior.",
        content: { [PROBLEM_CONTENT_TYPE]: { schema: ProblemSchema } },
      },
    },
  }),
  async (c) => {
    const personId = c.req.param("personId");
    const db = createDb(c.env.DB);

    const rows = await db
      .select()
      .from(schema.playerShooting)
      .where(eq(schema.playerShooting.personId, personId))
      .orderBy(asc(schema.playerShooting.seasonId));

    if (rows.length === 0) {
      return problem(c, {
        status: 404,
        code: "NO_SHOOTING_FOR_PLAYER",
        title: "No shooting record",
        detail: `No three-point record for ${personId}.`,
      }) as never;
    }

    const mostlyPrior = rows.filter((r) => !r.reportable).length;
    return c.json(
      envelope(c, rows, {
        snapshot: await snapshotId(db),
        warnings:
          mostlyPrior > 0
            ? [
                `${mostlyPrior} season(s) fall below the attempt floor; those values are ` +
                  "largely the league prior rather than a measurement of this player.",
              ]
            : [],
      })
    ) as never;
  }
);

/**
 * The leaderboard's parameters.
 *
 * `limit` was `Math.min(Number(...) || 25, 100)`, which answered a request for
 * 9999 rows with 100 and never said so. A silently clamped page is a claim
 * about the data that the caller did not make and cannot see, so an
 * out-of-range limit is now rejected rather than quietly rewritten. The
 * ceiling itself is unchanged.
 */
const LeaderboardQuery = zRuntime.object({
  season: zRuntime.string().default("NBA_2023"),
  limit: zRuntime.coerce.number().int().min(1).max(100).default(25),
});

/** Spacing leaderboard for one season. */
rolesRoute.openapi(
  createRoute({
    method: "get",
    path: "/leaderboards/shooting",
    tags: ["Roles"],
    summary: "Spacing leaderboard, restricted to players above the attempt floor.",
    description:
      "Ranking on a mostly-prior number would put the smallest samples on top, which is " +
      "the exact failure shrinkage exists to prevent, so players below the floor are " +
      "excluded rather than ranked.",
    request: {
      // Permissive here on purpose: `LeaderboardQuery` runs in the handler so a
      // bad parameter comes back as problem+json rather than in the validator's
      // own shape.
      query: z.object({
        season: z
          .string()
          .optional()
          .openapi({
            param: { name: "season", in: "query" },
            description: "Defaults to NBA_2023.",
            example: "NBA_2023",
          }),
        limit: z
          .string()
          .optional()
          .openapi({
            param: { name: "limit", in: "query" },
            description: "1-100, default 25. Outside that range the request is rejected.",
            example: "25",
          }),
      }),
    },
    responses: {
      200: {
        description: "Players above the attempt floor, ranked by spacing score.",
        content: {
          "application/json": {
            schema: EnvelopeSchema(z.array(SpacingLeaderSchema), "SpacingLeaderboard"),
          },
        },
      },
      404: {
        description:
          "NO_SHOOTING_FOR_SEASON: the season carries no player above the attempt floor, " +
          "or is not in the snapshot.",
        content: { [PROBLEM_CONTENT_TYPE]: { schema: ProblemSchema } },
      },
      422: {
        description: "INVALID_QUERY: `limit` is not an integer in 1-100.",
        content: { [PROBLEM_CONTENT_TYPE]: { schema: ProblemSchema } },
      },
    },
  }),
  async (c) => {
    const parsed = LeaderboardQuery.safeParse({
      season: c.req.query("season"),
      limit: c.req.query("limit"),
    });
    if (!parsed.success) {
      return problem(c, {
        status: 422,
        code: "INVALID_QUERY",
        title: "Invalid leaderboard parameters",
        detail: parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; "),
      }) as never;
    }

    const { season, limit } = parsed.data;

    const db = createDb(c.env.DB);
    const rows = await db
      .select({
        personId: schema.playerShooting.personId,
        displayName: schema.persons.displayName,
        seasonId: schema.playerShooting.seasonId,
        fg3a: schema.playerShooting.fg3a,
        fg3PctRaw: schema.playerShooting.fg3PctRaw,
        fg3PctShrunk: schema.playerShooting.fg3PctShrunk,
        shrinkageWeight: schema.playerShooting.shrinkageWeight,
        spacingScore: schema.playerShooting.spacingScore,
        modelVersion: schema.playerShooting.modelVersion,
      })
      .from(schema.playerShooting)
      .innerJoin(schema.persons, eq(schema.playerShooting.personId, schema.persons.personId))
      // Only players above the attempt floor: ranking by a number that is mostly
      // prior would put small samples at the top, which is the exact failure
      // shrinkage exists to prevent.
      .where(
        and(eq(schema.playerShooting.seasonId, season), eq(schema.playerShooting.reportable, true))
      )
      .orderBy(desc(schema.playerShooting.spacingScore))
      .limit(limit);

    if (rows.length === 0) {
      return problem(c, {
        status: 404,
        code: "NO_SHOOTING_FOR_SEASON",
        title: "No shooting data for that season",
        detail: `No reportable three-point records for ${season}.`,
      }) as never;
    }

    return c.json(envelope(c, rows, { snapshot: await snapshotId(db) })) as never;
  }
);
