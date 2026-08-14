import { and, desc, eq } from "drizzle-orm";
import { Hono } from "hono";
import { createDb, schema } from "../db/client";
import type { Env } from "../env";
import { envelope } from "../http/envelope";
import { problem } from "../http/problem";
import { snapshotId } from "../lib/snapshot";

export const reportsRoute = new Hono<{ Bindings: Env }>();

/**
 * Grounded scouting reports.
 *
 * The only model-written prose this API serves, and therefore the only thing
 * it serves with an audit attached to every response. `audit` is not optional
 * metadata: a reader deciding whether to believe a sentence needs to know how
 * many of its numbers were traced back to the evidence at the same moment as
 * they read it, not from a footnote on another page.
 *
 * There is no generation path here. Reports are written offline by the Python
 * package, checked there, and loaded as rows — the Worker gets 10 ms of CPU per
 * request and cannot call a language model within it, and would not want to:
 * a per-request generation is a per-request bill and a per-request chance of a
 * different answer to the same question.
 */
reportsRoute.get("/players/:personId/report", async (c) => {
  const personId = c.req.param("personId");
  const named = c.req.query("named") === "true";
  const db = createDb(c.env.DB);

  const [row] = await db
    .select()
    .from(schema.playerReports)
    .where(and(eq(schema.playerReports.personId, personId), eq(schema.playerReports.named, named)))
    .orderBy(desc(schema.playerReports.targetSeasonId))
    .limit(1);

  if (!row) {
    return problem(c, {
      status: 404,
      code: "NO_REPORT_FOR_PLAYER",
      title: "No scouting report for this player",
      detail:
        `No report has been generated for ${personId}. Reports are written offline against ` +
        "a fixed evidence bundle and committed with their groundedness audit, so a player " +
        "without one has no report rather than a generated-on-demand one.",
      extensions: { how: "services/ml: hoopslab report <person_id> --refresh-cache" },
    });
  }

  return c.json(
    envelope(
      c,
      {
        personId: row.personId,
        targetSeasonId: row.targetSeasonId,
        direction: row.direction,
        named: row.named,
        headline: row.headline,
        report: JSON.parse(row.claims) as unknown,
        evidence: row.evidence,
        audit: {
          grounded: row.grounded,
          numbersTraced: row.numbersTraced,
          numbersTotal: row.numbersTotal,
          checks: JSON.parse(row.checks) as unknown,
        },
        reportModel: row.reportModel,
        generatedAt: row.generatedAt,
      },
      {
        snapshot: await snapshotId(db),
        warnings: row.named
          ? [
              "This report was written with the player's name in the evidence, so the model " +
                "could have drawn on what it already knew about them. Its groundedness is not " +
                "independently verifiable; the reported figures come from anonymized runs.",
            ]
          : [],
      }
    )
  );
});
