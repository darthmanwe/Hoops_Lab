import { createRoute, OpenAPIHono, z } from "@hono/zod-openapi";
import type { Env } from "../env";
import { ENDPOINTS, GONE_ENDPOINTS, PENDING_ENDPOINTS } from "./registry";

export const metaRoute = new OpenAPIHono<{ Bindings: Env }>();

/**
 * One row per endpoint. The three states carry different fields because they
 * answer different questions: a live path needs describing, a pending one needs
 * to say what unblocks it, and a withdrawn one needs to say why it cannot come
 * back. Flattening them into a common shape would drop the reasons.
 */
const ListingSchema = z
  .object({
    service: z.literal("hoopslab-api"),
    status: z.literal("live"),
    summary: z.string(),
    counts: z.object({
      live: z.number().int(),
      pending: z.number().int(),
      withdrawn: z.number().int(),
    }),
    endpoints: z.array(
      z.object({
        path: z.string(),
        state: z.enum(["live", "pending", "gone"]),
        description: z.string().optional(),
        status: z.number().int().optional(),
        blocked_on: z.string().optional(),
        will_serve: z.string().optional(),
        reason: z.string().optional(),
      })
    ),
    roadmap: z.url(),
  })
  .openapi("Listing");

/**
 * Generated from the endpoint registry rather than hand-maintained, so it
 * cannot drift from what the router actually serves.
 */
metaRoute.openapi(
  createRoute({
    method: "get",
    path: "/",
    tags: ["Meta"],
    summary: "Every endpoint and its state.",
    description:
      "Generated from the endpoint registry, which is also what mounts the withdrawn " +
      "handlers and what the OpenAPI document is checked against.",
    responses: {
      200: {
        description: "The full surface, including what is pending and what is gone.",
        content: { "application/json": { schema: ListingSchema } },
      },
    },
  }),
  (c) =>
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
            return {
              path: endpoint.path,
              state: endpoint.state,
              description: endpoint.description,
            };
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
