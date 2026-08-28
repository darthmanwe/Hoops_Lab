import { createRoute, OpenAPIHono, z } from "@hono/zod-openapi";
import { cors } from "hono/cors";
import type { Env } from "./env";
import { problem } from "./http/problem";
import { healthRoute } from "./routes/health";
import { metaRoute } from "./routes/meta";
import { modelsRoute } from "./routes/models";
import { playersRoute } from "./routes/players";
import { rolesRoute } from "./routes/roles";
import { reconstructionRoute } from "./routes/reconstruction";
import { projectionsRoute } from "./routes/projections";
import { reportsRoute } from "./routes/reports";

const app = new OpenAPIHono<{ Bindings: Env }>();

/**
 * A request id on every response, echoed in every error body, so a report of
 * "it broke" can be traced to a specific invocation in the logs.
 */
app.use("*", async (c, next) => {
  c.header("X-Request-Id", c.req.header("cf-ray") ?? crypto.randomUUID());
  await next();
});

/**
 * Read-only public API with no authentication, so a wildcard origin is
 * correct. The previous version also advertised `Authorization` in the allowed
 * headers, implying an auth scheme that did not exist — and browsers reject
 * credentialed requests against a wildcard origin anyway.
 */
app.use(
  "*",
  cors({
    origin: "*",
    allowMethods: ["GET", "OPTIONS"],
    allowHeaders: ["Content-Type"],
    maxAge: 86400,
  })
);

app.route("/", metaRoute);
app.route("/", healthRoute);

// Live routes are mounted before the reconstruction handlers so that a path
// which has become real wins over its withdrawn placeholder.
app.route("/", playersRoute);
app.route("/", modelsRoute);
app.route("/", rolesRoute);
app.route("/", reportsRoute);
app.route("/", projectionsRoute);

app.route("/", reconstructionRoute);

/**
 * The document, and a page to read it on.
 *
 * Generated from the same `createRoute` definitions the router is built from,
 * so it cannot describe an endpoint that does not exist or omit one that does.
 * The roadmap claimed this existed for months while both paths returned 404.
 *
 * Registered with `createRoute` rather than `app.doc31()`, which serves the
 * document but does not put itself in it. That would leave two paths the
 * registry declares and the document omits, and `openapi.test.ts` asserts
 * those two sets are equal — an exception list is how that kind of rule stops
 * meaning anything.
 */
/** Exported so `scripts/gen.ts` writes the same document this serves. */
export const OPENAPI_INFO = {
  openapi: "3.1.0" as const,
  info: {
    title: "HoopsLab API",
    version: "1.0.0",
    description:
      "Cross-league basketball translation. Every served number comes from a fitted " +
      "model or a measured column and carries the version that produced it. Paths " +
      "marked pending are waiting on data this project does not yet have; paths " +
      "marked withdrawn measured something no public data supports, and say so " +
      "instead of returning a plausible number.",
    license: { name: "MIT", url: "https://github.com/darthmanwe/Hoops_Lab/blob/main/LICENSE" },
  },
  servers: [{ url: "https://hoopslab-api-production.kutlumizrak.workers.dev" }],
};

app.openapi(
  createRoute({
    method: "get",
    path: "/openapi.json",
    tags: ["Meta"],
    summary: "This document.",
    description:
      "Generated from the route definitions rather than maintained beside them. " +
      "The committed copy at contracts/openapi.json is asserted equal to this on " +
      "every test run.",
    responses: {
      200: {
        description: "An OpenAPI 3.1 document.",
        content: { "application/json": { schema: z.object({}).loose() } },
      },
    },
  }),
  (c) => c.json(app.getOpenAPI31Document(OPENAPI_INFO)) as never
);

app.openapi(
  createRoute({
    method: "get",
    path: "/docs",
    tags: ["Meta"],
    summary: "The document above, rendered to read.",
    responses: {
      200: {
        description: "An HTML page.",
        content: { "text/html": { schema: z.string() } },
      },
    },
  }),
  (c) =>
    c.html(
      // Scalar from a CDN rather than a bundled viewer: the Worker has a 3 MB
      // compressed limit and documentation chrome is not what it should be
      // spent on. The document itself is served from this origin.
      `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>HoopsLab API</title>
  </head>
  <body>
    <script id="api-reference" data-url="/openapi.json"></script>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
  </body>
</html>`
    ) as never
);

app.notFound((c) =>
  problem(c, {
    status: 404,
    code: "ROUTE_NOT_FOUND",
    title: "No such endpoint",
    detail: `No route matches ${c.req.method} ${new URL(c.req.url).pathname}.`,
    extensions: { listing: "/" },
  })
);

/**
 * The previous version registered no error handler at all, so any D1 or KV
 * failure surfaced as an unhandled Worker exception: an opaque 500 with no
 * body, no request id, and nothing in the logs.
 */
app.onError((err, c) => {
  const requestId = c.res.headers.get("X-Request-Id") ?? "unknown";
  console.error(
    JSON.stringify({
      level: "error",
      request_id: requestId,
      path: new URL(c.req.url).pathname,
      message: err.message,
      stack: err.stack,
    })
  );

  return problem(c, {
    status: 500,
    code: "INTERNAL_ERROR",
    title: "Internal error",
    detail: "The request failed unexpectedly. Quote the request id when reporting this.",
    extensions: { request_id: requestId },
  });
});

export default app;
