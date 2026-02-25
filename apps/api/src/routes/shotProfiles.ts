import { Hono } from "hono";
import type { Env } from "../db";
import { dbGet, resolveEntityId, resolveSeasonForEntity } from "../db";
import { cacheGetJson, cacheKey, cachePutJson } from "../cache";

export const shotProfilesRoute = new Hono<{ Bindings: Env }>();

shotProfilesRoute.get("/players/:id/shot-profile", async (c) => {
  const requestedPlayerId = c.req.param("id");
  const requestedSeason = c.req.query("season");
  if (!requestedSeason) return c.json({ error: "season is required" }, 400);
  const playerId = await resolveEntityId(c.env.DB, "players", "player_id", requestedPlayerId);
  if (!playerId) return c.json({ error: "player shot profile not found" }, 404);
  const season = await resolveSeasonForEntity(
    c.env.DB,
    "player_shot_profiles",
    "player_id",
    playerId,
    requestedSeason
  );
  if (!season) return c.json({ error: "player shot profile not found" }, 404);

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
  const payload = { ...row, resolved: { player_id: playerId, season_id: season } };
  await cachePutJson(c.env.CACHE, key, payload, 60 * 30);
  return c.json(payload);
});

shotProfilesRoute.get("/teams/:id/shot-profile", async (c) => {
  const requestedTeamId = c.req.param("id");
  const requestedSeason = c.req.query("season");
  if (!requestedSeason) return c.json({ error: "season is required" }, 400);
  const teamId = await resolveEntityId(c.env.DB, "teams", "team_id", requestedTeamId);
  if (!teamId) return c.json({ error: "team shot profile not found" }, 404);
  const season = await resolveSeasonForEntity(
    c.env.DB,
    "team_shot_profiles",
    "team_id",
    teamId,
    requestedSeason
  );
  if (!season) return c.json({ error: "team shot profile not found" }, 404);

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
  const payload = { ...row, resolved: { team_id: teamId, season_id: season } };
  await cachePutJson(c.env.CACHE, key, payload, 60 * 30);
  return c.json(payload);
});
