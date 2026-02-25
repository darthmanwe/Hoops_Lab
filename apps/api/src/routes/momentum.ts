import { Hono } from "hono";
import type { Env } from "../db";
import { dbGet, resolveEntityId } from "../db";
import { cacheGetJson, cacheKey, cachePutJson } from "../cache";

export const momentumRoute = new Hono<{ Bindings: Env }>();

momentumRoute.get("/games/:id/momentum", async (c) => {
  const requestedGameId = c.req.param("id");
  const gameId = await resolveEntityId(c.env.DB, "games", "game_id", requestedGameId);
  if (!gameId) return c.json({ error: "momentum record not found" }, 404);
  const key = cacheKey(["game", gameId, "momentum"]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  const row = await dbGet<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT game_id, best_run_team_id, best_run_points, swing_index, clutch_possessions, clutch_net_rating_home, clutch_net_rating_away
      FROM game_momentum
      WHERE game_id = ?
    `,
    [gameId]
  );
  if (!row) return c.json({ error: "momentum record not found" }, 404);

  const payload = { ...row, resolved: { game_id: gameId } };
  await cachePutJson(c.env.CACHE, key, payload, 60 * 30);
  return c.json(payload);
});
