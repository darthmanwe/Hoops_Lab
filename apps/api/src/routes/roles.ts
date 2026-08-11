import { and, asc, desc, eq } from "drizzle-orm";
import { Hono } from "hono";
import { createDb, schema } from "../db/client";
import type { Env } from "../env";
import { envelope } from "../http/envelope";
import { problem } from "../http/problem";
import { snapshotId } from "../lib/snapshot";

export const rolesRoute = new Hono<{ Bindings: Env }>();

/**
 * The archetype definitions, each with its bootstrap stability.
 *
 * Stability is part of the payload rather than a footnote. Clusters are not
 * equally real: presenting five labelled types without saying that one of them
 * barely reproduces under resampling would imply a crispness the clustering
 * does not have.
 */
rolesRoute.get("/archetypes", async (c) => {
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
  );
});

/** A player's archetype for a season, with the cluster's own stability. */
rolesRoute.get("/players/:personId/archetype", async (c) => {
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
    });
  }

  return c.json(envelope(c, rows, { snapshot: await snapshotId(db) }));
});

/**
 * Precomputed comparables.
 *
 * Replaces a route that scanned an entire season table and ran cosine
 * similarity in the Worker on every request. Distance is Euclidean in the
 * whitened archetype space, which is also the correct metric — cosine over
 * shares on a simplex was not.
 */
rolesRoute.get("/players/:personId/comps", async (c) => {
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
    });
  }

  return c.json(envelope(c, rows, { snapshot: await snapshotId(db) }));
});

/**
 * Three-point shooting threat.
 *
 * What replaces the withdrawn "gravity" metric, and named for what it actually
 * measures. `shrinkageWeight` says how much of the number is the player's own
 * attempts rather than the league prior.
 */
rolesRoute.get("/players/:personId/shooting", async (c) => {
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
    });
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
  );
});

/** Spacing leaderboard for one season. */
rolesRoute.get("/leaderboards/shooting", async (c) => {
  const season = c.req.query("season") ?? "NBA_2023";
  const limit = Math.min(Number(c.req.query("limit") ?? 25) || 25, 100);

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
    });
  }

  return c.json(envelope(c, rows, { snapshot: await snapshotId(db) }));
});
