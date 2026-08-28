import { createRoute, OpenAPIHono, z } from "@hono/zod-openapi";
import type { Env } from "../env";

type DependencyStatus = { ok: true; latency_ms: number } | { ok: false; error: string };

async function timed(probe: () => Promise<unknown>): Promise<DependencyStatus> {
  const started = Date.now();
  try {
    await probe();
    return { ok: true, latency_ms: Date.now() - started };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

export const healthRoute = new OpenAPIHono<{ Bindings: Env }>();

/** A discriminated union, because a latency and an error are not the same news. */
const DependencySchema = z.union([
  z.object({ ok: z.literal(true), latency_ms: z.number().int() }),
  z.object({ ok: z.literal(false), error: z.string() }),
]);

const HealthSchema = z
  .object({
    status: z.enum(["ok", "degraded"]),
    service: z.literal("hoopslab-api"),
    data_snapshot: z.string().nullable().openapi({
      description: "The snapshot this deployment serves. Every cache key is prefixed with it.",
    }),
    environment: z.string(),
    dependencies: z.object({ d1: DependencySchema, kv: DependencySchema }),
    checked_at: z.iso.datetime(),
  })
  .openapi("Health");

/**
 * The previous health check returned `{ok: true}` without touching any
 * dependency, so a green response proved only that the Worker had booted — it
 * stayed green through a total database outage. This one actually probes D1
 * and KV and reports 503 when either is unreachable.
 */
healthRoute.openapi(
  createRoute({
    method: "get",
    path: "/health",
    tags: ["Meta"],
    summary: "Liveness, and real D1 and KV reachability.",
    description:
      "Probes both dependencies rather than reporting on the Worker alone, and answers " +
      "503 when either is unreachable. Also reports the data snapshot, which is what " +
      "makes a stale cached response identifiable.",
    responses: {
      200: {
        description: "Both dependencies answered.",
        content: { "application/json": { schema: HealthSchema } },
      },
      503: {
        description: "D1 or KV is unreachable. The body names which and why.",
        content: { "application/json": { schema: HealthSchema } },
      },
    },
  }),
  async (c) => {
    const [db, cache] = await Promise.all([
      timed(() => c.env.DB.prepare("SELECT 1 AS ok").first()),
      timed(() => c.env.CACHE.get("__health_probe__")),
    ]);

    const healthy = db.ok && cache.ok;

    return c.json(
      {
        status: healthy ? "ok" : "degraded",
        service: "hoopslab-api",
        // Phase 0 serves no data at all, so there is no snapshot to report yet.
        data_snapshot: c.env.DATA_SNAPSHOT || null,
        environment: c.env.APP_ENV ?? "unknown",
        dependencies: { d1: db, kv: cache },
        checked_at: new Date().toISOString(),
      },
      healthy ? 200 : 503
    ) as never;
  }
);
