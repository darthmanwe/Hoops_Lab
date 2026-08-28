import { createRoute, OpenAPIHono, z } from "@hono/zod-openapi";
import { and, asc, desc, eq, like, sql } from "drizzle-orm";
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

export const playersRoute = new OpenAPIHono<{ Bindings: Env }>();

const SearchQuery = zRuntime.object({
  q: zRuntime.string().min(1).max(80),
  limit: zRuntime.coerce.number().int().min(1).max(50).default(20),
});

/** What search returns: enough to pick a player, not a career. */
const SearchResultSchema = z.object({
  personId: z.string(),
  displayName: z.string().nullable(),
  birthYear: z.number().int().nullable(),
  leagues: z.string().openapi({
    description: 'Which leagues this person appears in, e.g. "EL+NBA".',
    example: "EL+NBA",
  }),
});

const PersonSchema = z.object({
  personId: z.string(),
  displayName: z.string().nullable(),
  nameNormalized: z.string().nullable(),
  birthYear: z.number().int().nullable(),
  leagues: z.string(),
});

/**
 * Rate stats are nullable because a season can exist without them. The
 * previous data layer coerced every one of these through `Number(x ?? 0)`,
 * which is how a missing value became a confident zero.
 */
const PlayerSeasonSchema = z.object({
  seasonId: z.string(),
  league: z.string(),
  label: z.string(),
  seasonOrder: z.number().int().openapi({
    description: "Integer sort key. Season ids do not sort correctly across leagues.",
  }),
  teamName: z.string().nullable(),
  gamesPlayed: z.number().int().nullable(),
  minutes: z.number().nullable(),
  usgPct: z.number().nullable(),
  tsPct: z.number().nullable(),
  astPct: z.number().nullable(),
  ptsPer75: z.number().nullable(),
  age: z.number().nullable(),
  qualified: z.boolean().openapi({
    description: "Whether the season clears the minutes floor to count as a measurement.",
  }),
});

const PlayerIdentitySchema = z.object({
  league: z.string(),
  sourcePlayerId: z.string(),
  matchMethod: z.string().openapi({
    description: "How the link was made: anchor, shared_nba_person_id, name_and_age, ...",
  }),
  confidence: z.number().openapi({
    description: "Below 0.8 the link is reported but excluded from the modelling cohort.",
  }),
});

const CareerSchema = z.object({
  person: PersonSchema,
  seasons: z.array(PlayerSeasonSchema),
  identities: z.array(PlayerIdentitySchema),
});

/** The intervals are not nullable, because the schema will not store one without them. */
const PlayerTranslationSchema = z.object({
  personId: z.string(),
  sourceSeasonId: z.string(),
  targetSeasonId: z.string(),
  direction: z.string(),
  metric: z.string(),
  sourceValue: z.number(),
  predicted: z.number(),
  pi80Low: z.number(),
  pi80High: z.number(),
  pi95Low: z.number(),
  pi95High: z.number(),
  actualValue: z.number().nullable(),
  baselineLeagueMean: z.number(),
  baselineZPreservation: z.number(),
  baselineFolkRule: z.number(),
  modelVersion: z.string(),
});

/**
 * Diacritic-insensitive search over the normalised name column.
 *
 * The previous implementation ran `LIKE '%q%'` against the display name, which
 * cannot use an index and — more importantly — could not find "Jokić" for
 * anyone typing "Jokic". Roughly a third of EuroLeague players have diacritics,
 * so that was not an edge case.
 */
playersRoute.openapi(
  createRoute({
    method: "get",
    path: "/players/search",
    tags: ["Players"],
    summary: "Diacritic-insensitive search over every resolved person.",
    description:
      "Matches against a column Python already de-accented, so `jokic` finds `Jokić`. " +
      "Cross-league players rank first: they are the ones this project is about.",
    request: {
      // Permissive here on purpose: `SearchQuery` runs in the handler so a bad
      // parameter comes back as problem+json rather than in the validator's own
      // shape.
      query: z.object({
        q: z
          .string()
          .optional()
          .openapi({
            param: { name: "q", in: "query" },
            description: "1-80 characters. Accents optional.",
            example: "jokic",
          }),
        limit: z
          .string()
          .optional()
          .openapi({
            param: { name: "limit", in: "query" },
            description: "1-50, default 20. Outside that range the request is rejected.",
            example: "20",
          }),
      }),
    },
    responses: {
      200: {
        description: "Matching people, cross-league first, then alphabetical.",
        content: {
          "application/json": {
            schema: EnvelopeSchema(z.array(SearchResultSchema), "PlayerSearch"),
          },
        },
      },
      422: {
        description: "INVALID_QUERY: `q` is empty or over 80 characters, or `limit` is not 1-50.",
        content: { [PROBLEM_CONTENT_TYPE]: { schema: ProblemSchema } },
      },
    },
  }),
  async (c) => {
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
      }) as never;
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

    return c.json(envelope(c, rows, { snapshot: await snapshotId(db) })) as never;
  }
);

/** A person's full career across every league they appear in. */
playersRoute.openapi(
  createRoute({
    method: "get",
    path: "/players/{personId}",
    tags: ["Players"],
    summary: "A person's whole career across every league they appear in.",
    description:
      "Seasons are ordered by the integer sort key rather than the season id, which would " +
      "put NBA_2020 above EL_2021. Identity links carry the method and confidence that " +
      "produced them.",
    request: {
      params: z.object({
        personId: z.string().openapi({ param: { name: "personId", in: "path" } }),
      }),
    },
    responses: {
      200: {
        description: "The person, their seasons in chronological order, and their identity links.",
        content: { "application/json": { schema: EnvelopeSchema(CareerSchema, "PlayerCareer") } },
      },
      404: {
        description: "PERSON_NOT_FOUND: the id does not resolve. Ids are not guessable.",
        content: { [PROBLEM_CONTENT_TYPE]: { schema: ProblemSchema } },
      },
    },
  }),
  async (c) => {
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
      }) as never;
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
    ) as never;
  }
);

/** Translation predictions for a person, always with their intervals. */
playersRoute.openapi(
  createRoute({
    method: "get",
    path: "/players/{personId}/translation",
    tags: ["Players"],
    summary: "Cross-league translation predictions for one person.",
    description:
      "Every row carries its 80% and 95% intervals, and `meta.model` carries the measured " +
      "error of the model that produced them, so a value never appears without the " +
      "accuracy of the thing that made it.",
    request: {
      params: z.object({
        personId: z.string().openapi({ param: { name: "personId", in: "path" } }),
      }),
    },
    responses: {
      200: {
        description: "Predictions in source-season order, with the model's own error attached.",
        content: {
          "application/json": {
            schema: EnvelopeSchema(z.array(PlayerTranslationSchema), "PlayerTranslations"),
          },
        },
      },
      404: {
        description:
          "NO_TRANSITION_FOR_PLAYER: the person exists but never changed league, which is " +
          "the common case. /projections serves the counterfactual instead.",
        content: { [PROBLEM_CONTENT_TYPE]: { schema: ProblemSchema } },
      },
    },
  }),
  async (c) => {
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
      }) as never;
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
    ) as never;
  }
);

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
