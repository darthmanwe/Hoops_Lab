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
    status: "rebuilding",
    summary:
      "Every analytics endpoint is withdrawn. The previous version served " +
      "hardcoded constants as model output; they have been removed rather " +
      "than left in place while real models are built.",
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
