import type { Context } from "hono";

/**
 * RFC 9457 `application/problem+json`. Every non-2xx response in this API uses
 * this shape, so a client can branch on `code` without string-matching prose.
 */
export type Problem = {
  type: string;
  title: string;
  status: number;
  code: string;
  detail: string;
  [extension: string]: unknown;
};

const DOCS_BASE = "https://github.com/darthmanwe/Hoops_Lab";

export const PROBLEM_CONTENT_TYPE = "application/problem+json";

export function problem(
  c: Context,
  init: {
    status: number;
    code: string;
    title: string;
    detail: string;
    extensions?: Record<string, unknown>;
  }
): Response {
  const body: Problem = {
    type: `${DOCS_BASE}/blob/main/docs/errors.md#${init.code.toLowerCase().replace(/_/g, "-")}`,
    title: init.title,
    status: init.status,
    code: init.code,
    detail: init.detail,
    ...init.extensions,
  };

  return c.json(body, init.status as 400, {
    "Content-Type": PROBLEM_CONTENT_TYPE,
  });
}

/**
 * The Phase 0 response for every analytics endpoint.
 *
 * The previous version of this API answered these paths with hardcoded
 * constants that the UI labelled as model output. Rather than keep serving
 * them until real models exist, they now fail loudly and say exactly what they
 * used to do, what they will do, and what has to land first. A 501 that
 * explains itself is worth more than a 200 that lies.
 */
export function underReconstruction(
  c: Context,
  spec: {
    endpoint: string;
    willServe: string;
    blockedOn: string;
    previously: string;
  }
): Response {
  return problem(c, {
    status: 501,
    code: "UNDER_RECONSTRUCTION",
    title: "Endpoint under reconstruction",
    detail:
      "This endpoint previously returned fabricated values. It has been " +
      "withdrawn until it can be backed by a fitted model over real data.",
    extensions: {
      endpoint: spec.endpoint,
      will_serve: spec.willServe,
      blocked_on: spec.blockedOn,
      previously: spec.previously,
      roadmap: `${DOCS_BASE}#roadmap`,
    },
  });
}

/**
 * For metrics that are not coming back, as distinct from not built yet.
 *
 * `410 Gone` rather than `501` is the point: "gravity" cannot be computed from
 * public data at all, so promising it in a roadmap would be the same overclaim
 * in a slower form. A client that sees 410 should stop asking.
 */
export function withdrawn(
  c: Context,
  spec: { endpoint: string; reason: string; instead: string }
): Response {
  return problem(c, {
    status: 410,
    code: "METRIC_WITHDRAWN",
    title: "Metric permanently withdrawn",
    detail: spec.reason,
    extensions: {
      endpoint: spec.endpoint,
      instead: spec.instead,
      roadmap: `${DOCS_BASE}#what-this-is-not`,
    },
  });
}
