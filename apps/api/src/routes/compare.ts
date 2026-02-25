import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../db";
import { dbGet } from "../db";
import { cacheGetJson, cacheKey, cachePutJson } from "../cache";

export const compareRoute = new Hono<{ Bindings: Env }>();

const CompareQuery = z.object({
  playerA: z.string().trim().min(1),
  playerB: z.string().trim().min(1),
  season: z.string().trim().min(1),
});

compareRoute.get("/compare", async (c) => {
  const parsed = CompareQuery.safeParse({
    playerA: c.req.query("playerA"),
    playerB: c.req.query("playerB"),
    season: c.req.query("season"),
  });

  if (!parsed.success) {
    return c.json({ error: "playerA, playerB and season are required" }, 400);
  }

  const { playerA, playerB, season } = parsed.data;
  const key = cacheKey(["compare", playerA, playerB, season]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  const rowA = await dbGet<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT p.player_id, p.name, p.league_id, f.usage_proxy, f.ts_proxy, f.ast_rate_proxy, f.tov_rate_proxy, f.reb_share_proxy
      FROM players p
      LEFT JOIN player_season_features f ON f.player_id = p.player_id AND f.season_id = ?
      WHERE p.player_id = ?
    `,
    [season, playerA]
  );

  const rowB = await dbGet<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT p.player_id, p.name, p.league_id, f.usage_proxy, f.ts_proxy, f.ast_rate_proxy, f.tov_rate_proxy, f.reb_share_proxy
      FROM players p
      LEFT JOIN player_season_features f ON f.player_id = p.player_id AND f.season_id = ?
      WHERE p.player_id = ?
    `,
    [season, playerB]
  );

  if (!rowA || !rowB) {
    return c.json({ error: "One or both players not found" }, 404);
  }

  const payload = { season, playerA: rowA, playerB: rowB };
  await cachePutJson(c.env.CACHE, key, payload, 60 * 20);
  return c.json(payload);
});
