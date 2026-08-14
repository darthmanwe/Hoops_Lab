import { and, asc, desc, eq, like, sql } from "drizzle-orm";
import { Hono } from "hono";
import { z } from "zod";
import { createDb, schema } from "../db/client";
import type { Env } from "../env";
import { envelope } from "../http/envelope";
import { problem } from "../http/problem";
import { snapshotId } from "../lib/snapshot";

export const playersRoute = new Hono<{ Bindings: Env }>();

const SearchQuery = z.object({
  q: z.string().min(1).max(80),
  limit: z.coerce.number().int().min(1).max(50).default(20),
});

/**
 * Diacritic-insensitive search over the normalised name column.
 *
 * The previous implementation ran `LIKE '%q%'` against the display name, which
 * cannot use an index and — more importantly — could not find "Jokić" for
 * anyone typing "Jokic". Roughly a third of EuroLeague players have diacritics,
 * so that was not an edge case.
 */
playersRoute.get("/players/search", async (c) => {
  const parsed = SearchQuery.safeParse({
    q: c.req.query("q"),
    limit: c.req.query("limit"),
  });
  if (!parsed.success) {
    return problem(c, {
      status: 422,
      code: "INVALID_QUERY",
      title: "Invalid search parameters",
      detail: parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; "),
    });
  }

  const { q, limit } = parsed.data;
  const db = createDb(c.env.DB);
  const needle = `%${normalise(q)}%`;

  const rows = await db
    .select({
      personId: schema.persons.personId,
      displayName: schema.persons.displayName,
      birthYear: schema.persons.birthYear,
      leagues: schema.persons.leagues,
    })
    .from(schema.persons)
    .where(like(schema.persons.nameNormalized, needle))
    // Cross-league players first: they are the ones this project is about.
    .orderBy(desc(sql`instr(${schema.persons.leagues}, '+')`), asc(schema.persons.displayName))
    .limit(limit);

  return c.json(envelope(c, rows, { snapshot: await snapshotId(db) }));
});

/** A person's full career across every league they appear in. */
playersRoute.get("/players/:personId", async (c) => {
  const personId = c.req.param("personId");
  const db = createDb(c.env.DB);

  const [person] = await db
    .select()
    .from(schema.persons)
    .where(eq(schema.persons.personId, personId))
    .limit(1);

  if (!person) {
    return problem(c, {
      status: 404,
      code: "PERSON_NOT_FOUND",
      title: "No such player",
      detail: `No person with id ${personId}.`,
      extensions: { search: "/players/search?q=" },
    });
  }

  const seasons = await db
    .select({
      seasonId: schema.playerSeasons.seasonId,
      league: schema.playerSeasons.league,
      label: schema.seasons.label,
      seasonOrder: schema.seasons.seasonOrder,
      teamName: schema.playerSeasons.teamName,
      gamesPlayed: schema.playerSeasons.gamesPlayed,
      minutes: schema.playerSeasons.minutes,
      usgPct: schema.playerSeasons.usgPct,
      tsPct: schema.playerSeasons.tsPct,
      astPct: schema.playerSeasons.astPct,
      ptsPer75: schema.playerSeasons.ptsPer75,
      age: schema.playerSeasons.age,
      qualified: schema.playerSeasons.qualified,
    })
    .from(schema.playerSeasons)
    .innerJoin(schema.seasons, eq(schema.playerSeasons.seasonId, schema.seasons.seasonId))
    // Chronological across leagues, using the integer sort key. Ordering by
    // season_id text would put "NBA_2020" above "EL_2021".
    .orderBy(asc(schema.seasons.seasonOrder))
    .where(eq(schema.playerSeasons.personId, personId));

  const identities = await db
    .select({
      league: schema.playerIdentities.league,
      sourcePlayerId: schema.playerIdentities.sourcePlayerId,
      matchMethod: schema.playerIdentities.matchMethod,
      confidence: schema.playerIdentities.confidence,
    })
    .from(schema.playerIdentities)
    .where(eq(schema.playerIdentities.personId, personId));

  // Surfaced rather than hidden: a link made on name alone is weaker evidence
  // than one corroborated by age, and a caller deserves to know which.
  const warnings = identities.some((i) => i.confidence < 0.8)
    ? ["This player has at least one low-confidence cross-league identity link."]
    : [];

  return c.json(
    envelope(c, { person, seasons, identities }, { snapshot: await snapshotId(db), warnings })
  );
});

/** Translation predictions for a person, always with their intervals. */
playersRoute.get("/players/:personId/translation", async (c) => {
  const personId = c.req.param("personId");
  const db = createDb(c.env.DB);

  const rows = await db
    .select()
    .from(schema.translationPredictions)
    .where(eq(schema.translationPredictions.personId, personId))
    .orderBy(asc(schema.translationPredictions.sourceSeasonId));

  if (rows.length === 0) {
    return problem(c, {
      status: 404,
      code: "NO_TRANSITION_FOR_PLAYER",
      title: "No observed league transition",
      detail:
        `Player ${personId} has no transition meeting the modelling thresholds ` +
        "(400+ minutes in the source league, 300+ in the target, one or two seasons apart).",
      extensions: { leaderboard: "/leaderboards/translation" },
    });
  }

  const model = await modelMeta(db, rows[0]!.modelVersion);
  return c.json(
    envelope(c, rows, {
      snapshot: await snapshotId(db),
      // A prediction whose model version has vanished from the registry is a
      // broken foreign key, not a normal state; the row is still served, but
      // without a provenance block that would be a lie.
      ...(model ? { model } : {}),
    })
  );
});

async function modelMeta(db: ReturnType<typeof createDb>, modelVersion: string) {
  const [version] = await db
    .select()
    .from(schema.modelVersions)
    .where(eq(schema.modelVersions.modelVersion, modelVersion))
    .limit(1);

  if (!version) return undefined;
  return {
    name: version.modelName,
    version: version.modelVersion,
    primary_metric: version.primaryMetric,
    primary_value: version.primaryValue,
    primary_ci: [version.primaryCiLow ?? 0, version.primaryCiHigh ?? 0] as [number, number],
    card: version.cardPath,
  };
}

/**
 * Mirrors the Python normaliser closely enough for search.
 *
 * SQLite's built-in `lower()` does not fold accents, so the comparison happens
 * against a column that Python already normalised; this only has to prepare
 * the needle the same way.
 */
function normalise(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[.'’`´]/g, "")
    .replace(/[^\w\s]/g, " ")
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
}

export { normalise };
export const _test = { SearchQuery, and };
