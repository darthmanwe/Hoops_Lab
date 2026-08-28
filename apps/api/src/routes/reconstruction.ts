import { createRoute, OpenAPIHono, z } from "@hono/zod-openapi";
import type { Env } from "../env";
import { PROBLEM_CONTENT_TYPE, underReconstruction, withdrawn } from "../http/problem";
import { ProblemSchema } from "../http/schemas";
import { GONE_ENDPOINTS, PENDING_ENDPOINTS } from "./registry";

/**
 * Mounts a handler for every non-live path in the registry.
 *
 * These are registered explicitly rather than caught by a wildcard so that an
 * unknown path still 404s. "Withdrawn" and "never existed" are different
 * answers and a client deserves to be told which one it hit.
 *
 * Half the API's surface is registered here, from two loops, which is why it
 * was converted to `createRoute` first: one definition documents fourteen
 * paths. It also means the generated document describes the withdrawn
 * endpoints as carefully as the working ones — a reader who looks up
 * `/leaderboards/gravity` gets the reason it cannot exist, rather than a 404
 * from a document that quietly omits it.
 */
export const reconstructionRoute = new OpenAPIHono<{ Bindings: Env }>();

/**
 * Path parameters, derived from the registry's own `{name}` placeholders.
 *
 * Hand-writing these would reintroduce exactly the drift the registry exists
 * to prevent, one path at a time.
 */
function paramsFor(path: string) {
  const names = [...path.matchAll(/\{(\w+)\}/g)].map((match) => match[1] as string);
  if (names.length === 0) return undefined;
  return z.object(
    Object.fromEntries(
      names.map((name) => [name, z.string().openapi({ param: { name, in: "path" } })])
    )
  );
}

/** `501` and `410` both answer with problem+json, so the shape is shared. */
function problemResponse(status: 501 | 410, description: string) {
  return {
    [status]: {
      description,
      content: { [PROBLEM_CONTENT_TYPE]: { schema: ProblemSchema } },
    },
  };
}

for (const endpoint of PENDING_ENDPOINTS) {
  const params = paramsFor(endpoint.path);
  reconstructionRoute.openapi(
    createRoute({
      method: "get",
      path: endpoint.path,
      tags: ["Under reconstruction"],
      summary: endpoint.willServe,
      description: `Previously: ${endpoint.previously}\n\nBlocked on: ${endpoint.blockedOn}`,
      ...(params ? { request: { params } } : {}),
      responses: problemResponse(
        501,
        "UNDER_RECONSTRUCTION: withdrawn until real, fitted output backs it. Carries what " +
          "it will serve and what blocks it."
      ),
    }),
    (c) =>
      underReconstruction(c, {
        endpoint: endpoint.path,
        willServe: endpoint.willServe,
        blockedOn: endpoint.blockedOn,
        previously: endpoint.previously,
      }) as never
  );
}

for (const endpoint of GONE_ENDPOINTS) {
  const params = paramsFor(endpoint.path);
  reconstructionRoute.openapi(
    createRoute({
      method: "get",
      path: endpoint.path,
      tags: ["Withdrawn"],
      summary:
        "Permanently withdrawn — the underlying quantity is not computable from public data.",
      description: `${endpoint.reason}\n\nInstead: ${endpoint.instead}`,
      ...(params ? { request: { params } } : {}),
      responses: problemResponse(
        410,
        "METRIC_WITHDRAWN: gone rather than 501, because the data to support this does not " +
          "exist publicly. It is not on the roadmap."
      ),
    }),
    (c) =>
      withdrawn(c, {
        endpoint: endpoint.path,
        reason: endpoint.reason,
        instead: endpoint.instead,
      }) as never
  );
}
