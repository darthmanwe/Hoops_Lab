import { and, asc, desc, eq } from "drizzle-orm";
import { Hono } from "hono";
import { createDb, schema } from "../db/client";
import type { Env } from "../env";
import { envelope } from "../http/envelope";
import { problem } from "../http/problem";
import { snapshotId } from "../lib/snapshot";

/**
 * The model registry and its own evaluation, served.
 *
 * Publishing a model's error alongside its predictions is the point. The
 * previous version stamped every stored metric with the literal string
 * "v0_bootstrap" and had nowhere to look it up.
 */
export const modelsRoute = new Hono<{ Bindings: Env }>();

modelsRoute.get("/models", async (c) => {
  const db = createDb(c.env.DB);
  const rows = await db
    .select()
    .from(schema.modelVersions)
    .orderBy(desc(schema.modelVersions.trainedAt));

  return c.json(envelope(c, rows, { snapshot: await snapshotId(db) }));
});

/**
 * Everything needed to judge the model honestly: its error, its interval, the
 * baselines it beat, and the shuffled-target control.
 */
modelsRoute.get("/models/:modelVersion/evaluation", async (c) => {
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
    });
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
  );
});

/** Translation leaderboard, filtered to one direction and metric. */
modelsRoute.get("/leaderboards/translation", async (c) => {
  const direction = c.req.query("direction") ?? "EL->NBA";
  const metric = c.req.query("metric") ?? "usg_pct";
  const limit = Math.min(Number(c.req.query("limit") ?? 25) || 25, 100);

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
    .innerJoin(schema.persons, eq(schema.translationPredictions.personId, schema.persons.personId))
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
    });
  }

  return c.json(envelope(c, rows, { snapshot: await snapshotId(db) }));
});
