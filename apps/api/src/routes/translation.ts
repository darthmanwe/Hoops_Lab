import { Hono } from "hono";
import type { Env } from "../db";
import { dbAll, dbGet, resolveEntityId, resolveSeasonForEntity } from "../db";
import { cacheGetJson, cacheKey, cachePutJson } from "../cache";

export const translationRoute = new Hono<{ Bindings: Env }>();

translationRoute.get("/players/:id/translation", async (c) => {
  const requestedPlayerId = c.req.param("id");
  const requestedSeason = c.req.query("season");
  if (!requestedSeason) return c.json({ error: "season is required" }, 400);
  const playerId = await resolveEntityId(c.env.DB, "players", "player_id", requestedPlayerId);
  if (!playerId) return c.json({ error: "translation record not found" }, 404);
  const season = await resolveSeasonForEntity(
    c.env.DB,
    "player_translation_metrics",
    "player_id",
    playerId,
    requestedSeason
  );
  if (!season) return c.json({ error: "translation record not found" }, 404);

  const key = cacheKey(["player", playerId, "translation", season]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  const row = await dbGet<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT m.season_id, m.player_id, p.name, p.league_id, m.standardized_usage, m.standardized_ts,
             m.standardized_creation, m.translation_score, m.nba_equivalent_rating
      FROM player_translation_metrics m
      JOIN players p ON p.player_id = m.player_id
      WHERE m.season_id = ? AND m.player_id = ?
    `,
    [season, playerId]
  );
  if (!row) return c.json({ error: "translation record not found" }, 404);

  const payload = { ...row, resolved: { player_id: playerId, season_id: season } };
  await cachePutJson(c.env.CACHE, key, payload, 60 * 30);
  return c.json(payload);
});

translationRoute.get("/leaderboards/translation", async (c) => {
  const season = c.req.query("season");
  if (!season) return c.json({ error: "season is required" }, 400);

  const key = cacheKey(["leaderboard", "translation", season]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  const rows = await dbAll<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT p.player_id, p.name, p.league_id, m.translation_score, m.nba_equivalent_rating
      FROM player_translation_metrics m
      JOIN players p ON p.player_id = m.player_id
      WHERE m.season_id = ?
      ORDER BY m.translation_score DESC
      LIMIT 50
    `,
    [season]
  );
  const payload = { season, results: rows };
  await cachePutJson(c.env.CACHE, key, payload, 60 * 30);
  return c.json(payload);
});
