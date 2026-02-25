import { Hono } from "hono";

const app = new Hono();

app.get("/", (c) => {
  return c.json({
    ok: true,
    service: "hoopslab-api",
    message: "Scaffold ready"
  });
});

app.get("/health", (c) => {
  return c.json({ ok: true });
});

export default app;
