import { Hono } from "hono";
import type { Env } from "../env";
import { ENDPOINTS, GONE_ENDPOINTS, PENDING_ENDPOINTS } from "./registry";

export const metaRoute = new Hono<{ Bindings: Env }>();

/**
 * Generated from the endpoint registry rather than hand-maintained, so it
 * cannot drift from what the router actually serves.
 */
metaRoute.get("/", (c) =>
  c.json({
    service: "hoopslab-api",
    status: "live",
    summary:
      "Every served number comes from a fitted model or a measured column, and " +
      "carries the version that produced it. Paths still marked pending are " +
      "waiting on data this project does not yet have; paths marked gone " +
      "measured something no public data supports, and say so instead of " +
      "returning a plausible number.",
    counts: {
      live: ENDPOINTS.length - PENDING_ENDPOINTS.length - GONE_ENDPOINTS.length,
      pending: PENDING_ENDPOINTS.length,
      withdrawn: GONE_ENDPOINTS.length,
    },
    endpoints: ENDPOINTS.map((endpoint) => {
      switch (endpoint.state) {
        case "live":
          return { path: endpoint.path, state: endpoint.state, description: endpoint.description };
        case "pending":
          return {
            path: endpoint.path,
            state: endpoint.state,
            status: 501,
            blocked_on: endpoint.blockedOn,
            will_serve: endpoint.willServe,
          };
        case "gone":
          return {
            path: endpoint.path,
            state: endpoint.state,
            status: 410,
            reason: endpoint.reason,
          };
      }
    }),
    roadmap: "https://github.com/darthmanwe/Hoops_Lab#roadmap",
  })
);
