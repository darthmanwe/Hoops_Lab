/**
 * Zod descriptions of the two response shapes, and the catalogue of every
 * error this API can return.
 *
 * `envelope.ts` and `problem.ts` build the responses; this file describes them.
 * Keeping them separate is deliberate — rewriting the builders to construct
 * from schemas would make the runtime depend on the documentation, and the
 * builders are load-bearing on a 10ms CPU budget. The risk of a mirror is that
 * it stops matching what it mirrors, so `schemas.test.ts` parses the real
 * output of `envelope()` and `problem()` against these and fails if they part.
 *
 * `z` comes from `@hono/zod-openapi` rather than `zod` directly: it is the same
 * zod with an `.openapi()` method attached, and importing the bare package here
 * would produce schemas that silently carry no metadata into the document.
 */

import { z } from "@hono/zod-openapi";

export const MetaSchema = z
  .object({
    request_id: z.string().openapi({ example: "a3236f384d2ddfdb" }),
    snapshot: z
      .string()
      .nullable()
      .openapi({
        description:
          "The data snapshot every number in this response came from. Also " +
          "prefixes the cache key, so a stale response identifies itself.",
        example: "ee6b530f0aa0",
      }),
    generated_at: z.iso.datetime(),
    resolved: z
      .object({
        season_id: z.string().optional(),
        requested_season_id: z.string().nullable().optional(),
        resolution: z.enum(["exact", "latest_available"]).optional(),
      })
      .optional()
      .openapi({
        description:
          "Present when a season was resolved rather than matched. `exact` or " +
          "`latest_available` — never a silent substitution.",
      }),
    model: z
      .object({
        name: z.string(),
        version: z.string(),
        primary_metric: z.string().optional(),
        primary_value: z.number().optional(),
        primary_ci: z.tuple([z.number(), z.number()]).nullable().optional(),
        card: z.string().optional(),
      })
      .optional()
      .openapi({
        description:
          "The model that produced these numbers, with its headline error, so " +
          "a value never appears without the accuracy of the thing that made it.",
      }),
    page: z
      .object({
        total: z.number().int(),
        limit: z.number().int(),
        offset: z.number().int(),
        returned: z.number().int(),
      })
      .optional()
      .openapi({
        description:
          "How many rows matched against how many were returned. Without this a " +
          "truncated ranking and a complete one are indistinguishable.",
      }),
    warnings: z.array(z.string()),
  })
  .openapi("Meta");

/**
 * The success shape. Generic because every route wraps a different payload and
 * the alternative — one union of every response body — would document a
 * contract no single endpoint honours.
 */
export function EnvelopeSchema<T extends z.ZodType>(data: T, name?: string) {
  const schema = z.object({ data, meta: MetaSchema });
  return name ? schema.openapi(name) : schema;
}

export const ProblemSchema = z
  .object({
    type: z.url().openapi({
      description: "Link to this code's entry in docs/errors.md.",
    }),
    title: z.string(),
    status: z.number().int(),
    code: z.string(),
    detail: z.string(),
  })
  // RFC 9457 permits members beyond the five above, and this API uses them:
  // `directions` on a filter miss, `blocked_on` on a 501, `instead` on a 410.
  // They are per-code rather than universal, so they are documented in
  // ERROR_CODES and left open here rather than forced into one shape.
  .catchall(z.unknown())
  .openapi("Problem");

/** What a caller can do about it, which is the part a status code omits. */
type ErrorCode = {
  status: number;
  title: string;
  /** When it happens, in one sentence. */
  when: string;
  /** What to do next. */
  action: string;
  /** Members beyond RFC 9457's five, if any. */
  extensions?: readonly string[];
};

/**
 * Every code this API can return.
 *
 * `problem()` builds each `type` as an anchor into `docs/errors.md`, so a code
 * missing from that file is a link to nowhere — and until this catalogue
 * existed, eleven of the fifteen were exactly that. The file is now generated
 * from here by `npm run gen`, which makes the two impossible to separate.
 */
