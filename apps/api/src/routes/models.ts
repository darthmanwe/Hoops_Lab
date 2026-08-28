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

/**
 * The model registry and its own evaluation, served.
 *
 * Publishing a model's error alongside its predictions is the point. The
 * previous version stamped every stored metric with the literal string
 * "v0_bootstrap" and had nowhere to look it up.
 */
export const modelsRoute = new OpenAPIHono<{ Bindings: Env }>();

/** One registry row: what was fitted, from what, and how well it did. */
const ModelVersionSchema = z.object({
  modelVersion: z.string(),
  modelName: z.string(),
  trainedAt: z.string(),
  gitSha: z.string(),
  runId: z.string(),
  seed: z.number().int(),
  primaryMetric: z.string(),
  primaryValue: z.number(),
  primaryCiLow: z.number().nullable(),
  primaryCiHigh: z.number().nullable(),
  nTrain: z.number().int(),
  nEvaluated: z.number().int(),
  cardPath: z.string(),
});

const ModelEvaluationSchema = z.object({
  modelVersion: z.string(),
  metric: z.string(),
  fold: z.string().openapi({ description: '"overall" for the pooled row, otherwise the season.' }),
  nEvaluated: z.number().int(),
  mae: z.number(),
  maeCiLow: z.number().nullable(),
  maeCiHigh: z.number().nullable(),
  baselineName: z.string(),
  baselineMae: z.number(),
  shuffledMae: z.number().nullable().openapi({
    description: "The shuffled-target control, which a model with no signal matches.",
  }),
  beatsBestBaseline: z.boolean().openapi({
    description:
      "Whether the model beats the best baseline for this metric. Served rather than " +
      "logged, so a metric it loses on says so.",
  }),
  skillVsBest: z.number().openapi({
    description: "Fractional error reduction against the best baseline; negative is worse.",
  }),
});

const SelectionSummarySchema = z.object({
  modelVersion: z.string(),
  direction: z.string(),
  metric: z.string(),
  nMovers: z.number().int(),
  nLeague: z.number().int(),
  moverMeanZ: z.number(),
  leagueMeanZ: z.number(),
  gapSd: z.number(),
});

const EvaluationSchema = z.object({
  version: ModelVersionSchema,
  evaluations: z.array(ModelEvaluationSchema),
  selection: z.array(SelectionSummarySchema),
  interpretation: z.object({
    estimand: z.string(),
    selection_note: z.string(),
  }),
});

/** The leaderboard's row, which is a prediction joined to a name. */
const TranslationPredictionSchema = z.object({
  personId: z.string(),
  displayName: z.string().nullable(),
  sourceSeasonId: z.string(),
  targetSeasonId: z.string(),
  direction: z.string(),
  metric: z.string(),
  sourceValue: z.number(),
  predicted: z.number(),
  pi80Low: z.number(),
  pi80High: z.number(),
  actualValue: z.number().nullable().openapi({
    description: "What actually happened, where the move is already in the past.",
  }),
  modelVersion: z.string(),
});

modelsRoute.openapi(
  createRoute({
    method: "get",
    path: "/models",
    tags: ["Models"],
    summary: "Every model version this deployment can serve.",
    description:
      "Each row carries the run that produced it and its headline error, so a prediction " +
      "elsewhere in the API can always be looked up here.",
    responses: {
      200: {
        description: "The registry, most recently trained first.",
        content: {
          "application/json": {
            schema: EnvelopeSchema(z.array(ModelVersionSchema), "ModelRegistry"),
          },
        },
      },
    },
  }),
  async (c) => {
    const db = createDb(c.env.DB);
    const rows = await db
      .select()
      .from(schema.modelVersions)
      .orderBy(desc(schema.modelVersions.trainedAt));

    return c.json(envelope(c, rows, { snapshot: await snapshotId(db) })) as never;
  }
);

/**
 * Everything needed to judge the model honestly: its error, its interval, the
 * baselines it beat, and the shuffled-target control.
 */
