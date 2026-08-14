import { Hono } from "hono";
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

export const healthRoute = new Hono<{ Bindings: Env }>();

/**
 * The previous health check returned `{ok: true}` without touching any
 * dependency, so a green response proved only that the Worker had booted — it
 * stayed green through a total database outage. This one actually probes D1
 * and KV and reports 503 when either is unreachable.
 */
healthRoute.get("/health", async (c) => {
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
  );
});