export const ERROR_CODES = {
  ROUTE_NOT_FOUND: {
    status: 404,
    title: "No such endpoint",
    when: "The path is not registered.",
    action: "GET / lists every endpoint and its state.",
    extensions: ["listing"],
  },
  INTERNAL_ERROR: {
    status: 500,
    title: "Internal error",
    when: "An unhandled exception reached the error boundary.",
    action:
      "Quote the request_id. It is on the response and on the structured log line for the failure.",
    extensions: ["request_id"],
  },
  INVALID_QUERY: {
    status: 422,
    title: "Invalid query parameters",
    when: "A query parameter is missing, malformed, or outside its allowed range.",
    action: "`detail` names each offending parameter and why it was rejected.",
  },
  PERSON_NOT_FOUND: {
    status: 404,
    title: "No such person",
    when: "The person id does not resolve.",
    action: "Search by name at /players/search; ids are not guessable.",
    extensions: ["search"],
  },
  NO_TRANSITION_FOR_PLAYER: {
    status: 404,
    title: "No observed league transition",
    when: "The person exists but never changed league, so there is nothing to backtest against.",
    action:
      "This is the common case — most players never move. /projections serves the counterfactual instead.",
  },
  MODEL_VERSION_NOT_FOUND: {
    status: 404,
    title: "No such model version",
    when: "The requested model version is not in the registry.",
    action: "GET /models lists every version this deployment can serve.",
    extensions: ["registry"],
  },
  NO_PREDICTIONS_FOR_FILTER: {
    status: 404,
    title: "No predictions match that filter",
    when: "The direction and metric combination has no fitted predictions.",
    action: "`directions` lists the combinations that do.",
    extensions: ["directions"],
  },
  NO_PROJECTIONS: {
    status: 404,
    title: "No projections match that filter",
    when: "No player satisfies the direction, season and support filters together.",
    action: "Widen the season floor, or drop inSupportOnly.",
  },
  NO_ARCHETYPE_FOR_PLAYER: {
    status: 404,
    title: "No archetype assignment",
    when: "The player has no season clearing the minutes floor the archetype model requires.",
    action: "Low-minute seasons are excluded rather than clustered on noise.",
  },
  NO_COMPS_FOR_PLAYER: {
    status: 404,
    title: "No comparables",
    when: "The player has no archetype assignment, so there is no space to find neighbours in.",
    action: "See NO_ARCHETYPE_FOR_PLAYER.",
  },
  NO_SHOOTING_FOR_PLAYER: {
    status: 404,
    title: "No shooting estimate",
    when: "The player has no season above the three-point attempt floor.",
    action: "Below the floor the estimate would be almost entirely prior, so none is served.",
  },
  NO_SHOOTING_FOR_SEASON: {
    status: 404,
    title: "No shooting estimates for that season",
    when: "The season carries no player above the attempt floor, or is not in the snapshot.",
    action: "The hosted demo serves a slice; a local run carries every season.",
  },
  NO_REPORT_FOR_PLAYER: {
    status: 404,
    title: "No scouting report",
    when: "No report has been generated for this player and season.",
    action:
      "Reports are pre-generated for the evaluation set rather than written on demand, because generating one costs money and could not then be checked.",
  },
  UNDER_RECONSTRUCTION: {
    status: 501,
    title: "Endpoint under reconstruction",
    when: "The path previously returned fabricated values and has been withdrawn until real output backs it.",
    action:
      "`will_serve` states what it will return and `blocked_on` names the phase that unblocks it.",
    extensions: ["endpoint", "will_serve", "blocked_on", "previously", "roadmap"],
  },
  METRIC_WITHDRAWN: {
    status: 410,
    title: "Metric permanently withdrawn",
    when: "The underlying quantity cannot be computed from public data at all.",
    action:
      "`instead` names the nearest honest alternative. 410 rather than 501 is the signal: stop asking.",
    extensions: ["endpoint", "instead", "roadmap"],
  },
} as const satisfies Record<string, ErrorCode>;

export type ErrorCodeName = keyof typeof ERROR_CODES;
