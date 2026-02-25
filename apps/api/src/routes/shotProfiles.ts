import { Hono } from "hono";
import type { Env } from "../db";
import { dbGet } from "../db";
import { cacheGetJson, cacheKey, cachePutJson } from "../cache";

export const shotProfilesRoute = new Hono<{ Bindings: Env }>();

shotProfilesRoute.get("/players/:id/shot-profile", async (c) => {
  const playerId = c.req.param("id");
  const season = c.req.query("season");
  if (!season) return c.json({ error: "season is required" }, 400);

  const key = cacheKey(["player", playerId, "shot-profile", season]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  const row = await dbGet<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT season_id, player_id, rim_rate, mid_rate, corner3_rate, abv3_rate, rim_fg_pct, mid_fg_pct, three_fg_pct
      FROM player_shot_profiles
      WHERE season_id = ? AND player_id = ?
    `,
    [season, playerId]
  );

  if (!row) return c.json({ error: "player shot profile not found" }, 404);
  await cachePutJson(c.env.CACHE, key, row, 60 * 30);
  return c.json(row);
});

shotProfilesRoute.get("/teams/:id/shot-profile", async (c) => {
  const teamId = c.req.param("id");
  const season = c.req.query("season");
  if (!season) return c.json({ error: "season is required" }, 400);

  const key = cacheKey(["team", teamId, "shot-profile", season]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  const row = await dbGet<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT season_id, team_id, rim_rate, mid_rate, corner3_rate, abv3_rate, rim_fg_pct, mid_fg_pct, three_fg_pct
      FROM team_shot_profiles
      WHERE season_id = ? AND team_id = ?
    `,
    [season, teamId]
  );

  if (!row) return c.json({ error: "team shot profile not found" }, 404);
  await cachePutJson(c.env.CACHE, key, row, 60 * 30);
  return c.json(row);
});
