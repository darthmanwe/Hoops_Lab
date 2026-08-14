import { Hono } from "hono";
import { cors } from "hono/cors";
import type { Env } from "./env";
import { problem } from "./http/problem";
import { healthRoute } from "./routes/health";
import { metaRoute } from "./routes/meta";
import { modelsRoute } from "./routes/models";
import { playersRoute } from "./routes/players";
import { rolesRoute } from "./routes/roles";
import { reconstructionRoute } from "./routes/reconstruction";
import { reportsRoute } from "./routes/reports";

const app = new Hono<{ Bindings: Env }>();

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

app.route("/", reconstructionRoute);

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
