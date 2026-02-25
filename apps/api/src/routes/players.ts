import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../db";
import { dbAll, dbGet } from "../db";
import { cacheGetJson, cacheKey, cachePutJson } from "../cache";
import { cosineSimilarity, parseVector } from "../services/similarity";

type PlayerSearchRow = {
  player_id: string;
  league_id: string;
  name: string;
  position: string | null;
  nationality: string | null;
};

export const playersRoute = new Hono<{ Bindings: Env }>();

const SearchSchema = z.object({
  q: z.string().trim().min(1).max(80)
});

playersRoute.get("/players/search", async (c) => {
  const parsed = SearchSchema.safeParse({ q: c.req.query("q") ?? "" });
  if (!parsed.success) {
    return c.json({ error: "Invalid search query" }, 400);
  }

  const q = parsed.data.q.toLowerCase();
  const key = cacheKey(["players", "search", q]);
  const cached = await cacheGetJson<PlayerSearchRow[]>(c.env.CACHE, key);
  if (cached) {
    return c.json({ results: cached, cached: true });
  }

  const rows = await dbAll<PlayerSearchRow>(
    c.env.DB,
    `
      SELECT player_id, league_id, name, position, nationality
      FROM players
      WHERE lower(name) LIKE ?
      ORDER BY name ASC
      LIMIT 25
    `,
    [`%${q}%`]
  );

  await cachePutJson(c.env.CACHE, key, rows, 60 * 30);
  return c.json({ results: rows, cached: false });
});

playersRoute.get("/players/:id", async (c) => {
  const playerId = c.req.param("id");
  const season = c.req.query("season");

  const key = cacheKey(["players", playerId, season ?? ""]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) {
    return c.json(cached);
  }

  const player = await dbGet<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT player_id, league_id, name, birthdate, height_cm, weight_kg, position, nationality
      FROM players
      WHERE player_id = ?
    `,
    [playerId]
  );

  if (!player) {
    return c.json({ error: "Player not found" }, 404);
  }

  const features = season
    ? await dbGet<Record<string, unknown>>(
        c.env.DB,
        `
          SELECT *
          FROM player_season_features
          WHERE player_id = ? AND season_id = ?
        `,
        [playerId, season]
      )
    : null;

  const payload = { player, features };
  await cachePutJson(c.env.CACHE, key, payload);
  return c.json(payload);
});

playersRoute.get("/players/:id/comps", async (c) => {
  const playerId = c.req.param("id");
  const season = c.req.query("season");
  const k = Number(c.req.query("k") ?? "10");
  if (!season) {
    return c.json({ error: "season is required" }, 400);
  }
  const limit = Number.isFinite(k) && k > 0 ? Math.min(k, 50) : 10;

  const key = cacheKey(["players", playerId, "comps", season, limit]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  const target = await dbGet<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT f.player_id, p.name, p.league_id, f.archetype_vector_json
      FROM player_season_features f
      JOIN players p ON p.player_id = f.player_id
      WHERE f.player_id = ? AND f.season_id = ?
    `,
    [playerId, season]
  );
  if (!target) {
    return c.json({ error: "Target player features not found" }, 404);
  }

  const allRows = await dbAll<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT f.player_id, p.name, p.league_id, f.archetype_vector_json
      FROM player_season_features f
      JOIN players p ON p.player_id = f.player_id
      WHERE f.season_id = ? AND f.player_id != ?
    `,
    [season, playerId]
  );

  const targetVec = parseVector(target.archetype_vector_json);
  const comps = allRows
    .map((row) => {
      const vec = parseVector(row.archetype_vector_json);
      return {
        player_id: row.player_id,
        name: row.name,
        league_id: row.league_id,
        score: Number(cosineSimilarity(targetVec, vec).toFixed(4)),
      };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  const payload = {
    season,
    target: {
      player_id: target.player_id,
      name: target.name,
      league_id: target.league_id,
    },
    comps,
  };
  await cachePutJson(c.env.CACHE, key, payload, 60 * 30);
  return c.json(payload);
});
