import { Hono } from "hono";
import type { Env } from "../db";
import { dbGet, resolveEntityId, resolveSeasonForEntity } from "../db";
import { cacheGetJson, cacheKey, cachePutJson } from "../cache";

export const fatigueRoute = new Hono<{ Bindings: Env }>();

fatigueRoute.get("/teams/:id/fatigue", async (c) => {
  const requestedTeamId = c.req.param("id");
  const requestedSeason = c.req.query("season");
  if (!requestedSeason) {
    return c.json({ error: "season is required" }, 400);
  }
  const teamId = await resolveEntityId(c.env.DB, "teams", "team_id", requestedTeamId);
  if (!teamId) return c.json({ error: "fatigue record not found" }, 404);
  const season = await resolveSeasonForEntity(
    c.env.DB,
    "team_fatigue_effect",
    "team_id",
    teamId,
    requestedSeason
  );
  if (!season) return c.json({ error: "fatigue record not found" }, 404);

  const key = cacheKey(["team", teamId, "fatigue", season]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  const row = await dbGet<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT season_id, team_id, fatigue_score, rest_disadvantage_games, travel_km, model_version, computed_at
      FROM team_fatigue_effect
      WHERE season_id = ? AND team_id = ?
    `,
    [season, teamId]
  );
  if (!row) return c.json({ error: "fatigue record not found" }, 404);

  const payload = { ...row, resolved: { team_id: teamId, season_id: season } };
  await cachePutJson(c.env.CACHE, key, payload, 60 * 30);
  return c.json(payload);
});

fatigueRoute.get("/games/:id/fatigue-flags", async (c) => {
  const requestedGameId = c.req.param("id");
  const gameId = await resolveEntityId(c.env.DB, "games", "game_id", requestedGameId);
  if (!gameId) return c.json({ error: "fatigue flags not found" }, 404);

  const key = cacheKey(["game", gameId, "fatigue-flags"]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  const row = await dbGet<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT game_id, home_fatigue_score, away_fatigue_score, rest_disadvantage_flag, travel_disadvantage_flag
      FROM game_fatigue_flags
      WHERE game_id = ?
    `,
    [gameId]
  );
  if (!row) return c.json({ error: "fatigue flags not found" }, 404);

  const payload = { ...row, resolved: { game_id: gameId } };
  await cachePutJson(c.env.CACHE, key, payload, 60 * 30);
  return c.json(payload);
});