modelsRoute.openapi(
  createRoute({
    method: "get",
    path: "/models/{modelVersion}/evaluation",
    tags: ["Models"],
    summary: "One model's held-out error against all four baselines.",
    description:
      "Includes the metric the model loses on and the selection gaps that condition every " +
      "number here, because an evaluation that reports only the wins is not an evaluation.",
    request: {
      params: z.object({
        modelVersion: z.string().openapi({
          param: { name: "modelVersion", in: "path" },
          example: "translation-v1",
        }),
      }),
    },
    responses: {
      200: {
        description: "The registry row, its per-fold evaluation, and the selection summaries.",
        content: {
          "application/json": { schema: EnvelopeSchema(EvaluationSchema, "ModelEvaluation") },
        },
      },
      404: {
        description: "MODEL_VERSION_NOT_FOUND: the version is not in the registry.",
        content: { [PROBLEM_CONTENT_TYPE]: { schema: ProblemSchema } },
      },
    },
  }),
  async (c) => {
    const modelVersion = c.req.param("modelVersion");
    const db = createDb(c.env.DB);

    const [version] = await db
      .select()
      .from(schema.modelVersions)
      .where(eq(schema.modelVersions.modelVersion, modelVersion))
      .limit(1);

    if (!version) {
      return problem(c, {
        status: 404,
        code: "MODEL_VERSION_NOT_FOUND",
        title: "No such model version",
        detail: `${modelVersion} is not in the registry.`,
        extensions: { registry: "/models" },
      }) as never;
    }

    const evaluations = await db
      .select()
      .from(schema.modelEvaluations)
      .where(eq(schema.modelEvaluations.modelVersion, modelVersion))
      .orderBy(asc(schema.modelEvaluations.metric), asc(schema.modelEvaluations.baselineName));

    const selection = await db
      .select()
      .from(schema.selectionSummaries)
      .where(eq(schema.selectionSummaries.modelVersion, modelVersion))
      .orderBy(asc(schema.selectionSummaries.metric), asc(schema.selectionSummaries.direction));

    return c.json(
      envelope(
        c,
        {
          version,
          evaluations,
          selection,
          // Stated in the payload, not just in prose, because it is the caveat
          // most likely to be dropped when someone quotes a number from here.
          interpretation: {
            estimand:
              "Conditional on a transition having occurred. This answers what history " +
              "says to expect given a player moved, not what a randomly chosen player would do.",
            selection_note:
              "Movers are not a random sample: the two headline directions are selected " +
              "in opposite directions, and the gap is reported per direction above.",
          },
        },
        { snapshot: await snapshotId(db) }
      )
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
  direction: zRuntime.string().default("EL->NBA"),
  metric: zRuntime.string().default("usg_pct"),
  limit: zRuntime.coerce.number().int().min(1).max(100).default(25),
});

/** Translation leaderboard, filtered to one direction and metric. */
modelsRoute.openapi(
  createRoute({
    method: "get",
    path: "/leaderboards/translation",
    tags: ["Models"],
    summary: "Players ranked by projected translated production.",
    description:
      "Every row carries its 80% interval and, where the move has already happened, what " +
      "the player actually did.",
    request: {
      // Permissive here on purpose: `LeaderboardQuery` runs in the handler so a
      // bad parameter comes back as problem+json rather than in the validator's
      // own shape.
      query: z.object({
        direction: z
          .string()
          .optional()
          .openapi({
            param: { name: "direction", in: "query" },
            description: "Defaults to EL->NBA.",
            example: "EL->NBA",
          }),
        metric: z
          .string()
          .optional()
          .openapi({
            param: { name: "metric", in: "query" },
            description: "Defaults to usg_pct.",
            example: "usg_pct",
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
        description: "The ranking for that direction and metric.",
        content: {
          "application/json": {
            schema: EnvelopeSchema(z.array(TranslationPredictionSchema), "TranslationLeaderboard"),
          },
        },
      },
      404: {
        description:
          "NO_PREDICTIONS_FOR_FILTER: no fitted predictions for that direction and metric.",
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
      direction: c.req.query("direction"),
      metric: c.req.query("metric"),
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

    const { direction, metric, limit } = parsed.data;

    const db = createDb(c.env.DB);
    const rows = await db
      .select({
        personId: schema.translationPredictions.personId,
        displayName: schema.persons.displayName,
        sourceSeasonId: schema.translationPredictions.sourceSeasonId,
        targetSeasonId: schema.translationPredictions.targetSeasonId,
        direction: schema.translationPredictions.direction,
        metric: schema.translationPredictions.metric,
        sourceValue: schema.translationPredictions.sourceValue,
        predicted: schema.translationPredictions.predicted,
        pi80Low: schema.translationPredictions.pi80Low,
        pi80High: schema.translationPredictions.pi80High,
        actualValue: schema.translationPredictions.actualValue,
        modelVersion: schema.translationPredictions.modelVersion,
      })
      .from(schema.translationPredictions)
      .innerJoin(
        schema.persons,
        eq(schema.translationPredictions.personId, schema.persons.personId)
      )
      .where(
        and(
          eq(schema.translationPredictions.direction, direction),
          eq(schema.translationPredictions.metric, metric)
        )
      )
      .orderBy(desc(schema.translationPredictions.predicted))
      .limit(limit);

    if (rows.length === 0) {
      return problem(c, {
        status: 404,
        code: "NO_PREDICTIONS_FOR_FILTER",
        title: "No predictions match",
        detail: `No predictions for direction=${direction}, metric=${metric}.`,
        extensions: { directions: ["EL->NBA", "NBA->EL", "GL->NBA", "NBA->GL"] },
      }) as never;
    }

    return c.json(envelope(c, rows, { snapshot: await snapshotId(db) })) as never;
  }
);
