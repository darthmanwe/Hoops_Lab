import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../db";
import { dbAll } from "../db";
import { cacheGetJson, cacheKey, cachePutJson } from "../cache";

export const leaderboardsRoute = new Hono<{ Bindings: Env }>();

const SeasonQuery = z.object({
  season: z.string().trim().min(1).max(32),
});

leaderboardsRoute.get("/leaderboards/gravity", async (c) => {
  const parsed = SeasonQuery.safeParse({ season: c.req.query("season") });
  if (!parsed.success) {
    return c.json({ error: "season is required" }, 400);
  }
  const season = parsed.data.season;
  const key = cacheKey(["leaderboard", "gravity", season]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  const rows = await dbAll<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT p.player_id, p.name, g.gravity_overall, g.gravity_on_ball, g.gravity_off_ball
      FROM nba_gravity g
      JOIN players p ON p.player_id = g.player_id
      WHERE g.season_id = ?
      ORDER BY g.gravity_overall DESC
      LIMIT 50
    `,
    [season]
  );

  const payload = { season, results: rows };
  await cachePutJson(c.env.CACHE, key, payload, 60 * 30);
  return c.json(payload);
});

leaderboardsRoute.get("/leaderboards/clutch", async (c) => {
  const parsed = SeasonQuery.safeParse({ season: c.req.query("season") });
  if (!parsed.success) {
    return c.json({ error: "season is required" }, 400);
  }
  const season = parsed.data.season;
  const key = cacheKey(["leaderboard", "clutch", season]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  const rows = await dbAll<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT p.player_id, p.name, f.clutch_impact
      FROM player_season_features f
      JOIN players p ON p.player_id = f.player_id
      WHERE f.season_id = ?
      ORDER BY f.clutch_impact DESC
      LIMIT 50
    `,
    [season]
  );

  const payload = { season, results: rows };
  await cachePutJson(c.env.CACHE, key, payload, 60 * 30);
  return c.json(payload);
});
