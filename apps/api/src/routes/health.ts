import { Hono } from "hono";
import type { Env } from "../db";

export const healthRoute = new Hono<{ Bindings: Env }>();

healthRoute.get("/health", (c) => {
  return c.json({
    ok: true,
    service: "hoopslab-api",
    ts: new Date().toISOString()
  });
});
