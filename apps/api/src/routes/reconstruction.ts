import { Hono } from "hono";
import type { Env } from "../env";
import { underReconstruction, withdrawn } from "../http/problem";
import { GONE_ENDPOINTS, PENDING_ENDPOINTS, toHonoPath } from "./registry";

/**
 * Mounts a handler for every non-live path in the registry.
 *
 * These are registered explicitly rather than caught by a wildcard so that an
 * unknown path still 404s. "Withdrawn" and "never existed" are different
 * answers and a client deserves to be told which one it hit.
 */
export const reconstructionRoute = new Hono<{ Bindings: Env }>();

for (const endpoint of PENDING_ENDPOINTS) {
  reconstructionRoute.get(toHonoPath(endpoint.path), (c) =>
    underReconstruction(c, {
      endpoint: endpoint.path,
      willServe: endpoint.willServe,
      blockedOn: endpoint.blockedOn,
      previously: endpoint.previously,
    })
  );
}

for (const endpoint of GONE_ENDPOINTS) {
  reconstructionRoute.get(toHonoPath(endpoint.path), (c) =>
    withdrawn(c, {
      endpoint: endpoint.path,
      reason: endpoint.reason,
      instead: endpoint.instead,
    })
  );
}
